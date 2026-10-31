"""Operator-run: the contract periods notices state (WP-159, migration 0151).

    python -m dgate.ops.contract_periods                               coverage of the stored periods, per source
    python -m dgate.ops.contract_periods --backfill de_bkms            report what the raw store would fill
    python -m dgate.ops.contract_periods --backfill de_bkms --yes      fill it
    python -m dgate.ops.contract_periods --backfill fr_boamp --yes

New notices get their period from the mappers (`normalise.contract_period`). The stored ones are filled here from the
raw store, where the payload carries the whole notice: Germany (BKMS, eForms XML) and France (BOAMP, eForms bodies;
the older French schemas are not read). Each kept notice's latest landed payload is mapped again and its period written
on the serving row with no version (an attribute, like the lot count); a period already held is replaced only by one
the payload states, never by nothing. Idempotent: a second run finds nothing to do.

TED and PLACSP land no period: TED's comes with `python -m dgate.ops.repair_ted --refetch --epoch N` (external calls),
PLACSP's with an archive replay (external downloads). Both only with the owner's yes. Run this as a worker job
(`docker compose run --rm worker python -m dgate.ops.contract_periods ...`), not on the host.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from typing import Any

from .. import db
from ..config import settings
from ..normalise import from_boamp, from_de_bkms, strip_personal_data
from ..rawstore import RawStore, build_store

log = logging.getLogger("contract_periods")

COLUMNS = db.CONTRACT_PERIOD_COLUMNS
BACKFILL = {"de_bkms": from_de_bkms, "fr_boamp": from_boamp}


def coverage(conn) -> list[dict[str, Any]]:
    """Per source, of the kept notices (`is_defence`): how many state a period, an end, a duration, a renewal, and
    how many ends fall in the next twelve months by the list's rule (WP-160 `expiring.end_sql`: stated, or start +
    duration; estimates are counted apart)."""
    from ..expiring import end_sql

    return conn.execute(
        f"""SELECT s.code AS source, count(*) AS notices,
                  count(*) FILTER (WHERE o.contract_start IS NOT NULL OR o.contract_end IS NOT NULL
                                      OR o.contract_duration IS NOT NULL) AS with_period,
                  count(*) FILTER (WHERE o.contract_end IS NOT NULL) AS with_end,
                  count(*) FILTER (WHERE o.contract_duration IS NOT NULL) AS with_duration,
                  count(*) FILTER (WHERE o.contract_renewal) AS with_renewal,
                  count(*) FILTER (WHERE {end_sql(estimated=False)} BETWEEN current_date AND current_date + 365) AS ends_12m,
                  count(*) FILTER (WHERE o.contract_start IS NULL AND o.contract_end IS NULL
                                     AND {end_sql()} BETWEEN current_date AND current_date + 365) AS estimated_12m
             FROM opportunity o JOIN source s ON s.id = o.source_id
            WHERE o.is_defence
            GROUP BY s.code ORDER BY s.code""").fetchall()


def _rows(conn, src_id: int, limit: int | None) -> list[dict[str, Any]]:
    """Each notice of the source with its latest landed payload's key and the period it holds, in key order (a
    bundle is read once, not once per notice)."""
    return conn.execute(
        f"""SELECT o.id, o.native_id, r.storage_key, {', '.join('o.' + c for c in COLUMNS)}
              FROM opportunity o
              JOIN LATERAL (SELECT storage_key FROM raw_ingest r
                             WHERE r.source_id = o.source_id AND r.native_id = o.native_id
                             ORDER BY r.fetched_at DESC, r.id DESC LIMIT 1) r ON TRUE
             WHERE o.source_id = %s
             ORDER BY r.storage_key LIMIT %s""", (src_id, limit)).fetchall()


def moves(held: dict[str, Any], stated: dict[str, Any]) -> dict[str, Any]:
    """The period columns `stated` changes: a value it states that the row does not hold. Nothing stated, nothing
    moves."""
    return {c: v for c, v in stated.items() if v is not None and held.get(c) != v}


def backfill(conn, source: str, *, write: bool, store: RawStore | None = None, batch: int = 200,
             workers: int = 1, limit: int | None = None) -> Counter:
    from ..reprocess import _read_batch

    mapper = BACKFILL[source]
    store = store or build_store()
    rows = _rows(conn, db.source_id(conn, source), limit)
    conn.commit()                       # nothing is open across the slow store reads
    c: Counter = Counter(notices=len(rows))
    for start in range(0, len(rows), batch):
        chunk = rows[start:start + batch]
        payloads = _read_batch(store, [r["storage_key"] for r in chunk], workers, 4, 10.0)
        for row, payload in zip(chunk, payloads, strict=True):
            if isinstance(payload, Exception):
                c["unreadable"] += 1
                continue
            try:
                opp = mapper(strip_personal_data(payload))
            except Exception as exc:  # noqa: BLE001 - one payload must not stop the run
                log.warning("%s %s: %s", source, row["native_id"], exc)
                c["unreadable"] += 1
                continue
            stated = {col: getattr(opp, col) for col in COLUMNS}
            c["stated"] += any(v is not None for v in stated.values())
            change = moves(row, stated)
            if not change:
                c["unchanged"] += 1
                continue
            c["filled" if all(row[col] is None for col in COLUMNS) else "updated"] += 1
            if write:
                conn.execute(f"UPDATE opportunity SET {', '.join(f'{k} = %s' for k in change)} WHERE id = %s",
                             [*change.values(), row["id"]])
        if write:
            conn.commit()
        log.info("contract_periods %s: %s", source, dict(c))
    return c


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m dgate.ops.contract_periods", description=__doc__.split("\n")[0])
    p.add_argument("--backfill", choices=sorted(BACKFILL), help="fill the stored notices of a source from the raw store")
    p.add_argument("--yes", action="store_true", help="write (default: report only)")
    p.add_argument("--limit", type=int, help="at most this many notices")
    p.add_argument("--workers", type=int, default=1, help="payloads read at once")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        if a.backfill:
            got = backfill(conn, a.backfill, write=a.yes, limit=a.limit, workers=a.workers)
            print(("written: " if a.yes else "dry run (add --yes): ") + ", ".join(f"{k} {v}" for k, v in got.items()))
            if not a.yes:
                conn.rollback()
            if got["unreadable"]:
                return 1
        for r in coverage(conn):
            print(f"{r['source']:<16} notices {r['notices']:>7}  period {r['with_period']:>6}  end {r['with_end']:>6}  "
                  f"duration {r['with_duration']:>6}  renewal {r['with_renewal']:>6}  ends in 12 months {r['ends_12m']:>6}  "
                  f"(estimated {r['estimated_12m']:>6})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
