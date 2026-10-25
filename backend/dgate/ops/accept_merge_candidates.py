"""Process the pending organisation merge candidates that a shared identifier proves (WP-72).

On 21 October 2026 164,827 candidate pairs were pending (QA audit, finding 1). Only one kind is
accepted here without a person: a pair found by a strong identifier, i.e. one organisation holds the
registration or tax number the notice states and the name the notice gives is filed under the other
(`resolve_organisation`, method `identifier`, confidence 0.97), and the stored confidence is at
least 0.97. Everything else stays `pending` for review: the 0.50 kinds say the identifier and the
name DISAGREE (`identifier_name_mismatch`, `same_name_different_identifier`), and a trigram or a
folded name is a resemblance, not a fact.

A pair, and the group it joins by shared members, is refused when anything contradicts it:

  * the two are already one organisation (an earlier merge)
  * different countries
  * two different registration numbers, VAT numbers or PICs anywhere in the group (bodies with
    different registration numbers are never merged: the owner's standing decision)
  * a row removed on request (suppressed) or marked as a natural person
  * a name that says one body acts for another ("per conto", "pour le compte", "im Auftrag" ...):
    the number is the agent's (`ACTING_FOR`)
  * either side is a public authority or a unit of one (`buyer_family.is_public_body`: the
    defence-buyer flag, `org_role` buyer, a public legal form, or a name of an administration or of
    a department, directorate, service ...): a regional government, a ministry or a city council
    files every department under one tax id, so the number proves one legal entity, not one buyer
    (WP-74: the run of 21 October 2026 merged 6,641 such rows and was undone by `ops.undo_merges`).
    With `--yes` such pairs are marked `rejected_public_units` and `ops.buyer_families` shows each
    connected set as one buyer under the parent body's name (rule `shared_tax_id`). Companies that
    share a VAT number, a registration number or a PIC are still merged.
    WP-76 widened the signals: the buyer role (the row publishes notices and no name of it states a
    company's legal form), identifiers shaped like a public body's (`buyer_family.PUBLIC_ID`: a
    French SIREN beginning 1 or 2, a Spanish NIF P/Q/S, an Italian codice fiscale 8/9, a Belgian
    enterprise number 02/03, a Swedish 2..., a Dutch government OIN, a German Leitweg-ID ...) and the
    vocabulary of every country held
  * the two rows state different legal forms (`different_legal_form`)
  * nothing but the number agrees (`no_second_signal`, WP-76): the names must be alike, or both
    rows state the same legal form and one name begins or ends the other (`agreement`)

The head of a group is the row with the most notices, then the one holding a PIC, then the
oldest. Each other row is merged with `db.merge_organisations`, which stores the method
(`identifier+name`, `identifier+legal_form` or `identifier+name+legal_form`: what agreed) and its
confidence (0.98 or 0.99) on the absorbed row, re-points aliases and notices,
and deletes nothing (the alias keeps `prev_organisation_id`). The group's candidate rows are marked
`merged`. Public bodies split by office id (BAAINBw: 67 rows, each with its own Leitweg-ID) are NOT
merged: different identifiers. The buyer list shows them as one buyer through the buyer families
(`ops.buyer_families`, rule `baainbw`); the dry run reports how many such rows a family covers.

    python -m dgate.ops.accept_merge_candidates                  # dry run: counts and 30 sampled pairs
    python -m dgate.ops.accept_merge_candidates --yes --limit 200 --sample 30   # one batch, then read it
    python -m dgate.ops.accept_merge_candidates --undo-batch FROM TO [--yes]     # undo a batch's window

WP-115: pairs of two rows that nothing references (no notice, award or participation) are skipped and stay
pending (`unlinked`); details are read 1,000 ids at a time; every statement stops after 60 s; a run merges at most 200
groups unless `--limit` says otherwise.

WP-129: `--ids-file PATH` takes the candidates a person reviewed instead (`run_reviewed`, `read_reviewed` for the
format), of any method. For those ids only the judgement rules are a person's (public body, acting for another,
short name, legal form, sister company, no second signal: the report counts what they would have said); the facts
still refuse: one organisation already, different countries, suppressed, a natural person, and two different numbers
of one kind in the group (two VAT numbers, two PICs, two NIPs, two REGONs; a NIP on one row and a REGON on the other is
one body's two registers and is merged). The head is the row named after the body, not a generic name ('zaklad
karny' beside 'zaklad karny we wronki'), then the most notices; a head column overrides. Each merge stores method
`person_review` and the reviewer's confidence (else the candidate's); every other pending candidate between rows that
are now one is marked `merged`; REJECT rows become `rejected` with the reviewer's reason after the evidence; UNSURE
rows stay pending. `--undo-batch` reverses such a batch too.

    python -m dgate.ops.accept_merge_candidates --ids-file decisions.csv          # report: groups, heads, refusals
    python -m dgate.ops.accept_merge_candidates --ids-file decisions.csv --yes    # merge, reject; prints the undo
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from .. import db, networks
from ..buyer_family import is_public_body
from ..config import settings
from ..resolution.names import key_of, legal_form_of
from . import buyer_families, undo_merges

log = logging.getLogger("accept_merge_candidates")

DETECTED_BY = "ops.accept_merge_candidates"
STRONG_METHODS = ("identifier",)
MIN_CONFIDENCE = 0.97
IDENTIFIERS = ("reg", "vat", "pic")
# WP-76: the merge methods this script writes (the plain 'identifier' of WP-72 and the two-signal
# ones); `--undo-batch` undoes any of them
MERGE_METHODS = ("identifier", "identifier+name", "identifier+legal_form", "identifier+name+legal_form", "person_review")
REVIEWED = "person_review"          # WP-129: a pair a person read and accepted (`--ids-file`)
DECISIONS = ("ACCEPT", "REJECT", "UNSURE")
# read on the production pairs of 22 October 2026: at 0.85 a typo, a hyphen, a dropped article or
# an added abbreviation still agree ('xestion do solo de galicia' / '.. xestur'); two units of one
# body whose names share only the body's abbreviation do not ('ssc iuc dji' / 'sic dji': 0.67)
NAME_SIMILARITY = 0.85

# A body that procures for another states its own number beside the other's name ("commune de
# Villefontaine represented by SARA", "SUA Provincia di Cosenza per conto del Comune ..."): the number
# then proves the agent, not that the two names are one body. 2 of the 30 pairs read by hand on
# 21 October 2026; such pairs wait for a person. Names are stored lower-case and unaccented.
ACTING_FOR = re.compile(
    r"\b(?:per conto|pour (?:le )?compte|repres(?:ente|entee)? par|au nom d|on behalf|im auftrag"
    r"|w imieniu|por cuenta|en (?:nombre|representacion)\b|c/o|mandatair"
    # WP-76, read on the accepted pairs of 22 October 2026: 'gse ggmbh vertreten durch die vea
    # beratungs-gmbh', 'agb boortmeerbeek bijgestaan door belfius bank', '.. c o inventura' (the
    # stored form of c/o), 'verdo varme a s pa vegne af ..', 'septalia maitrise d ouvrage deleguee
    # pour vilogia', 'obb- holding sowie die mit ihr ..' (a holding and its affiliates), and names
    # that list several bodies ('hlm des chalets et sccv le clos tolosan ..')
    r"|vertr?eten durch|bijgestaan door|\bnamens\b|\bc o\b|pa vegne a[fv]|pa uppdrag av"
    r"|ouvrage deleguee|\bagissant\b|sowie die mit ihr"
    r"|\b(?:et|und|og|och|en|y|and) (?:sccv|sci|sarl|sas|sa|gmbh|ag|as|ab|bv|nv|sl)\b"
    # Dutch "p.a." (per adres: care of; "p a ku leuven", "p a csg"), not the "s p a" of an Italian name
    r"|(?<!\bs )p a\b)", re.IGNORECASE)
# Norwegian and Danish "v/" or "ved" (by, care of) is stored as a lone "v": 'innkjopssamarbeidet i
# nord-gudbrandsdalen v abakus', 'holmegaarden ved h skjode knudsen'. Not elsewhere: a Czech or
# Slovak "v" is "in" ('nemocnice v praze').
# The words that tell the companies of one group apart: 'provas - haderslev forsyning a s' (the
# holding) and 'provas - haderslev forsyningsservice a s', 'verdo' and 'verdo holding',
# 'medfacilities' and 'medfacilities betrieb'. A group often states one number for all of them;
# when one name has such a word and the other not, the pair waits (`sister_company`).
SISTER = re.compile(r"holding|service|betrieb|drift|beteiligung|verwaltung|management|immobilien|netz")
ACTING_FOR_NORDIC = re.compile(r"\bv(?:ed)?\b(?= \w)")


def pending_by_method(conn) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT match_method, round(confidence, 2) AS confidence, count(*) AS n
             FROM organisation_merge_candidate WHERE status = 'pending'
            GROUP BY 1, 2 ORDER BY n DESC""").fetchall()]


_PAIRS = """SELECT c.id, c.match_method, c.confidence, c.evidence, c.status,
                   COALESCE(la.live_id, c.organisation_id) AS a,
                   COALESCE(lb.live_id, c.candidate_org_id) AS b
              FROM organisation_merge_candidate c
              LEFT JOIN organisation_merged_live la ON la.id = c.organisation_id
              LEFT JOIN organisation_merged_live lb ON lb.id = c.candidate_org_id
             WHERE {} ORDER BY c.id"""


def strong_pairs(conn) -> list[dict[str, Any]]:
    """The pending candidates of a strong method, with both ends taken to their live row."""
    return [dict(r) for r in conn.execute(
        _PAIRS.format("c.status = 'pending' AND c.match_method = ANY(%s) AND c.confidence >= %s"),
        (list(STRONG_METHODS), MIN_CONFIDENCE)).fetchall()]


def reviewed_pairs(conn, ids: list[int]) -> list[dict[str, Any]]:
    """WP-129: the candidates `ids`, of any method and status, with both ends taken to their live row."""
    return [dict(r) for r in conn.execute(_PAIRS.format("c.id = ANY(%s)"), (ids,)).fetchall()]


# WP-115: ids per detail query, and the longest any statement of this script may run. On 22-24 October 2026 one
# detail query over 5,000 ids ran 44 times at 5.5 min mean (12 min max) beside the site: it read every notice once
# per organisation (no index on opportunity.buyer_org_id over all notices until migration 0127).
CHUNK = 1000
STATEMENT_TIMEOUT = "60s"
DEFAULT_LIMIT = 200


def linked(conn, ids: set[int]) -> set[int]:
    """The rows of `ids` that something references: a notice (as its buyer), an award or a project participation.
    The others are 79 % of all organisations (24 October 2026: mostly buyers of notices the classifier did not
    keep, resolved before the notice was dropped). A pair of two such rows is skipped by the merge queue: merging
    them changes nothing a reader sees; the pair stays `pending`. A pair with one referenced row is decided as
    before (a public parent body that publishes nothing still heads its units' buyer family)."""
    out: set[int] = set()
    chunk = sorted(ids)
    for n in range(0, len(chunk), CHUNK):
        part = chunk[n:n + CHUNK]
        out.update(r["id"] for r in conn.execute(
            """SELECT g.id FROM unnest(%s::bigint[]) AS g(id)
                WHERE EXISTS (SELECT 1 FROM opportunity o WHERE o.buyer_org_id = g.id)
                   OR EXISTS (SELECT 1 FROM award a WHERE a.organisation_id = g.id)
                   OR EXISTS (SELECT 1 FROM participation p WHERE p.organisation_id = g.id)""",
            (part,)).fetchall())
    return out


def organisations(conn, ids: set[int]) -> dict[int, dict[str, Any]]:
    """The rows of `ids`, with what the rule reads: identifiers, flags, defence notices, whether
    the row publishes notices at all (`buys`), and up to five raw names of its aliases (they keep
    the legal form the stored name drops)."""
    out: dict[int, dict[str, Any]] = {}
    chunk = sorted(ids)
    for n in range(0, len(chunk), CHUNK):
        part = chunk[n:n + CHUNK]
        for r in conn.execute(
                """SELECT g.id, g.country, g.canonical_name AS name, g.display_name, g.suppressed,
                          g.individual_reason IS NOT NULL AS person,
                          g.is_defence_buyer, g.org_role, g.legal_form,
                          NULLIF(btrim(g.national_reg_no), '') AS reg,
                          NULLIF(upper(regexp_replace(coalesce(g.vat_number, ''), '[^A-Za-z0-9]', '', 'g')), '') AS vat,
                          NULLIF(btrim(g.eu_pic), '') AS pic,
                          (SELECT count(*) FROM opportunity o WHERE o.buyer_org_id = g.id AND o.is_defence) AS notices,
                          EXISTS (SELECT 1 FROM opportunity o WHERE o.buyer_org_id = g.id) AS buys,
                          ARRAY(SELECT a.raw_name FROM organisation_alias a
                                 WHERE a.organisation_id = g.id ORDER BY a.id LIMIT 5) AS raw_names
                     FROM organisation g WHERE g.id = ANY(%s)""", (part,)).fetchall():
            out[r["id"]] = dict(r)
    return out


def legal_forms(o: dict[str, Any]) -> set[str]:
    """The legal-form classes the row's names state (`resolution.names.legal_form_of`)."""
    names = (o.get("legal_form"), o.get("name"), o.get("display_name"), *(o.get("raw_names") or ()))
    return {f for f in map(legal_form_of, names) if f}


def name_similarity(a: str | None, b: str | None) -> float:
    """How alike two names are, 0..1: the ratio of `difflib` over the networks keys (legal forms,
    hyphens and transliteration folded), so 'secom - drobeta turnu severin' and 'secom
    drobeta-turnu severin' are 1.0."""
    ka, kb = key_of(a or "")[0], key_of(b or "")[0]
    if not ka or not kb:
        return 0.0
    return SequenceMatcher(None, ka, kb, autojunk=False).ratio()


# legal-form words a key can still carry inside it (key_of strips them only at its ends)
_FORM_WORDS = frozenset(
    "sa sl slu sau ab as oy oyj bv nv ag kg gmbh mbh spa srl sro spol aktiebolag aps ltd plc sas sarl"
    " doo ood eood ead ad".split())


# A name whose own part (without legal-form words and single letters) is shorter than this waits for a
# person: 'clk spol' / 'clk spol s r o' may be two firms of one short name (owner, 22 Oct 2026).
MIN_CORE_CHARS = 5


def _short_name(name: str | None) -> bool:
    core = [w for w in key_of(name or "")[0].split() if len(w) > 1 and w not in _FORM_WORDS]
    return len("".join(core)) < MIN_CORE_CHARS


def _long_form(a: str | None, b: str | None) -> bool:
    """One name is the other's long form: the longer key begins with the shorter and goes on with
    two words or more that name nothing else ('enbw' / 'enbw energie baden-wurttemberg', 'ebn' / 'ebn
    energie beheer nederland'), or it is the same name written twice. Read on the 275 such pairs
    accepted on production (22 October 2026), these are NOT long forms and wait:
      one more word        a sister company ('verdo' / 'verdo holding', 'bitmarck' / '.. service',
                           'medfacilities' / '.. betrieb', 'femern' / 'femern landanlaeg')
      the name repeated    a list of companies ('50hertz transmission 50hertz offshore 50hertz ..')
      a legal form inside  a list of bodies ('sonderborg forsyningsservice a s nordals fjernvarme')
      words in front       an agent or a parent ('holmegaarden ved ..', 'consejero delegado de ..',
                           'energinet gas storage denmark')"""
    ka, kb = sorted((key_of(a or "")[0], key_of(b or "")[0]), key=len)
    if not ka:
        return False
    short = ka.split()
    if kb == ka or kb == f"{ka} {ka}":
        return True
    if not kb.startswith(ka + " "):
        return False
    rest = kb[len(ka):].split()
    while rest and rest[-1] in _FORM_WORDS:
        rest.pop()
    if not rest:
        return True
    if set(rest) & (set(short) | _FORM_WORDS):
        return False
    return len(rest) >= 2


def agreement(a: dict[str, Any], b: dict[str, Any]) -> tuple[str, float] | None:
    """What agrees with the shared identifier besides it: the merge method and its confidence, or
    None (the pair then waits). A shared number alone is not enough (WP-76: 2 of 30 sampled
    accepted pairs were two units of one Dutch government body):

      name        the names are alike (`name_similarity` >= NAME_SIMILARITY)
      legal_form  both rows state one and the same legal form, e.g. both B.V., and one name is
                  the other's long form (`_long_form`). A shared word is not enough: two
                  companies of one municipal group are both GmbH and both 'hamm'
                  ('verkehrsbetrieb hamm' / 'energie- und wasserversorgung hamm')

    Each agreeing signal adds 0.01 to the identifier's 0.97. The city or postcode would be a third
    signal; no table holds either (organisation stores no address), so it is not used."""
    signals = []
    if name_similarity(a["name"], b["name"]) >= NAME_SIMILARITY:
        signals.append("name")
    fa, fb = legal_forms(a), legal_forms(b)
    if fa and fa == fb and _long_form(a["name"], b["name"]):
        signals.append("legal_form")
    if not signals:
        return None
    return "+".join(("identifier", *signals)), round(MIN_CONFIDENCE + 0.01 * len(signals), 2)


def _pair_refusal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> str | None:
    if a is None or b is None:
        return "unknown_organisation"
    if a["id"] == b["id"]:
        return "already_one"
    if a["country"] != b["country"]:
        return "different_countries"
    if a["suppressed"] or b["suppressed"]:
        return "suppressed"
    if a["person"] or b["person"]:
        return "natural_person"
    if ACTING_FOR.search(a["name"] or "") or ACTING_FOR.search(b["name"] or ""):
        return "acting_for_another_body"
    if a["country"] in ("NO", "DK") and (ACTING_FOR_NORDIC.search(a["name"] or "")
                                         or ACTING_FOR_NORDIC.search(b["name"] or "")):
        return "acting_for_another_body"
    for k in IDENTIFIERS:
        if a[k] and b[k] and a[k] != b[k]:
            return f"different_{k}"
    if _public(a) or _public(b):
        return "public_body"
    if _short_name(a["name"]) or _short_name(b["name"]):
        return "short_name"
    fa, fb = legal_forms(a), legal_forms(b)
    if fa and fb and not fa & fb:
        # 'sci tertiaire mixte' / 'sas tertiaire mixte' under one SIRET: two forms are two bodies
        # unless a person reads the register (WP-41)
        return "different_legal_form"
    if set(SISTER.findall(a["name"] or "")) != set(SISTER.findall(b["name"] or "")):
        return "sister_company"
    if agreement(a, b) is None:
        return "no_second_signal"
    return None


def _public(o: dict[str, Any]) -> bool:
    return is_public_body(o["name"], o["country"], legal_form=o.get("legal_form"),
                          org_role=o.get("org_role"), defence_buyer=bool(o.get("is_defence_buyer")),
                          buys=bool(o.get("buys")), company_form=bool(legal_forms(o)),
                          identifiers=(o.get("reg"), o.get("vat")))


def _components(pairs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """The pairs grouped by shared members (union-find over their ends `a` and `b`)."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        parent[find(p["a"])] = find(p["b"])
    by_root: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        by_root[find(p["a"])].append(p)
    return list(by_root.values())


def plan(pairs: list[dict[str, Any]], orgs: dict[int, dict[str, Any]]
         ) -> tuple[list[dict[str, Any]], Counter[str]]:
    """The groups to merge ({head, members, candidates, confidence}) and the refusals by reason."""
    refused: Counter[str] = Counter()
    kept: list[dict[str, Any]] = []
    for p in pairs:
        why = _pair_refusal(orgs.get(p["a"]), orgs.get(p["b"]))
        if why:
            refused[why] += 1
            continue
        p = {**p}
        p["method"], p["merge_confidence"] = agreement(orgs[p["a"]], orgs[p["b"]])  # type: ignore[misc]
        kept.append(p)
    groups: list[dict[str, Any]] = []
    for cands in _components(kept):
        ids = sorted({i for p in cands for i in (p["a"], p["b"])})
        rows = [orgs[i] for i in ids]
        clash = next((k for k in IDENTIFIERS if len({r[k] for r in rows if r[k]}) > 1), None)
        if clash:
            refused[f"group_different_{clash}"] += len(cands)
            continue
        head = min(rows, key=lambda r: (-r["notices"], r["pic"] is None, r["id"]))
        groups.append({"head": head["id"], "members": [i for i in ids if i != head["id"]],
                       "candidates": cands,
                       "confidence": float(min(p["merge_confidence"] for p in cands))})
    groups.sort(key=lambda g: (-len(g["members"]), g["head"]))
    return groups, refused


def office_splits(conn) -> dict[str, int]:
    """Live rows of one country and one folded name that carry different registration numbers
    (BAAINBw: 67, one per office), and how many of those holding defence notices a buyer family
    shows as one buyer. Never merged: a display question, answered by `ops.buyer_families`."""
    r = conn.execute(
        """WITH g AS (
               SELECT country, dg_fold(canonical_name) AS k
                 FROM organisation WHERE merged_into IS NULL AND national_reg_no IS NOT NULL
                GROUP BY 1, 2 HAVING count(DISTINCT national_reg_no) > 1),
           m AS (
               SELECT o.id,
                      EXISTS (SELECT 1 FROM opportunity x WHERE x.buyer_org_id = o.id AND x.is_defence) AS buys,
                      EXISTS (SELECT 1 FROM buyer_family_member f
                               WHERE f.org_id = o.id OR f.head_org_id = o.id) AS in_family
                 FROM organisation o JOIN g ON g.country = o.country AND g.k = dg_fold(o.canonical_name)
                WHERE o.merged_into IS NULL)
           SELECT (SELECT count(*) FROM g) AS groups, count(*) AS rows,
                  count(*) FILTER (WHERE buys) AS buying_rows,
                  count(*) FILTER (WHERE buys AND in_family) AS buying_rows_in_a_family
             FROM m""").fetchone()
    return dict(r)


def sample_pairs(groups: list[dict[str, Any]], orgs: dict[int, dict[str, Any]],
                 n: int = 30) -> list[dict[str, Any]]:
    """`n` accepted pairs, spread by a hash of the candidate id (the same sample on every run)."""
    cands = [(g, p) for g in groups for p in g["candidates"]]
    cands.sort(key=lambda gp: hashlib.sha1(str(gp[1]["id"]).encode()).hexdigest())
    out = []
    for g, p in cands[:n]:
        a, b = orgs[p["a"]], orgs[p["b"]]
        out.append({"candidate": p["id"], "country": a["country"], "head": g["head"],
                    "method": p.get("method"), "confidence": p.get("merge_confidence"),
                    "a": (a["id"], a["name"], a["reg"] or a["vat"] or a["pic"]),
                    "b": (b["id"], b["name"], b["reg"] or b["vat"] or b["pic"]),
                    "evidence": p["evidence"]})
    return out


def run(conn, *, apply: bool = False, limit: int | None = None, sample: int = 30,
        with_office_splits: bool = True, out=print) -> dict[str, Any]:
    pending = pending_by_method(conn)
    out("pending candidates by method: " + ", ".join(
        f"{r['match_method']}@{r['confidence']} {r['n']}" for r in pending))
    conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
    pairs = strong_pairs(conn)
    strong = len(pairs)
    used = linked(conn, {i for p in pairs for i in (p["a"], p["b"])})
    unlinked = [p for p in pairs if p["a"] not in used and p["b"] not in used]
    pairs = [p for p in pairs if p["a"] in used or p["b"] in used]
    orgs = organisations(conn, {i for p in pairs for i in (p["a"], p["b"])})
    groups, refused = plan(pairs, orgs)
    if unlinked:
        refused["unlinked"] = len(unlinked)
    result: dict[str, Any] = {
        "pending": sum(r["n"] for r in pending), "strong_candidates": strong,
        "accepted_candidates": sum(len(g["candidates"]) for g in groups),
        "groups": len(groups), "rows_to_merge": sum(len(g["members"]) for g in groups),
        "refused": dict(refused), "merged": 0}
    out(f"strong candidates ({'/'.join(STRONG_METHODS)} >= {MIN_CONFIDENCE}): {strong}; accepted "
        f"{result['accepted_candidates']} in {len(groups)} groups ({result['rows_to_merge']} rows to "
        f"merge); refused {dict(refused)}")
    public = [p for p in pairs
              if _pair_refusal(orgs.get(p["a"]), orgs.get(p["b"])) == "public_body"]
    result["families"] = buyer_families.run(
        conn, write=False, extra_pairs=[(p["a"], p["b"]) for p in public])
    result["left_pending"] = sum(refused.values()) - len(public)
    out(f"public-body pairs (never merged, shown as buyer families): {len(public)}; buyer families "
        f"once they are: {result['families']}; left pending for a person: {result['left_pending']}")
    result["public_sample"] = [
        {"candidate": p["id"], "a": (p["a"], orgs[p["a"]]["name"]), "b": (p["b"], orgs[p["b"]]["name"])}
        for p in sorted(public, key=lambda p: hashlib.sha1(str(p["id"]).encode()).hexdigest())[:sample]]
    for s in result["public_sample"]:
        out(f"  public #{s['candidate']}: {s['a'][0]} {s['a'][1][:50]!r} ~ {s['b'][0]} {s['b'][1][:50]!r}")
    result["sample"] = sample_pairs(groups, orgs, sample)
    for s in result["sample"]:
        out(f"  #{s['candidate']} {s['country']} head {s['head']}: {s['a'][0]} {s['a'][1][:45]!r} "
            f"[{s['a'][2]}] ~ {s['b'][0]} {s['b'][1][:45]!r} [{s['b'][2]}]")
    if with_office_splits:
        result["office_splits"] = office_splits(conn)
        out(f"same name, different registration numbers (never merged): {result['office_splits']}")
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return result
    conn.execute(
        """UPDATE organisation_merge_candidate SET status = 'rejected_public_units', decided_at = now()
            WHERE id = ANY(%s) AND status = 'pending'""", ([p["id"] for p in public],))
    conn.commit()
    result["rejected_public_units"] = len(public)
    batch = groups[:limit]
    started = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    for g in batch:
        for member in g["members"]:
            # the pair that joined this member: its method (which signals agreed) and confidence
            p = next(p for p in g["candidates"] if member in (p["a"], p["b"]))
            db.merge_organisations(
                conn, g["head"], member, method=p["method"], confidence=p["merge_confidence"],
                evidence=f"{p['evidence']}; agreeing: {p['method'].split('+', 1)[1]}",
                detected_by=DETECTED_BY)
            result["merged"] += 1
        conn.execute(
            """UPDATE organisation_merge_candidate SET status = 'merged', decided_at = now()
                WHERE id = ANY(%s) AND status = 'pending'""", ([p["id"] for p in g["candidates"]],))
        conn.commit()
    ended = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    result["batch_window"] = (started.isoformat(), ended.isoformat())
    result["families_written"] = buyer_families.run(conn, write=True)
    result["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"merged {result['merged']} rows in {len(batch)} groups; "
        f"{len(groups) - len(batch)} accepted groups left for the next batch")
    result["batch_sample"] = sample_pairs(batch, orgs, sample)
    out(f"{len(result['batch_sample'])} sampled merged pairs of this batch (read them before the next):")
    for s in result["batch_sample"]:
        out(f"  #{s['candidate']} {s['country']} {s['method']} {s['confidence']} head {s['head']}: "
            f"{s['a'][0]} {s['a'][1][:45]!r} ~ {s['b'][0]} {s['b'][1][:45]!r} [{s['a'][2] or s['b'][2]}]")
    out(f"to undo this batch: python -m dgate.ops.accept_merge_candidates --undo-batch "
        f"'{started.isoformat()}' '{ended.isoformat()}' [--yes]")
    return result


# ----------------------------------------------------------------------------- WP-129: a person's review

def read_reviewed(path: str) -> dict[int, dict[str, Any]]:
    """The candidates of an ids file, by candidate id: {decision, head, confidence, reason}.

    CSV, one candidate per line; blank lines and lines beginning with '#' are skipped. Without a header line each
    line is `candidate_id[,head_org_id]`, every one ACCEPT. With one (its first cell is no number, e.g. the reviewer's
    decisions.csv as it is) the columns read are `candidate_id` and, when present, `decision` (ACCEPT, REJECT or
    UNSURE; empty is ACCEPT), `head` (an organisation id), `confidence` (0..1) and `evidence` or `reason`.
    `-` reads standard input (`docker compose run -T worker ... --ids-file - < decisions.csv`)."""
    with (open(path, newline="", encoding="utf-8-sig") if path != "-" else sys.stdin) as f:
        rows = [r for r in csv.reader(f) if r and r[0].strip() and not r[0].lstrip().startswith("#")]
    if rows:
        rows[0][0] = rows[0][0].lstrip("﻿")            # a byte-order mark on standard input
    cols =(["candidate_id", "head"] if not rows or rows[0][0].strip().isdigit()
            else [c.strip().lower() for c in rows.pop(0)])
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        d = {k: v.strip() for k, v in zip(cols, r, strict=False)}
        decision = (d.get("decision") or "ACCEPT").upper()
        conf = float(d["confidence"]) if d.get("confidence") else None
        if decision not in DECISIONS or (conf is not None and not 0 < conf <= 1):
            raise ValueError(f"candidate {d['candidate_id']}: decision {decision!r} / confidence {conf} not allowed")
        out[int(d["candidate_id"])] = {"decision": decision, "head": int(d["head"]) if d.get("head") else None,
                                       "confidence": conf, "reason": d.get("evidence") or d.get("reason") or ""}
    return out


def number_kinds(o: dict[str, Any]) -> list[tuple[str, str]]:
    """The row's numbers as (kind, value): a Polish registration number by its register (NIP, KRS written with its
    leading zeros, REGON of 9 or 14 digits) and a Polish VAT number as the NIP it is; elsewhere one kind per column."""
    out = []
    reg, vat, pl = o.get("reg"), o.get("vat"), o["country"] == "PL"
    if reg:
        kind = "reg"
        if pl and reg.isdigit():
            kind = {9: "regon", 14: "regon", 10: "krs" if reg.startswith("000") else "nip"}.get(len(reg), "reg")
        out.append((kind, reg))
    if vat:
        v = vat.removeprefix("PL") if pl else vat
        out.append(("nip" if pl and len(v) == 10 and v.isdigit() else "vat", v))
    if o.get("pic"):
        out.append(("pic", o["pic"]))
    return out


def _number_clash(rows: list[dict[str, Any]]) -> str | None:
    """Two different numbers of one kind among `rows` (two bodies: the owner's rule), as `different_<kind>`."""
    seen: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        for kind, value in number_kinds(r):
            seen[kind].add(value)
    return next((f"different_{k}" for k, v in sorted(seen.items()) if len(v) > 1), None)


def _fact_refusal(a: dict[str, Any] | None, b: dict[str, Any] | None) -> str | None:
    """What refuses a reviewed pair: the facts a person's reading cannot change."""
    if a is None or b is None:
        return "unknown_organisation"
    if a["id"] == b["id"]:
        return "already_one"
    if a["country"] != b["country"]:
        return "different_countries"
    if a["suppressed"] or b["suppressed"]:
        return "suppressed"
    if a["person"] or b["person"]:
        return "natural_person"
    return _number_clash([a, b])


def _generic(o: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    """A name that is no one body's: one more than one public body bears (`org_repair.ambiguous_name`), or another
    row's name without its place ('zaklad karny' beside 'zaklad karny we wronki')."""
    # imported here: org_repair imports supplier_dedupe, which imports this module
    from .org_repair import ambiguous_name
    n = o["name"] or ""
    return ambiguous_name(o["country"], n) or any(
        (r["name"] or "").startswith(f"{n} {p} ") for r in rows if r is not o for p in ("w", "we"))


def plan_reviewed(pairs: list[dict[str, Any]], orgs: dict[int, dict[str, Any]], reviewed: dict[int, dict[str, Any]]
                  ) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    """The groups of the ACCEPT pairs ({head, members, candidates, confidence}), the refusals by reason, and what the
    judgement rules of `_pair_refusal` would have said of the accepted pairs (the review decided instead)."""
    refused: Counter[str] = Counter()
    overridden: Counter[str] = Counter()
    kept = []
    for p in pairs:
        r = reviewed.get(p["id"])
        if r is None or r["decision"] != "ACCEPT":
            continue
        why = "not_pending" if p["status"] != "pending" else _fact_refusal(orgs.get(p["a"]), orgs.get(p["b"]))
        if why:
            refused[why] += 1
            continue
        overridden[_pair_refusal(orgs[p["a"]], orgs[p["b"]]) or "none"] += 1
        kept.append({**p, "method": REVIEWED, "merge_confidence": r["confidence"] or float(p["confidence"]),
                     "review": r["reason"], "head_hint": r["head"]})
    groups = []
    for cands in _components(kept):
        ids = sorted({i for p in cands for i in (p["a"], p["b"])})
        rows = [orgs[i] for i in ids]
        clash = _number_clash(rows)
        hints = {p["head_hint"] for p in cands if p["head_hint"]}
        if clash or len(hints) > 1 or not hints <= set(ids):
            refused[f"group_{clash}" if clash else "head_not_in_group"] += len(cands)
            continue
        head = hints.pop() if hints else min(
            rows, key=lambda r: (_generic(r, rows), -r["notices"], r["reg"] is None, r["pic"] is None, r["id"]))["id"]
        groups.append({"head": head, "members": [i for i in ids if i != head], "candidates": cands,
                       "confidence": min(p["merge_confidence"] for p in cands)})
    groups.sort(key=lambda g: (-len(g["members"]), g["head"]))
    return groups, refused, overridden


def _pending_between(conn, ids: list[int]) -> list[int]:
    """The pending candidates between two of the live rows `ids` (either end may be a row merged into one): one
    organisation once `ids` are. A stale one between a live row and a row already merged into it is not touched."""
    live = {i: i for i in ids} | {r["id"]: r["merged_into"] for r in conn.execute(
        "SELECT id, merged_into FROM organisation WHERE merged_into = ANY(%s)", (ids,)).fetchall()}
    return [r["id"] for r in conn.execute(
        """SELECT id, organisation_id AS a, candidate_org_id AS b FROM organisation_merge_candidate
            WHERE status = 'pending' AND organisation_id = ANY(%s) AND candidate_org_id = ANY(%s)""",
        (list(live), list(live))).fetchall() if live[r["a"]] != live[r["b"]]]


def run_reviewed(conn, reviewed: dict[int, dict[str, Any]], *, apply: bool = False, limit: int | None = None,
                 out=print) -> dict[str, Any]:
    """WP-129: merge the ACCEPT candidates of a person's review, reject the REJECT ones, leave UNSURE pending."""
    conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
    pairs = reviewed_pairs(conn, sorted(reviewed))
    orgs = organisations(conn, {i for p in pairs for i in (p["a"], p["b"])})
    groups, refused, overridden = plan_reviewed(pairs, orgs, reviewed)
    if missing := set(reviewed) - {p["id"] for p in pairs}:
        refused["unknown_candidate"] = len(missing)
    by = {d: [p for p in pairs if reviewed[p["id"]]["decision"] == d] for d in DECISIONS}
    rejects = [p for p in by["REJECT"] if p["status"] == "pending"]
    for g in groups:
        g["between"] = _pending_between(conn, [g["head"], *g["members"]])
    res: dict[str, Any] = {
        "reviewed": {d: len(v) for d, v in by.items()}, "groups": len(groups),
        "accepted_candidates": sum(len(g["candidates"]) for g in groups),
        "rows_to_merge": sum(len(g["members"]) for g in groups), "refused": dict(refused),
        "judgement_rules_overridden": dict(overridden),
        "other_candidates_to_merged": sum(len(g["between"]) - len(g["candidates"]) for g in groups),
        "to_reject": len(rejects), "unsure_left_pending": len(by["UNSURE"]), "merged": 0,
        "heads": [(g["head"], g["members"]) for g in groups]}
    out(f"reviewed {res['reviewed']}: {res['accepted_candidates']} accepted in {len(groups)} groups "
        f"({res['rows_to_merge']} rows to merge); refused {res['refused']}; the review decided where the rules said "
        f"{res['judgement_rules_overridden']}; other pending candidates of those pairs to merged "
        f"{res['other_candidates_to_merged']}; to reject {len(rejects)}; unsure left pending {len(by['UNSURE'])}")
    for g in groups:
        out(f"  head {g['head']} {str(orgs[g['head']]['name'])[:60]!r} <- " + ", ".join(
            f"{m} {str(orgs[m]['name'])[:40]!r}" for m in g["members"]) +
            f" (candidates {[p['id'] for p in g['candidates']]})")
    if not apply:
        conn.rollback()
        out("dry run: nothing written (add --yes)")
        return res
    batch = groups[:limit]
    started = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    for g in batch:
        for member in g["members"]:
            p = next(p for p in g["candidates"] if member in (p["a"], p["b"]))
            # the plan refused any group with two numbers of one kind: a number beside another is of another kind
            db.merge_organisations(
                conn, g["head"], member, method=REVIEWED, confidence=p["merge_confidence"],
                evidence=f"candidate {p['id']} ({p['match_method']}): {p['evidence']}; accepted by a person's review: "
                         f"{p['review']}", detected_by=DETECTED_BY, allow_identifier_conflict=True)
            res["merged"] += 1
        conn.execute("""UPDATE organisation_merge_candidate SET status = 'merged', decided_at = now()
                         WHERE id = ANY(%s) AND status = 'pending'""", (g["between"],))
        conn.commit()
    for p in rejects:
        conn.execute("""UPDATE organisation_merge_candidate SET status = 'rejected', decided_at = now(),
                               evidence = evidence || %s WHERE id = %s AND status = 'pending'""",
                     (f" | rejected by a person's review: {reviewed[p['id']]['reason']}", p["id"]))
    ended = conn.execute("SELECT now() AS t").fetchone()["t"]
    conn.commit()
    res["rejected"] = len(rejects)
    res["batch_window"] = (started.isoformat(), ended.isoformat())
    res["families_written"] = buyer_families.run(conn, write=True)
    res["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"merged {res['merged']} rows in {len(batch)} groups ({len(groups) - len(batch)} left for the next run); "
        f"rejected {len(rejects)}")
    out(f"to undo the merges: python -m dgate.ops.accept_merge_candidates --undo-batch "
        f"'{started.isoformat()}' '{ended.isoformat()}' [--yes]")
    return res


def undo_batch(conn, start: str, end: str, *, apply: bool = False, out=print) -> dict[str, Any]:
    """Undo every merge this script wrote between `start` and `end` (`ops.undo_merges`, WP-74's
    logic, for any window and any of MERGE_METHODS; no expected count: the window is the batch).
    WP-129: the candidates of other methods a reviewed merge marked `merged` (between rows it made one) go back to
    pending too; rejections stay (a person's decision, not a merge)."""
    rows = undo_merges.batch(conn, start, end, MERGE_METHODS)
    ids = sorted({i for r in rows for i in (r["id"], r["head"])})
    ids += [r["id"] for r in conn.execute("SELECT id FROM organisation WHERE merged_into = ANY(%s)", (ids,)).fetchall()]
    others = [r["id"] for r in conn.execute(
        """SELECT id FROM organisation_merge_candidate
            WHERE status = 'merged' AND decided_at >= %s AND decided_at < %s AND NOT (match_method = ANY(%s))
              AND organisation_id = ANY(%s) AND candidate_org_id = ANY(%s)""",
        (start, end, list(MERGE_METHODS), ids, ids)).fetchall()]
    res = undo_merges.run(conn, apply=apply, start=start, end=end, methods=MERGE_METHODS, expected=None, out=out)
    res["other_candidates_pending"] = len(others)
    out(f"candidates of other methods back to pending: {len(others)}")
    if apply and others:
        conn.execute("""UPDATE organisation_merge_candidate SET status = 'pending', decided_at = NULL
                         WHERE id = ANY(%s) AND status = 'merged'""", (others,))
        conn.commit()
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="merge; without it nothing changes")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help="merge at most this many groups (the largest first, default %(default)s); run again "
                        "for the next batch")
    p.add_argument("--sample", type=int, default=30,
                   help="how many pairs to print: accepted (dry run) or merged in this batch (--yes)")
    p.add_argument("--no-office-splits", action="store_true",
                   help="skip the report on same-name rows with different numbers (a full scan)")
    p.add_argument("--undo-batch", nargs=2, metavar=("FROM", "TO"),
                   help="undo the merges this script wrote in [FROM, TO) (timestamps with zone); "
                        "dry run unless --yes")
    p.add_argument("--ids-file", metavar="PATH",
                   help="WP-129: decide the candidates a person reviewed (CSV, see read_reviewed) instead")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        if a.undo_batch:
            undo_batch(conn, *a.undo_batch, apply=a.yes)
        elif a.ids_file:
            run_reviewed(conn, read_reviewed(a.ids_file), apply=a.yes, limit=a.limit)
        else:
            run(conn, apply=a.yes, limit=a.limit, sample=a.sample,
                with_office_splits=not a.no_office_splits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
