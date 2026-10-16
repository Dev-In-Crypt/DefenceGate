"""Group the organisation rows that are one body into buyer families (WP-22).

Display layer only: `buyer_family_member` says which rows the buyer list shows as one
buyer. No organisation, alias or `opportunity.buyer_org_id` is touched, and emptying the
table undoes everything. The rules are in `dgate/buyer_family.py`.

Reads the organisations that buy at least one defence notice, groups them by rule (two
rows at least), picks the head of each group (most defence notices, then the lowest id),
and brings `buyer_family_member` in line: rows are added or updated, and rows no rule
produces any more are deleted (this table only). Idempotent.

    python -m dgate.ops.buyer_families          # dry run: every group, nothing written
    python -m dgate.ops.buyer_families --yes    # write
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from .. import db
from ..buyer_family import family_of
from ..config import settings

log = logging.getLogger("buyer_families")


@dataclass
class Member:
    org_id: int
    name: str
    notices: int
    method: str
    confidence: float
    reg_no: str | None = None


@dataclass
class Group:
    key: str
    head: Member
    members: list[Member] = field(default_factory=list)   # without the head

    @property
    def notices(self) -> int:
        return self.head.notices + sum(m.notices for m in self.members)


def organisations(conn) -> list[tuple[int, str, str, int, str | None]]:
    """(id, country, canonical name, defence notices, national registration number) of
    every organisation that is the buyer of a defence notice. Suppressed ones are left
    out: a name withheld on request is not shown through a family either."""
    return [(r["id"], r["country"], r["canonical_name"], r["n"], r["national_reg_no"])
            for r in conn.execute(
        """SELECT org.id, org.country, org.canonical_name, org.national_reg_no, count(*) AS n
             FROM opportunity o JOIN organisation org ON org.id = o.buyer_org_id
            WHERE o.is_defence AND NOT o.suppressed AND NOT o.buyer_withheld
              AND NOT org.suppressed
            GROUP BY org.id, org.country, org.canonical_name, org.national_reg_no""").fetchall()]


def groups_of(rows: list[tuple[int, str, str, int, str | None]]) -> list[Group]:
    by_key: dict[str, list[Member]] = defaultdict(list)
    for org_id, country, name, n, reg in rows:
        fam = family_of(country, name)
        if fam:
            by_key[fam.key].append(Member(org_id, name, n, fam.method, fam.confidence, reg))
    out = []
    for key, members in by_key.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda m: (-m.notices, m.org_id))
        out.append(Group(key, members[0], members[1:]))
    out.sort(key=lambda g: (-g.notices, g.key))
    return out


def run(conn, *, write: bool = False) -> dict[str, int]:
    groups = groups_of(organisations(conn))
    wanted = {m.org_id: (g.head.org_id, m.method, m.confidence)
              for g in groups for m in g.members}
    stored = {r["org_id"]: (r["head_org_id"], r["method"], float(r["confidence"]))
              for r in conn.execute(
        "SELECT org_id, head_org_id, method, confidence FROM buyer_family_member").fetchall()}
    changed = [o for o, v in wanted.items() if stored.get(o) != v]
    gone = [o for o in stored if o not in wanted]
    if write:
        for o in changed:
            head, method, conf = wanted[o]
            conn.execute(
                """INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (org_id) DO UPDATE SET head_org_id = EXCLUDED.head_org_id,
                       method = EXCLUDED.method, confidence = EXCLUDED.confidence""",
                (o, head, method, conf))
        if gone:
            conn.execute("DELETE FROM buyer_family_member WHERE org_id = ANY(%s)", (gone,))
        conn.commit()
    return {"groups": len(groups), "members": len(wanted), "written": len(changed),
            "removed": len(gone), "notices": sum(g.notices for g in groups)}


def report(conn) -> list[str]:
    lines = []
    for g in groups_of(organisations(conn)):
        regs = {m.reg_no for m in [g.head, *g.members] if m.reg_no}
        lines.append(f"{g.key}  [{g.notices} notices, {1 + len(g.members)} rows"
                     + (f", {len(regs)} different registration numbers" if len(regs) > 1 else "")
                     + "]")
        lines.append(f"    head   {g.head.org_id:>7} {g.head.notices:>6}  {g.head.name}")
        for m in g.members:
            lines.append(f"    member {m.org_id:>7} {m.notices:>6}  {m.name}  ({m.method}, {m.confidence})")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        for line in report(conn):
            print(line)
        counts = run(conn, write=args.yes)
    log.info("%s (%s)", ", ".join(f"{k} {v}" for k, v in counts.items()),
             "written" if args.yes else "dry run, nothing is written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
