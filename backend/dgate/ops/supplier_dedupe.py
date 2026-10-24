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
  company_number_division  (WP-104) one company number, and one name is the other's followed by a division
                      ("Leonardo S.p.A. - Aircraft Division" with Leonardo's own number): a division has no legal
                      personality of its own                                                             0.95

  stated_number_prefix  (WP-104) a row with no number of its own whose award rows state a number the other row
                      holds, and whose name begins with the other's (Navantia Sistemas, A84076397)        0.90
  curated_source_review  (WP-104) rows a person read in the source (`REVIEWED`: the company row's number, the other
                      rows' names, the evidence stored with the merge; Works 11 Sp. z o.o.)               0.90

A shared number joins rows of two countries only under one name key (WP-104: a winner filed under its buyer's country
by the notices that state its number). Nothing joined may contradict it:

  * two numbers that cannot be one company's (`awards.numbers_conflict`: same kind, neither the start of the other,
    two characters apart; a VAT number and a register number are of two kinds): the owner's rule, other numbers are
    other companies. Rheinmetall Electronics GmbH stands three times with DE811127845, DE119356818 and DE251121155:
    left alone, reported
  * two legal-form classes among the names (RENK AG / RENK GmbH)

WP-104: the joins are made numbers first, names second, and only where no part joined has a conflict among what it
is joined to (`plan`): a conflict keeps apart the rows it concerns, not every row a name links to them, and a row
without a number that two conflicting companies could be is joined to neither.
  * a public body (`buyer_family.is_public_body`: public bodies are never merged by a company rule; the buyer
    families group them), a row removed on request or marked a natural person

WP-111: a number is the company's own only when it has the shape of one (`supplier_identity.own_number`): the code a
Spanish defence buyer gives a foreign supplier ("DE0000CGC00430", Heckler & Koch) and a value of no shape an Italian or a
British company number has ("0006001333" for Leonardo S.p.A., "0898937602" for Leonardo UK Ltd) are no evidence for or
against; the name key reads "and" / "und" as the "&" they stand for; and a row with no number of its own whose name is
another's with the Irish eTenders reference after it ("Leonardo Spa_149684") is that row (`name_key_portal_suffix`, 0.90).
The report lists every pair it merges and every set it leaves apart, each with its numbers.

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
from ..supplier_identity import _FORM_COUNTRIES, own_number, piva_valid
from . import undo_merges
from .accept_merge_candidates import _FORM_WORDS, name_similarity

log = logging.getLogger("supplier_dedupe")

DETECTED_BY = "ops.supplier_dedupe"
# WP-104, owner decision of 24 October 2026: rows a person read in the source and found to be one company, each by the
# number the company row holds and the names (folded as `stated_key`) the other rows carry, with the evidence stored.
CURATED_REVIEW = "curated_source_review"


@dataclass(frozen=True)
class Reviewed:
    country: str
    number: str                    # the company row's number (`company_number` form)
    names: frozenset[str]          # the other rows' names, `stated_key`; rows of them holding a number are never taken
    evidence: str


REVIEWED: tuple[Reviewed, ...] = (
    Reviewed("PL", "6462895170", frozenset({"works11spzoo", "workss11spzoo", "worksspzoo"}),
             "WORKS 11 Sp. z o.o. (NIP 6462895170): 'Works11 Sp. z o. o.' (TED 315699-2023), 'WORKSS - 11 Sp. z o.o.' "
             "(TED 629838-2023, which also lists 'WORKS 11- Sp. z o.o.') and 'Works Sp. z o.o.' (TED 753670-2023, buyer "
             "JW 2305, which also lists 'Works 11 Sp. z o.o.') are typing variants of the one company; read by the "
             "orchestrator on production, 24 October 2026"),
)

METHODS = {"company_number": 0.97, "name_key": 0.95, "company_number_division": 0.95, "it_tax_pair": 0.90,
           "name_key_spaces": 0.90, "stated_number_prefix": 0.90, CURATED_REVIEW: 0.90, "name_key_portal_suffix": 0.90}
# the methods of the first pass (`plan`): evidence by number, or a person's review of the source
NUMBER_METHODS = frozenset({"company_number", "company_number_division", "it_tax_pair", "stated_number_prefix",
                            CURATED_REVIEW})
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
    own: set[str] = field(default_factory=set)                   # WP-104: the row's own numbers (not the stated ones)

    @property
    def key(self) -> str:
        return core_key(self.name)


# legal-form words the name key can still end with ("SAAB Aktiebolag" keys as "saab aktiebolag", "KNDS Deutschland GmbH
# & Co. KG" as "knds deutschland co")
_TAIL = _FORM_WORDS | {"co", "kg", "ohg", "mbh"}
_PORTAL_SUFFIX = re.compile(r"(?<=[^\W\d_])_\d{1,6}\s*$")
_AND = frozenset({"and", "und"})


def core_key(name: str) -> str:
    """The name key (`resolution.names.key_of`) without the legal-form words left at its end. WP-104: and without an
    Italian company's "Societa" in front ("SOCIETA LEONARDO S.P.A." is Leonardo S.p.A.)."""
    # WP-111: "and" / "und" between words, which "&" stands for ("HECKLER AND KOCH GMBH." is "Heckler & Koch GmbH"; the key
    # reads "&" as a space)
    words = [w for w in key_of(name or "")[0].split() if w not in _AND]
    while len(words) > 1 and words[-1] in _TAIL:
        words.pop()
    if len(words) > 1 and words[0] == "societa" and legal_form_of(name) in ("spa", "srl"):
        words.pop(0)
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
        # WP-111: a buyer's or a portal's code in the number field is no number of the company (`own_number`)
        nums = {n for n in (own_number(x, country) for x in (r["national_reg_no"], r["vat_number"], *(r["ids"] or ())))
                if n}
        stated: dict[str, set[str]] = defaultdict(set)
        for s in r["stated"] or ():
            name, _, ident = s.partition(chr(1))
            if (n := own_number(ident, country)):
                stated[stated_key(name)].add(n)
        out.append(Row(r["id"], country, r["name"] or "", nums,
                       {f for f in map(legal_form_of, (r["name"], *(r["aliases"] or ()))) if f}, r["n"],
                       is_public_body(r["name"], country, defence_buyer=bool(r["is_defence_buyer"]),
                                      org_role=r["org_role"]),
                       dict(stated),
                       {n for n in (own_number(x, country) for x in (r["national_reg_no"], r["vat_number"])) if n}))
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


# WP-104: a division of a company is the company (it has no legal personality of its own): "Leonardo S.p.A. - Aircraft
# Division" and "Leonardo S.p.A. Divisione Sistemi di Difesa" state Leonardo's own number. Read only with one shared
# number: a name that merely begins with another is never enough.
_DIVISION = re.compile(r"\b(?:division|divisione|divisao|divisie|geschaftsbereich|sparte)\b")


def group_country(rows: list[Row]) -> str | None:
    """The one country of rows that are one company, or None when nothing decides it. WP-104: one company number under
    one name in two countries is a winner the notices of one country filed under that country. The country its legal
    form allows (`supplier_identity._FORM_COUNTRIES`: an s.r.o. is Czech or Slovak), else the one most of its award
    rows are under when they are more than all the others together (Pilatus Aircraft Ltd: 16 under CH, 3 under BG)."""
    countries = {("GB" if r.country == "UK" else r.country) for r in rows}
    if len(countries) == 1:
        return countries.pop()
    holders = [set(_FORM_COUNTRIES[f]) for r in rows for f in r.forms if f in _FORM_COUNTRIES]
    allowed = countries & set.intersection(*holders) if holders else countries
    if len(allowed) == 1:
        return allowed.pop()
    awards: dict[str, int] = defaultdict(int)
    for r in rows:
        c = "GB" if r.country == "UK" else r.country
        if c in (allowed or countries):
            awards[c] += r.awards
    top = max(awards, key=lambda c: awards[c])
    return top if awards[top] * 2 > sum(awards.values()) else None


def _division_of(a: Row, b: Row) -> bool:
    """One name is the other's followed by words that name a division."""
    short, long_ = sorted((a.key, b.key), key=len)
    return bool(short) and long_.startswith(short + " ") and bool(_DIVISION.search(long_[len(short):]))


def _stated_prefix(a: Row, b: Row) -> bool:
    """WP-104: one of the two has no number of its own, only numbers its award rows state, one of which the other holds,
    and its name begins with the other's ("NAVANTIA SISTEMAS", whose two award rows state A84076397, and NAVANTIA S.A.,
    S.M.E.). The name test keeps out the joint ventures that state a partner's number ("UTE NAVANTIA S.A. E INDRA"), and
    a name that goes on to name another company or a partnership is never taken: a legal form or a partnership word
    after the shared part ("JUMABEDA, S.L. CONST ... SL", "CLAYMORE Sp. z o.o. Sp. J", "STAR SAN DUO ... Sp. K."), or a
    joining sign or word the other name does not have ("SERANCO, S.A.U.- PRACE S.A.", "Seyntex-Sioen", "... & ...").
    ponytail: a name test, not a register; it leaves some spellings of one company apart rather than join two."""
    for x, y in ((a, b), (b, a)):
        if not x.own and x.numbers & y.numbers and y.key and x.key.startswith(y.key + " "):
            tail = x.key[len(y.key):].split()
            if any(w in _TAIL_STOP for w in tail):
                continue
            if any(ch in x.name and ch not in y.name for ch in "-&+/,"):
                continue
            if _JOINING.search(x.name.lower()) and not _JOINING.search(y.name.lower()):
                continue
            return True
    return False


_TAIL_STOP = _FORM_WORDS | {"s", "ute", "sp", "spolka", "sociedad", "soc", "coop", "partner", "partners", "j", "k",
                            "consorcio", "konsorcjum", "kft", "zrt", "korlatolt", "co", "kg"}
_JOINING = re.compile(r"\s(?:y|e|i|und|and|et|en)\s")


def _pair_conflict(a: Row, b: Row, it_keys: set[tuple[int, int]]) -> str | None:
    """Why two rows cannot be one company, or None: two numbers that cannot be one company's (the owner's rule: other
    numbers, other companies), or two legal-form classes (RENK AG / RENK GmbH). An Italian tax pair one stated name
    carries is not a conflict of numbers."""
    if _conflict(a.numbers, b.numbers) and (min(a.id, b.id), max(a.id, b.id)) not in it_keys:
        return "different_company_numbers"
    if a.forms and b.forms and not a.forms & b.forms:
        return "different_legal_forms"
    return None


def plan(rows: list[Row], apart: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    """The groups to merge ({head, members: [(id, method, confidence)], names}), the groups left alone by reason, and
    report lines for the Italian pairs that wait (two numbers under one name, not stated together).

    WP-104: the rows a rule joins are merged in two passes, numbers first, names second, and a join is made only where
    it cannot be wrong: two parts are joined when neither has, among the parts it is joined to in that pass, one it
    cannot be one company with (`_pair_conflict`). So one row whose number another number contradicts no longer keeps
    a whole group apart (Heckler & Koch: four rows stated with N0047964B stood apart because a fifth row carries
    another number), and a row without a number that two companies of one name could be (Rheinmetall Electronics GmbH,
    three VAT numbers) is joined to none of them. A part that ends with a conflict inside is left whole, as before."""
    by_id = {r.id: r for r in rows}
    edges: dict[tuple[int, int], str] = {}

    def join(a: Row, b: Row, method: str) -> None:
        k = (min(a.id, b.id), max(a.id, b.id))
        if k not in edges or METHODS[method] > METHODS[edges[k]]:
            edges[k] = method

    buckets: dict[tuple[str, str], list[Row]] = defaultdict(list)
    numbers: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        k = r.key
        if len(k) >= MIN_KEY and not k.isdigit() and not r.public:
            buckets[(r.country, fold_key(k))].append(r)
        for n in r.numbers:
            if not r.public:
                numbers[n].append(r)
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
    # WP-111: a name with the Irish eTenders reference TED carries after it ("Leonardo Spa_149684", as after the buyer's "Irish
    # Defence Forces_1144": `tenders.clean_buyer_name`) is the name without it, for a row that holds no number of its own
    # (a row with a number of its own stays apart as before: its number may be another company's)
    for r in rows:
        if r.public or r.numbers or not _PORTAL_SUFFIX.search(r.name):
            continue
        bare = core_key(_PORTAL_SUFFIX.sub("", r.name))
        if len(bare) < MIN_KEY:
            continue
        for b in buckets.get((r.country, fold_key(bare)), ()):
            if b.id != r.id and b.key == bare:
                join(r, b, "name_key_portal_suffix")
    for members in numbers.values():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if a.id == b.id:
                    continue
                # WP-104: one number in two countries only under one name key (Pilatus Aircraft Ltd, CH, and the same
                # company filed under Bulgaria by its Bulgarian notices, both stated with 15030004652)
                if a.country != b.country and (a.key != b.key or group_country([a, b]) is None):
                    continue
                if _names_agree(a, b):
                    join(a, b, "company_number")
                elif a.country == b.country and _division_of(a, b):
                    join(a, b, "company_number_division")
                elif a.country == b.country and _stated_prefix(a, b):
                    join(a, b, "stated_number_prefix")
    for rv in REVIEWED:
        heads = [r for r in rows if r.country == rv.country and rv.number in r.numbers and not r.public]
        if len(heads) == 1:
            for r in rows:
                if (r.country == rv.country and not r.numbers and not r.public
                        and stated_key(r.name) in rv.names):
                    join(heads[0], r, CURATED_REVIEW)
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

    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def members_of() -> dict[int, list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for x in by_id:
            out[find(x)].append(x)
        return out

    def clash(ids: list[int]) -> str | None:
        rs = [by_id[i] for i in ids]
        reasons = {_pair_conflict(a, b, it_keys) for i, a in enumerate(rs) for b in rs[i + 1:]} - {None}
        return min(reasons) if reasons else None     # numbers before forms

    for number_pass in (True, False):
        parts = members_of()
        links: dict[int, set[int]] = defaultdict(set)
        for (a, b), method in edges.items():
            if (method in NUMBER_METHODS) == number_pass:
                pa, pb = find(a), find(b)
                if pa != pb:
                    links[pa].add(pb)
                    links[pb].add(pa)
        safe = {p for p, near in links.items() if not clash([i for q in (p, *near) for i in parts[q]])}
        for p in sorted(links):
            for q in sorted(links[p]):
                if p in safe and q in safe:
                    parent[find(p)] = find(q)
    # what the joins left apart, by reason: each set of rows a rule links (every edge), once
    full: dict[int, int] = {}

    def find_full(x: int) -> int:
        while full.setdefault(x, x) != x:
            full[x] = full[full[x]]
            x = full[x]
        return x

    for a, b in edges:
        full[find_full(a)] = find_full(b)
    linked: dict[int, list[int]] = defaultdict(list)
    for x in full:
        linked[find_full(x)].append(x)
    for ids in linked.values():
        if (why := clash(ids)):
            left[why] += 1
            if apart is not None:
                # WP-111: every set left apart, with its evidence: the rows, their own numbers, the rule that linked them
                rs = sorted((by_id[i] for i in ids), key=lambda r: r.id)
                rules = sorted({m for k, m in edges.items() if k[0] in ids and k[1] in ids})
                apart.append(f"  apart {why} [{', '.join(rules)}]: " + " | ".join(
                    f"{r.id} {r.country} {r.name[:40]!r} {sorted(r.numbers) or 'no number'} {r.awards} awards" for r in rs))
    groups = []
    for ids in members_of().values():
        if len(ids) < 2 or clash(ids):    # a chain of safe joins that still meets a conflict: left whole
            continue
        if (country := group_country([by_id[i] for i in ids])) is None:
            left["countries_undecided"] += 1
            continue
        # the head is a row of the company's country (a row filed under another country is never the head)
        members = sorted((by_id[i] for i in ids),
                         key=lambda m: (("GB" if m.country == "UK" else m.country) != country, -m.awards,
                                        not m.numbers, m.id))
        head = members[0]
        joined = []
        for m in members[1:]:
            mine = [k for k in edges if m.id in k and k[0] in ids and k[1] in ids]
            # a pair only the stated name proves says so, whatever else joined it
            method = ("it_tax_pair" if any(k in it_keys for k in mine)
                      else max((edges[k] for k in mine), key=lambda x: METHODS[x]))
            joined.append((m.id, method, METHODS[method]))
        groups.append({"head": head.id, "members": joined, "names": [m.name for m in members],
                       "numbers": sorted({n for m in members for n in m.numbers}), "country": country,
                       # the rows filed under another country, corrected before the merge (`run`)
                       "recountry": sorted(m.id for m in members if m.country != country)})
    groups.sort(key=lambda g: (-len(g["members"]), g["head"]))
    return groups, dict(left), waiting


def run(conn, *, apply: bool = False, limit: int | None = None, out=print, sample: int = 40) -> dict[str, Any]:
    rows = load(conn)
    apart: list[str] = []
    groups, left, waiting = plan(rows, apart)
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
    # WP-104: every pair the write merges, exactly (head <- member, method, confidence)
    for g in groups:
        for oid, method, conf in g["members"]:
            out(f"  pair {g['head']} <- {oid} {method} {conf}")
        # WP-111: the evidence of the group, under its pairs
        out(f"    evidence {g['head']}: numbers {g['numbers'][:4]}; names " + " | ".join(n[:40] for n in g["names"]))
    for line in apart:
        out(line)
    for line in waiting[:sample]:
        out(line)
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return result
    started = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
    conn.commit()
    result["recountried"] = 0
    for g in groups[:limit]:
        for oid in g["recountry"]:
            # WP-104: the award rows of a row filed under another country move to the company's country first, recorded
            # as a correction (`organisation_country_fix`, basis `company_number_twin`); the row itself keeps the
            # country its notices stated. `--undo-batch` puts both back.
            old = conn.execute("SELECT btrim(country) AS c FROM organisation WHERE id = %s", (oid,)).fetchone()["c"]
            n = conn.execute("UPDATE award SET supplier_country = %s WHERE organisation_id = %s AND supplier_country = %s",
                             (g["country"], oid, old)).rowcount
            conn.execute("""INSERT INTO organisation_country_fix (org_id, old_country, new_country, basis, award_rows)
                            VALUES (%s, %s, %s, 'company_number_twin', %s)""", (oid, old, g["country"], n))
            result["recountried"] += 1
        for oid, method, conf in g["members"]:
            db.merge_organisations(conn, g["head"], oid, method=method, confidence=conf,
                                   evidence=next((rv.evidence for rv in REVIEWED if method == CURATED_REVIEW
                                                  and rv.number in g["numbers"]),
                                                 f"supplier rule {method}; numbers {g['numbers'][:4]}"),
                                   detected_by=DETECTED_BY, allow_identifier_conflict=True,
                                   allow_other_country=oid in g["recountry"])
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
    """Undo the merges of [start, end), then the country corrections the same run recorded (WP-104)."""
    from . import supplier_countries

    result = undo_merges.run(conn, apply=apply, start=start, end=end, methods=tuple(METHODS),
                             expected=None, detected_by=DETECTED_BY, out=out)
    result["countries_put_back"] = supplier_countries.undo(conn, start, end, apply=apply, out=out)
    return result


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
