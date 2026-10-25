"""WP-133: two buyer rows that hold the same notice, as merge candidates. Nothing here merges anything.

The Polish procurement bulletin (e-Zamówienia, `pl_ezam`) and its mirror (`pl_atlas`) publish one notice under one
number ("2025/BZP 00224230"). When the two copies were filed under two organisation rows that state the same buyer name,
the rows are one body: "Zakład Karny we Wronkach" was row 8840 (the mirror's 5 notices) and row 195698 (the bulletin's
same 5), two buyers of 5 notices each in the buyer search on 25 October 2026. Each such pair is written to
`organisation_merge_candidate` (`db.add_merge_candidate`) with method `same_notice_number`, confidence 0.95 and the
numbers as evidence, `status = 'pending'`, for the review queue (`ops.accept_merge_candidates`). Rows of one buyer family
already are one buyer and are left out; a pair whose stated names differ is not written (a notice may be filed under a
parent body in one source and its unit in the other).

    python -m dgate.ops.shared_notice_candidates          # report: the pairs, nothing written
    python -m dgate.ops.shared_notice_candidates --yes    # write them (an existing pair of this method is left as it is)
"""

from __future__ import annotations

import argparse
import sys

from .. import db
from ..config import settings

DETECTED_BY = "ops.shared_notice_candidates"
METHOD = "same_notice_number"
CONFIDENCE = 0.95
SOURCES = ("pl_ezam", "pl_atlas")      # one notice number, two publications

PAIRS_SQL = """
    WITH x AS MATERIALIZED (
      SELECT LEAST(o.buyer_org_id, p.buyer_org_id) AS a, GREATEST(o.buyer_org_id, p.buyer_org_id) AS b,
             o.native_id, o.buyer_name_raw AS name, dg_fold(o.buyer_name_raw) = dg_fold(p.buyer_name_raw) AS same_name
        FROM opportunity o
        JOIN opportunity p ON p.native_id = o.native_id AND p.source_id = (SELECT id FROM source WHERE code = %(b)s)
        JOIN organisation ga ON ga.id = o.buyer_org_id AND ga.merged_into IS NULL AND NOT ga.suppressed
        JOIN organisation gb ON gb.id = p.buyer_org_id AND gb.merged_into IS NULL AND NOT gb.suppressed
       WHERE o.source_id = (SELECT id FROM source WHERE code = %(a)s) AND p.buyer_org_id <> o.buyer_org_id
         AND ga.country = gb.country AND dgate_buyer_head(o.buyer_org_id) <> dgate_buyer_head(p.buyer_org_id))
    SELECT a, b, min(name) AS name, count(*) AS shared, array_agg(native_id ORDER BY native_id) AS numbers
      FROM x GROUP BY a, b HAVING bool_and(same_name) ORDER BY a, b"""


def pairs(conn) -> list[dict]:
    """(a, b, the stated name, how many notices they share, the numbers) of each pair of live rows holding one notice."""
    return conn.execute(PAIRS_SQL, {"a": SOURCES[1], "b": SOURCES[0]}).fetchall()


def run(conn, *, apply: bool = False, out=print) -> dict[str, int]:
    found = pairs(conn)
    for p in found:
        out(f"  {p['a']} ~ {p['b']}  {p['shared']} shared  {p['name'][:60]!r}")
    out(f"pairs: {len(found)}")
    if not apply:
        out("report only: nothing written (add --yes)")
        return {"pairs": len(found), "written": 0}
    for p in found:
        shown = ", ".join(p["numbers"][:5]) + (f" and {p['shared'] - 5} more" if p["shared"] > 5 else "")
        db.add_merge_candidate(
            conn, p["a"], p["b"], method=METHOD, confidence=CONFIDENCE, detected_by=DETECTED_BY,
            evidence=f"the same {p['shared']} notice(s) ({shown}) in {SOURCES[0]} and {SOURCES[1]}, "
                     f"each under one of the two rows, buyer stated as {p['name']!r} in both")
    conn.commit()
    out(f"written (an existing pair of this method is left as it is): {len(found)}")
    return {"pairs": len(found), "written": len(found)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true", help="write the candidates")
    args = ap.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        run(conn, apply=args.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
