"""Re-attach the notices filed under a generic buyer row to the unit their own text names (WP-170, backlog item of WP-143).

Some Polish notices state only a unit's bare name, with no town: "Komenda Powiatowa Państwowej Straży Pożarnej". Resolution files
them under the row of that name, so rows 13952 and 184800 hold the same 9 notices of several district fire services (titles name
Głubczyce and Świebodzin), and 14912 and 174324 the same 11-12 of city fire services (one names Nowy Sącz; 174324 also holds
Opole's NIP). A buyer page of such a row lists other towns' notices.

For each given row: its notices whose stated buyer name folds to the row's own name (a notice that states a town is left alone),
and the live rows of the same country named `<that name> w <place>`. A notice whose title, English title or summary holds
"w <place>" of exactly one of them is moved to it (`opportunity.buyer_org_id`; the versions keep what was archived). None or more
than one: it stays where it is. Each move is written down in `resolution_review` (the two rows, relation `notice_unit`, method
`place_in_notice`, confidence 0.90, the notice ids and the place as evidence, decided by this module). Nothing is merged and no
row is deleted. Undo: move the listed notices back (the evidence holds them).

    python -m dgate.ops.generic_buyers --org 184800 --org 13952 --org 174324 --org 14912        # report, writes nothing
    python -m dgate.ops.generic_buyers --org 184800 --org 13952 --org 174324 --org 14912 --yes

ponytail: a later notice that states the bare name again goes to the generic row (resolution is not changed); run it again.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from typing import Any

from psycopg.types.json import Jsonb

from .. import db
from ..config import settings
from ..textsearch import fold

log = logging.getLogger("generic_buyers")

DETECTED_BY = "ops.generic_buyers"
METHOD = "place_in_notice"
RELATION = "notice_unit"
CONFIDENCE = 0.90


def plan(conn, org_ids: list[int]) -> list[dict[str, Any]]:
    """One line per notice of the rows: {notice, native_id, title, org, target, place, why}; `target` None when it stays."""
    out = []
    for oid in org_ids:
        row = conn.execute("SELECT id, canonical_name, country FROM organisation WHERE id = %s AND merged_into IS NULL",
                           (oid,)).fetchone()
        if row is None:
            out.append({"notice": None, "org": oid, "target": None, "why": "not a live row"})
            continue
        bare = fold(row["canonical_name"])
        units = conn.execute(
            """SELECT id, canonical_name FROM organisation
                WHERE country = %s AND merged_into IS NULL AND NOT suppressed AND lower(canonical_name) LIKE %s""",
            (row["country"], f"{row['canonical_name'].lower()} w %")).fetchall()
        places = {u["id"]: fold(u["canonical_name"])[len(bare):].strip() for u in units}     # "w glubczycach"
        for n in conn.execute(
                """SELECT id, native_id, buyer_name_raw, title_original, title_en, summary_en FROM opportunity
                    WHERE buyer_org_id = %s ORDER BY id""", (oid,)).fetchall():
            line = {"notice": n["id"], "native_id": n["native_id"], "title": (n["title_original"] or "")[:90], "org": oid,
                    "target": None, "place": None}
            if fold(n["buyer_name_raw"]) != bare:
                out.append({**line, "why": "states another name"})
                continue
            text = f" {fold(' '.join(filter(None, (n['title_original'], n['title_en'], n['summary_en']))))} "
            hits = [u for u, p in places.items() if p.startswith("w ") and f" {p} " in text]
            if len(hits) == 1:
                out.append({**line, "target": hits[0], "place": places[hits[0]], "why": "moved"})
            else:
                out.append({**line, "why": "several places" if hits else "no place of a known unit"})
    return out


def run(conn, org_ids: list[int], *, apply: bool = False, out=print) -> dict[str, Any]:
    lines = plan(conn, org_ids)
    moves = [x for x in lines if x["target"]]
    for x in lines:
        out(f"  {x['org']} notice {x['notice']} {x.get('native_id') or ''} {x.get('title', '')!r}: {x['why']}"
            + (f" -> {x['target']} ({x['place']})" if x["target"] else ""))
    res = {"notices": sum(1 for x in lines if x["notice"]), "to_move": len(moves),
           "stay": {w: sum(1 for x in lines if x["why"] == w) for w in {x["why"] for x in lines} - {"moved"}}}
    out(f"notices {res['notices']}, to move {res['to_move']}, staying {res['stay']}")
    if not apply:
        conn.rollback()
        out("report only: nothing written (add --yes)")
        return res
    pairs: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for x in moves:
        got = conn.execute("UPDATE opportunity SET buyer_org_id = %s WHERE id = %s AND buyer_org_id = %s RETURNING id",
                           (x["target"], x["notice"], x["org"])).fetchone()
        if got:
            pairs[(x["org"], x["target"])].append(x)
    for (src, dst), xs in pairs.items():
        conn.execute(
            """INSERT INTO resolution_review (org_a, org_b, proposed_relation, method, confidence, evidence, status,
                                              decided_by, decided_at)
               VALUES (LEAST(%s::bigint, %s::bigint), GREATEST(%s::bigint, %s::bigint), %s, %s, %s, %s, 'related', %s, now())
               ON CONFLICT (org_a, org_b, method) DO UPDATE
                  SET evidence = jsonb_set(resolution_review.evidence, '{notices}',
                                           (resolution_review.evidence->'notices') || (EXCLUDED.evidence->'notices')),
                      decided_at = now()""",
            (src, dst, src, dst, RELATION, METHOD, CONFIDENCE,
             Jsonb({"from": src, "to": dst, "place": xs[0]["place"], "notices": [x["notice"] for x in xs]}), DETECTED_BY))
    conn.commit()
    res["moved"] = sum(len(v) for v in pairs.values())
    out(f"moved {res['moved']} notices to {len(pairs)} units")
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--org", type=int, action="append", required=True, help="a generic buyer row (repeat)")
    p.add_argument("--yes", action="store_true", help="move the notices; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, a.org, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
