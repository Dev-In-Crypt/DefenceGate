"""WP-113: re-derive the stored rows the corrected source mappings change, from the raw store. Nothing is fetched.

Notices go through `ops.remap_source` at epoch 113: the current version's own stored payload is mapped again and a
versioned field that now differs is a new version (`changed_fields`, note `remapped`: a DefenceGate correction, never
counted as the buyer's amendment); an attribute that differs is updated in place; no version is updated or deleted.

    fr_boamp       deadline (national forms in the buyer's zone, overseas buyers in theirs), legal basis 2014/24, /25, /23
    nl_tenderned   deadline (the rectified one), the flagged main CPV first (attribute: the same codes are not a version)
    de_bkms        link: the notice's page on oeffentlichevergabe.de; BT-15 kept as the documents link
    es_placsp(_agg) procedure code 7 named (Derivado de acuerdo marco)

Calls (not versioned: a living row, `db.upsert_call`): who may apply (`who_apply.run`: AID's page rules, a national call text
naming SMEs, the verified "legal entities (public or private bodies)" of an EU call document) and an EU portal deadline that is
a date only, given the time its stored call document states for that day (`eu_portal.document_closing`); the nightly EU run
keeps both.

TED's legacy procedure codes and "CODE_OTHERS" are labels of the serving layer and need no data change.

Report by default: counts per source and field. `--yes` writes. Idempotent (remap markers; calls written only where they differ).

    python -m dgate.ops.wp113_rederive                       # report, every source
    python -m dgate.ops.wp113_rederive --source nl_tenderned --yes
    python -m dgate.ops.wp113_rederive --calls-only --yes
"""

from __future__ import annotations

import argparse
import logging
import sys

from .. import db, who_apply
from ..config import settings
from ..normalise import Call
from ..sources import eu_portal
from . import remap_source

EPOCH = 113
SOURCES = ("nl_tenderned", "fr_boamp", "de_bkms", "es_placsp", "es_placsp_agg")
# The rows a correction can reach, where a column says which: PLACSP's code 7 (8,186 of 45,774 rows), so the other 37,000
# stored payloads are not read on a 3.8 GB server.
PROCEDURE = {"es_placsp": "7", "es_placsp_agg": "7"}


def eu_deadlines(conn, *, write: bool) -> dict[str, int]:
    """Date-only EU portal deadlines whose stored call document states a time for that day."""
    rows = conn.execute(
        """SELECT c.id, c.native_id, p.code AS programme, c.deadline_at, c.deadline_precision
             FROM call c JOIN programme p ON p.id = c.programme_id JOIN source s ON s.id = c.source_id
            WHERE s.code = %s AND c.deadline_precision = 'date' AND c.deadline_at IS NOT NULL ORDER BY c.id""",
        (eu_portal.SOURCE_CODE,)).fetchall()
    counts = {"date_only": len(rows), "time_from_document": 0}
    for r in rows:
        call = Call(programme_code=r["programme"], native_id=r["native_id"], title="", deadline_at=r["deadline_at"],
                    deadline_precision=r["deadline_precision"])
        call = eu_portal.with_document_time(conn, call)
        if call.deadline_precision is None:
            counts["time_from_document"] += 1
            if write:
                conn.execute("UPDATE call SET deadline_at = %s, deadline_precision = NULL WHERE id = %s",
                             (call.deadline_at, r["id"]))
    return counts


def run(*, write: bool, sources: tuple[str, ...] = SOURCES, calls: bool = True, limit: int | None = None,
        workers: int = 1) -> list[str]:
    lines = []
    for source in sources:
        result = remap_source.run(source, write=write, epoch=EPOCH, limit=limit, workers=workers,
                                  procedure=PROCEDURE.get(source))
        lines.append(f"{source}: {result}")
    if calls:
        with db.connect(settings().dsn) as conn:
            lines.append(f"calls, who may apply: {who_apply.run(conn, write=write)}")
            lines.append(f"calls, EU deadline time: {eu_deadlines(conn, write=write)}")
            if write:
                conn.commit()
    return lines


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="wp113-rederive", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report only)")
    p.add_argument("--source", choices=SOURCES, help="one source only")
    p.add_argument("--calls-only", action="store_true", help="only the calls")
    p.add_argument("--no-calls", action="store_true", help="leave the calls")
    p.add_argument("--limit", type=int, help="at most this many notices per source")
    p.add_argument("--workers", type=int, default=1)
    a = p.parse_args(argv)
    sources = () if a.calls_only else ((a.source,) if a.source else SOURCES)
    for line in run(write=a.yes, sources=sources, calls=not a.no_calls, limit=a.limit, workers=a.workers):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
