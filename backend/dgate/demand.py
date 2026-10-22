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

What it is not: the sub-tier needs of prime contractors are not published, and TED holds about a tenth of EU
defence spending; the coverage line says so on every answer.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings
from .funding import get_conn, make_slug
from .normalise import redact_emails
from .suppliers import K_MIN, PLACSP_SOURCES, TED_NOTE, placsp_note
from .tenders import _day, clean_buyer_name

router = APIRouter()

COUNTRIES = ("ES", "DE", "FR", "PL", "NL")
MAX_CODES = 15
YEARS = 3
TOP_BUYERS = 10
TOP_WINNERS = 10
LATEST = 5
WINNER_NOTICES = 3
CODE = re.compile(r"^[0-9]{8}$")

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
           o.cpv_codes, hashtextextended({KEY}, 0) AS key
      FROM opportunity o
      LEFT JOIN opportunity t ON o.ted_ref IS NOT NULL AND t.native_id = o.ted_ref
                             AND t.source_id = (SELECT id FROM source WHERE code = 'ted')
      LEFT JOIN buyer_family_member f ON f.org_id = o.buyer_org_id
     WHERE o.is_defence AND NOT o.suppressed AND o.country = ANY(%(countries)s)
       AND COALESCE(o.published_at, o.notice_date) >= %(since)s
       AND dgate_cpv_heads(o.cpv_codes) && %(prefixes)s::text[]
), c AS (
    SELECT country, count(DISTINCT key) AS n, count(DISTINCT key) FILTER (WHERE lb) AS d
      FROM m GROUP BY GROUPING SETS ((country), ())
), b AS (
    SELECT country, bk, bool_or(core) AS core, count(DISTINCT key) AS n,
           mode() WITHIN GROUP (ORDER BY buyer_name_raw COLLATE "C") FILTER (WHERE NOT bw) AS name
      FROM m WHERE bk IS NOT NULL GROUP BY country, bk
), k AS (
    -- each code of a notice cut to each prefix length asked, then a hash join on the prefixes
    SELECT p, count(DISTINCT key) AS n
      FROM m, unnest(m.cpv_codes) AS c, unnest(%(lengths)s::int[]) AS len
      JOIN unnest(%(prefixes)s::text[]) AS p ON TRUE
     WHERE left(c, len) = p GROUP BY p
), l AS (
    SELECT * FROM (SELECT x.*, row_number() OVER (PARTITION BY country ORDER BY day DESC NULLS LAST, id DESC) AS r
                     FROM (SELECT DISTINCT ON (key) id, country, day, key, lb FROM m
                            ORDER BY key, is_ted DESC, day DESC NULLS LAST, id DESC) x) y
     WHERE r <= {LATEST}
), aw AS MATERIALIZED (
    SELECT m.country, m.key, m.id, m.day, org.id AS org, org.country AS org_country, a.name_as_stated
      FROM m JOIN award a ON a.opportunity_id = m.id
      JOIN organisation raw_org ON raw_org.id = a.organisation_id
      JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)
     WHERE {AWARD_OK} AND (%(placsp)s OR NOT m.placsp)
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
       (SELECT array_agg(DISTINCT id) FROM aw) AS award_ids
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


class Demand(BaseModel):
    since: str
    until: str
    kMin: int
    countries: list[str]
    codes: list[DemandCode]
    total: DemandTotal
    byCountry: list[DemandCountry]
    coverage: str
    winnersFrom: str
    sources: list[DemandSource]
    notice: str


@router.post("/v1/readiness/demand", response_model=Demand)
def post_demand(body: DemandIn, conn=Depends(get_conn)):
    return demand(conn, body.cpv, body.countries)
