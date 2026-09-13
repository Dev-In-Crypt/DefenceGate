"""Repair histories that recorded re-read content as change.

Until 13 September 2026 the archive compared incoming content only with the
latest version, and PLACSP was read newest first. Every run re-read old states
and archived them as changes, so affected notices alternate between the same
payloads, and some are left showing an earlier state as current.

Versions cannot be deleted -- the archive is append-only by trigger, rightly --
so this repair only adds:

  - a note on every version whose content was already archived (`reread`) or
    that was published before the version it followed (`out_of_order`)
  - where the current state is wrong, one correcting version restoring the
    latest state by the source's own date, noted `correction`

Idempotent: notes are unique per version and kind, and a notice whose current
state is already right gets no correction.

    python -m dgate.ops.repair_reversions            # repair
    python -m dgate.ops.repair_reversions --dry-run  # report only
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field

from .. import db
from ..config import settings

log = logging.getLogger("repair_reversions")


@dataclass
class Repair:
    opportunity_id: int
    native_id: str
    notes: list[tuple[int, str, str]] = field(default_factory=list)  # (version, kind, note)
    correct_to: int | None = None      # version whose content should be current


def _published(row: dict) -> str:
    return str(row["payload"].get("published_at") or "")[:10]


def plan_repair(opp_id: int, native_id: str, versions: list[dict]) -> Repair:
    """Decide what an opportunity's history needs, without touching it.

    `versions` are rows ordered by version with keys version, raw_hash, payload.
    The true current state is the content with the latest source date; between
    contents published the same day, the one first archived last.
    """
    repair = Repair(opp_id, native_id)
    seen: dict[str, int] = {}
    latest_date = ""
    for row in versions:
        v, digest, published = row["version"], row["raw_hash"], _published(row)
        if row.get("is_correction"):
            # A correction repeats the content it restores on purpose. Marking
            # it `reread` would tell clients to hide the one version that is
            # right -- which a second run of the first version of this repair
            # did, to all 53 corrections.
            seen.setdefault(digest, v)
            latest_date = max(latest_date, published)
            continue
        if digest in seen:
            repair.notes.append((v, "reread",
                                 f"same content as version {seen[digest]}, read again later"))
        elif published and latest_date and published < latest_date:
            repair.notes.append((v, "out_of_order",
                                 f"published {published}, before the {latest_date} "
                                 "version it followed"))
        seen.setdefault(digest, v)
        latest_date = max(latest_date, published)

    first_seen: dict[str, dict] = {}
    for row in versions:
        first_seen.setdefault(row["raw_hash"], row)
    best = max(first_seen.values(), key=lambda r: (_published(r), r["version"]))
    if versions[-1]["raw_hash"] != best["raw_hash"]:
        repair.correct_to = best["version"]
    return repair


def affected(conn) -> list[tuple[int, str, list[dict]]]:
    rows = conn.execute(
        "SELECT id, native_id FROM opportunity WHERE current_version > 1 ORDER BY id"
    ).fetchall()
    out = []
    for r in rows:
        versions = conn.execute(
            """SELECT v.id, v.version, v.raw_hash, v.payload,
                      EXISTS (SELECT 1 FROM opportunity_version_note n
                               WHERE n.opportunity_version_id = v.id
                                 AND n.kind = 'correction') AS is_correction
                 FROM opportunity_version v
                WHERE v.opportunity_id = %s ORDER BY v.version""",
            (r["id"],),
        ).fetchall()
        out.append((r["id"], r["native_id"], versions))
    return out


def apply(conn, repair: Repair, versions: list[dict]) -> int | None:
    by_version = {row["version"]: row for row in versions}
    for v, kind, note in repair.notes:
        conn.execute(
            """INSERT INTO opportunity_version_note (opportunity_version_id, kind, note)
               VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
            (by_version[v]["id"], kind, note),
        )
    if repair.correct_to is None:
        return None

    target = by_version[repair.correct_to]
    latest = versions[-1]
    opp = db.opportunity_from_payload(target["payload"])
    changed = [f for f in db.VERSIONED_FIELDS
               if latest["payload"].get(f) != target["payload"].get(f)]
    new_version = db.append_version(conn, repair.opportunity_id, opp, target["raw_hash"],
                                    changed, after=latest["version"])
    new_id = conn.execute(
        "SELECT id FROM opportunity_version WHERE opportunity_id = %s AND version = %s",
        (repair.opportunity_id, new_version),
    ).fetchone()["id"]
    conn.execute(
        """INSERT INTO opportunity_version_note (opportunity_version_id, kind, note)
           VALUES (%s, 'correction', %s) ON CONFLICT DO NOTHING""",
        (new_id, f"restores version {repair.correct_to}, the latest state by source date; "
                 f"version {latest['version']} had re-read older content"),
    )
    return new_version


def run(dry_run: bool = False, dsn: str | None = None) -> dict[str, int]:
    totals = {"examined": 0, "notes": 0, "corrected": 0}
    with db.connect(dsn or settings().dsn) as conn:
        for opp_id, native_id, versions in affected(conn):
            totals["examined"] += 1
            repair = plan_repair(opp_id, native_id, versions)
            totals["notes"] += len(repair.notes)
            if repair.correct_to is not None:
                totals["corrected"] += 1
                log.info("%s: current state wrong, restoring version %s",
                         native_id, repair.correct_to)
            if not dry_run:
                apply(conn, repair, versions)
        if dry_run:
            conn.rollback()
    return totals


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="repair-reversions")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    print(run(dry_run=a.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
