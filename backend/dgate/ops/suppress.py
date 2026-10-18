"""Owner-run: remove a notice, a buyer's name or a funding call from the public site.

    python -m dgate.ops.suppress add --kind notice --source ted --native-id 123456-2026 \
        --reason personal_data --requested-at 2026-10-15 --decided-by "Owner" [--note ...] [--yes]
    python -m dgate.ops.suppress add --kind organisation --organisation 4711 ...
    python -m dgate.ops.suppress add --kind document --source EDF --native-id 12345 ...
    python -m dgate.ops.suppress list [--all]
    python -m dgate.ops.suppress lift ID --by "Owner" [--note ...] [--yes]

Dry run unless --yes. What changes: one row in `suppression`; a database trigger then
flags the serving rows, and a re-ingest cannot clear the flag. The archive rows are not
touched. Adding or lifting an entry also drops the stored digest issues (`digest_issue`, built
weeks ahead, with titles and buyer names) and the pre-computed list pages (`list_snapshot`, up to
eight hours old): both are derived and replaceable, and neither was reading the flag. The digest
is rebuilt at once; the list pages are served from the live query until the worker's next round
(every four hours; `python -m dgate.ops.warm_lists --yes` does it now). An organisation entry also
leaves the directory table `organisation_network` (the organisation list, its count, the sitemap and the
partner lists): a database trigger on `organisation.suppressed` deletes the merge family's rows in the same
transaction (migration 0080, verify2-abuse N3), and `lift` rebuilds the table, which puts the organisation
back. What may still be shown from a cache: the API keeps a list a minute, an issue five minutes, an
organisation list or partner tab five minutes and the Ukraine and gap analytics fifteen, the site's pages five
minutes, its CSV export ten, and the Atom feeds are sent with `max-age=3600`, so a reader or a
feed reader can hold a copy for an hour. Nothing needs a restart.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

from .. import db
from ..config import settings

KINDS = ("notice", "organisation", "document")


def _when(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def affected(conn, kind: str, source: str | None, native_id: str | None,
             organisation: int | None) -> int:
    """How many serving rows the entry flags now (0 for a notice not yet ingested)."""
    if kind == "notice":
        sql, args = ("SELECT count(*) AS n FROM opportunity o JOIN source s ON s.id = o.source_id "
                     "WHERE s.code = %s AND o.native_id = %s"), (source, native_id)
    elif kind == "organisation":
        sql, args = "SELECT count(*) AS n FROM opportunity WHERE buyer_org_id = %s", (organisation,)
    else:
        sql, args = ("SELECT count(*) AS n FROM call c JOIN programme p ON p.id = c.programme_id "
                     "WHERE p.code = %s AND c.native_id = %s"), (source, native_id)
    return conn.execute(sql, args).fetchone()["n"]


def drop_derived(conn) -> dict[str, int]:
    """Delete what was built from the serving rows before the entry changed: the stored digest
    issues and the pre-computed list pages. Both tables are derived (the digest is rebuilt from
    the archive, the snapshots by the worker), so nothing is lost, and the API falls back to the
    live query, which honours the flags. Runs in the caller's transaction, so the flag and the
    deletion commit together. (A worker build that read the rows just before the entry and
    writes just after it can bring a stale row back: the daily rebuild of the last two weeks and
    the four-hourly snapshots replace it; the CLI rebuilds the digest right after this.)"""
    return {table: conn.execute(f"DELETE FROM {table}").rowcount
            for table in ("digest_issue", "list_snapshot")}


def add(conn, *, kind: str, source: str | None, native_id: str | None,
        organisation: int | None, reason: str, requested_at: datetime, decided_by: str,
        note: str = "") -> int:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    row = conn.execute(
        """INSERT INTO suppression (kind, source_code, native_id, organisation_id, reason,
                                    requested_at, decided_by, note)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (kind, source, native_id, organisation, reason, requested_at, decided_by, note),
    ).fetchone()
    drop_derived(conn)
    return row["id"]


def lift(conn, entry_id: int, *, by: str, note: str = "") -> bool:
    got = conn.execute(
        "UPDATE suppression SET lifted_at = now(), lifted_by = %s, lifted_note = %s "
        "WHERE id = %s AND lifted_at IS NULL RETURNING id", (by, note, entry_id)).fetchone()
    if got:
        drop_derived(conn)
    return got is not None


LIST_HINT = ("list pages: closed and all-status tender lists use the live query (about 3 s each) until "
             "`python -m dgate.ops.warm_lists --yes` runs or the worker's next round (within 4 hours)")


def rebuild_directory(conn) -> str:
    """Rebuild `organisation_network` from the participations (a lifted entry brings the organisation back
    into the directory). A failure is reported, not raised: the entry is already committed."""
    from .. import networks

    try:
        done = networks.refresh_organisation_network(conn)
        return f"directory rebuilt: {done['organisations']} organisations"
    except Exception as exc:  # noqa: BLE001 - the lift stands; the monthly refresh does it otherwise
        conn.rollback()
        return f"directory NOT rebuilt ({str(exc)[:200]}): the next CORDIS or EDF load rebuilds it"


def rebuild_digest(conn) -> str:
    """Store the digest issues again from the rows as they now stand (the worker does it daily
    for the last two weeks and for missing weeks, eight a run). A failure is reported, not
    raised: the entry is already committed and the API computes an issue itself meanwhile."""
    from .. import weekly_digest

    try:
        return f"digest rebuilt: {weekly_digest.refresh(conn, max_builds=26)}"
    except Exception as exc:  # noqa: BLE001 - say what happened; the removal itself stands
        conn.rollback()
        return (f"digest NOT rebuilt ({str(exc)[:200]}): the worker rebuilds it at its next daily run; "
                "until then the API computes each issue on the request")


def listing(conn, *, include_lifted: bool) -> list[dict[str, Any]]:
    where = "" if include_lifted else "WHERE lifted_at IS NULL"
    return conn.execute(f"SELECT * FROM suppression {where} ORDER BY id").fetchall()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.suppress", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--kind", choices=KINDS, required=True)
    a.add_argument("--source", help="source code (notice) or programme code (document)")
    a.add_argument("--native-id")
    a.add_argument("--organisation", type=int)
    a.add_argument("--reason", required=True, help="code, lower case letters and underscores")
    a.add_argument("--requested-at", required=True, help="ISO date or time the request arrived")
    a.add_argument("--decided-by", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--yes", action="store_true", help="write (the default is a dry run)")
    li = sub.add_parser("list")
    li.add_argument("--all", action="store_true", help="include lifted entries")
    lf = sub.add_parser("lift")
    lf.add_argument("id", type=int)
    lf.add_argument("--by", required=True)
    lf.add_argument("--note", default="")
    lf.add_argument("--yes", action="store_true")
    args = p.parse_args(argv)

    with db.connect(settings().dsn) as conn:
        if args.cmd == "list":
            for r in listing(conn, include_lifted=args.all):
                state = "active" if r["lifted_at"] is None else f"lifted {r['lifted_at']:%Y-%m-%d}"
                subject = (f"org {r['organisation_id']}" if r["kind"] == "organisation"
                           else f"{r['source_code']}/{r['native_id']}")
                print(f"{r['id']:>5}  {r['kind']:<12} {subject:<40} {r['reason']:<20} "
                      f"requested {r['requested_at']:%Y-%m-%d} by {r['decided_by']}  [{state}]")
            return 0
        if args.cmd == "lift":
            if not args.yes:
                print(f"dry run: would lift entry {args.id} (add --yes)")
                return 0
            ok = lift(conn, args.id, by=args.by, note=args.note)
            conn.commit()
            print("lifted" if ok else "no active entry with that id")
            if ok:
                print(rebuild_digest(conn))
                print(rebuild_directory(conn))
                print(LIST_HINT)
            return 0 if ok else 1
        if args.kind == "organisation":
            if not args.organisation:
                p.error("--organisation is required for kind organisation")
        elif not (args.source and args.native_id):
            p.error("--source and --native-id are required for kind notice and document")
        n = affected(conn, args.kind, args.source, args.native_id, args.organisation)
        print(f"{'would flag' if not args.yes else 'flags'} {n} serving row(s)"
              + (" (none held yet: the entry applies when it is first ingested)" if not n else ""))
        if not args.yes:
            print("dry run: nothing written (add --yes)")
            return 0
        try:
            entry = add(conn, kind=args.kind, source=args.source, native_id=args.native_id,
                        organisation=args.organisation, reason=args.reason,
                        requested_at=_when(args.requested_at), decided_by=args.decided_by,
                        note=args.note)
        except Exception as exc:  # noqa: BLE001 - say what the database refused
            conn.rollback()
            print(f"refused: {exc}")
            return 1
        conn.commit()
        print(f"entry {entry} written; stored digest issues and list pages dropped"
              + ("; the organisation and its merge family left the directory table" if args.kind == "organisation" else ""))
        print(rebuild_digest(conn))
        print(LIST_HINT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
