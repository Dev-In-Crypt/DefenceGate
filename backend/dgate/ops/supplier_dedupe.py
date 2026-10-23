"""One company under two contract-winner rows: merge them, with method and confidence stored (WP-96, persona round of
23 October 2026, A2.1).

    python -m dgate.ops.supplier_dedupe                    # report: every group and why others are left alone
    python -m dgate.ops.supplier_dedupe --yes              # merge (db.merge_organisations), then rebuild the directory
    python -m dgate.ops.supplier_dedupe --undo-batch FROM TO [--yes]   # undo the merges of one run (printed by --yes)

Only rows that won a contract of the supplier map (an award row) are looked at, both sides, in one country. Two rows
are one company when

  company_number      they hold one company number once written alike (`supplier_identity.company_number`: SAAB AB
                      556036-0793 and SAAB Aktiebolag SE556036079301) and their names agree (same key, same key
                      without spaces, or 0.85 alike)                                          confidence 0.97
  it_tax_pair         Italy: two valid 11-digit numbers (a company's codice fiscale and its partita IVA, Leonardo
                      00401990585 / 00881841001) and one stated name that the notices give with each of the two
                      numbers. Two numbers under one name alone are reported, never merged (namesakes)   0.90
  name_key            the same name key (`resolution.names.key_of`: case, accents, hyphens, legal forms; a form
                      word the key keeps at its end, "aktiebolag", "co kg", dropped: `core_key`)      0.95
  name_key_spaces     the same key once spaces are removed (Landsysteme / Land Systeme, RheinmetallMAN /
                      Rheinmetall MAN), keys of 12 characters or more                                    0.90

and nothing in the group contradicts it:

  * two numbers that cannot be one company's (`awards.numbers_conflict`: same kind, neither the start of the other,
    two characters apart; a VAT number and a register number are of two kinds). Rheinmetall Electronics GmbH stands
    three times with DE119356818 and DE251121155: left alone, reported
  * two legal-form classes among the names (RENK AG / RENK GmbH)
  * a public body (`buyer_family.is_public_body`: public bodies are never merged by a company rule; the buyer
    families group them), a row removed on request or marked a natural person

The head is the row with the most award rows, then the one holding a number, then the oldest. Nothing is deleted: the
absorbed row keeps `merged_into`, its method and confidence, and `ops.undo_merges`' logic undoes a run's window.
Idempotent: a second run finds no group.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from .. import db, networks
from ..awards import numbers_conflict
from ..buyer_family import is_public_body
from ..config import settings
from ..resolution.names import fold_key, key_of, legal_form_of
from ..supplier_identity import company_number, piva_valid
from . import undo_merges
from .accept_merge_candidates import _FORM_WORDS, name_similarity

log = logging.getLogger("supplier_dedupe")

DETECTED_BY = "ops.supplier_dedupe"
METHODS = {"company_number": 0.97, "name_key": 0.95, "it_tax_pair": 0.90, "name_key_spaces": 0.90}
MIN_FOLD = 12
MIN_KEY = 4


@dataclass
class Row:
    id: int
    country: str
    name: str
    numbers: set[str]
    forms: set[str]
    awards: int
    public: bool
    stated: dict[str, set[str]] = field(default_factory=dict)   # stated name (folded) -> numbers stated with it

    @property
    def key(self) -> str:
        return core_key(self.name)


# legal-form words the name key can still end with ("SAAB Aktiebolag" keys as "saab aktiebolag", "KNDS Deutschland GmbH
# & Co. KG" as "knds deutschland co")
_TAIL = _FORM_WORDS | {"co", "kg", "ohg", "mbh"}


def core_key(name: str) -> str:
    """The name key (`resolution.names.key_of`) without the legal-form words left at its end."""
    words = key_of(name or "")[0].split()
    while len(words) > 1 and words[-1] in _TAIL:
        words.pop()
    return " ".join(words)


def load(conn) -> list[Row]:
    """The live contract winners with their numbers (own and as the notices state them), the legal forms of their
    names and aliases, and the stated names with the numbers each was stated with."""
    rows = conn.execute(
        """WITH w AS (
               SELECT COALESCE(org.merged_into, org.id) AS id, count(*) AS n,
                      array_agg(DISTINCT a.identifier_as_stated) FILTER (WHERE a.identifier_as_stated IS NOT NULL) AS ids,
                      array_agg(DISTINCT a.name_as_stated || chr(1) || COALESCE(a.identifier_as_stated, '')) AS stated
                 FROM award a JOIN organisation org ON org.id = a.organisation_id
                WHERE a.superseded_at IS NULL AND a.excluded_reason IS NULL
                GROUP BY 1)
           SELECT g.id, g.country, COALESCE(g.display_name, g.canonical_name) AS name, g.national_reg_no, g.vat_number,
                  g.suppressed, g.individual_reason, g.is_defence_buyer, g.org_role, w.n, w.ids, w.stated,
                  ARRAY(SELECT x.raw_name FROM organisation_alias x WHERE x.organisation_id = g.id
                         ORDER BY x.id LIMIT 8) AS aliases
             FROM w JOIN organisation g ON g.id = w.id
            WHERE g.merged_into IS NULL AND NOT g.suppressed AND g.individual_reason IS NULL""").fetchall()
    out = []
    for r in rows:
        country = (r["country"] or "").strip()
        nums = {n for n in (company_number(x, country) for x in (r["national_reg_no"], r["vat_number"], *(r["ids"] or ())))
                if n}
        stated: dict[str, set[str]] = defaultdict(set)
        for s in r["stated"] or ():
            name, _, ident = s.partition(chr(1))
            if (n := company_number(ident, country)):
                stated[stated_key(name)].add(n)
        out.append(Row(r["id"], country, r["name"] or "", nums,
                       {f for f in map(legal_form_of, (r["name"], *(r["aliases"] or ()))) if f}, r["n"],
                       is_public_body(r["name"], country, defence_buyer=bool(r["is_defence_buyer"]),
                                      org_role=r["org_role"]),
                       dict(stated)))
    return out


def stated_key(name: str) -> str:
    """A name as the notices write it, legal form kept, only case, accents and punctuation folded: "LEONARDO SPA" and
    "Leonardo S.p.A." are one written name, "Leonardo" another."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return "".join(re.findall(r"[a-z0-9]+", s))


def _conflict(a: set[str], b: set[str]) -> bool:
    return bool(a and b and not a & b and any(numbers_conflict(x, y) for x in a for y in b))


def _names_agree(a: Row, b: Row) -> bool:
    return (a.key == b.key or fold_key(a.key) == fold_key(b.key)
            or name_similarity(a.name, b.name) >= 0.85)


def _it_pair(a: Row, b: Row) -> bool:
    """One stated name given with a number of each row, both valid Italian 11-digit numbers."""
    if a.country != "IT" or fold_key(a.key) != fold_key(b.key):
        return False
    va, vb = {n for n in a.numbers if piva_valid(n)}, {n for n in b.numbers if piva_valid(n)}
    if not va or not vb or va & vb:
        return False
    names = defaultdict(set)
    for r in (a, b):
        for name, nums in r.stated.items():
            names[name] |= nums
    return any(nums & va and nums & vb for nums in names.values())


def plan(rows: list[Row]) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    """The groups to merge ({head, members: [(id, method, confidence)], names}), the groups left alone by reason, and
    report lines for the Italian pairs that wait (two numbers under one name, not stated together)."""
    by_id = {r.id: r for r in rows}
    parent: dict[int, int] = {}
    edge: dict[tuple[int, int], str] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def join(a: Row, b: Row, method: str) -> None:
        k = (min(a.id, b.id), max(a.id, b.id))
        if k not in edge or METHODS[method] > METHODS[edge[k]]:
            edge[k] = method
        parent[find(a.id)] = find(b.id)

    buckets: dict[tuple[str, str], list[Row]] = defaultdict(list)
    numbers: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for r in rows:
        k = r.key
        if len(k) >= MIN_KEY and not k.isdigit() and not r.public:
            buckets[(r.country, fold_key(k))].append(r)
        for n in r.numbers:
            if not r.public:
                numbers[(r.country, n)].append(r)
    left: dict[str, int] = defaultdict(int)
    waiting: list[str] = []
    it_keys: set[tuple[int, int]] = set()      # the Italian pairs whose two numbers one stated name carries
    for (_, folded), members in buckets.items():
        if len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if a.key == b.key:
                    join(a, b, "name_key")
                elif len(folded) >= MIN_FOLD:
                    join(a, b, "name_key_spaces")
                else:
                    left["spacing_on_a_short_key"] += 1
    for members in numbers.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if a.id != b.id and _names_agree(a, b):
                    join(a, b, "company_number")
    for members in buckets.values():
        if members[0].country != "IT":
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if _it_pair(a, b):
                    join(a, b, "it_tax_pair")
                    it_keys.add((min(a.id, b.id), max(a.id, b.id)))
                elif ({n for n in a.numbers if piva_valid(n)} and {n for n in b.numbers if piva_valid(n)}
                      and not a.numbers & b.numbers):
                    waiting.append(f"  IT {a.id} {a.name[:40]!r} {sorted(a.numbers)} ~ {b.id} {b.name[:40]!r} "
                                   f"{sorted(b.numbers)}: two numbers under one name, never stated together")
    comps: dict[int, list[int]] = defaultdict(list)
    for x in parent:
        comps[find(x)].append(x)
    groups = []
    for ids in comps.values():
        if len(ids) < 2:
            continue
        members = [by_id[i] for i in ids]
        forms = {f for m in members for f in m.forms}
        it_pairs = {k for k in it_keys if k[0] in ids}
        clash = any(_conflict(a.numbers, b.numbers) and (min(a.id, b.id), max(a.id, b.id)) not in it_pairs
                    for i, a in enumerate(members) for b in members[i + 1:])
        if clash and not it_pairs:
            left["different_company_numbers"] += 1
        elif clash:
            left["different_company_numbers_beyond_the_pair"] += 1
        elif len(forms) > 1:
            left["different_legal_forms"] += 1
        else:
            members.sort(key=lambda m: (-m.awards, not m.numbers, m.id))
            head = members[0]
            joined = []
            for m in members[1:]:
                mine = [k for k in edge if m.id in k and k[0] in ids and k[1] in ids]
                # a pair only the stated name proves says so, whatever else joined it
                method = ("it_tax_pair" if any(k in it_pairs for k in mine)
                          else max((edge[k] for k in mine), key=lambda x: METHODS[x]))
                joined.append((m.id, method, METHODS[method]))
            groups.append({"head": head.id, "members": joined, "names": [m.name for m in members],
                           "numbers": sorted({n for m in members for n in m.numbers})})
    groups.sort(key=lambda g: (-len(g["members"]), g["head"]))
    return groups, dict(left), waiting


def run(conn, *, apply: bool = False, limit: int | None = None, out=print, sample: int = 40) -> dict[str, Any]:
    rows = load(conn)
    groups, left, waiting = plan(rows)
    result: dict[str, Any] = {"winners": len(rows), "groups": len(groups),
                              "rows_to_merge": sum(len(g["members"]) for g in groups),
                              "left": left, "it_pairs_waiting": len(waiting), "merged": 0}
    out(f"contract winners read: {len(rows)}; groups to merge: {len(groups)} ({result['rows_to_merge']} rows); "
        f"left alone: {left}; Italian pairs waiting for a source: {len(waiting)}")
    by_method: dict[str, int] = defaultdict(int)
    for g in groups:
        for _, method, _ in g["members"]:
            by_method[method] += 1
    result["by_method"] = dict(by_method)
    out(f"rows by method: {dict(by_method)}")
    for g in groups[:sample]:
        out(f"  head {g['head']} {g['names'][0][:50]!r} <- " + " | ".join(n[:40] for n in g["names"][1:5])
            + f"  [{', '.join(m for _, m, _ in g['members'])}] {g['numbers'][:3]}")
    for line in waiting[:sample]:
        out(line)
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return result
    started = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
    conn.commit()
    for g in groups[:limit]:
        for oid, method, conf in g["members"]:
            db.merge_organisations(conn, g["head"], oid, method=method, confidence=conf,
                                   evidence=f"supplier rule {method}; numbers {g['numbers'][:4]}",
                                   detected_by=DETECTED_BY, allow_identifier_conflict=True)
            result["merged"] += 1
        conn.commit()
    ended = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
    conn.commit()
    result["batch_window"] = (started.isoformat(), ended.isoformat())
    result["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"merged {result['merged']} rows; to undo: python -m dgate.ops.supplier_dedupe --undo-batch "
        f"'{started.isoformat()}' '{ended.isoformat()}' [--yes]")
    return result


def undo_batch(conn, start: str, end: str, *, apply: bool = False, out=print) -> dict[str, Any]:
    return undo_merges.run(conn, apply=apply, start=start, end=end, methods=tuple(METHODS),
                           expected=None, detected_by=DETECTED_BY, out=out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="merge; without it nothing changes")
    p.add_argument("--limit", type=int, default=None, help="merge at most this many groups")
    p.add_argument("--undo-batch", nargs=2, metavar=("FROM", "TO"), help="undo the merges of [FROM, TO); dry run unless --yes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        if a.undo_batch:
            undo_batch(conn, *a.undo_batch, apply=a.yes)
        else:
            run(conn, apply=a.yes, limit=a.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
