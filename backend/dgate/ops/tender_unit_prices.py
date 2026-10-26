"""Owner-run: notices whose stated total is a unit price get `value_kind = unit_price` (WP-138, r8-data problem 3).

    python -m dgate.ops.tender_unit_prices            # report: how many, per source and code family
    python -m dgate.ops.tender_unit_prices --yes      # write
    python -m dgate.ops.tender_unit_prices --undo [--yes]   # every unit_price back to total

The rule is the TED mapper's (`normalise.unit_price_total`: a total of at most EUR 500 on a notice whose main CPV is the
supply of personnel, 7962, or electricity, 0931), which every new read applies; this command applies it to the rows
already held. `value_kind` is an attribute: no version is written and the amount stays as the notice states it. The
API then serves the notice with no value, no twin borrows it, no value range matches it.
Expected on production (25 October 2026, read-only): 318 rows, de_bkms 131 (7962, EUR 27.10 to 100), TED 163 (7962,
27.10 to 300) and 24 (0931, 1.25 to 9.29); all defence and served. No sum reads these values (supplier sums read award
rows, and TED contract values under 1,000 are in none already: `suppliers.is_suspect`).
"""

from __future__ import annotations

import argparse
import sys

from .. import db
from ..config import settings
from ..normalise import (
    PLACEHOLDER_AMOUNT_MAX,
    UNIT_PRICE_CPV_PREFIXES,
    UNIT_PRICE_TOTAL_MAX,
    VALUE_UNIT_PRICE,
)

RULE = ("o.value_kind = 'total' AND o.value_amount > %(low)s AND o.value_amount <= %(high)s "
        "AND left(o.cpv_codes[1], 4) = ANY(%(prefixes)s)")
PARAMS = {"low": PLACEHOLDER_AMOUNT_MAX, "high": UNIT_PRICE_TOTAL_MAX, "prefixes": list(UNIT_PRICE_CPV_PREFIXES)}


def run(conn, *, write: bool, undo: bool = False) -> dict[str, int]:
    where = "o.value_kind = %(unit)s" if undo else RULE
    params = {**PARAMS, "unit": VALUE_UNIT_PRICE}
    rows = conn.execute(
        f"""SELECT s.code, left(o.cpv_codes[1], 4) AS family, count(*) AS n
              FROM opportunity o JOIN source s ON s.id = o.source_id
             WHERE {where} GROUP BY 1, 2 ORDER BY 1, 2""", params).fetchall()
    out = {f"{r['code']}_{r['family']}": r["n"] for r in rows}
    out["total"] = sum(r["n"] for r in rows)
    if write:
        new = "'total'" if undo else "%(unit)s"
        conn.execute(f"UPDATE opportunity o SET value_kind = {new} WHERE {where}", params)
        conn.commit()
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.tender_unit_prices", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (the default is a report)")
    p.add_argument("--undo", action="store_true", help="put every unit_price back to total")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        out = run(conn, write=a.yes, undo=a.undo)
    print(("written" if a.yes else "report only (add --yes to write)") + (" (undo)" if a.undo else ""))
    for k in sorted(out):
        print(f"  {k}: {out[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
