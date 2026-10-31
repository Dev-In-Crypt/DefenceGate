"""The "Who to sell to" supplier report (WP-162, owner, 31 October 2026).

One report for one company, 3 to 5 printed pages, answering: who in European defence buys what it makes, who wins those
contracts, what is open now, what it lacks to qualify, and what to do in the next 90 days. Two kinds of company:

  A  a company in our data (TED awards or EU-funded projects): `org` is its slug; its CPV codes are those of the contracts it
     won (or the codes sent with the request), its EU projects come from CORDIS and the EDF factsheets;
  B  a civilian maker not in our data, described by a form: CPV codes (chosen in the browser from the CPV dictionary and the
     product-word map, never by a model), country, certificates declared.

Nothing here is a second definition of anything: the sections read the modules the site already serves (reuse list in
docs/verification/features/wp162-selfcheck.md):

  2 Who buys      `demand.demand` (the award set's window, buyer families, contract values per currency)
  3 Who wins      `demand.demand` `approach` (legal entities only; natural persons are never counted or named)
  4 Open now      `tenders.list_tenders` and `funding.list_funding`, called as plain functions
  5 Ending soon   `ending_soon`, the seam for WP-160 (None until it is wired: the section is skipped)
  6 To qualify    the readiness content (`readiness.api.content`, primary-source passages) and its rules' verdicts
  7 Next 90 days  fixed templates (`STEPS`), triggered by the gaps and matches above; no text written by a model
  8 Sources       `demand.COVERAGE`, the source notes, the disclaimer

Privacy (owner's hard constraint 1). The form of mode B is used in memory for the request and never logged, cached or
stored, unless the account ticks the consent box (`consent`): then that one form is kept (`sell_profile`, migration 0154) so
the account can generate again; it can delete it. Only the use is counted (`sell_report_use`: account, month, and for mode A
the company), never a field of the form. The tests prove it (tests/integration/test_wp162_sell_report.py).

Mosaic rule (constraint 2): in section 3 a company is named only when it is large (`is_large`) or when every cell it is in,
its country of registration x a CPV code of the report, holds at least MOSAIC_MIN companies; otherwise it is counted, not
named, and carries no link. Section 2 names contracting authorities and entities: they publish the notices themselves.
Anonymous visitors (the public sample) see no company name in section 3 at all.

Access: Pro 3 a month, Team 15, Consultant unlimited (`billing.REPORTS_PER_MONTH`, as the company report) and the
Consultant's own name and logo on the cover (`branded_reports`); a cluster licence draws on its yearly pool
(`association.sell_reports_per_year`). Dark behind DGATE_COMPANY_REPORT_OPEN, and the WP-124 rule holds: while no plan is on
sale nothing is counted against anyone. The admin's one-off report is `python -m dgate.ops.sell_report` (read-only, never
counted).
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import accounts, award_set, billing, demand
from .accounts import AccountError, throttled
from .config import settings
from .funding import get_conn
from .listcache import cache_list

router = APIRouter()
account_router = APIRouter(prefix="/v1/account/sell-report",
                           dependencies=[Depends(accounts.internal_only), Depends(accounts.no_store)])

FEATURE = "sell_report"
MOSAIC_MIN = 5                 # companies a cell needs before a small or medium one of it is named (owner, constraint 2)
BUYERS_PER_COUNTRY = 5          # the company's own country (or the largest); 3 in the others, to keep to 3-5 printed pages
BUYERS_ELSEWHERE = 3
BUYER_COUNTRIES = 4             # countries listed with their buyers; the others with their counts only
WINNERS = 10
OPEN_TENDERS = 5
OPEN_CALLS = 5
CALL_WORDS = 5                 # product words searched in the funding calls
CODE = re.compile(r"^[0-9]{8}$")
DISCLAIMER = "Indicative information, not legal advice, not an eligibility decision."

# The certificates and registrations a form may declare: the keys of the supplier profile (web/lib/profile.ts CERTIFICATES,
# REGISTRATIONS), so the two pages speak of the same things.
HELD = ("ISO9001", "IATF16949", "ISO27001", "EN9100", "AQAP2110", "AQAP2310", "PECAL", "ISO14001", "ISO45001", "ISO50001",
        "VCA", "PASSI", "SECNUMCLOUD", "CSPN", "RID", "NCAGE", "NSPA")
Held = Literal["ISO9001", "IATF16949", "ISO27001", "EN9100", "AQAP2110", "AQAP2310", "PECAL", "ISO14001", "ISO45001",
               "ISO50001", "VCA", "PASSI", "SECNUMCLOUD", "CSPN", "RID", "NCAGE", "NSPA"]
Tri = Literal["yes", "no", "unsure", ""]

# The demo company of the free public sample: a fictitious Spanish automotive parts maker (no real company is described), the
# codes of the supplier profile's automotive set (web/lib/cpv.ts AUTOMOTIVE_SET).
DEMO: dict[str, Any] = {
    "name": "Demo automotive parts maker (fictitious)", "country": "ES", "size": "sme",
    "cpv": ["34300000", "34320000", "34330000", "35400000", "34322000", "34312000", "44470000", "44530000", "31611000"],
    "held": ["ISO9001", "IATF16949"], "classified": "no", "exports": "within_eu", "usComponents": "unsure",
}


# ------------------------------------------------------------------ input
class ReportIn(BaseModel):
    """The request. Mode A: `org` (a supplier or organisation slug), the rest optional. Mode B: the form, no `org`."""
    model_config = ConfigDict(extra="forbid")
    org: str | None = Field(default=None, max_length=120, pattern=r"^[0-9]{1,19}(-[a-z0-9-]{0,100})?$")
    name: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    cpv: list[str] = Field(default_factory=list, max_length=demand.MAX_CODES)
    nace: str | None = Field(default=None, pattern=r"^[A-Z]?[0-9]{2}(\.[0-9]{1,2}){0,2}$")
    size: Literal["sme", "large", ""] = ""
    held: list[Held] = Field(default_factory=list, max_length=len(HELD))
    classified: Tri = ""
    exports: Literal["none", "within_eu", "outside_eu", "unsure", ""] = ""
    usComponents: Tri = ""
    consent: bool = False             # keep this form on the server (mode B); without it nothing of it is stored

    @field_validator("cpv")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        codes = [c.strip().split("-")[0] for c in v]
        if any(not CODE.match(c) for c in codes):
            raise ValueError("cpv: codes of 8 digits from the CPV vocabulary")
        return list(dict.fromkeys(codes))

    @field_validator("name")
    @classmethod
    def _plain(cls, v: str | None) -> str | None:
        v = " ".join((v or "").split())
        return v or None


# ------------------------------------------------------------------ the seam for section 5 (WP-160)
def ending_soon(conn, codes: list[str], countries: list[str], today: date) -> list[dict[str, Any]] | None:
    """Section 5: the contracts under these codes and countries ending in the next 12 months, newest end first, at most 10,
    each `{"title", "buyer", "country", "end", "endStated", "winner", "href", "sourceUrl"}`. None while the WP-160 code
    (one end-date rule over `opportunity.contract_*`) is not in this tree: the report then skips the section. The orchestrator
    wires WP-160's function here at merge."""
    return None


# ------------------------------------------------------------------ section 1: the profile
def _org_id(slug: str) -> int:
    return int(slug.split("-", 1)[0])


def profile_of_org(conn, slug: str) -> dict[str, Any]:
    """Mode A: the company as our data has it: its name and country, the CPV classes of the contracts it won in the award set's
    window (its main codes, most contracts first) and its EU-funded projects by programme. 404 / 410 as its pages."""
    from .network_api import live_organisation, org_ref

    org = live_organisation(conn, slug)                    # 404, 410 (removed on request, a natural person)
    ref = org_ref(org)
    rows = conn.execute(
        f"""SELECT left(o.cpv_codes[1], 4) AS c, count(DISTINCT {award_set.KEY_HASH}) AS n
              {award_set.FROM} WHERE {award_set.scope()} AND {award_set.OF_ORGS} AND o.cpv_codes[1] ~ '^[0-9]{{4}}'
             GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 6""", {"orgs": [org["id"]], "since": award_set.since()}).fetchall()
    awards = conn.execute(f"SELECT count(DISTINCT {award_set.KEY_HASH}) AS n {award_set.FROM} "
                          f"WHERE {award_set.scope()} AND {award_set.OF_ORGS}",
                          {"orgs": [org["id"]], "since": award_set.since()}).fetchone()["n"]
    projects = conn.execute(
        """SELECT COALESCE(pr.code, '') AS programme, count(DISTINCT pa.project_id) AS n
             FROM participation pa JOIN project p ON p.id = pa.project_id LEFT JOIN programme pr ON pr.id = p.programme_id
            WHERE pa.organisation_id = ANY(%s) AND pa.active GROUP BY 1 ORDER BY 2 DESC, 1""", (org["family"],)).fetchall()
    page = f"/suppliers/{ref['slug']}" if rows else f"/organisations/{ref['slug']}" if projects else None
    return {"name": ref["name"], "slug": ref["slug"], "country": ref["country"], "href": page,
            "wonCodes": [{"code": r["c"] + "0000", "contracts": r["n"]} for r in rows],
            "awards": awards,
            "projects": [{"programme": r["programme"] or "Other", "projects": r["n"]} for r in projects]}


def _profile(inp: ReportIn, org: dict[str, Any] | None) -> dict[str, Any]:
    from .tenders import cpv_titles

    codes = inp.cpv or ([c["code"] for c in org["wonCodes"]] if org else [])
    return {
        "mode": "A" if org else "B", "name": (org or {}).get("name") or inp.name, "slug": (org or {}).get("slug"),
        "href": (org or {}).get("href"),
        "country": inp.country or (org or {}).get("country"), "cpv": codes, "cpvTitles": cpv_titles(codes),
        "cpvFrom": "request" if inp.cpv else ("awards" if org and codes else None),
        "nace": inp.nace, "size": inp.size or None, "held": list(inp.held),
        "classified": inp.classified or None, "exports": inp.exports or None, "usComponents": inp.usComponents or None,
        "awards": (org or {}).get("awards"), "projects": (org or {}).get("projects", []),
    }


# ------------------------------------------------------------------ sections 2 and 3: who buys, who wins
LARGE_SOURCE = demand.SIPRI[1]


def is_large(canonical_name: str | None) -> bool:
    """The size rule of the mosaic rule: a company counts as large only when it is on the curated prime list (`demand.PRIMES`)
    under the SIPRI Top 100 arms-producing and military services companies (2024): each of them has arms revenue far above
    the ceiling of a medium-sized enterprise in Commission Recommendation 2003/361/EC (fewer than 250 staff, turnover of at
    most EUR 50 million). Every other winner may be small or medium: we hold no staff or turnover figures for winners."""
    p = demand.prime_of(canonical_name)
    return bool(p) and p["sourceUrl"] == LARGE_SOURCE


CELLS = f"""
SELECT org.id AS org, min(org.country) AS country, min(org.canonical_name) AS cn, array_agg(DISTINCT p) AS prefixes
  {award_set.FROM}
  JOIN unnest(%(prefixes)s::text[]) AS p ON dgate_cpv_heads(o.cpv_codes) && ARRAY[p]
 WHERE {{scope}} AND o.country = ANY(%(countries)s)
 GROUP BY org.id"""


def mosaic(rows: list[dict[str, Any]], minimum: int = MOSAIC_MIN) -> dict[int, bool]:
    """Per winner: whether it may be named. A cell is a country of registration and a CPV code of the report; a winner is
    named when it is large, or when every cell it is in holds at least `minimum` companies. Pure (unit-tested)."""
    cells: dict[tuple[str | None, str], int] = {}
    for r in rows:
        for p in r["prefixes"]:
            cells[(r["country"], p)] = cells.get((r["country"], p), 0) + 1
    return {r["org"]: is_large(r["cn"]) or all(cells[(r["country"], p)] >= minimum for p in r["prefixes"])
            for r in rows}


def _newest_buyer_notices(conn, bks: list[int], countries: list[str], prefixes: list[str], since: date) -> dict[int, int]:
    if not bks:
        return {}
    rows = conn.execute(
        f"""SELECT DISTINCT ON (COALESCE(f.head_org_id, o.buyer_org_id)) COALESCE(f.head_org_id, o.buyer_org_id) AS bk, o.id
              FROM opportunity o LEFT JOIN buyer_family_member f ON f.org_id = o.buyer_org_id
             WHERE {demand.MATCH} AND NOT o.buyer_withheld
               AND COALESCE(f.head_org_id, o.buyer_org_id) = ANY(%(bks)s)
             ORDER BY 1, COALESCE(o.published_at, o.notice_date) DESC NULLS LAST, o.id DESC""",
        {"countries": countries, "since": since, "prefixes": prefixes, "bks": bks}).fetchall()
    return {r["bk"]: r["id"] for r in rows}


def _newest_award_notices(conn, orgs: list[int], countries: list[str], prefixes: list[str], since: date) -> dict[int, int]:
    if not orgs:
        return {}
    rows = conn.execute(
        f"""SELECT DISTINCT ON (org.id) org.id AS org, o.id {award_set.FROM}
             WHERE {award_set.scope()} AND {award_set.OF_ORGS} AND o.country = ANY(%(countries)s) AND {award_set.CPV_MATCH}
             ORDER BY org.id, COALESCE(o.published_at, o.notice_date) DESC NULLS LAST, o.id DESC""",
        {"orgs": orgs, "countries": countries, "prefixes": prefixes, "since": since}).fetchall()
    return {r["org"]: r["id"] for r in rows}


def _link(n: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if n is None else {"href": f"/tenders/{n['slug']}", "sourceUrl": n["sourceUrl"], "noticeId": n["noticeId"],
                                   "publishedAt": n["publishedAt"], "source": n["source"]}


def market(conn, codes: list[str], home: str | None, names: bool, today: date, own: int | None = None) -> dict[str, Any]:
    """Sections 2 and 3 from one demand answer (all the map's countries, the company's own first). `own`: the company of a
    mode A report, left out of "who wins" (its own contracts are counted apart, `ownContracts`)."""
    if not codes:
        return {"available": False, "reason": "no_codes"}
    countries = list(demand.COUNTRIES)
    try:
        d = demand.demand(conn, codes, countries, today=today, home=home if home in countries else None)
    except demand.TooBroad:
        return {"available": False, "reason": "too_broad", "message": demand.TOO_BROAD}
    prefixes = list(dict.fromkeys(award_set.prefix(c) for c in codes))
    since = date.fromisoformat(d["since"])
    blocks = sorted((c for c in d["byCountry"] if c["procurements"]),
                    key=lambda c: (c["country"] != home, -c["procurements"], c["country"]))
    shown = {c["country"]: c["topBuyers"][:BUYERS_PER_COUNTRY if i == 0 else BUYERS_ELSEWHERE if i < BUYER_COUNTRIES else 0]
             for i, c in enumerate(blocks)}
    bks = sorted({_org_id(b["slug"]) for xs in shown.values() for b in xs})
    newest_b = _newest_buyer_notices(conn, bks, countries, prefixes, since)

    # who wins: the listed winners (the trade's own first, as "who to approach" orders them)
    everyone = sorted(d["approach"]["winners"], key=lambda w: w.get("byOtherCodeOnly", False))
    mine = [w for w in everyone if own is not None and w["slug"] and _org_id(w["slug"]) == own]
    listed = [w for w in everyone if w not in mine][:WINNERS]
    cells = conn.execute(CELLS.format(scope=award_set.scope()),
                         {"prefixes": prefixes, "countries": countries, "since": since}).fetchall()
    may = mosaic(cells)
    large = {c["org"] for c in cells if is_large(c["cn"])}
    orgs = [_org_id(w["slug"]) for w in listed if w["slug"]]
    newest_w = _newest_award_notices(conn, orgs, countries, prefixes, since) if names else {}
    links = demand._notices(conn, list(newest_b.values()) + list(newest_w.values()))
    cpv = ",".join(prefixes)

    buyers = [{
        "country": c["country"], "procurements": c["procurements"], "directive": c["directive"],
        "buyers": c["coreBuyers"] + c["otherBuyers"], "coreBuyers": c["coreBuyers"],
        "href": f"/tenders?country={c['country']}&cpv={cpv}&status=all",
        "rows": [{"name": b["name"], "core": b["core"], "procurements": b["procurements"],
                  "awardedValue": b.get("awardedValue", []),
                  "href": demand_buyer_href(b["slug"], prefixes),
                  "notice": _link(links.get(newest_b.get(_org_id(b["slug"]))))} for b in shown[c["country"]]],
    } for c in blocks]

    rows, hidden = [], {}
    for w in listed:
        org = _org_id(w["slug"]) if w["slug"] else None
        if names and org is not None and may.get(org, False):
            rows.append({"name": w["name"], "country": w["country"], "contracts": w["contracts"],
                         "countries": w["countries"], "values": w["values"], "prime": w["prime"],
                         "large": org in large,
                         "edfProjects": w["edfProjects"], "byOtherCodeOnly": w.get("byOtherCodeOnly", False),
                         "href": f"/suppliers/{w['slug']}?cpv={','.join(codes)}&buyerCountry={','.join(countries)}",
                         "notice": _link(links.get(newest_w.get(org)))})
        else:
            h = hidden.setdefault(w["country"] or "", {"country": w["country"], "companies": 0, "contracts": 0})
            h["companies"] += 1
            h["contracts"] += w["contracts"]
    total = d["total"]
    return {
        "available": True, "since": d["since"], "until": d["until"], "countries": countries,
        "codes": d["codes"], "total": {"procurements": total["procurements"], "directive": total["directive"],
                                       "buyers": total["coreBuyers"] + total["otherBuyers"], "awarded": total["awarded"],
                                       "winners": total["winners"]},
        "buyers": buyers,
        "winners": {"rows": rows, "notNamed": sorted(hidden.values(), key=lambda h: (-h["contracts"], h["country"] or "")),
                    "listed": len(listed), "total": total["winners"], "names": names, "mosaicMin": MOSAIC_MIN,
                    "ownContracts": sum(w["contracts"] for w in mine) if own is not None else None,
                    "href": f"/suppliers?cpv={','.join(codes)}&buyerCountry={','.join(countries)}"},
        "coverage": d["coverage"], "winnersFrom": d["winnersFrom"], "sources": d["sources"],
    }


def demand_buyer_href(slug: str, prefixes: list[str]) -> str:
    """A buyer's page under the report's codes (web/lib/demand.ts buyerHref)."""
    return f"/buyers/{slug}?cpv={','.join(prefixes)}"


# ------------------------------------------------------------------ section 4: open now
def open_tenders(conn, codes: list[str], profile: dict[str, Any]) -> dict[str, Any]:
    """Up to OPEN_TENDERS open notices under the codes, as /tenders lists them by default (core first, soonest deadline)."""
    from .tenders import list_tenders

    if not codes:
        return {"rows": [], "total": 0, "href": None}
    cpv = ",".join(dict.fromkeys(award_set.prefix(c) for c in codes))
    page = list_tenders(q=None, country=None, cpv=cpv, status="open", scope="relevant", goods=None, buyer=None, from_=None,
                        to=None, min_=None, max_=None, currency=None, sort=None, page=1, pageSize=OPEN_TENDERS,
                        confidence=None, cpvMain=False, notCpv=None, unit=None, conn=conn, with_meta=False)
    rows = []
    for t in page["items"]:
        clearance = bool(t["securityClearance"])
        flag = ("clearance_held" if clearance and profile.get("classified") == "yes" else
                "clearance" if clearance else "not_read")
        rows.append({"title": t["title"], "buyer": t["buyerName"], "country": t["country"], "deadline": t["deadline"],
                     "deadlineKnown": t["deadlineKnown"], "href": f"/tenders/{t['slug']}",
                     "sourceUrl": (t.get("source") or {}).get("url"), "legalBasis": t["legalBasis"], "flag": flag})
    return {"rows": rows, "total": page["total"], "totalCapped": page["totalCapped"], "href": f"/tenders?cpv={cpv}"}


def call_words(codes: list[str]) -> list[str]:
    """The product words to search the funding calls with: the first term of each group of the product-word map
    (`search_terms`, WP-98) whose codes contain a code of the report or lie under it. No model."""
    from .search_terms import groups

    prefixes = [award_set.prefix(c) for c in codes]
    out: list[str] = []
    for g in groups():
        if any(p.startswith(c) or c.startswith(p) for p in prefixes for c in g.cpv) and g.terms:
            word = " ".join(g.terms[0])
            if word not in out:
                out.append(word)
    return out[:CALL_WORDS]


def open_calls(conn, codes: list[str], profile: dict[str, Any]) -> dict[str, Any]:
    """Up to OPEN_CALLS open funding calls whose texts hold a product word of the codes (`call_words`), soonest deadline
    first, each with what the call says of who may apply (`whoMayApply`, `smeOnly`: the eligibility flag)."""
    from .funding import list_funding

    words = call_words(codes)
    seen: dict[str, dict[str, Any]] = {}
    for w in words:
        got = list_funding(q=w, programme=None, regime=None, country=None, status="open", from_=None, to=None, min_=None,
                           max_=None, currency=None, sort="deadline-asc", cascade=None, ukraine=None, uaNoFunding=None,
                           who=None, page=1, pageSize=OPEN_CALLS, conn=conn, with_meta=False)
        for c in got["items"]:
            seen.setdefault(c["id"], {**c, "word": w})
    calls = sorted(seen.values(), key=lambda c: (c["deadline"] is None, c["deadline"] or datetime.max.replace(tzinfo=timezone.utc)))
    rows = []
    for c in calls[:OPEN_CALLS]:
        if c.get("whoMayApply") == "public":
            flag = "public_only"
        elif c.get("smeOnly"):
            flag = "sme_only" if profile.get("size") != "large" else "sme_only_large"
        elif c.get("whoMayApply") == "companies":
            flag = "companies"
        else:
            flag = "not_stated"
        rows.append({"title": c["title"], "programme": c["programmeName"], "deadline": c["deadline"],
                     "rolling": c.get("rolling", False), "href": f"/funding/{c['slug']}",
                     "sourceUrl": (c.get("source") or {}).get("url"), "flag": flag, "word": c["word"]})
    return {"rows": rows, "words": words, "matched": len(calls)}


# ------------------------------------------------------------------ section 6: what is missing to qualify
# Requirement rules v1 (owner): each item names the requirement of the readiness content and the rules whose primary-source
# passages are quoted (status V, origin primary); `applies` is what those passages say about who must hold it.
#   key, requirement, quoted rules, country (None: every country), applies, a consultant decides, held keys
ITEMS: tuple[tuple[str, str | None, tuple[str, ...], str | None, str, bool, tuple[str, ...]], ...] = (
    ("RID", "REQ-RID", ("ES-RID",), "ES", "prime", False, ("RID",)),
    ("PECAL", "REQ-PECAL", ("ES-PECAL-CONTRACT",), "ES", "prime", False, ("PECAL",)),
    ("HSES", "REQ-HSES-ES", ("ES-HSES", "ES-HSEM"), "ES", "both", True, ()),
    ("HSEM", "REQ-FSC-ES", ("ES-HSEM",), "ES", "both", True, ()),
    ("AQAP2110", "REQ-AQAP2110", ("NATO-AQAP-ED",), None, "contract", False, ("AQAP2110",)),
    ("AQAP2310", "REQ-AQAP2310", ("NATO-AQAP-ED",), None, "contract", False, ("AQAP2310",)),
    ("NCAGE", "REQ-NCAGE", ("ES-NCAGE",), None, "not_stated", False, ("NCAGE",)),
    ("ISO9001", "REQ-ISO9001", ("ES-PECAL-ISO",), None, "not_stated", False, ("ISO9001",)),
    ("EN9100", "REQ-EN9100", ("Q-EN9100-FILTER",), None, "not_stated", False, ("EN9100",)),
    ("EXPORT", "REQ-EXPORT", ("EU-DUALUSE-EXPERT", "G-EXPORT-MIL"), None, "exporter", True, ()),
    ("ITAR-EAR", None, (), None, "us_origin", True, ()),
)
# ITAR / EAR: no rule of the readiness content covers US-origin parts, so the passages are kept here, verbatim from the
# official annual edition of the Code of Federal Regulations (GPO govinfo, read on 31 October 2026).
US_RULES = (
    {"ref": "15 CFR 734.3(a)(2)-(3), Export Administration Regulations (2025 edition)",
     "url": "https://www.govinfo.gov/content/pkg/CFR-2025-title15-vol2/xml/CFR-2025-title15-vol2-sec734-3.xml",
     "text": "(2) All U.S. origin items wherever located; (3) Foreign-made commodities that incorporate controlled U.S.-origin "
             "commodities [...] (ii) In quantities exceeding the de minimis levels"},
    {"ref": "22 CFR 123.9(a), International Traffic in Arms Regulations (2025 edition)",
     "url": "https://www.govinfo.gov/content/pkg/CFR-2025-title22-vol1/xml/CFR-2025-title22-vol1-sec123-9.xml",
     "text": "The written approval of the Directorate of Defense Trade Controls must be obtained before reselling, "
             "transferring, reexporting, retransferring, transshipping, or disposing of a defense article to any end-user, "
             "end-use, or destination other than as stated on the export license"},
)
ITAR_NAME = "US export rules (EAR and ITAR) on US-origin parts, software or technology"
# What v1 could not source from a primary text (no source, no rule): listed in the report, never assessed.
NOT_SOURCED = (
    {"key": "NSPA", "name": "NSPA Source File registration",
     "why": "NSPA's public pages refused an automated read (HTTP 403, a bot check) and its registration pages need a "
            "sign-in; no primary text was quoted."},
    {"key": "ISO27001", "name": "ISO/IEC 27001",
     "why": "No primary text we hold makes it a condition of defence supply; ISO's own catalogue refused an automated read."},
    {"key": "CLEARANCE", "name": "Security clearances outside Spain",
     "why": "Rules of other countries are not in v1 (Germany and others later)."},
)


def _passage(rule) -> dict[str, Any] | None:
    if rule is None or rule.status != "V" or rule.text_origin != "primary":
        return None
    text = (rule.source_text or "").split("\n\n")[0].strip()
    m = re.match(r"^\[([^\]]*)\]\s*(.*)$", text, re.S)
    ref, text = (m.group(1), m.group(2)) if m else (rule.source_ref, text)
    return {"ref": ref or rule.source_ref, "url": rule.source_url, "text": text} if text else None


def _fmt_cost(req) -> str | None:
    """A cost only when the requirement's own source is verified (status V); never a vendor range."""
    if req is None or req.status != "V" or req.cost is None or req.cost.basis == "vendor_range":
        return None
    return req.cost.text


def _fmt_days(req) -> str | None:
    if req is None or req.status != "V" or req.days is None:
        return None
    return req.days.text


def qualify(conn, profile: dict[str, Any]) -> dict[str, Any]:
    """The v1 requirement items for the company's country, each with its status, who it applies to, cost and time only where a
    verified source states them, and its quote and link; and the readiness rules' verdicts of the supply routes and EU funding."""
    from .readiness import api as readiness

    try:
        c = readiness.content(conn)
    except HTTPException:
        return {"available": False, "items": [], "verdicts": [], "notSourced": list(NOT_SOURCED)}
    rules = {r.code: r for p in c.programmes.values() for r in p.rules}
    country = profile.get("country")
    held = set(profile.get("held") or [])
    items = []
    for key, req_code, quoted, only, applies, consultant, held_keys in ITEMS:
        if only and country != only:
            continue
        req = c.requirements.get(req_code) if req_code else None
        quotes = list(US_RULES) if key == "ITAR-EAR" else [q for q in (_passage(rules.get(r)) for r in quoted) if q]
        if not quotes:
            continue                                   # no primary passage, no rule
        status = "consultant" if consultant else ("have" if held & set(held_keys) else "missing")
        items.append({"key": key, "name": ITAR_NAME if key == "ITAR-EAR" else req.name if req else key,
                      "applies": applies, "status": status, "cost": _fmt_cost(req), "time": _fmt_days(req),
                      "quotes": quotes})
    verdicts = []
    if country:
        chosen = [p for p in ("ES-MOD", "NATO-SUPPLY", "EDF", "EDIP") if p in c.programmes and (p != "ES-MOD" or country == "ES")]
        engine_profile = readiness.ProfileIn(
            country=country if country in readiness.ISO_COUNTRIES else "XX",
            handles_classified={"yes": True, "no": False}.get(profile.get("classified") or ""),
            export_intent=profile.get("exports") or None,
            us_components={"yes": True, "no": False}.get(profile.get("usComponents") or ""),
            headcount=None).to_engine()
        statuses = {code: "held" for key, code, *_ in ITEMS if code and key in held and code in c.requirements}
        out = readiness.assess_payload(c, engine_profile, statuses, chosen)
        for a in out["assessments"]:
            verdicts.append({"programme": a["programme"], "name": a["name"], "kind": a["kind"], "verdict": a["verdict"],
                             "blocking": len(a["blocking"]), "toObtain": len(a["toObtain"]), "missing": len(a["missing"]),
                             "sourceUrl": a["sourceUrl"]})
    not_sourced = [n for n in NOT_SOURCED if not (n["key"] == "CLEARANCE" and country == "ES")]
    return {"available": True, "items": items, "verdicts": verdicts, "notSourced": not_sourced,
            "rulesReviewed": c.reviewed}


# ------------------------------------------------------------------ section 7: the next 90 days
# Fixed templates, in the order printed; each has a window and is triggered by the report's own findings. `{...}` slots are
# filled from the report's data only.
STEPS: tuple[tuple[str, str, str], ...] = (
    ("codes", "Days 1-30", "Your CPV codes found no defence procurement in the countries we cover. Check the codes with the CPV "
                           "dictionary: a group code (such as 34300000) finds more than a narrow one."),
    ("broad", "Days 1-30", "Your CPV codes match too many notices for one report. Choose narrower codes and generate it again."),
    ("buyers", "Days 1-30", "Read the newest notices of the buyers in section 2, starting with {buyers}, and follow them on "
                            "DefenceGate so new tenders under your codes reach you."),
    ("open", "Days 1-30", "Open the {n} tenders in section 4 and read their documents before the first deadline ({deadline})."),
    ("calls", "Days 1-30", "Check the {n} open funding calls in section 4 against their call documents: who may apply, and the "
                           "consortium they ask for."),
    ("rid", "Days 1-30", "Apply for registration in the Registro de la Industria de Defensa (RID), the Ministry of Defence's "
                         "e-office procedure SIA 993054: it is the way into the Ministry's catalogue of suppliers."),
    ("ncage", "Days 1-30", "Request an NCAGE code; NSPA states that it is free of charge."),
    ("winners", "Days 31-60", "Contact the purchasing departments of the companies named in section 3 ({winners}): they win "
                              "these contracts and may buy parts or services for them."),
    ("iso", "Days 31-60", "Plan an ISO 9001 certification: it is the civil base of the AQAP and PECAL quality requirements."),
    ("aqap", "Days 31-60", "Ask a certification body for an AQAP 2110 gap assessment against your ISO 9001 system."),
    ("export", "Days 31-60", "Have a specialist classify your products against Annex I of Regulation (EU) 2021/821 and the "
                             "national lists of military items before you quote for a defence buyer abroad."),
    ("us", "Days 31-60", "Ask a specialist whether US-origin parts, software or technology in your products bring them under "
                         "the US EAR or ITAR."),
    ("classified", "Days 61-90", "If a contract will give you access to classified information, ask the Ministry of Defence's "
                                 "industrial security office about the HSEM and HSES clearances: a consultant decides this."),
    ("ending", "Days 61-90", "Note the end dates in section 5: when a contract ends, the buyer usually tenders again."),
    ("review", "Days 61-90", "Generate this report again to see what changed in the last three months."),
)


def steps(rep: dict[str, Any]) -> list[dict[str, str]]:
    """The 90-day plan: the templates whose trigger holds, in order, slots filled from the report."""
    m, o, q = rep["market"], rep["open"], rep["qualify"]
    status = {i["key"]: i["status"] for i in q.get("items", [])}
    p = rep["profile"]
    fill: dict[str, dict[str, Any] | None] = {}
    if not m.get("available"):
        fill["broad" if m.get("reason") == "too_broad" else "codes"] = {}
    elif not m["total"]["procurements"]:
        fill["codes"] = {}
    else:
        names = [r["name"] for b in m["buyers"][:1] for r in b["rows"][:2]]
        fill["buyers"] = {"buyers": " and ".join(names)} if names else None
    if o["tenders"]["rows"]:
        first = min((r["deadline"] for r in o["tenders"]["rows"] if r["deadline"]), default=None)
        fill["open"] = {"n": len(o["tenders"]["rows"]),
                        "deadline": first.date().isoformat() if isinstance(first, datetime) else (first or "not stated")}
    if o["calls"]["rows"]:
        fill["calls"] = {"n": len(o["calls"]["rows"])}
    if status.get("RID") == "missing":
        fill["rid"] = {}
    if status.get("NCAGE") == "missing":
        fill["ncage"] = {}
    if m.get("available") and m["winners"]["rows"]:
        fill["winners"] = {"winners": ", ".join(r["name"] for r in m["winners"]["rows"][:3])}
    if status.get("ISO9001") == "missing":
        fill["iso"] = {}
    elif status.get("ISO9001") == "have" and status.get("AQAP2110") == "missing":
        fill["aqap"] = {}
    if p.get("exports") in ("outside_eu", "within_eu", "unsure", None):
        fill["export"] = {}
    if p.get("usComponents") != "no":
        fill["us"] = {}
    if p.get("country") == "ES" and p.get("classified") in ("yes", "unsure"):
        fill["classified"] = {}
    if rep.get("ending") and rep["ending"].get("rows"):
        fill["ending"] = {}
    fill["review"] = {}
    out = []
    for key, window, text in STEPS:
        slots = fill.get(key)
        if slots is not None:
            out.append({"key": key, "window": window, "text": text.format(**slots)})
    return out


# ------------------------------------------------------------------ the whole report
def build(conn, inp: ReportIn, *, names: bool, today: date | None = None, sample: bool = False,
          brand: dict[str, Any] | None = None) -> dict[str, Any]:
    """The report for one request. `names`: the viewer is signed in (section 3 names companies under the mosaic rule).
    Pure reads; nothing of `inp` is stored or logged here."""
    today = today or datetime.now(timezone.utc).date()
    org = profile_of_org(conn, inp.org) if inp.org else None
    profile = _profile(inp, org)
    m = market(conn, profile["cpv"], profile["country"], names, today, own=_org_id(org["slug"]) if org else None)
    rep: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "sample": sample, "brand": brand,
        "profile": profile, "market": m,
        "open": {"tenders": open_tenders(conn, profile["cpv"], profile), "calls": open_calls(conn, profile["cpv"], profile)},
        "ending": None,
        "qualify": qualify(conn, profile),
    }
    rows = ending_soon(conn, profile["cpv"], list(demand.COUNTRIES), today) if profile["cpv"] else None
    rep["ending"] = None if rows is None else {"rows": rows}
    rep["steps"] = steps(rep)
    rep["sources"] = {
        "coverage": m.get("coverage") or demand.COVERAGE, "winnersFrom": m.get("winnersFrom"),
        "notes": m.get("sources") or [demand.TED_NOTE],
        "projects": "EU projects as the European Commission's CORDIS database and the European Defence Fund factsheets "
                    "state them." if profile["projects"] else None,
        "rules": "Requirement rules quoted from primary sources (Ministerio de Defensa, BOE, EUR-Lex, the US Code of Federal "
                 "Regulations); each item links to its text.",
        "disclaimer": DISCLAIMER,
    }
    return rep


# ------------------------------------------------------------------ access: quotas, pool, consented profile
def _month(today: date) -> date:
    return date(today.year, today.month, 1)


def quota(aconn, user: dict[str, Any], org: int | None, *, count: bool, today: date | None = None) -> dict[str, Any]:
    """Takes one report for the account (or tells that none is left: 402 `report_quota`). Mode A: one company once a calendar
    month (UTC), as the company report; mode B: every generation. A member of an association whose licence sets a yearly
    pool draws on the pool (calendar year, every member together) instead of the plan's monthly number. WP-124: while no
    plan is on sale nothing is counted against anyone (rows are still written, the limit is None)."""
    today = today or datetime.now(timezone.utc).date()
    month = _month(today)
    aconn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 162))", (str(user["id"]),))
    pool = aconn.execute(
        """SELECT a.id, a.sell_reports_per_year AS n FROM association_member m
             JOIN association a ON a.id = m.association_id AND a.licensed_at IS NOT NULL AND a.licensed_until > now()
            WHERE m.account_id = %s AND a.sell_reports_per_year IS NOT NULL""", (user["id"],)).fetchone()
    on_sale = billing.plans_on_sale()
    if pool:
        used = aconn.execute("SELECT count(*) AS n FROM sell_report_use WHERE association_id = %s AND month >= %s",
                             (pool["id"], date(today.year, 1, 1))).fetchone()["n"]
        limit, scope = (pool["n"] if on_sale else None), "year"
    else:
        used = aconn.execute("SELECT count(*) AS n FROM sell_report_use WHERE account_id = %s AND month = %s",
                             (user["id"], month)).fetchone()["n"]
        limit, scope = billing.report_limit(user), "month"
    again = org is not None and aconn.execute(
        "SELECT 1 FROM sell_report_use WHERE account_id = %s AND month = %s AND org_id = %s",
        (user["id"], month, org)).fetchone() is not None
    if not again and limit is not None and used >= limit:
        resets = date(today.year + 1, 1, 1) if scope == "year" else date(month.year + month.month // 12, month.month % 12 + 1, 1)
        raise AccountError(402, "report_quota",
                           f"no supplier reports left this {scope}: {used} of {limit} used; the count starts again on "
                           f"{resets.isoformat()} (UTC)")
    if count and not again:
        aconn.execute("INSERT INTO sell_report_use (account_id, month, org_id, association_id) VALUES (%s, %s, %s, %s)",
                      (user["id"], month, org, pool["id"] if pool else None))
        used += 1
    return {"used": used, "limit": limit, "left": None if limit is None else max(0, limit - used), "per": scope,
            "counted": count and not again}


def _require_open(user: dict[str, Any]) -> None:
    if not settings().company_report_open:
        raise AccountError(404, "not_open", "supplier reports are not open")
    billing.require(user, FEATURE)


LOGO_TYPES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
LOGO_MAX = 10 * 1024           # bytes; the account routes' body limit is 16 KiB (hardening.BODY_MAX), base64 included


def brand_of(aconn, user: dict[str, Any]) -> dict[str, Any] | None:
    """The Consultant's own name and logo for the cover (`branded_reports`), or None (our name and logo)."""
    if not billing.may(user, "branded_reports"):
        return None
    row = aconn.execute("SELECT u.report_name, l.type, l.data FROM app_user u LEFT JOIN report_logo l ON l.account_id = u.id "
                        "WHERE u.id = %s", (user["id"],)).fetchone()
    if not row or not (row["report_name"] or row["data"]):
        return None
    logo = f"data:{row['type']};base64,{base64.b64encode(bytes(row['data'])).decode()}" if row["data"] else None
    return {"name": row["report_name"], "logo": logo}


@router.get("/v1/sell-report/sample")
@cache_list("sell_report_sample", ttl=60 * 60)
def get_sample(conn=Depends(get_conn)):
    """The free public sample: the fictitious demo company's report, no company named in section 3, never counted. Exists
    only while reports are open (DGATE_COMPANY_REPORT_OPEN)."""
    if not settings().company_report_open:
        raise HTTPException(404, "supplier reports are not open")
    return build(conn, ReportIn(**DEMO), names=False, sample=True)


@account_router.get("/sample")
def get_named_sample(conn=Depends(get_conn), user=Depends(throttled)):
    """The same sample for a signed-in account: companies named under the mosaic rule; never counted."""
    if not settings().company_report_open:
        raise AccountError(404, "not_open", "supplier reports are not open")
    return build(conn, ReportIn(**DEMO), names=True, sample=True)


@account_router.post("")
def generate(body: ReportIn, conn=Depends(get_conn), aconn=Depends(accounts.get_conn), user=Depends(throttled)):
    """One report for the account (mode A with `org`, mode B with the form), counted (`quota`). The form is kept only with
    `consent` (one per account, replaced by the next consented one); otherwise nothing of it outlives this request."""
    _require_open(user)
    org = None
    if body.org:
        from .network_api import live_organisation

        org = live_organisation(conn, body.org)["id"]          # 404 / 410 before anything is counted
    if not body.org and not body.country:
        raise AccountError(422, "invalid", "country: the country where the company is established")
    quota(aconn, user, org, count=False)                       # refused before the work when none is left
    report = build(conn, body, names=True, brand=brand_of(aconn, user))
    used = quota(aconn, user, org, count=True)
    if body.consent and not body.org:
        aconn.execute(
            "INSERT INTO sell_profile (account_id, body) VALUES (%s, %s) "
            "ON CONFLICT (account_id) DO UPDATE SET body = EXCLUDED.body, saved_at = now()",
            (user["id"], json.dumps(body.model_dump(exclude={"consent", "org"}))))
        accounts._audit("sell_profile_saved", user["id"])
    accounts._audit("sell_report", user["id"], mode="A" if org else "B")       # O3: no field of the form
    return {**report, "quota": used}


@account_router.get("/profile")
def get_profile(aconn=Depends(accounts.get_conn), user=Depends(accounts.current)):
    """The form this account chose to keep (consent), or 404."""
    row = aconn.execute("SELECT body, saved_at FROM sell_profile WHERE account_id = %s", (user["id"],)).fetchone()
    if not row:
        raise AccountError(404, "not_found", "no supplier profile is kept for this account")
    return {"profile": row["body"], "savedAt": row["saved_at"]}


@account_router.delete("/profile", status_code=204)
def delete_profile(aconn=Depends(accounts.get_conn), user=Depends(accounts.current)):
    aconn.execute("DELETE FROM sell_profile WHERE account_id = %s", (user["id"],))
    accounts._audit("sell_profile_deleted", user["id"])


class LogoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["image/png", "image/jpeg"]
    data: str = Field(max_length=4 * (LOGO_MAX // 3 + 1))


@account_router.put("/logo", status_code=204)
def put_logo(body: LogoIn, aconn=Depends(accounts.get_conn), user=Depends(accounts.current)):
    """The Consultant's logo for the cover: a PNG or JPEG of at most LOGO_MAX bytes, checked by its first bytes (no SVG: a
    script could ride in it). Stored on the account; deleted with it."""
    billing.require(user, "branded_reports")
    try:
        raw = base64.b64decode(body.data, validate=True)
    except ValueError:
        raise AccountError(422, "invalid", "data: base64 of the image") from None
    if not raw or len(raw) > LOGO_MAX or not raw.startswith(LOGO_TYPES[body.type]):
        raise AccountError(422, "invalid", f"a PNG or JPEG image of at most {LOGO_MAX // 1024} KB")
    aconn.execute("INSERT INTO report_logo (account_id, type, data) VALUES (%s, %s, %s) ON CONFLICT (account_id) "
                  "DO UPDATE SET type = EXCLUDED.type, data = EXCLUDED.data, set_at = now()", (user["id"], body.type, raw))
    accounts._audit("report_logo_set", user["id"], bytes=len(raw))


@account_router.delete("/logo", status_code=204)
def delete_logo(aconn=Depends(accounts.get_conn), user=Depends(accounts.current)):
    aconn.execute("DELETE FROM report_logo WHERE account_id = %s", (user["id"],))
