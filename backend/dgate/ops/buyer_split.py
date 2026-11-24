"""Take another body out of a buyer family, by a person's reviewed decision (WP-175, QA of 24 November 2026, D-4 and F06).

The BAAINBw page (/buyers/196) lists the Federal Office for Infrastructure (BAIUDBw, its own buyer /buyers/330) and the
Bundeswehr IT office (BAIT) among its units and name variants: other federal offices. A name rule, a shared tax id or a twin
notice put a row of theirs into the BAAINBw family, or their notices were filed under one of its rows. This splits them out:

  members  the family's rows whose name matches `--name` (folded: lower case, no accents or marks) leave the family. The
           decision is stored in `resolution_review` (the head and the row, relation `not_one_buyer`, method `reviewed_split`,
           the confidence given, the pattern and `--why` as evidence, status `rejected`), and `ops.buyer_families` honours it
           at every run (`split_decisions`): the row is never put back under that head, and joins the `--to` buyer's family.
  notices  the family's notices whose stated buyer name matches `--name` move to the `--to` row (`opportunity.buyer_org_id`;
           the archived versions keep what was published), each pair written down in `resolution_review` (relation
           `notice_unit`, method `stated_buyer_name`, the notice ids as evidence), as `ops.generic_buyers` does.

Nothing is merged or deleted but the family rows of the members it splits. Report by default; `--yes` writes, then the
families and the buyer aggregate are computed again. Undo: set the review rows' status to `withdrawn` and move the listed
notices back.

    python -m dgate.ops.buyer_split --head 196 --to 330 --name "baiudbw|infrastruktur umweltschutz und dienstleistungen" \\
        --why "BAIUDBw is a federal office of its own (BAIUDBwOrgErl)"                 # report
    ... --yes

ponytail: a later notice that states the other office's name but resolves to a family row moves only when this runs again.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from typing import Any

from psycopg.types.json import Jsonb

from .. import db
from ..config import settings
from ..textsearch import fold

log = logging.getLogger("buyer_split")

DETECTED_BY = "ops.buyer_split"
SPLIT = "reviewed_split"
SPLIT_RELATION = "not_one_buyer"
MOVE = "stated_buyer_name"
MOVE_RELATION = "notice_unit"
MOVE_CONFIDENCE = 0.90


def split_decisions(conn) -> list[dict[str, Any]]:
    """The stored splits, for `ops.buyer_families`: {member, head, to, confidence} (`to` None: the row stands alone)."""
    try:
        with conn.transaction():
            rows = conn.execute(
                "SELECT evidence, confidence FROM resolution_review WHERE method = %s AND status = 'rejected'",
                (SPLIT,)).fetchall()
    except Exception:  # noqa: BLE001 - a role that may not read the table splits nothing
        return []
    return [{"member": int(e["member"]), "head": int(e["head"]), "to": int(e["to"]) if e.get("to") else None,
             "confidence": float(r["confidence"] or 0.95)}
            for r in rows if isinstance(e := r["evidence"], dict) and e.get("member") and e.get("head")]


def plan(conn, head: int, pattern: str, to: int | None) -> dict[str, Any]:
    rx = re.compile(pattern)
    head = conn.execute("SELECT dgate_buyer_head(%s) AS h", (head,)).fetchone()["h"]
    family = conn.execute("SELECT dgate_family_ids(%s) AS ids", (head,)).fetchone()["ids"] or [head]
    rows = conn.execute(
        """SELECT org.id, org.canonical_name, m.method, m.confidence FROM organisation org
             LEFT JOIN buyer_family_member m ON m.org_id = org.id WHERE org.id = ANY(%s) ORDER BY org.id""",
        (family,)).fetchall()
    members = [r for r in rows if r["id"] != head and rx.search(fold(r["canonical_name"] or ""))]
    notices = [n for n in conn.execute(
        """SELECT id, native_id, buyer_org_id, buyer_name_raw FROM opportunity
            WHERE buyer_org_id = ANY(%s) AND buyer_name_raw IS NOT NULL ORDER BY id""", (family,)).fetchall()
        if rx.search(fold(n["buyer_name_raw"]))]
    # a leaving row keeps its notices (they go with it); only the rows that stay lose the other body's notices
    leaving = {m["id"] for m in members}
    notices = [n for n in notices if n["buyer_org_id"] != to and n["buyer_org_id"] not in leaving]
    return {"head": head, "family": len(family), "members": members, "notices": notices}


def run(conn, head: int, pattern: str, *, to: int | None, why: str, confidence: float, apply: bool = False,
        out=print) -> dict[str, Any]:
    if to is not None and not conn.execute("SELECT 1 FROM organisation WHERE id = %s AND merged_into IS NULL "
                                           "AND NOT suppressed", (to,)).fetchone():
        raise SystemExit(f"--to {to} is not a live organisation")
    p = plan(conn, head, pattern, to)
    out(f"family of {p['head']}: {p['family']} rows")
    for m in p["members"]:
        out(f"  member {m['id']:>8} {m['canonical_name']!r} ({m['method']}, {m['confidence']}) -> leaves"
            + (f", joins {to}" if to else ""))
    names = defaultdict(int)
    for n in p["notices"]:
        names[(n["buyer_org_id"], n["buyer_name_raw"])] += 1
    for (org, name), k in sorted(names.items(), key=lambda x: -x[1]):
        out(f"  notices {k:>6} under {org} stating {name!r}" + (f" -> {to}" if to else " (stay: no --to)"))
    res = {"members": len(p["members"]), "notices": len(p["notices"]) if to else 0}
    if not apply:
        conn.rollback()
        out(f"{res}; report only: nothing written (add --yes)")
        return res
    for m in p["members"]:
        conn.execute(
            """INSERT INTO resolution_review (org_a, org_b, proposed_relation, method, confidence, evidence, status,
                                              decided_by, decided_at)
               VALUES (LEAST(%s::bigint, %s::bigint), GREATEST(%s::bigint, %s::bigint), %s, %s, %s, %s, 'rejected', %s, now())
               ON CONFLICT (org_a, org_b, method) DO UPDATE SET evidence = EXCLUDED.evidence, status = 'rejected',
                   confidence = EXCLUDED.confidence, decided_by = EXCLUDED.decided_by, decided_at = now()""",
            (p["head"], m["id"], p["head"], m["id"], SPLIT_RELATION, SPLIT, confidence,
             Jsonb({"head": p["head"], "member": m["id"], "to": to, "pattern": pattern, "why": why,
                    "was": {"method": m["method"], "confidence": float(m["confidence"] or 0)}}), DETECTED_BY))
        conn.execute("DELETE FROM buyer_family_member WHERE org_id = %s AND head_org_id = %s", (m["id"], p["head"]))
    moved: dict[int, list[int]] = defaultdict(list)
    if to is not None:
        for n in p["notices"]:
            if conn.execute("UPDATE opportunity SET buyer_org_id = %s WHERE id = %s AND buyer_org_id = %s RETURNING id",
                            (to, n["id"], n["buyer_org_id"])).fetchone():
                moved[n["buyer_org_id"]].append(n["id"])
        for src, ids in moved.items():
            conn.execute(
                """INSERT INTO resolution_review (org_a, org_b, proposed_relation, method, confidence, evidence, status,
                                                  decided_by, decided_at)
                   VALUES (LEAST(%s::bigint, %s::bigint), GREATEST(%s::bigint, %s::bigint), %s, %s, %s, %s, 'related', %s, now())
                   ON CONFLICT (org_a, org_b, method) DO UPDATE
                      SET evidence = jsonb_set(resolution_review.evidence, '{notices}',
                                               (resolution_review.evidence->'notices') || (EXCLUDED.evidence->'notices')),
                          decided_at = now()""",
                (src, to, src, to, MOVE_RELATION, MOVE, MOVE_CONFIDENCE,
                 Jsonb({"from": src, "to": to, "pattern": pattern, "why": why, "notices": ids}), DETECTED_BY))
    conn.commit()
    res["moved"] = sum(len(v) for v in moved.values())
    from . import buyer_families
    buyer_families.run(conn, write=True, refresh=True)
    out(f"{res}: written; families and the buyer aggregate computed again")
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--head", type=int, required=True, help="a row of the family to split (its head is found)")
    p.add_argument("--name", required=True, help="regular expression on the folded name (lower case, no accents)")
    p.add_argument("--to", type=int, help="the other body's buyer row: its notices go there, the split rows join its family")
    p.add_argument("--why", required=True, help="the evidence a person checked (stored with the decision)")
    p.add_argument("--confidence", type=float, default=0.95)
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, a.head, a.name, to=a.to, why=a.why, confidence=a.confidence, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
