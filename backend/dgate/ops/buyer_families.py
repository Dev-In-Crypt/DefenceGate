"""Group the organisation rows that are one body into buyer families (WP-22).

Display layer only: `buyer_family_member` says which rows the buyer list shows as one
buyer. No organisation, alias or `opportunity.buyer_org_id` is touched, and emptying the
table undoes everything. The rules are in `dgate/buyer_family.py`.

Reads the organisations that buy at least one defence notice, groups them by rule (two
rows at least), picks the head of each group (most defence notices, then the lowest id),
adds the rule `shared_tax_id` for the rows the name rules left alone (public bodies one tax id
proves one legal entity, never merged: WP-74, `tax_id_groups`), and brings `buyer_family_member` in line: rows are added or updated, and rows no rule
produces any more are deleted (this table only). Idempotent.

    python -m dgate.ops.buyer_families          # dry run: every group and the rows that change, nothing written
    python -m dgate.ops.buyer_families --changes   # dry run: only the rows that change (WP-104)
    python -m dgate.ops.buyer_families --yes    # write
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from .. import db
from ..buyer_family import (
    CURATED_RENAME,
    RULE,
    SHARED_TAX_ID,
    family_of,
    is_public_body,
    is_sub_unit,
)
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
        # WP-87: a renamed body's family is headed by its successor (curated renames), whatever the counts. WP-104: and an
        # office by its own name ("Staatliches Hochbauamt Ulm", not "Bundesrepublik Deutschland vertreten durch ... das
        # Staatliche Hochbauamt Ulm"), where one is among its rows
        members.sort(key=lambda m: (m.method == CURATED_RENAME, " vertreten " in f" {m.name} ", -m.notices, m.org_id))
        out.append(Group(key, members[0], members[1:]))
    out.sort(key=lambda g: (-g.notices, g.key))
    return out


def tax_id_pairs(conn) -> list[tuple[int, int]]:
    """The pairs one tax id proves to be one legal entity and that are never merged because one
    side is a public body (`ops.accept_merge_candidates`, status `rejected_public_units`), both ends
    taken to their live row."""
    return [(r["a"], r["b"]) for r in conn.execute(
        """SELECT COALESCE(la.live_id, c.organisation_id) AS a,
                  COALESCE(lb.live_id, c.candidate_org_id) AS b
             FROM organisation_merge_candidate c
             LEFT JOIN organisation_merged_live la ON la.id = c.organisation_id
             LEFT JOIN organisation_merged_live lb ON lb.id = c.candidate_org_id
            WHERE c.status = 'rejected_public_units'""").fetchall()]


def tax_id_groups(conn, pairs: list[tuple[int, int]], buyers: dict[int, Member],
                  placed: set[int]) -> list[Group]:
    """Rule `shared_tax_id` (WP-74): the rows a chain of such pairs joins are one buyer, shown
    under the parent body: the row of the set whose name is not a unit's ('gobierno vasco', not
    'gobierno vasco departamento de salud'), without a dash, the one most other names begin with,
    then the one with the most defence notices (`rank`). A set
    with no such row stays apart (no parent name is known), and so does a row a name rule placed."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        if a != b:
            parent[find(a)] = find(b)
    sets: dict[int, list[int]] = defaultdict(list)
    for x in parent:
        sets[find(x)].append(x)
    ids = sorted({x for s in sets.values() for x in s if x not in placed})
    rows = {r["id"]: r for r in conn.execute(
        """SELECT id, country, canonical_name FROM organisation
            WHERE id = ANY(%s) AND merged_into IS NULL AND NOT suppressed""", (ids,)).fetchall()}
    out = []
    for members in sets.values():
        live = [x for x in members if x in rows]
        parents = [x for x in live if not is_sub_unit(rows[x]["canonical_name"])]
        if not parents:
            continue
        names = [rows[x]["canonical_name"] for x in live]

        def rank(x: int, names: list[str] = names) -> tuple:
            # "comune di firenze - direzione ..", "gobierno vasco - seguridad": a dash mostly brings a
            # unit after the body. Then the name the others begin with ("gobierno vasco" before
            # "gobierno vasco hacienda y economia"), then the most notices (not a typo or an
            # abbreviation of 0 notices), then the shortest.
            n = rows[x]["canonical_name"]
            return (" - " in n, -sum(o.startswith(n + " ") for o in names),
                    -(buyers[x].notices if x in buyers else 0), len(n), x)

        head = min(parents, key=rank)
        units = sorted((buyers[x] for x in live if x in buyers and x != head),
                       key=lambda m: (-m.notices, m.org_id))
        if not units:
            continue
        h = buyers.get(head) or Member(head, rows[head]["canonical_name"], 0, SHARED_TAX_ID, RULE)
        out.append(Group(f"{rows[head]['country']}:tax:{head}", h, [
            Member(m.org_id, m.name, m.notices, SHARED_TAX_ID, RULE, m.reg_no) for m in units]))
    return out


TWIN_NOTICE = "twin_notice"
TWIN_CONFIDENCE = 0.85
# Links that name the TED notice by an identifier (migration 0035); a `heuristic` twin is not enough to move a buyer.
TWIN_METHODS = ("stated_ted_ref", "doue_ref", "procedure_id")


def twin_pairs(conn) -> list[tuple[int, int]]:
    """(the national copy's buyer, the TED twin's buyer) of every notice published in TED and in a national portal
    (Video Downlink Track Antenna: TED 146213 under 'Ministry of Defence', its TenderNed copy 146554 under 'Ministerie
    van Defensie'), the twin linked by an identifier. WP-104: the pairs whose two rows are one buyer row are returned
    too: they are the copies that say the row stays where it is (`twin_groups` counts them)."""
    return [(r["copy"], r["twin"]) for r in conn.execute(
        """SELECT o.buyer_org_id AS copy, t.buyer_org_id AS twin
             FROM opportunity o
             JOIN opportunity t ON t.native_id = o.ted_ref AND t.source_id = (SELECT id FROM source WHERE code = 'ted')
            WHERE o.ted_ref IS NOT NULL AND o.twin_method = ANY(%s) AND o.is_defence AND t.is_defence
              AND NOT o.suppressed AND NOT t.suppressed AND NOT o.buyer_withheld AND NOT t.buyer_withheld
              AND o.buyer_org_id IS NOT NULL AND t.buyer_org_id IS NOT NULL
              AND o.country = t.country""", (list(TWIN_METHODS),)).fetchall()]


def twin_groups(groups: list[Group], pairs: list[tuple[int, int]], buyers: dict[int, Member]) -> list[Group]:
    """WP-96: the copy follows the twin's buyer family. A buyer row that no rule placed and whose notices are the
    national copies of TED notices joins the family of the TED notices' buyer (the one most of its copies point at);
    a twin's buyer with no family heads a new one. A row a rule placed is never moved, and a head is never made a
    member.

    WP-104: only when more than half of the row's twinned copies point at that one buyer. A copy whose TED twin is
    under the row itself is a vote to stay: the Polish Ministry of National Defence (107 copies of its own TED notices)
    was put under the Cyberspace Resources Centre of the Armed Forces (buyer 9770) because 28 of its copies are TED
    notices the centre published, the ministry being named as the legal entity in the national bulletin."""
    head_of = {m.org_id: g for g in groups for m in (g.head, *g.members)}
    votes: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for copy, twin in pairs:
        if copy in head_of or copy not in buyers:
            continue
        target = head_of[twin].head.org_id if twin in head_of else twin
        votes[copy][target] += 1        # target == copy: a copy of the row's own TED notice
    moving = {copy for copy, by_target in votes.items()
              if max((n for t, n in by_target.items() if t != copy), default=0) * 2 > sum(by_target.values())}
    added: dict[int, Group] = {}
    for copy in sorted(moving):
        by_target = {t: n for t, n in votes[copy].items() if t != copy}
        target = max(by_target, key=lambda t: (by_target[t], -t))
        if target in moving:            # the target is itself a copy that moves: left alone (no chains)
            continue
        member = Member(copy, buyers[copy].name, buyers[copy].notices, TWIN_NOTICE, TWIN_CONFIDENCE,
                        buyers[copy].reg_no)
        if target in head_of:
            head_of[target].members.append(member)
        else:
            g = added.get(target)
            if g is None:
                head = buyers.get(target)
                if head is None:
                    continue
                g = added[target] = Group(f"twin:{target}", Member(target, head.name, head.notices, TWIN_NOTICE,
                                                                   TWIN_CONFIDENCE, head.reg_no))
            g.members.append(member)
    return list(added.values())


def all_groups(conn, extra_pairs: list[tuple[int, int]] = ()) -> list[Group]:
    """The name rules first; the shared tax id joins only rows they left alone; then a national copy's buyer follows
    its TED twin's buyer (`twin_groups`)."""
    rows = organisations(conn)
    groups = groups_of(rows)
    placed = {m.org_id for g in groups for m in (g.head, *g.members)}
    buyers = {r[0]: Member(r[0], r[2], r[3], SHARED_TAX_ID, RULE, r[4]) for r in rows}
    groups += tax_id_groups(conn, tax_id_pairs(conn) + list(extra_pairs), buyers, placed)
    pairs = twin_pairs(conn)
    # WP-119: a company is never put into a buyer's family by a twin notice: a copy's buyer row that wins contracts (an
    # award row) and whose name is no public body's is the winner the national copy named as its buyer (BOAMP 24-21330:
    # SPIE FACILITIES, its TED twin 109763-2024 under ESID Rennes, SPIE the winner)
    winners = {r["organisation_id"] for r in conn.execute(
        "SELECT DISTINCT organisation_id FROM award WHERE organisation_id = ANY(%s)",
        (sorted({c for c, _ in pairs}),)).fetchall()}
    country = {r[0]: r[1] for r in rows}
    companies = {c for c in winners if c in buyers and not is_public_body(buyers[c].name, country.get(c))}
    groups += twin_groups(groups, [(c, t) for c, t in pairs if c not in companies], buyers)
    groups.sort(key=lambda g: (-g.notices, g.key))
    return groups


def run(conn, *, write: bool = False, extra_pairs: list[tuple[int, int]] = (), out=None,
        refresh: bool = False) -> dict[str, int]:
    """`extra_pairs`: pairs to treat as `rejected_public_units` although not yet stored (the dry run
    of `ops.accept_merge_candidates`). `out`: where the rows that change are printed, one line each."""
    groups = all_groups(conn, extra_pairs)
    wanted = {m.org_id: (g.head.org_id, m.method, m.confidence)
              for g in groups for m in g.members}
    stored = {r["org_id"]: (r["head_org_id"], r["method"], float(r["confidence"]))
              for r in conn.execute(
        "SELECT org_id, head_org_id, method, confidence FROM buyer_family_member").fetchall()}
    changed = [o for o, v in wanted.items() if stored.get(o) != v]
    gone = [o for o in stored if o not in wanted]
    if out:
        # WP-104: the exact rows the write changes, before it writes: (member, head, method) now and as stored
        for o in sorted(changed):
            out(f"  set    {o:>7} -> {wanted[o][0]:>7} {wanted[o][1]} {wanted[o][2]}"
                + (f"  (stored -> {stored[o][0]} {stored[o][1]})" if o in stored else "  (new)"))
        for o in sorted(gone):
            out(f"  remove {o:>7} -> {stored[o][0]:>7} {stored[o][1]} {stored[o][2]}")
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
        if refresh and (changed or gone):
            # WP-111: the stored buyer aggregate is computed again at once (a pass over every notice, seconds), so a
            # twin under two rows now one family is counted once on the list as it is on the buyer page (the command's
            # --yes; without a stored aggregate the API counts each notice once, a twin twice, as it always did)
            from . import warm_lists
            warm_lists._write_views(conn, [v for v in warm_lists.views([]) if v[0] == "buyer-base"], [], True)
    return {"groups": len(groups), "members": len(wanted), "written": len(changed),
            "removed": len(gone), "notices": sum(g.notices for g in groups)}


def report(conn) -> list[str]:
    lines = []
    for g in all_groups(conn):
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
    parser.add_argument("--changes", action="store_true", help="print only the rows that change, not every group")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        if not args.changes:
            for line in report(conn):
                print(line)
        print("rows that change (member -> head, method, confidence):")
        counts = run(conn, write=args.yes, out=print, refresh=True)
    log.info("%s (%s)", ", ".join(f"{k} {v}" for k, v in counts.items()),
             "written" if args.yes else "dry run, nothing is written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
