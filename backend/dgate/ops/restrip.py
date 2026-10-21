"""Pass already-stored payloads through today's personal-data boundary again (WP-71).

`strip_personal_data` became recursive and source-aware on 21 October 2026: e-Zamowienia
`contractors[]` of natural persons, eForms person elements at any depth, the TED award
names outside the longest tenderer list. What was landed or archived before that still
carries what the boundary now removes, and so do the TED versions `ops.repair_ted` wrote on
12 and 14 October with the description of the version before (e-mail addresses in it).

Two targets, both report-only unless told otherwise:

  raw       the raw store. Each bundle of a source is read, every record is stripped
            again (`ted_awards` also through `awards.read_award`'s redaction), and with
            `--yes` a bundle in which a record changed is written back under its own key,
            with its lines in the same order, so every `raw_ingest` row still points at its
            record. `content_hash` keeps meaning the payload as first landed. Bundles of
            today and yesterday are left alone (a writer may still be appending), single
            objects are counted and not rewritten (compaction verifies them by hash), and
            `de_bkms` is refused (its XML is re-serialised by every strip, so nothing would
            ever read as unchanged). The Storage Box snapshots keep the old bytes until
            they roll off.

  archive   `opportunity_version`. The trigger refuses any change to a payload, by design,
            and this tool never disables it. It finds the versions whose payload the
            boundary would change and, with `--emit-sql FILE`, writes the break-glass
            transaction of docs/RUNBOOK.md ("Data subject requests", step 4) for the owner
            to run as the owner role with the API and worker stopped. Each UPDATE is
            guarded by the md5 of the payload it was planned on, so a row that changed
            since is left alone. The file holds the redacted payloads only.

    python -m dgate.ops.restrip raw --source pl_ezam                 # report only
    python -m dgate.ops.restrip raw --source pl_ezam --limit 20      # report, 20 bundles
    python -m dgate.ops.restrip raw --source pl_ezam --yes
    python -m dgate.ops.restrip archive                              # report only
    python -m dgate.ops.restrip archive --emit-sql /tmp/restrip.sql  # prepare, never run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from datetime import date, timedelta
from typing import Any, Callable, Iterator

from .. import db
from ..config import settings
from ..normalise import strip_personal_data
from ..rawstore import BUNDLE_EXTENSION, RawStore, build_store

log = logging.getLogger("restrip")

REFUSED_SOURCES = {"de_bkms"}


def _awards_strip(rec: dict[str, Any]) -> dict[str, Any]:
    from ..awards import read_award

    redacted = read_award(rec).redacted
    return strip_personal_data(redacted or rec)


def stripper(source: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    return _awards_strip if source == "ted_awards" else strip_personal_data


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def _bundle_day(key: str) -> date | None:
    parts = key.split("/")
    try:
        return date(int(parts[1]), int(parts[2]), int(parts[3]))
    except (IndexError, ValueError):
        return None


def restrip_raw(store: RawStore, source: str, *, write: bool, limit: int | None = None,
                today: date | None = None) -> Counter:
    if source in REFUSED_SOURCES:
        raise SystemExit(f"{source}: refused, see the module docstring")
    strip = stripper(source)
    fresh = (today or date.today()) - timedelta(days=1)
    out: Counter = Counter()
    for key, _ in store.listing(f"{source}/", suffix=".json"):
        out["single_objects"] += 1          # counted, never rewritten
        try:
            payload = store.get(key)
        except Exception:  # noqa: BLE001 - a bad object is counted, not fatal
            out["unreadable"] += 1
            continue
        if isinstance(payload, dict) and not _same(strip(payload), payload):
            out["single_objects_with_personal_data"] += 1
    done = 0
    for key, _ in store.listing(f"{source}/", suffix=BUNDLE_EXTENSION):
        day = _bundle_day(key)
        if day is None or day >= fresh:
            out["bundles_skipped_recent"] += 1
            continue
        if limit is not None and done >= limit:
            break
        done += 1
        out["bundles"] += 1
        try:
            lines = store._bundle_lines(key)
        except Exception:  # noqa: BLE001
            out["unreadable"] += 1
            continue
        new_lines: list[Any] = []
        changed = bad = 0
        for line in lines:
            out["records"] += 1
            try:
                rec = json.loads(line)
            except ValueError:
                out["records_unparsable"] += 1
                bad += 1
                continue
            clean = strip(rec) if isinstance(rec, dict) else rec
            if not _same(clean, rec):
                changed += 1
            new_lines.append(clean)
        if not changed:
            continue
        out["records_with_personal_data"] += changed
        out["bundles_to_rewrite"] += 1
        if bad:
            out["bundles_not_rewritten_unparsable"] += 1      # line positions would move
        elif write:
            written = store.put_records(key, new_lines)
            if written != len(lines):
                raise RuntimeError(f"{key}: wrote {written} lines, read {len(lines)}")
            store._bundle_cache = None
            out["bundles_rewritten"] += 1
    return out


# --------------------------------------------------------------------------- archive

def _versions(conn, step: int = 50_000) -> Iterator[dict[str, Any]]:
    """Versions whose payload holds an '@': the only thing the boundary changes in an archived
    payload (the payload is the normalised record, which has no nested contact fields)."""
    top = conn.execute("SELECT coalesce(max(id), 0) AS m FROM opportunity_version").fetchone()["m"]
    lo = 0
    while lo < top:
        rows = conn.execute(
            """SELECT v.id, v.payload, md5(v.payload::text) AS digest, s.code AS source
                 FROM opportunity_version v
                 JOIN opportunity o ON o.id = v.opportunity_id
                 JOIN source s ON s.id = o.source_id
                WHERE v.id > %s AND v.id <= %s AND strpos(v.payload::text, '@') > 0
                ORDER BY v.id""", (lo, lo + step)).fetchall()
        conn.rollback()
        yield from rows
        lo += step


def plan_archive(conn) -> tuple[Counter, list[tuple[int, str, dict[str, Any]]]]:
    counts: Counter = Counter()
    plan: list[tuple[int, str, dict[str, Any]]] = []
    for row in _versions(conn):
        counts["examined_with_at"] += 1
        clean = strip_personal_data(row["payload"])
        if _same(clean, row["payload"]):
            continue
        counts[f"to_redact_{row['source']}"] += 1
        counts["to_redact"] += 1
        plan.append((row["id"], row["digest"], clean))
    return counts, plan


def break_glass_sql(plan: list[tuple[int, str, dict[str, Any]]]) -> str:
    def lit(text: str) -> str:
        return "'" + text.replace("'", "''") + "'"

    body = [
        "-- WP-71 re-strip of archived versions. Break-glass step of docs/RUNBOOK.md, 'Data",
        "-- subject requests', step 4: owner role, API and worker stopped. Prepared by",
        "-- `python -m dgate.ops.restrip archive --emit-sql`; not run by any agent.",
        f"-- {len(plan)} versions; each UPDATE applies only if the payload is still the one planned on.",
        "BEGIN;",
        "ALTER TABLE opportunity_version DISABLE TRIGGER opportunity_version_append_only;",
    ]
    for vid, digest, clean in plan:
        body.append(
            f"UPDATE opportunity_version SET payload = {lit(json.dumps(clean, ensure_ascii=False))}::jsonb"
            f" WHERE id = {int(vid)} AND md5(payload::text) = {lit(digest)};")
    body += [
        "ALTER TABLE opportunity_version ENABLE TRIGGER opportunity_version_append_only;",
        "COMMIT;",
        "-- confirm: SELECT tgenabled FROM pg_trigger WHERE tgname = 'opportunity_version_append_only';  -- 'O'",
        "",
    ]
    return "\n".join(body)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="restrip", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="target", required=True)
    r = sub.add_parser("raw")
    r.add_argument("--source", required=True)
    r.add_argument("--limit", type=int, default=None, help="at most this many bundles")
    r.add_argument("--yes", action="store_true", help="rewrite the bundles (default: report only)")
    a = sub.add_parser("archive")
    a.add_argument("--emit-sql", default=None, help="write the break-glass SQL here (never executed)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.target == "raw":
        counts = restrip_raw(build_store(), args.source, write=args.yes, limit=args.limit)
        print(("" if args.yes else "[report only] ") + json.dumps(dict(counts), sort_keys=True))
        return 0
    with db.connect(settings().dsn) as conn:
        conn.execute("SET statement_timeout = '30s'")
        counts, plan = plan_archive(conn)
    # With `--emit-sql -` the SQL goes to stdout and the report to stderr, so it can be redirected from a
    # container that cannot write to the host.
    report = sys.stderr if args.emit_sql == "-" else sys.stdout
    print("[report only] " + json.dumps(dict(counts), sort_keys=True), file=report)
    print("version ids: " + ",".join(str(v) for v, _, _ in plan), file=report)
    if args.emit_sql:
        sql = break_glass_sql(plan)
        if args.emit_sql == "-":
            sys.stdout.write(sql)
        else:
            with open(args.emit_sql, "w", encoding="utf-8") as fh:
                fh.write(sql)
        print(f"break-glass SQL written to {args.emit_sql} ({hashlib.sha256(sql.encode()).hexdigest()[:12]}); "
              "the owner runs it, this tool does not", file=report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
