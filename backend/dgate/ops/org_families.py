"""Group the organisation rows that are one body into name families for the directory (WP-41, N5).

    python -m dgate.ops.org_families                 # dry run: the biggest families, nothing written
    python -m dgate.ops.org_families --yes           # write, then rebuild the directory table
    python -m dgate.ops.org_families --top 40        # print the 40 biggest families (the hand-review list)

Display layer only: `organisation_family_member` says which rows the directory shows as one card. No
organisation, alias or participation is touched and emptying the table undoes everything. The rules,
and the vetoes that stop a pair (different countries, PICs, registration numbers or legal forms), are
in `dgate/org_family.py`. Reads the pairs the cascade queued in `resolution_review` (trigram and
exact-name-ambiguous, still open), follows merged rows to their live row, builds stars around the
organisation with the most projects, and brings the table in line: rows are added or updated and rows no
rule produces any more are deleted (this table only). Idempotent. No network, no language model.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from typing import Any

from .. import db, networks, org_family
from ..config import settings
from ..resolution.names import key_of

log = logging.getLogger("org_families")


def nodes_of(conn) -> dict[int, dict[str, Any]]:
    """The live organisations that took part in a project, with what the vetoes need."""
    out = {}
    for r in conn.execute(
            """SELECT o.id, o.country, o.canonical_name, o.display_name, o.eu_pic, o.national_reg_no,
                      o.vat_number, a.projects
                 FROM (SELECT COALESCE(l.live_id, pa.organisation_id) AS org,
                              count(DISTINCT pa.project_id) AS projects
                         FROM participation pa
                         LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
                        WHERE pa.active AND NOT COALESCE(l.suppressed, FALSE) GROUP BY 1) a
                 JOIN organisation o ON o.id = a.org WHERE NOT o.suppressed AND o.merged_into IS NULL""").fetchall():
        name = r["display_name"] or r["canonical_name"]
        out[r["id"]] = {"id": r["id"], "country": r["country"].strip(), "key": key_of(name)[0], "display": r["display_name"],
                        "name": name, "pic": r["eu_pic"], "reg": r["national_reg_no"], "vat": r["vat_number"],
                        "projects": r["projects"]}
    return out


def pairs_of(conn) -> list[org_family.Pair]:
    """The open pairs, each end followed to its live row (a merge since the pair was queued)."""
    seen: set[tuple[int, int, str]] = set()
    out = []
    for r in conn.execute(
            """SELECT COALESCE(la.live_id, rr.org_a) AS a, COALESCE(lb.live_id, rr.org_b) AS b, rr.method,
                      rr.confidence
                 FROM resolution_review rr
                 LEFT JOIN organisation_merged_live la ON la.id = rr.org_a
                 LEFT JOIN organisation_merged_live lb ON lb.id = rr.org_b
                WHERE rr.status = 'open' AND rr.method IN ('trigram', 'exact_name_ambiguous')""").fetchall():
        a, b = sorted((r["a"], r["b"]))
        if a != b and (a, b, r["method"]) not in seen:
            seen.add((a, b, r["method"]))
            out.append(org_family.Pair(a, b, r["method"], float(r["confidence"] or 0)))
    return out


def families(conn) -> tuple[dict[int, tuple[int, str, float]], dict[str, int], dict[int, dict[str, Any]]]:
    nodes = nodes_of(conn)
    member_of, counts = org_family.build(nodes, pairs_of(conn))
    return member_of, counts, nodes


def run(conn, *, apply: bool = False, top: int = 0, out=print) -> dict[str, int]:
    wanted, pair_counts, nodes = families(conn)
    stored = {r["org_id"]: (r["head_org_id"], r["method"], float(r["confidence"]))
              for r in conn.execute(
                  "SELECT org_id, head_org_id, method, confidence FROM organisation_family_member").fetchall()}
    changed = [o for o, v in wanted.items() if stored.get(o) != v]
    gone = [o for o in stored if o not in wanted]
    members_of: dict[int, list[int]] = defaultdict(list)
    for m, (h, _, _) in wanted.items():
        members_of[h].append(m)
    counts = {"families": len(members_of), "members": len(wanted), "written": len(changed), "removed": len(gone),
              **{f"pairs_{k}": v for k, v in pair_counts.items()}}
    if top:
        biggest = sorted(members_of, key=lambda h: -(nodes[h]["projects"] + sum(nodes[m]["projects"] for m in members_of[h])))
        for h in biggest[:top]:
            ms = sorted(members_of[h], key=lambda m: (-nodes[m]["projects"], m))
            total = nodes[h]["projects"] + sum(nodes[m]["projects"] for m in ms)
            out(f"{nodes[h]['country']}  {nodes[h]['name'][:70]}  [head {h}, {nodes[h]['projects']} projects, "
                f"PIC {nodes[h]['pic'] or '-'}]  family total at most {total} projects, {len(ms)} variants")
            for m in ms:
                w = wanted[m]
                out(f"      {m:>7} {nodes[m]['projects']:>5}  {nodes[m]['name'][:70]}  PIC {nodes[m]['pic'] or '-'}  ({w[1]}, {w[2]})")
    if apply:
        for o in changed:
            head, method, conf = wanted[o]
            conn.execute(
                """INSERT INTO organisation_family_member (org_id, head_org_id, method, confidence)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (org_id) DO UPDATE SET head_org_id = EXCLUDED.head_org_id,
                       method = EXCLUDED.method, confidence = EXCLUDED.confidence""", (o, head, method, conf))
        if gone:
            conn.execute("DELETE FROM organisation_family_member WHERE org_id = ANY(%s)", (gone,))
        conn.commit()
        counts["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"{counts} ({'written' if apply else 'dry run, nothing is written'})")
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    p.add_argument("--top", type=int, default=10, help="print this many of the biggest families")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=a.yes, top=a.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
