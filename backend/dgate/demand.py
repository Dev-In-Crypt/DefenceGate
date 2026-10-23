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
- procurements with a published winner, and the winners: the rows of the award set (`award_set.py`, WP-85), the
  one the supplier map counts: legal entities only (a winner the directory treats as a natural person, or a
  winner string that is no supplier, is never counted or named), from TED result notices, and from PLACSP's award
  results only while DGATE_PLACSP_AWARDS_PUBLIC is on; an award TED and PLACSP both publish once. So every winner
  named has a supplier page, and `/v1/suppliers?cpv=<the codes>&buyerCountry=<the countries>` gives it the same
  number of contracts. WP-81 (owner decision of 22 October 2026): every legal-entity winner is named,
  whatever its number of procurements (`K_MIN` is 1; the lists stop at `TOP_WINNERS` per country and `APPROACH`).

Who to approach (WP-80, `approach`): the same winners across the countries asked, each named (WP-81: from one
procurement; `below` is always empty now), most contracts first: how many, the buyers they win from most, the
countries, the newest notice's publication date (PLACSP: the procurement's, the award date is not stored), a link to the supplier
page (every winner has one since WP-85), the EDF projects, the mark "prime contractor or large defence group" from the curated, sourced list
`PRIMES`, and (WP-81, owner decision of 22 October 2026) the sum of the values of its contracts per currency, by the supplier
profile's own rule (`suppliers.valued`, `suppliers.value_totals`: a value only from a notice naming this one winner, each
contract once, never converted; how many state no value). An award TED and PLACSP both publish counts once
(`award_twin_set`), here and in the per-country winners. A request matching more than `MAX_ROWS` notices is refused (422,
`too_broad`) so that no answer risks the API's 5 s budget.

What it is not: the sub-tier needs of prime contractors are not published, and TED holds about a tenth of EU
defence spending; the coverage line says so on every answer.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import award_set
from .award_set import CPV_MATCH, KEY, NOTICES, prefix
from .classify import DEFENCE_PROGRAMMES
from .config import settings
from .funding import get_conn, make_slug
from .normalise import redact_emails
from .suppliers import (
    K_MIN,
    TED_NOTE,
    ValueTotals,
    placsp_note,
    value_of,
    value_totals,
)
from .tenders import _day, clean_buyer_name

router = APIRouter()

COUNTRIES = ("ES", "DE", "FR", "PL", "NL")
MAX_CODES = 15
YEARS = award_set.YEARS
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
     ("General Dynamics in the SIPRI Top 100, 2024; Santa BГЎrbara Sistemas as a GDELS company (FEINDEF exhibitor page)",
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


# The notices of an answer: the award set's notices (`award_set.NOTICES`: defence scope, not removed, the window), in the
# countries asked, with a code under one of the prefixes (`award_set.CPV_MATCH`, index 0099). KEY: `award_set.KEY`.
MATCH = f"{NOTICES} AND o.country = ANY(%(countries)s) AND {CPV_MATCH}"
# WP-80: at most this many matched notices per answer. Measured on production on 22 October 2026 (loaded server): 8,130 rows
# (the vehicle-parts sample) 0.8-1.2 s, 22,921 rows 1.1-1.9 s, 40,843 rows 2.3-2.6 s, 116,562 (15 divisions) 5.6-6.0 s.
MAX_ROWS = 30_000
TOO_BROAD = ("These CPV codes cover too many defence-scope notices for one map (more than 30,000 in three years). Choose more "
             "specific codes: a group such as 34300000 rather than a whole division such as 34000000, or fewer codes.")


class TooBroad(Exception):
    """The request matches more than MAX_ROWS notices: refused with 422, the codes not echoed."""


def query() -> str:
    """The one statement of an answer. Built per call: the award set's condition reads the PLACSP switch."""
    return f"""
WITH m AS MATERIALIZED (
    SELECT o.id, o.country, COALESCE(o.published_at, o.notice_date) AS day, o.sig_legal_basis AS lb,
           (o.sig_buyer OR o.buyer_class = 'defence') AS core,
           COALESCE(f.head_org_id, o.buyer_org_id) AS bk,                    -- dgate_buyer_head, as a join
           o.buyer_withheld AS bw, o.buyer_name_raw,
           o.source_id = (SELECT id FROM source WHERE code = 'ted') AS is_ted,
           o.cpv_codes, hashtextextended({KEY}, 0) AS key
      FROM opportunity o
      LEFT JOIN opportunity t ON o.ted_ref IS NOT NULL AND t.native_id = o.ted_ref
                             AND t.source_id = (SELECT id FROM source WHERE code = 'ted')
      LEFT JOIN buyer_family_member f ON f.org_id = o.buyer_org_id
     WHERE {MATCH}
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
), aw AS MATERIALIZED (
    -- WP-85: the winners of these notices are the award set's rows (`award_set.scope`: legal entities, the PLACSP switch,
    -- an award that TED and PLACSP both publish once), exactly as the supplier map counts them
    SELECT m.country, m.key, m.id, m.day, org.id AS org, org.country AS org_country, a.name_as_stated, a.id AS award_id,
           a.winners_in_notice AS wn, m.bk, m.bw, m.buyer_name_raw AS bn,
           org.canonical_name AS cn, org.is_defence_buyer AS db
      FROM m JOIN award a ON a.opportunity_id = m.id
      JOIN opportunity o ON o.id = m.id
      JOIN organisation raw_org ON raw_org.id = a.organisation_id
      JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)
     WHERE {award_set.scope()}
), ap AS (
    -- WP-80, who to approach: each winner across the countries asked (WP-81: K_MIN is 1, every legal entity)
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
       (SELECT json_agg(ap) FROM ap) AS ap, (SELECT json_agg(apb) FROM apb) AS apb,
       (SELECT array_agg(award_id) FROM aw) AS aw_ids
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


def _ranked(r: dict[str, Any]) -> list[dict[str, Any]]:
    """Every winner of the answer (`ap`), the most contracts first, each with its prime mark."""
    rows = sorted(r["ap"] or [], key=lambda w: (-w["n"], w["name"], w["org"]))
    for w in rows:
        w["prime"] = prime_of(w["cn"])
    return rows


# WP-81: the sum of the listed winners' contract values per currency, each contract (the procurement key of the answer)
# once, by the supplier profile's rule (`suppliers.value_of`: a PLACSP awarded amount first, else a TED value; a twin pair
# from either copy). A statement of its own over the answer's award rows of the listed winners only: inside QUERY it
# valued every winner's rows (6,700 winners at the cap) for the 30 shown, +50 % on the whole answer.
VALUES = f"""
SELECT org, ok, shared, CASE WHEN ok THEN vc END AS vc, sum(va) FILTER (WHERE ok) AS amount, count(*) AS n,
       count(*) FILTER (WHERE ok AND vk = 'lot_sum') AS lots
  FROM (SELECT DISTINCT ON (org.id, kk.k) org.id AS org, kk.k, v.va IS NOT NULL AS ok,
               a.winners_in_notice > 1 AS shared, v.va, v.vc, v.vk
          FROM award a
          JOIN organisation raw_org ON raw_org.id = a.organisation_id
          JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)
          JOIN opportunity o ON o.id = a.opportunity_id
          LEFT JOIN opportunity t ON o.ted_ref IS NOT NULL AND t.native_id = o.ted_ref
                                 AND t.source_id = (SELECT id FROM source WHERE code = 'ted')
          CROSS JOIN LATERAL (SELECT hashtextextended({KEY}, 0) AS k) kk
          {value_of("a.id", "%(placsp)s")}
         WHERE a.id = ANY(%(ids)s)
           AND a.organisation_id IN (SELECT id FROM organisation WHERE id = ANY(%(orgs)s) OR merged_into = ANY(%(orgs)s))
         ORDER BY org.id, kk.k, 3 DESC, (v.vk = 'awarded') DESC, (v.vk = 'total') DESC, v.va DESC) x
 GROUP BY org, ok, shared, 4
"""


def _items(conn, r: dict[str, Any], listed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The "who to approach" entries of these winners: buyers, values, countries, page link, marks."""
    shown = {w["org"] for w in listed}
    buyers: dict[int, list[dict[str, Any]]] = {}
    for b in sorted(r["apb"] or [], key=lambda b: b["r"]):
        name = clean_buyer_name(b["name"])
        buyers.setdefault(b["org"], []).append({"slug": make_slug(b["bk"], name), "name": name, "country": b["country"],
                                                "contracts": b["n"]})
    sums: dict[int, list[dict[str, Any]]] = {}
    if shown:
        for v in conn.execute(VALUES, {"ids": r["aw_ids"] or [], "orgs": sorted(shown),
                                       "placsp": settings().placsp_awards_public}).fetchall():
            sums.setdefault(v["org"], []).append(v)
    edf = _edf_projects(conn, sorted(shown))

    def item(w: dict[str, Any]) -> dict[str, Any]:
        name = redact_emails(w["name"]).strip()
        return {"name": name, "country": w["org_country"], "contracts": w["n"],
                # WP-85: every winner has a supplier page; the map counts the same award set (`award_set`)
                "slug": make_slug(w["org"], name),
                "values": value_totals(sums.get(w["org"], []), w["n"]),
                "buyers": buyers.get(w["org"], []), "countries": w["countries"],
                "lastAward": str(w["last"])[:10] if w["last"] else None, "prime": w["prime"],
                "edfProjects": edf.get(w["org"], 0), "defenceBuyer": bool(w["db"])}

    return [item(w) for w in listed]


def approach(conn, r: dict[str, Any], winners: list[dict[str, Any]]) -> dict[str, Any]:
    """Who to approach (WP-80): the companies that win these procurements, across the countries asked, every legal entity
    named (WP-81). The most contracts first; every prime or large defence group is listed, past the first APPROACH too.
    Every one of them, a page at a time: `winners_page` (POST /v1/readiness/winners)."""
    rows = _ranked(r)
    listed = rows[:APPROACH] + [w for w in rows[APPROACH:] if w["prime"]]
    shown = {w["org"] for w in listed}
    per_org: dict[int, int] = {}
    for w in winners:                       # per country; a procurement is in one country, so the sum is the total
        per_org[w["org"]] = per_org.get(w["org"], 0) + w["n"]
    big = {w["org"] for w in rows}
    return {
        "winners": _items(conn, r, listed),
        "below": {"winners": sum(1 for o in per_org if o not in big),
                  "awards": sum(n for o, n in per_org.items() if o not in big)},
        "more": {"winners": len(big - shown), "awards": sum(per_org[o] for o in big - shown)},
    }


def _answer(conn, codes: list[str], countries: list[str], today: date) -> tuple[dict[str, Any], date, bool]:
    """The one statement of an answer (after the too-broad check): its row, the window's start, the PLACSP switch."""
    since = award_set.since(today)
    prefixes = list(dict.fromkeys(prefix(c) for c in codes))
    public = settings().placsp_awards_public
    # WP-80: the work grows with the notices matched (15 whole divisions: 116,562 rows, 4-6 s on production, against the
    # API's 5 s budget). Counted first, stopping at the cap, so a request that would read more is refused before it costs.
    matched = conn.execute(f"SELECT count(*) AS n FROM (SELECT 1 FROM opportunity o WHERE {MATCH} LIMIT %(cap)s) x",
                           {"countries": countries, "since": since, "prefixes": prefixes, "cap": MAX_ROWS + 1}).fetchone()["n"]
    if matched > MAX_ROWS:
        raise TooBroad()
    r = conn.execute(query(), {"countries": countries, "since": since, "prefixes": prefixes, "placsp": public,
                             "lengths": sorted({len(p) for p in prefixes})}).fetchone()
    return r, since, public


WINNERS_PAGE = 100


def winners_page(conn, codes: list[str], countries: list[str], page: int, today: date | None = None) -> dict[str, Any]:
    """WP-81: every winner of the answer, `WINNERS_PAGE` at a time, in the order and form of "who to approach" (the
    report's list stops at APPROACH; this one does not). The same statement as `demand`, so the same budget."""
    today = today or datetime.now(timezone.utc).date()
    r, since, public = _answer(conn, codes, countries, today)
    rows = _ranked(r)
    start = (page - 1) * WINNERS_PAGE
    note = placsp_note(conn, "o.id = ANY(%s)", (r["award_ids"] or [],)) if public and r["award_ids"] else None
    return {"since": since.isoformat(), "until": today.isoformat(), "countries": countries, "total": len(rows),
            "page": page, "pageSize": WINNERS_PAGE, "winners": _items(conn, r, rows[start:start + WINNERS_PAGE]),
            "winnersFrom": WINNERS_WITH_PLACSP if note else WINNERS_TED, "sources": [TED_NOTE] + ([note] if note else [])}


def demand(conn, codes: list[str], countries: list[str], today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    r, since, public = _answer(conn, codes, countries, today)
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


class ApproachWinner(BaseModel):
    name: str
    country: str | None
    contracts: int
    slug: str | None
    values: ValueTotals                       # WP-81: `of` is `contracts`
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
    below: ApproachCount          # winners with fewer than kMin procurements (WP-81: kMin is 1, so none)
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
    try:
        return demand(conn, body.cpv, body.countries)
    except TooBroad:
        raise HTTPException(422, {"code": "too_broad", "message": TOO_BROAD}) from None


class WinnersIn(DemandIn):
    page: int = Field(default=1, ge=1, le=1000)


class WinnersPage(BaseModel):
    since: str
    until: str
    countries: list[str]
    total: int
    page: int
    pageSize: int
    winners: list[ApproachWinner]
    winnersFrom: str
    sources: list[DemandSource]


@router.post("/v1/readiness/winners", response_model=WinnersPage)
def post_winners(body: WinnersIn, conn=Depends(get_conn)):
    """WP-81: every winner of the demand answer for these codes and countries, a page of 100 at a time. Stateless,
    as /v1/readiness/demand: nothing is kept or logged."""
    try:
        return winners_page(conn, body.cpv, body.countries, body.page)
    except TooBroad:
        raise HTTPException(422, {"code": "too_broad", "message": TOO_BROAD}) from None
