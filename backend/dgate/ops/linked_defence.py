"""Bring `sig_linked_defence` of the stored notices in line with the twin rule of WP-72.

A notice is linked defence when its twin (the TED notice a national row states, by `ted_ref` or
the eForms procedure identifier; for a TED row, a national notice that states it) is in the
default list by its OWN signals (`classify.own_relevance_sql`). Until WP-72 any `is_defence`
twin counted, so a TED notice that is only dual-use lifted its national copy into `supply`: 264
rows on 21 October 2026, most of them GDDKiA motorway works (QA audit, finding 3).

What changes for a row whose twin no longer counts: `sig_linked_defence` is set to false and
`is_defence` is derived again from the other stored signals (legal basis, military CPV, listed
buyer; `classify.DefenceSignals.is_defence`). A row with none of them leaves the lists; it keeps its
row, its history and its other signals. No version is written: the classification is our
conclusion, not what the source said (`db.refresh_classification`). The flag is never set by this
tool, only cleared, so a second run finds nothing.

    python -m dgate.ops.linked_defence          # dry run: counts per source and a sample
    python -m dgate.ops.linked_defence --yes    # write; then `python -m dgate.ops.warm_lists --yes`
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from typing import Any

from .. import db
from ..classify import CORE_SQL, SUPPLY_SQL, own_relevance_sql
from ..config import settings

log = logging.getLogger("linked_defence")



def _twin_sql(own: bool) -> str:
    """Whether row `o` has a twin we hold (that is relevant on its own, with `own`), as
    pipeline._twin_is_defence decides it for one notice."""
    n, t = (f" AND {own_relevance_sql('n')}", f" AND {own_relevance_sql('t')}") if own else ("", "")
    return f"""(CASE WHEN o.source_id = %(ted)s THEN EXISTS (
        SELECT 1 FROM opportunity n WHERE n.ted_ref = o.native_id{n})
    ELSE EXISTS (
        SELECT 1 FROM opportunity t WHERE t.source_id = %(ted)s AND t.native_id = o.ted_ref{t})
      OR (btrim(coalesce(o.procedure_identifier, ''), '{{}} ') <> '' AND EXISTS (
        SELECT 1 FROM opportunity t WHERE t.source_id = %(ted)s
           AND t.procedure_identifier = ANY(ARRAY[btrim(o.procedure_identifier, '{{}} '),
                                                  lower(btrim(o.procedure_identifier, '{{}} ')),
                                                  upper(btrim(o.procedure_identifier, '{{}} '))]){t}))
    END)"""


TWIN_COUNTS_SQL = _twin_sql(own=True)


def run(conn, *, apply: bool = False, batch: int = 2000, sample: int = 15,
        out=print) -> dict[str, Any]:
    ted = db.source_id(conn, "ted")
    counts: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    leaves: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    last = 0
    while True:
        rows = conn.execute(
            f"""SELECT o.id, s.code, o.native_id, o.ted_ref, o.buyer_name_raw, o.title_original,
                       ({CORE_SQL}) AS core, ({SUPPLY_SQL}) AS supply,
                       (o.sig_legal_basis OR o.sig_cpv_military OR o.sig_buyer) AS still_defence,
                       {own_relevance_sql('o')} AS relevant_after,
                       {TWIN_COUNTS_SQL} AS twin_counts, {_twin_sql(own=False)} AS twin_held
                  FROM opportunity o JOIN source s ON s.id = o.source_id
                 WHERE o.sig_linked_defence AND o.id > %(last)s
                 ORDER BY o.id LIMIT %(batch)s""",
            {"ted": ted, "last": last, "batch": batch}).fetchall()
        if not rows:
            break
        last = rows[-1]["id"]
        drop = [r for r in rows if not r["twin_counts"]]
        counts["linked"] += len(rows)
        counts["kept"] += len(rows) - len(drop)
        for r in drop:
            by_source[r["code"]] += 1
            counts["supply_before"] += bool(r["supply"])
            leaves["stays_defence" if r["still_defence"] else "leaves_defence"] += 1
            leaves["still_relevant" if r["relevant_after"] else "leaves_relevant"] += 1
            leaves["twin_held_not_relevant" if r["twin_held"] else "twin_not_held"] += 1
            if len(examples) < sample:
                examples.append(r)
        counts["cleared"] += len(drop)
        if apply and drop:
            conn.execute(
                """UPDATE opportunity
                      SET sig_linked_defence = FALSE,
                          is_defence = (sig_legal_basis OR sig_cpv_military OR sig_buyer)
                    WHERE id = ANY(%s) AND sig_linked_defence""", ([r["id"] for r in drop],))
            conn.commit()
    result = {**counts, "by_source": dict(by_source), **leaves}
    out(f"linked rows {counts['linked']}: twin still counts {counts['kept']}, "
        f"to clear {counts['cleared']} ({dict(by_source)}); of those in supply before: "
        f"{counts['supply_before']}; {dict(leaves)}")
    for r in examples:
        out(f"  {r['code']:12s} {r['native_id']:28s} twin {r['ted_ref'] or '-':16s} "
            f"{(r['buyer_name_raw'] or '')[:40]!r} {(r['title_original'] or '')[:60]!r}")
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
