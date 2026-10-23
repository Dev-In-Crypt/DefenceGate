"""Owner-run: the other buyers of the joint procurements already held (WP-95, A1.4).

    python -m dgate.ops.co_buyers               # report: how many defence-scope TED notices name more than one buyer
    python -m dgate.ops.co_buyers --yes         # write `opportunity.other_buyers`
    python -m dgate.ops.co_buyers --limit 2000  # a rehearsal on the first notices

A TED notice of a joint procurement names every buyer (TED 711894-2026: Nodrosinajuma valsts agentura and Valsts
policija); the site showed the first only. The mapper keeps the others from now on (`normalise._ted_other_buyers`);
this reads them from the landed raw payload of each defence-scope TED notice that has none yet, asks TED nothing and
writes no version (an attribute, like the subtype). Idempotent: a notice once filled is not read again.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from .. import db
from ..config import settings
from ..normalise import _ted_other_buyers
from ..rawstore import build_store
from ..reprocess import _read_batch

BATCH = 500


def run(conn, *, write: bool, limit: int | None = None, store=None, examples: list[str] | None = None) -> Counter:
    c: Counter = Counter()
    store = store or build_store()
    rows = conn.execute(
        """SELECT DISTINCT ON (o.id) o.id, o.native_id, r.storage_key
             FROM opportunity o
             JOIN raw_ingest r ON r.source_id = o.source_id AND r.native_id = o.native_id
            WHERE o.source_id = (SELECT id FROM source WHERE code = 'ted') AND o.is_defence AND o.other_buyers IS NULL
            ORDER BY o.id, r.id DESC LIMIT %s""", (limit or 100_000_000,)).fetchall()
    conn.rollback()            # the store is read outside a transaction (the worker role's idle timeout)
    c["notices"] = len(rows)
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        payloads = _read_batch(store, [r["storage_key"] for r in batch], workers=16, attempts=5, pause=5.0)
        for r, payload in zip(batch, payloads, strict=True):
            if isinstance(payload, Exception) or not isinstance(payload, dict):
                c["unreadable"] += 1
                continue
            names = _ted_other_buyers(payload.get("buyer-name"))
            if not names:
                continue
            c["joint"] += 1
            if examples is not None and len(examples) < 10:
                examples.append(f"{r['native_id']}: + {'; '.join(names)}")
            if write:
                conn.execute("UPDATE opportunity SET other_buyers = %s WHERE id = %s AND other_buyers IS NULL",
                             (names, r["id"]))
        if write:
            conn.commit()
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.co_buyers", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (the default is a report)")
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args(argv)
    examples: list[str] = []
    with db.connect(settings().dsn) as conn:
        c = run(conn, write=a.yes, limit=a.limit, examples=examples)
    print("written" if a.yes else "report only (add --yes to write)", dict(c))
    for e in examples:
        print("  " + e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
