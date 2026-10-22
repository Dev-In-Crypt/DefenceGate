"""The demand map of the supplier report (WP-66): who in defence buys what a company makes.

    POST /v1/readiness/demand    {"cpv": ["34300000", ...], "countries": ["ES", ...]}

Stateless, like `/v1/readiness/assess`: the request carries the CPV codes and the countries, the answer is
computed and returned, and nothing of it is stored, cached or logged. The codes say what a company makes, so
they are treated as private; a refused request is not echoed back (`api._validation_error`).

For each country, over the last three years, the defence-scope notices (`is_defence`, not removed on request)
with a code under one of the chosen codes, matched by the code's own level: 34300000 is the group 343, so
34352100 is in it; 44470000 is the class 4447; 35000000 the whole division 35 (`prefix`, index
`opp_cpv_heads`, migration 0099). Counted:

- procurements: a procurement published in several notices (TED and a national portal, a TED notice and its
  corrigendum, the two Polish sources of one notice) counts once (`KEY`);
- how many name Directive 2009/81/EC as their legal basis (`sig_legal_basis`);
- buyers, as buyer families (`dgate_buyer_head`), split into core defence buyers (on the curated defence-buyer
  list, or of class `defence`: ministries, armed forces, procurement agencies) and the other defence-scope
  buyers (police, security, other public bodies);
- procurements with a published winner, and the winners: legal entities only (a winner the directory treats as
  a natural person, or a winner string that is no supplier, is never counted or named), from TED result
  notices, and from PLACSP's award results only while DGATE_PLACSP_AWARDS_PUBLIC is on (the supplier map's
  switch, `suppliers.py`). The mosaic rule: a winner is named only with at least `K_MIN` procurements in the
  answer; the rest are one aggregate count.

Who to approach (WP-80, `approach`): the same winners across the countries asked, each named only with at least `K_MIN`
procurements in the answer (the rest one count), most contracts first: how many, the value a TED result notice states for a contract
with this one winner (PLACSP states the call's estimate, so it adds none), the buyers they win from most, the countries, the newest
notice's publication date (PLACSP: the procurement's, the award date is not stored), a link to the supplier page where one exists, the EDF projects, and the mark "prime contractor or large defence group"
from the curated, sourced list `PRIMES`. An award TED and PLACSP both publish counts once (`award_twin_set`), here and in the
per-country winners.

What it is not: the sub-tier needs of prime contractors are not published, and TED holds about a tenth of EU
defence spending; the coverage line says so on every answer.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .classify import DEFENCE_PROGRAMMES
from .config import settings
from .funding import get_conn, make_slug
from .normalise import PLACEHOLDER_AMOUNT_MAX, redact_emails
from .suppliers import FROM as SUPPLIER_FROM
from .suppliers import K_MIN, PLACSP_SOURCES, TED_NOTE, placsp_note
from .suppliers import scope as supplier_scope
from .tenders import _day, clean_buyer_name

router = APIRouter()

COUNTRIES = ("ES", "DE", "FR", "PL", "NL")
MAX_CODES = 15
YEARS = 3
TOP_BUYERS = 10
TOP_WINNERS = 10
LATEST = 5
WINNER_NOTICES = 3
APPROACH = 30                  # winners listed under "who to approach"; a prime or large defence group is never cut
APPROACH_BUYERS = 3
CODE = re.compile(r"^[0-9]{8}$")

# WP-80: the prime contractors and large defence groups a winner is marked as, by its normalised name
# (`organisation.canonical_name`: lower case, accents folded, legal form taken off). The European companies of the SIPRI
# Top 100 arms-producing and military services companies of 2024 (SIPRI fact sheet, December 2025; ThyssenKrupp as its
# naval arm only, General Dynamics as its European land arm GDELS), and Indra, which ran a supplier selection for
# automotive firms in 2026. A name match marks a group member that carries the group's name; a subsidiary under another
# name is not marked. `ponytail:` a curated list read by name, not an ownership register; extend it with a source.
SIPRI = ("SIPRI Top 100 arms-producing and military services companies, 2024 (fact sheet, December 2025)",
         "https://www.sipri.org/publications/2025/sipri-fact-sheets/sipri-top-100-arms-producing-and-military-services-companies-2024")
PRIMES: tuple[tuple[str, str, tuple[str, str]], ...] = (
    ("BAE Systems", r"\bbae systems\b", SIPRI),
    ("Airbus", r"\bairbus\b", SIPRI),
    ("Leonardo", r"^leonardo\b(?!.*\bhotel)", SIPRI),
    ("Thales", r"\bthales\b", SIPRI),
    ("Rheinmetall", r"\brheinmetall\b", SIPRI),
    ("Rolls-Royce", r"\brolls royce\b(?!.*\bmotor cars\b)", SIPRI),
    ("Saab", r"^saab\b(?!.*\bautomobile)", SIPRI),
    ("Safran", r"\bsafran\b", SIPRI),
    ("MBDA", r"\bmbda\b", SIPRI),
    ("Naval Group", r"\bnaval group\b", SIPRI),
    ("Babcock International", r"^babcock (international|integrated|mission)\b", SIPRI),
    ("Dassault Aviation", r"\bdassault aviation\b", SIPRI),
    ("KNDS", r"\bknds\b|\bkrauss maffei wegmann\b|^nexter\b",
     ("KNDS in the SIPRI Top 100, 2024: the group of Krauss-Maffei Wegmann and Nexter (KNDS Deutschland, KNDS France)",
      SIPRI[1])),
    ("Czechoslovak Group", r"\bczechoslovak group\b", SIPRI),
    ("PGZ (Polska Grupa Zbrojeniowa)", r"^pgz\b|\bpolska grupa zbrojeniowa\b", SIPRI),
    ("Fincantieri", r"\bfincantieri\b", SIPRI),
    ("ThyssenKrupp Marine Systems", r"\bthyssenkrupp marine systems\b", SIPRI),
    ("Hensoldt", r"\bhensoldt\b", SIPRI),
    ("Diehl", r"^diehl\b", SIPRI),
    ("Kongsberg", r"^kongsberg\b(?!.*\bautomotive\b)", SIPRI),
    ("Navantia", r"\bnavantia\b", SIPRI),
    ("General Dynamics (GDELS)", r"\bgeneral dynamics european land systems\b|^santa barbara sistemas\b",
     ("General Dynamics in the SIPRI Top 100, 2024; Santa Bárbara Sistemas as a GDELS company (FEINDEF exhibitor page)",
      "https://www.feindef.com/index.php/en/ficha-gdels-santa-barbara-sistemas-en")),
    ("Indra", r"\bindra\b",
     ("Indra's 2026 supplier selection for automotive firms (elDiario.es, 16 June 2026)",
      "https://www.eldiario.es/motor/sector_y_mercado/fabricar-coches-componentes-vehiculos-militares-indra-busca-proveedores-automocion_1_13308288.html")),
)
_PRIMES = tuple((group, re.compile(rx), src) for group, rx, src in PRIMES)
# A Spanish joint venture (UTE) of a prime and others: the way in is still the prime.
JOINT_VENTURE = re.compile(r"^(ute|u t e)\b|\bunion temporal\b")


def prime_of(canonical_name: str | None) -> dict[str, Any] | None:
    """The prime or large defence group a winner's normalised name belongs to, with the source of the list; None if none."""
    name = canonical_name or ""
    for group, rx, (source, url) in _PRIMES:
        if rx.search(name):
            return {"group": group, "jointVenture": bool(JOINT_VENTURE.search(name)), "source": source, "sourceUrl": url}
    return None

COVERAGE = ("Direct buying by defence bodies, as published on TED and the national portals we read; not the sub-tier "
            "needs of prime contractors, which are not published. TED covers about a tenth of EU defence spending (a "
            "2025 ECIPE policy brief; we have not re-checked that figure). National coverage differs: Spain (PLACSP) "
            "and Poland (e-Zamówienia) in full, Germany (the federal procurement office's portal) since 2025, France "
            "(BOAMP) since late 2023, the Netherlands (TenderNed) with one defence buyer.")
WINNERS_TED = ("Winners are those named in TED result notices; most contracts below the EU thresholds name no winner "
               "here. Natural persons are never counted or named.")
WINNERS_WITH_PLACSP = ("Winners are those named in TED result notices and in PLACSP's award results (Spain); a winner "
                       "published in both is counted once. Natural persons are never counted or named.")
NOTICE = ("Computed from the CPV codes and countries in the request; nothing was stored or logged. Counts of notices, "
          "not of money: the stated values of notices are budgets or framework ceilings as often as contract values.")


def prefix(code: str) -> str:
    """The leading part a code stands for, by its level in the CPV tree: the code without its trailing zeros,
    never shorter than its division (34300000 -> 343, 44470000 -> 4447, 35000000 -> 35, 10000000 -> 10)."""
    head = code.rstrip("0")
    return head if len(head) >= 2 else code[:2]


class DemandIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cpv: list[str] = Field(min_length=1, max_length=MAX_CODES)
    countries: list[Literal["ES", "DE", "FR", "PL", "NL"]] = Field(default=list(COUNTRIES), min_length=1,
                                                                    max_length=len(COUNTRIES))

    @field_validator("cpv")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        # A check digit as the vocabulary prints it (34300000-0) is taken off.
        codes = [c.strip().split("-")[0] for c in v]
        if any(not CODE.match(c) for c in codes):
            raise ValueError("cpv: codes of 8 digits from the CPV vocabulary")
        return list(dict.fromkeys(codes))

    @field_validator("countries")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return [c for c in COUNTRIES if c in set(v)]


# One procurement, however many notices publish it: the eForms procedure identifier (of the notice, or of the TED
# notice a national notice was forwarded as), else the TED publication number, else the national number within
# its country (the two Polish sources share it).
KEY = """COALESCE('p:' || COALESCE(o.procedure_identifier, t.procedure_identifier),
                  'ted:' || COALESCE(o.ted_ref, CASE WHEN o.source_id = (SELECT id FROM source WHERE code = 'ted')
                                                     THEN o.native_id END),
                  o.country || ':' || o.native_id)"""
PLACSP_IDS = "(SELECT id FROM source WHERE code IN (" + ", ".join(f"'{c}'" for c in PLACSP_SOURCES) + "))"
# The award rows the supplier map would serve, less its core-scope test (a defence body's commodity purchase under
# the civil directive is demand too): legal entities, not removed, not superseded, not a placeholder string.
AWARD_OK = ("NOT org.suppressed AND NOT raw_org.suppressed AND a.excluded_reason IS NULL AND a.superseded_at IS NULL "
            "AND org.individual_reason IS NULL AND raw_org.individual_reason IS NULL")

QUERY = f"""
WITH m AS MATERIALIZED (
    SELECT o.id, o.country, COALESCE(o.published_at, o.notice_date) AS day, o.sig_legal_basis AS lb,
           (o.sig_buyer OR o.buyer_class = 'defence') AS core,
           COALESCE(f.head_org_id, o.buyer_org_id) AS bk,                    -- dgate_buyer_head, as a join
           o.buyer_withheld AS bw, o.buyer_name_raw, o.source_id IN {PLACSP_IDS} AS placsp,
           o.source_id = (SELECT id FROM source WHERE code = 'ted') AS is_ted,
           o.cpv_codes, hashtextextended({KEY}, 0) AS key,
           o.value_amount AS va, o.value_currency AS vc, o.value_kind AS vk
      FROM opportunity o
      LEFT JOIN opportunity t ON o.ted_ref IS NOT NULL AND t.native_id = o.ted_ref
                             AND t.source_id = (SELECT id FROM source WHERE code = 'ted')
      LEFT JOIN buyer_family_member f ON f.org_id = o.buyer_org_id
     WHERE o.is_defence AND NOT o.suppressed AND o.country = ANY(%(countries)s)
       AND COALESCE(o.published_at, o.notice_date) >= %(since)s
       AND dgate_cpv_heads(o.cpv_codes) && %(prefixes)s::text[]
), c AS (
    -- WP-80: one row per procurement first (a hash aggregate), then counted: count(DISTINCT) sorted 116,562 rows for 15
    -- divisions; the total (country NULL) is its own pass, so a procurement in two countries is one
    SELECT country, count(*) AS n, count(*) FILTER (WHERE lb) AS d
      FROM (SELECT country, key, bool_or(lb) AS lb FROM m GROUP BY country, key) x GROUP BY country
    UNION ALL
    SELECT NULL, count(*), count(*) FILTER (WHERE lb) FROM (SELECT key, bool_or(lb) AS lb FROM m GROUP BY key) x
), b AS (
    SELECT country, bk, bool_or(core) AS core, count(DISTINCT key) AS n,
           mode() WITHIN GROUP (ORDER BY buyer_name_raw COLLATE "C") FILTER (WHERE NOT bw) AS name
      FROM m WHERE bk IS NOT NULL GROUP BY country, bk
), k AS (
    -- each code of a notice cut to each prefix length asked, then a hash join on the prefixes
    SELECT p, count(*) AS n FROM (
        SELECT DISTINCT p, m.key
          FROM m, unnest(m.cpv_codes) AS c, unnest(%(lengths)s::int[]) AS len
          JOIN unnest(%(prefixes)s::text[]) AS p ON TRUE
         WHERE left(c, len) = p) x GROUP BY p
), l AS (
    SELECT * FROM (SELECT x.*, row_number() OVER (PARTITION BY country ORDER BY day DESC NULLS LAST, id DESC) AS r
                     FROM (SELECT DISTINCT ON (key) id, country, day, key, lb FROM m
                            ORDER BY key, is_ted DESC, day DESC NULLS LAST, id DESC) x) y
     WHERE r <= {LATEST}
), aw0 AS MATERIALIZED (
    SELECT m.country, m.key, m.id, m.day, org.id AS org, org.country AS org_country, a.name_as_stated, a.id AS award_id,
           a.winners_in_notice AS wn, m.bk, m.bw, m.buyer_name_raw AS bn, m.va, m.vc, m.vk,
           org.canonical_name AS cn, org.is_defence_buyer AS db
      FROM m JOIN award a ON a.opportunity_id = m.id
      JOIN organisation raw_org ON raw_org.id = a.organisation_id
      JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)
     WHERE {AWARD_OK} AND (%(placsp)s OR NOT m.placsp)
), aw AS MATERIALIZED (
    -- WP-80: an award that TED and PLACSP both publish counts once, under the row `award_twin_set` prefers, when that
    -- row is in this answer too (two organisation rows of one company were two winners before)
    SELECT * FROM aw0
     WHERE award_id NOT IN (SELECT tw.award_id FROM award_twin_set tw JOIN aw0 p ON p.award_id = tw.preferred_id)
), ap AS (
    -- WP-80, who to approach: each winner across the countries asked, with at least K_MIN procurements (the mosaic rule)
    SELECT org, count(DISTINCT key) AS n, max(day) AS last, array_agg(DISTINCT country ORDER BY country) AS countries,
           mode() WITHIN GROUP (ORDER BY name_as_stated) AS name, min(cn) AS cn, min(org_country) AS org_country,
           COALESCE(bool_or(db), FALSE) AS db
      FROM aw GROUP BY org HAVING count(DISTINCT key) >= {K_MIN}
), apb AS (
    -- the buyers each of them wins from most often (a withheld buyer is never named)
    SELECT * FROM (SELECT x.*, row_number() OVER (PARTITION BY org ORDER BY n DESC, bk) AS r FROM (
        SELECT aw.org, aw.bk, min(aw.country) AS country, count(DISTINCT aw.key) AS n,
               mode() WITHIN GROUP (ORDER BY aw.bn COLLATE "C") FILTER (WHERE NOT aw.bw) AS name
          FROM aw JOIN ap ON ap.org = aw.org WHERE aw.bk IS NOT NULL GROUP BY aw.org, aw.bk) x
        WHERE name IS NOT NULL) y WHERE r <= {APPROACH_BUYERS}
), apv AS (
    -- the value a TED result notice states for a contract it awards to this one winner (as the supplier profile shows
    -- it), once per procurement; PLACSP states the estimate of the call, not the award, and is not read here
    SELECT org, vc AS currency, sum(va) AS amount, count(*) AS n FROM (
        SELECT DISTINCT ON (aw.org, aw.key) aw.org, aw.va, trim(aw.vc) AS vc FROM aw JOIN ap ON ap.org = aw.org
         WHERE aw.wn = 1 AND aw.vk IN ('total', 'lot_sum') AND aw.va > {PLACEHOLDER_AMOUNT_MAX} AND aw.vc IS NOT NULL
         ORDER BY aw.org, aw.key, aw.va DESC) v GROUP BY org, vc
), an AS (
    SELECT country, count(DISTINCT key) AS n FROM aw GROUP BY GROUPING SETS ((country), ())
), w AS (
    SELECT country, org, org_country, count(DISTINCT key) AS n,
           mode() WITHIN GROUP (ORDER BY name_as_stated) AS name
      FROM aw GROUP BY country, org, org_country
), wt AS (
    SELECT * FROM (SELECT w.*, row_number() OVER (PARTITION BY country ORDER BY n DESC, name, org) AS r
                     FROM w WHERE n >= {K_MIN}) x WHERE r <= {TOP_WINNERS}
), wr AS (
    SELECT DISTINCT ON (aw.country, aw.org, aw.key) aw.country, aw.org, aw.id, aw.day
      FROM aw JOIN wt ON wt.country = aw.country AND wt.org = aw.org
     ORDER BY aw.country, aw.org, aw.key, aw.day DESC NULLS LAST, aw.id DESC
)
SELECT (SELECT json_agg(c) FROM c) AS c, (SELECT json_agg(b) FROM b) AS b, (SELECT json_agg(k) FROM k) AS k,
       (SELECT json_agg(l) FROM l) AS l, (SELECT json_agg(an) FROM an) AS an,
       (SELECT json_agg(json_build_object('country', country, 'org', org, 'n', n)) FROM w) AS w,
       (SELECT json_agg(wt) FROM wt) AS wt,
       (SELECT json_agg(z) FROM (SELECT * FROM (SELECT wr.*, row_number() OVER (PARTITION BY country, org
                                                      ORDER BY day DESC NULLS LAST, id DESC) AS r FROM wr) q
                                  WHERE r <= {WINNER_NOTICES}) z) AS wr,
       (SELECT array_agg(DISTINCT id) FROM aw) AS award_ids,
       (SELECT json_agg(ap) FROM ap) AS ap, (SELECT json_agg(apb) FROM apb) AS apb, (SELECT json_agg(apv) FROM apv) AS apv
"""


def _notices(conn, ids: list[int]) -> dict[int, dict[str, Any]]:
    """The link of each notice: its page on this site and at its source."""
    if not ids:
        return {}
    rows = conn.execute(
        """SELECT o.id, o.native_id, o.title_en, o.title_original, o.buyer_name_raw, o.buyer_withheld,
                  COALESCE(o.published_at, o.notice_date) AS day, o.source_url, o.sig_legal_basis,
                  (SELECT code FROM source WHERE id = o.source_id) AS source
             FROM opportunity o WHERE o.id = ANY(%s)""", (ids,)).fetchall()
    out = {}
    for r in rows:
        title = redact_emails(r["title_en"] or r["title_original"]) or ""
        out[r["id"]] = {"id": str(r["id"]), "slug": make_slug(r["id"], title), "noticeId": r["native_id"],
                        "title": title, "buyerName": None if r["buyer_withheld"] else clean_buyer_name(r["buyer_name_raw"]),
                        "publishedAt": _day(r["day"]), "source": r["source"], "sourceUrl": r["source_url"],
                        "directive": bool(r["sig_legal_basis"])}
    return out


def _edf_projects(conn, orgs: list[int]) -> dict[int, int]:
    """The defence-relevant EU projects (EDF and its forerunners) each organisation, or one merged into it, took part in."""
    if not orgs:
        return {}
    rows = conn.execute(
        """SELECT COALESCE(o.merged_into, o.id) AS org, count(DISTINCT pa.project_id) AS n
             FROM organisation o JOIN participation pa ON pa.organisation_id = o.id AND pa.active
             JOIN project p ON p.id = pa.project_id JOIN programme pg ON pg.id = p.programme_id AND pg.code = ANY(%s)
            WHERE o.id = ANY(%s) OR o.merged_into = ANY(%s) GROUP BY 1""",
        (list(DEFENCE_PROGRAMMES), orgs, orgs)).fetchall()
    return {r["org"]: r["n"] for r in rows}


def _with_page(conn, orgs: list[int]) -> set[int]:
    """The organisations the supplier map serves a page for (`/v1/suppliers/{slug}`: an award in its scope, by the
    organisation or one merged into it), so that a link never leads to "no such supplier"."""
    if not orgs:
        return set()
    rows = conn.execute(
        f"""SELECT DISTINCT org.id {SUPPLIER_FROM} WHERE {supplier_scope()} AND a.organisation_id IN (
                SELECT id FROM organisation WHERE id = ANY(%(orgs)s) OR merged_into = ANY(%(orgs)s))""",
        {"orgs": orgs}).fetchall()
    return {r["id"] for r in rows}


def approach(conn, r: dict[str, Any], winners: list[dict[str, Any]]) -> dict[str, Any]:
    """Who to approach (WP-80): the companies that win these procurements, across the countries asked. Named only with at
    least K_MIN procurements; the others are one count. The most contracts first; every prime or large defence group with
    K_MIN is listed, past the first APPROACH too."""
    rows = sorted(r["ap"] or [], key=lambda w: (-w["n"], w["name"], w["org"]))
    for w in rows:
        w["prime"] = prime_of(w["cn"])
    listed = rows[:APPROACH] + [w for w in rows[APPROACH:] if w["prime"]]
    shown = {w["org"] for w in listed}
    per_org: dict[int, int] = {}
    for w in winners:                       # per country; a procurement is in one country, so the sum is the total
        per_org[w["org"]] = per_org.get(w["org"], 0) + w["n"]
    big = {w["org"] for w in rows}
    buyers: dict[int, list[dict[str, Any]]] = {}
    for b in sorted(r["apb"] or [], key=lambda b: b["r"]):
        name = clean_buyer_name(b["name"])
        buyers.setdefault(b["org"], []).append({"slug": make_slug(b["bk"], name), "name": name, "country": b["country"],
                                                "contracts": b["n"]})
    values: dict[int, list[dict[str, Any]]] = {}
    for v in sorted(r["apv"] or [], key=lambda v: (-v["n"], v["currency"])):
        values.setdefault(v["org"], []).append({"currency": v["currency"], "amount": round(float(v["amount"]), 2),
                                                "contracts": v["n"]})
    edf = _edf_projects(conn, sorted(shown))
    pages = _with_page(conn, sorted(shown))

    def item(w: dict[str, Any]) -> dict[str, Any]:
        name = redact_emails(w["name"]).strip()
        return {"name": name, "country": w["org_country"], "contracts": w["n"],
                "slug": make_slug(w["org"], name) if w["org"] in pages else None,
                "values": values.get(w["org"], []), "buyers": buyers.get(w["org"], []), "countries": w["countries"],
                "lastAward": str(w["last"])[:10] if w["last"] else None, "prime": w["prime"],
                "edfProjects": edf.get(w["org"], 0), "defenceBuyer": bool(w["db"])}

    return {
        "winners": [item(w) for w in listed],
        "below": {"winners": sum(1 for o in per_org if o not in big),
                  "awards": sum(n for o, n in per_org.items() if o not in big)},
        "more": {"winners": len(big - shown), "awards": sum(per_org[o] for o in big - shown)},
    }


def demand(conn, codes: list[str], countries: list[str], today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    since = today - timedelta(days=round(365.25 * YEARS))
    prefixes = list(dict.fromkeys(prefix(c) for c in codes))
    public = settings().placsp_awards_public
    r = conn.execute(QUERY, {"countries": countries, "since": since, "prefixes": prefixes, "placsp": public,
                             "lengths": sorted({len(p) for p in prefixes})}).fetchone()
    counts = {x["country"]: x for x in r["c"] or []}
    awards = {x["country"]: x["n"] for x in r["an"] or []}
    buyers = r["b"] or []
    winners = r["w"] or []
    top = r["wt"] or []
    refs = r["wr"] or []
    latest = r["l"] or []
    links = _notices(conn, [x["id"] for x in latest] + [x["id"] for x in refs])

    def country_block(cc: str) -> dict[str, Any]:
        mine = [b for b in buyers if b["country"] == cc]
        # Two buyer families under one name (two organisation rows of one federal office) are one line here, under
        # the larger one's link; the counts above stay by family.
        same: dict[str, dict[str, Any]] = {}
        for b in sorted((b for b in mine if b["name"]), key=lambda b: (-b["n"], b["bk"])):
            name = clean_buyer_name(b["name"])
            if name.casefold() in same:
                same[name.casefold()]["n"] += b["n"]
                same[name.casefold()]["core"] |= b["core"]
            else:
                same[name.casefold()] = {**b, "name": name}
        named = sorted(same.values(), key=lambda b: (-b["n"], b["name"], b["bk"]))
        won = [w for w in winners if w["country"] == cc]
        listed = sorted((w for w in top if w["country"] == cc), key=lambda w: w["r"])
        shown = {w["org"] for w in listed}
        return {
            "country": cc,
            "procurements": (counts.get(cc) or {}).get("n", 0),
            "directive": (counts.get(cc) or {}).get("d", 0),
            "coreBuyers": sum(1 for b in mine if b["core"]),
            "otherBuyers": sum(1 for b in mine if not b["core"]),
            "topBuyers": [{"slug": make_slug(b["bk"], b["name"]), "name": b["name"], "core": b["core"],
                           "procurements": b["n"]} for b in named[:TOP_BUYERS]],
            "awarded": awards.get(cc, 0),
            "winners": len(won),
            "topWinners": [{"name": redact_emails(w["name"]).strip(), "country": w["org_country"], "awards": w["n"],
                            "notices": [links[x["id"]] for x in sorted((x for x in refs if x["country"] == cc
                                                                         and x["org"] == w["org"]), key=lambda x: x["r"])
                                        if x["id"] in links]}
                           for w in listed],
            "otherWinners": {"winners": sum(1 for w in won if w["org"] not in shown),
                             "awards": sum(w["n"] for w in won if w["org"] not in shown)},
            "latest": [links[x["id"]] for x in sorted((x for x in latest if x["country"] == cc), key=lambda x: x["r"])
                       if x["id"] in links],
        }

    total = counts.get(None) or {}
    note = placsp_note(conn, "o.id = ANY(%s)", (r["award_ids"] or [],)) if public and r["award_ids"] else None
    by_prefix = {x["p"]: x["n"] for x in r["k"] or []}
    return {
        "since": since.isoformat(), "until": today.isoformat(), "kMin": K_MIN, "countries": countries,
        "codes": [{"code": c, "prefix": prefix(c), "procurements": by_prefix.get(prefix(c), 0)} for c in codes],
        "total": {"procurements": total.get("n", 0), "directive": total.get("d", 0),
                  "coreBuyers": len({b["bk"] for b in buyers if b["core"]}),
                  "otherBuyers": len({b["bk"] for b in buyers} - {b["bk"] for b in buyers if b["core"]}),
                  "awarded": awards.get(None, 0), "winners": len({w["org"] for w in winners})},
        "byCountry": [country_block(cc) for cc in countries],
        "approach": approach(conn, r, winners),
        "coverage": COVERAGE,
        "winnersFrom": WINNERS_WITH_PLACSP if note else WINNERS_TED,
        "sources": [TED_NOTE] + ([note] if note else []),
        "notice": NOTICE,
    }


class DemandRef(BaseModel):
    id: str
    slug: str
    noticeId: str
    title: str
    buyerName: str | None
    publishedAt: datetime | None
    source: str
    sourceUrl: str | None
    directive: bool


class DemandBuyer(BaseModel):
    slug: str
    name: str
    core: bool
    procurements: int


class DemandWinner(BaseModel):
    name: str
    country: str
    awards: int
    notices: list[DemandRef]


class OtherWinners(BaseModel):
    winners: int
    awards: int


class DemandCountry(BaseModel):
    country: str
    procurements: int
    directive: int
    coreBuyers: int
    otherBuyers: int
    topBuyers: list[DemandBuyer]
    awarded: int
    winners: int
    topWinners: list[DemandWinner]
    otherWinners: OtherWinners
    latest: list[DemandRef]


class DemandCode(BaseModel):
    code: str
    prefix: str
    procurements: int


class DemandTotal(BaseModel):
    procurements: int
    directive: int
    coreBuyers: int
    otherBuyers: int
    awarded: int
    winners: int


class DemandSource(BaseModel):
    code: str
    name: str
    attribution: str
    lastUpdated: datetime | None = None


class Prime(BaseModel):
    group: str
    jointVenture: bool
    source: str
    sourceUrl: str


class ApproachBuyer(BaseModel):
    slug: str
    name: str
    country: str
    contracts: int


class StatedValue(BaseModel):
    currency: str
    amount: float
    contracts: int


class ApproachWinner(BaseModel):
    name: str
    country: str | None
    contracts: int
    slug: str | None
    values: list[StatedValue]
    buyers: list[ApproachBuyer]
    countries: list[str]
    lastAward: str | None
    prime: Prime | None
    edfProjects: int
    defenceBuyer: bool


class ApproachCount(BaseModel):
    winners: int
    awards: int


class Approach(BaseModel):
    winners: list[ApproachWinner]
    below: ApproachCount          # winners with fewer than kMin procurements: counted, never named
    more: ApproachCount           # winners with kMin or more past the first APPROACH (no prime among them)


class Demand(BaseModel):
    since: str
    until: str
    kMin: int
    countries: list[str]
    codes: list[DemandCode]
    total: DemandTotal
    byCountry: list[DemandCountry]
    approach: Approach
    coverage: str
    winnersFrom: str
    sources: list[DemandSource]
    notice: str


@router.post("/v1/readiness/demand", response_model=Demand)
def post_demand(body: DemandIn, conn=Depends(get_conn)):
    return demand(conn, body.cpv, body.countries)
