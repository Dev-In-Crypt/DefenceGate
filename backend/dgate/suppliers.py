"""The supplier map: who has won the defence-relevant result notices of TED (WP-37).

    GET /v1/suppliers?country=&buyerCountry=&cpv=&q=   the suppliers, most contracts first
    GET /v1/suppliers/summary                          the public aggregate: by CPV division and country
    GET /v1/suppliers/{slug}                           one supplier: wins by year and CPV, buyers, the notices

What this is, and is not. It is the open segment: the winners that a buyer published in a TED result
notice (and, while switched on, a PLACSP award result) of the defence scope over the last three years.
WP-85 (owner decision of 22 October 2026): the rows are the award set of `award_set.py`, the one the
supplier report's demand answer (`demand.py`) counts, so a winner it names has a page here with the same
number of contracts under the same filters. A count is of procurements (`award_set.KEY`), not of notices;
`country` is the supplier's country, `buyerCountry` the buyer's (the demand answer's countries), and `cpv`
matches any code of a notice (before WP-85: the core scope from 2023, the main CPV code, notices counted).
TED holds only part of European defence spending (a 2025 ECIPE policy brief puts it at about a tenth; not re-checked);
most defence contracts are awarded outside it, and a supplier absent here is not a supplier that wins
nothing. Every figure on a profile is a fact from a notice, with its link; nothing is derived from several
notices into a ranking, a share or a dependency score.

The mosaic effect, and what stops it: separate facts that are each public can add up to a picture
nobody published. The map therefore (1) shows supplier-level detail only as the notices state it
(name, country, buyer, date, CPV, value of a notice with one winner), (2) names every winner that is a
legal entity, whatever its number of awards, and every group of them (WP-81, owner decision of 22 October
2026: the earlier rule that published a group only from `K_MIN` = 3 suppliers, and named a winner only from
3 awards, is lifted for legal entities; `K_MIN` is now 1), while a natural person or sole trader
(`individual_reason`) is counted and never named, never listed and never given a sum, (3) states no
ranking of suppliers by contract value, no share and no "sole source" or "single point of failure"
label, (4) honours a removal request: an organisation or a notice removed on request (`suppression`) is
out of every answer here, and (5, WP-39) serves at most `MAX_OFFSET` positions of the list, so the table
cannot be walked page by page (a narrower filter answers what lies beyond).

PLACSP (Spain's national portal, WP-60/61): its award winners are stored and served only with
DGATE_PLACSP_AWARDS_PUBLIC=true. Then an award that TED and PLACSP both publish counts once (`award_twin`,
migration 0093; `award_set.NOT_TWIN`), the other publication is listed under it, and PLACSP is credited with the
date of last update its terms ask for (`placsp_note`). Natural persons are counted, never named.

Sum of values per supplier (WP-81, owner decision of 22 October 2026, lifting the earlier "no sum of values per
supplier" for sums only; everything else above stands): `value_totals` sums, per currency and never converted, the
value of each procurement once (`value_of`: a PLACSP awarded amount without VAT of the lots naming this one winner,
else a TED value of a notice naming this one winner, `valued`; a TED+PLACSP twin pair from either copy, never both),
and says how many of the supplier's notices state no value it can be given and how many of those name several
winners. WP-95 (persona round of 23 October 2026, A1.1): each value has a kind (`award_value`: contract, framework
ceiling, estimate); only contract values are summed (`byCurrency`), ceilings and estimates are listed apart and never
added (`frameworks`, `estimates`), so a framework and its call-offs are never counted twice; the profile and the
supplier report name the largest contract values with their notices (`largest`), and a call-off row names the
framework its source says it is based on. Natural persons have no page and no sum.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .award_set import CPV_MATCH, FROM, KEY, KEY_HASH, NOT_PLACSP, PLACSP_IDS, prefix, scope, since
from .award_value import CONTRACT, ESTIMATE, FRAMEWORK
from .config import settings
from .countries import to_iso2
from .funding import get_conn, make_slug
from .listcache import cache_list
from .normalise import (
    PLACEHOLDER_AMOUNT_MAX,
    looks_like_contact,
    normalise_identifier,
    redact_emails,
)
from .suppress import not_published, removed
from .tenders import _buyer_names, _day, _id_of, _split, search_words

router = APIRouter()

# WP-81: a group (and a winner) is published from one legal-entity supplier; natural persons are never named
K_MIN = 1
# The deepest list position served (WP-39, verify2-abuse N5/N7). 4,186 suppliers were 42 requests of 100;
# nobody reads past the first few pages of a list, and a longer walk is a name, country or product-group
# search. Narrowing is the way to everything: this raises the price of copying the table, it does not make
# it impossible (the data is public in TED; the rate limit prices the rest).
MAX_OFFSET = 500
MAX_BIGINT = 9_223_372_036_854_775_807
PROFILE_NOTICES = 50
PROFILE_BUYERS = 20
# WP-87: a contract value below this (in its own currency) is shown as published but read as a unit price, not the
# contract's value: "EUR 48 over 1 contract" was a price per item. Such values are left out of every sum, and counted.
# Only a value a notice states (TED's `total` or `lot_sum`): a PLACSP awarded amount (kind `awarded`) is the contract's total
# without VAT, and a Spanish minor contract of EUR 300 is real (owner, 23 October 2026: 1,013 of 31,933 are under EUR 1,000).
SUSPECT_VALUE_MAX = 1000


def is_suspect(amount, kind: str | None, placsp: bool = False) -> bool:
    """WP-87: a contract value a notice states (not a PLACSP awarded amount) under SUSPECT_VALUE_MAX: probably a unit
    price. WP-95: only a contract value is read so; a framework ceiling or an estimate is never summed anyway."""
    return amount is not None and kind == CONTRACT and not placsp and amount < SUSPECT_VALUE_MAX


def valued(wn: str, amount: str, currency: str, kind: str) -> str:
    """WP-81: the SQL condition "this notice's value is this winner's", for a row whose value kind is not derived yet
    (WP-95): the notice names one winner (a value shared by several winners is attributed to none) and states a total
    or a sum of lots (TED's `value_kind`; PLACSP and the other national sources state the call's estimate and carry no
    kind) above the placeholder amount, with a currency."""
    return (f"({wn} = 1 AND {kind} IN ('total', 'lot_sum') AND {amount} > {PLACEHOLDER_AMOUNT_MAX} "
            f"AND {currency} IS NOT NULL)")


_AWARDED = f"(c.value_amount > {PLACEHOLDER_AMOUNT_MAX} AND c.value_currency IS NOT NULL)"
# WP-95: a contract value first, then a framework ceiling, then an estimate
RANK = {CONTRACT: 0, FRAMEWORK: 1, ESTIMATE: 2}
_RANK_SQL = f"CASE x.vk WHEN '{CONTRACT}' THEN 0 WHEN '{FRAMEWORK}' THEN 1 ELSE 2 END"


def value_of(award_id: str, twins: str) -> str:
    """WP-81: a LATERAL join giving the award row `award_id` its value as `v.va, v.vc` with its kind `v.vk` (WP-95:
    contract, framework or estimate) and `v.vp` (a PLACSP awarded amount); NULL: none it can be given. Candidates: the
    row itself and, where `twins` (an SQL boolean: the PLACSP winners are served), the current rows `award_twin_set`
    drops in its favour, so a twin pair is valued once from whichever copy states a value: a contract value before a
    ceiling before an estimate, then PLACSP's awarded amount (without VAT) before TED's, then the row itself.
    A row's value is `award.value_amount` with `award.value_kind` (the loaders and `ops/award_values` set them); a row
    without a kind is read as before WP-95: a PLACSP awarded amount is a contract value, else a TED value by `valued`,
    a total a contract value and a sum of lot estimates an estimate."""
    return f"""LEFT JOIN LATERAL (
        SELECT x.va, x.vc, x.vk, x.vp FROM (
            SELECT CASE WHEN c.value_kind IS NOT NULL OR {_AWARDED} THEN c.value_amount ELSE oc.value_amount END AS va,
                   trim(CASE WHEN c.value_kind IS NOT NULL OR {_AWARDED} THEN c.value_currency
                             ELSE oc.value_currency END) AS vc,
                   COALESCE(c.value_kind, CASE WHEN {_AWARDED} OR oc.value_kind = 'total' THEN '{CONTRACT}'
                                               ELSE '{ESTIMATE}' END) AS vk,
                   oc.source_id IN {PLACSP_IDS} AS vp, c.id = {award_id} AS own,
                   (c.value_kind IS NOT NULL OR {_AWARDED}
                    OR {valued("c.winners_in_notice", "oc.value_amount", "oc.value_currency", "oc.value_kind")}) AS ok
              FROM (SELECT {award_id} AS cid UNION ALL
                    SELECT tw.award_id FROM award_twin_set tw WHERE {twins} AND tw.preferred_id = {award_id}) ids
              JOIN award c ON c.id = ids.cid JOIN opportunity oc ON oc.id = c.opportunity_id
             WHERE (c.id = {award_id} OR (NOT oc.suppressed AND c.superseded_at IS NULL AND c.excluded_reason IS NULL))) x
         WHERE x.ok AND x.va > {PLACEHOLDER_AMOUNT_MAX} AND x.vc IS NOT NULL
         ORDER BY {_RANK_SQL}, x.vp DESC, x.own DESC
         LIMIT 1) v ON TRUE"""


def best(rows: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    """WP-95: per procurement (`k`), the row whose value stands for it: a valued row first, then by kind (`RANK`), a
    PLACSP awarded amount, the larger amount."""
    out: dict[Any, dict[str, Any]] = {}

    def order(r: dict[str, Any]) -> tuple:
        return (r["va"] is None, RANK.get(r["vk"], 3), not r.get("vp"), -(float(r["va"]) if r["va"] is not None else 0))

    for r in rows:
        if r["k"] not in out or order(r) < order(out[r["k"]]):
            out[r["k"]] = r
    return out


LARGEST = 10


def _sums(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        cur = r["vc"].strip()
        s = by.setdefault(cur, {"currency": cur, "amount": 0.0, "count": 0, "lotEstimates": 0})
        s["amount"] += float(r["va"])
        s["count"] += 1
    out = [{**s, "amount": round(s["amount"], 2)} for s in by.values()]
    out.sort(key=lambda v: (-v["count"], v["currency"]))
    return out


def largest_item(r: dict[str, Any]) -> dict[str, Any]:
    title = redact_emails(r["title_en"] or r["title_original"]) or ""
    return {"id": str(r["id"]), "slug": make_slug(r["id"], title), "noticeId": r["native_id"], "title": title,
            "buyerName": None if r["buyer_withheld"] else r["buyer_name_raw"], "publishedAt": _day(r["published_at"]),
            "amount": float(r["va"]), "currency": r["vc"].strip(), "sourceUrl": r["source_url"],
            "source": r["source_code"]}


def value_totals(rows: list[dict[str, Any]], of: int, largest: bool = False) -> dict[str, Any]:
    """The values of one supplier's procurements (WP-81; WP-95 by kind): `rows` one per procurement (`best`), each
    `{va, vc, vk, vp, shared}`, out of `of` procurements. Contract values are summed per currency, never converted, the
    largest count first (`byCurrency`); framework ceilings (`frameworks`) and estimates (`estimates`) are summed apart
    and never added to them. WP-87: a contract value under SUSPECT_VALUE_MAX that a notice states (a unit price) is in
    no sum and is counted (`suspect`). `largest`: the LARGEST largest contract values with their notices (rows carrying
    the notice columns of `largest_item`), in the currencies' order, the largest first."""
    valued_rows = [r for r in rows if r["va"] is not None]
    suspect = [r for r in valued_rows if is_suspect(float(r["va"]), r["vk"], bool(r.get("vp")))]
    unit_prices = {id(r) for r in suspect}
    contracts = [r for r in valued_rows if r["vk"] == CONTRACT and id(r) not in unit_prices]
    by = _sums(contracts)
    out: dict[str, Any] = {
        "byCurrency": by, "of": of, "withoutValue": max(of - len(valued_rows), 0),
        "shared": sum(1 for r in rows if r["va"] is None and r["shared"]), "suspect": len(suspect),
        "frameworks": _sums([r for r in valued_rows if r["vk"] == FRAMEWORK]),
        "estimates": _sums([r for r in valued_rows if r["vk"] == ESTIMATE]),
    }
    if largest:
        place = {s["currency"]: i for i, s in enumerate(by)}
        top = sorted(contracts, key=lambda r: (place[r["vc"].strip()], -float(r["va"]), r["id"]))[:LARGEST]
        out["largest"] = [largest_item(r) for r in top]
    return out


class SupplierItem(BaseModel):
    id: str
    slug: str
    name: str
    country: str
    awardCount: int
    firstYear: int | None
    lastYear: int | None
    cpvDivisions: list[str]


class SupplierPage(BaseModel):
    items: list[SupplierItem]
    total: int
    page: int
    pageSize: int
    maxOffset: int = MAX_OFFSET              # the list serves no position beyond this
    withheld: bool = False                   # WP-81: always false (a small group was withheld before)


class Count(BaseModel):
    year: int | None = None
    division: str | None = None
    awards: int


class SupplierBuyer(BaseModel):
    slug: str
    name: str
    country: str | None
    awards: int


class NoticeRef(BaseModel):
    source: str
    noticeId: str
    sourceUrl: str | None


class FrameworkRef(NoticeRef):
    """WP-95: the framework agreement a call-off is based on, with its page here."""
    slug: str


class SupplierNotice(BaseModel):
    id: str
    slug: str
    noticeId: str
    title: str
    buyerName: str | None
    buyerCountry: str | None
    publishedAt: datetime | None
    cpv: str | None
    winnersInNotice: int
    valueAmount: float | None
    valueCurrency: str | None
    # WP-87: the value is under SUSPECT_VALUE_MAX: shown as published, probably a unit price, in no sum
    valueSuspect: bool = False
    # WP-95: what the value is: contract (the contract awarded), framework (a framework agreement's ceiling) or
    # estimate (the buyer's estimate; the award states no value). Null with no value.
    valueKind: str | None = None
    # WP-95: the framework agreement this call-off states it is based on, where the source says (a PLACSP title)
    framework: FrameworkRef | None = None
    sourceUrl: str | None
    source: str = "ted"                       # where the notice shown is from: ted, es_placsp, es_placsp_agg
    alsoPublished: list[NoticeRef] = []       # the same award in the other source, counted once (WP-61)


class ValueSum(BaseModel):
    currency: str
    amount: float
    count: int                                # the procurements whose value this is
    lotEstimates: int = 0                     # WP-95: always 0 (a sum of lot estimates is an estimate, in `estimates`)


class LargestContract(BaseModel):
    """WP-95: one of a supplier's largest contract values, with its notice."""
    id: str
    slug: str
    noticeId: str
    title: str
    buyerName: str | None
    publishedAt: datetime | None
    amount: float
    currency: str
    sourceUrl: str | None
    source: str


class ValueTotals(BaseModel):
    """WP-81: the values of one supplier's procurements, summed per currency (`suppliers.value_totals`)."""
    byCurrency: list[ValueSum]
    of: int                                   # the procurements behind the sums
    withoutValue: int                         # of them, those with no value given to this winner
    shared: int                               # of those, the ones naming several winners
    suspect: int = 0                          # WP-87: of them, those whose value is under 1,000 (a unit price): in no sum
    # WP-95: framework ceilings and estimates, per currency, never added to the contract values above
    frameworks: list[ValueSum] = []
    estimates: list[ValueSum] = []
    # WP-95: the largest contract values (at most LARGEST), with their notices
    largest: list[LargestContract] = []


class UnderCodes(BaseModel):
    """WP-89: of the supplier's contracts, those with a code under the CPV codes asked (and of the buyer countries asked),
    counted as /v1/suppliers?cpv=&buyerCountry= and the supplier report's "who to approach" count them."""
    cpv: list[str]
    buyerCountries: list[str]
    contracts: int


class Supplier(SupplierItem):
    underCodes: UnderCodes | None = None
    values: ValueTotals
    byYear: list[Count]
    byCpv: list[Count]
    buyers: list[SupplierBuyer]
    notices: list[SupplierNotice]
    noticeCount: int
    namesAsStated: list[str]
    identifiers: list[str]
    attribution: str


class Group(BaseModel):
    key: str
    suppliers: int
    awards: int


class Cell(BaseModel):
    division: str
    country: str
    suppliers: int
    awards: int


class SourceNote(BaseModel):
    code: str
    name: str
    attribution: str
    lastUpdated: datetime | None = None       # the newest update stamp of what was read (PLACSP's terms ask for it)


class Summary(BaseModel):
    kMin: int
    since: str
    noticesRead: int
    noticesWithSupplier: int
    suppliers: int
    awards: int
    skippedNaturalPersons: int
    firstPublished: datetime | None
    lastPublished: datetime | None
    byCpv: list[Group]
    byCountry: list[Group]
    cells: list[Cell]
    suppressedGroups: int
    coverage: str
    sources: list[SourceNote] = []


COVERAGE = ("Winners named in TED result notices of the defence-relevant scope, published in the last three years. TED holds "
            "only part of European defence spending (a 2025 ECIPE policy brief puts it at about a tenth; we have not re-checked "
            "that figure); contracts awarded outside TED are not in this map, and a supplier absent here may win many.")
# With the PLACSP winners on the map (DGATE_PLACSP_AWARDS_PUBLIC, WP-61).
COVERAGE_WITH_PLACSP = (
    "Winners named in TED result notices of the defence-relevant scope, and in the award results of Spain's national "
    "procurement portal (PLACSP, Plataforma de Contratación del Sector Público), published in the last three years; an "
    "award published in both "
    "is counted once. TED holds only part of European defence spending (a 2025 ECIPE policy brief puts it at about a "
    "tenth; we have not re-checked that figure); contracts awarded outside TED and PLACSP are not in this map, and a "
    "supplier absent here may win many. Winners that are natural persons are counted, never named.")
TED_NOTE = {"code": "ted", "name": "TED (Tenders Electronic Daily)",
            "attribution": "Source: TED (Tenders Electronic Daily), © European Union."}


def placsp_note(conn, where: str = "TRUE", params: tuple | dict = ()) -> dict[str, Any] | None:
    """The PLACSP attribution its publisher's terms ask for (docs/sources/es_placsp.md): the source, as the source
    row of migration 0092 words it, and the date of the last update of what was read (the newest entry stamp of the
    PLACSP award results behind the rows `where` selects, over `award_notice n` and `opportunity o`). None when no
    PLACSP award result is behind them."""
    row = conn.execute(
        f"""SELECT max(n.payload_updated_at) AS updated, count(*) AS n FROM award_notice n
              JOIN opportunity o ON o.id = n.opportunity_id
             WHERE n.payload_hash IS NOT NULL AND NOT ({NOT_PLACSP}) AND {where}""", params).fetchone()
    if not row["n"]:
        return None
    src = conn.execute("SELECT attribution FROM source WHERE code = 'es_placsp_awards'").fetchone()
    return {"code": "es_placsp", "name": "PLACSP (Plataforma de Contratación del Sector Público, Spain)",
            "attribution": (src["attribution"] if src else "Origen de los datos: Ministerio de Hacienda") + ".",
            "lastUpdated": row["updated"]}


def _name(row: dict[str, Any]) -> str:
    return (row.get("shown") or row["canonical_name"]).strip()


# The spelling of a supplier's name we show: the one most notices use, a mixed-case one before a
# capitals-only one, then alphabetical. Only the page's rows are asked.
# The ids as an array, not an OR: the OR read the whole award table once per row of the page (WP-75).
SHOWN = """(SELECT x.name_as_stated FROM award x
             WHERE x.organisation_id = ANY(ARRAY(SELECT m.id UNION ALL
                                                 SELECT id FROM organisation WHERE merged_into = m.id)){placsp}
             GROUP BY 1 ORDER BY count(*) DESC, (x.name_as_stated = upper(x.name_as_stated)), 1 LIMIT 1)"""
# While the PLACSP winners are off the map, their spelling of a name is not shown either (WP-61).
_SHOWN_NOT_PLACSP = ("\n               AND NOT EXISTS (SELECT 1 FROM opportunity xo WHERE xo.id = x.opportunity_id AND "
                     + NOT_PLACSP.replace("o.source_id NOT IN", "xo.source_id IN") + ")")


def shown() -> str:
    return SHOWN.format(placsp="" if settings().placsp_awards_public else _SHOWN_NOT_PLACSP)


def _countries(value: str | None, name: str) -> list[str]:
    out: list[str] = []
    for given in _split(value, name, max_length=60):
        # A code (DE), a three-letter code (DEU) or an English name (Germany): all read as the alpha-2 code stored.
        iso2 = to_iso2(given)
        if iso2 is None:
            raise HTTPException(422, f"{name}: '{given[:40]}' is not a country; use a code (DE, DEU) or an English name (Germany)")
        out.append(iso2)
    return out


CPV_PART = re.compile(r"^[0-9]{2,8}$")


def _filters(q: str | None, country: str | None, cpv: str | None,
             buyer_country: str | None = None) -> tuple[list[str], dict[str, Any]]:
    """The filters over the award set (`award_set`), with the window as a parameter. `country` is the supplier's
    country as the notice states it; `buyerCountry` the buyer's (the notice's), as the demand answer's countries;
    `cpv` any code of the notice under a prefix, an 8-digit code standing for its level (`award_set.prefix`), as the
    demand answer reads its codes."""
    where: list[str] = []
    params: dict[str, Any] = {"since": since()}
    words = search_words((q or "").replace("\x00", "").strip())
    for i, w in enumerate(words):
        # Each word begins a word of the supplier's normalised name or of a name as stated.
        where.append(f"(dg_fold(org.canonical_name) LIKE dg_word_pattern(%(q{i})s) "
                     f"OR dg_fold(a.name_as_stated) LIKE dg_word_pattern(%(q{i})s))")
        params[f"q{i}"] = w
    if supplier := _countries(country, "country"):
        where.append("a.supplier_country = ANY(%(supplier)s)")
        params["supplier"] = supplier
    if buyer := _countries(buyer_country, "buyerCountry"):
        where.append("o.country = ANY(%(buyer)s)")
        params["buyer"] = buyer
    parts = _split(cpv, "cpv", max_length=8)
    if parts:
        if any(not CPV_PART.match(p) for p in parts):
            raise HTTPException(422, "cpv: CPV codes or their leading part, 2 to 8 digits")
        where.append(CPV_MATCH)
        params["prefixes"] = list(dict.fromkeys(prefix(p) if len(p) == 8 else p for p in parts))
    return where, params


def _item(r: dict[str, Any]) -> dict[str, Any]:
    name = _name(r)
    return {"id": str(r["id"]), "slug": make_slug(r["id"], name), "name": name,
            "country": r["country"], "awardCount": r["n"],
            "firstYear": r["first_year"], "lastYear": r["last_year"],
            "cpvDivisions": sorted(d for d in (r["divisions"] or []) if d)[:6]}


@router.get("/v1/suppliers", response_model=SupplierPage)
@cache_list("suppliers", ttl=5 * 60)
def list_suppliers(
    q: str | None = Query(None, max_length=100),
    country: str | None = Query(None, max_length=200),
    cpv: str | None = Query(None, max_length=200),
    buyerCountry: str | None = Query(None, max_length=200),
    sort: str = Query("awards", pattern="^(awards|name)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=100),
    conn=Depends(get_conn),
):
    offset = (page - 1) * pageSize
    if offset >= MAX_OFFSET:
        raise HTTPException(422, f"page: the list serves the first {MAX_OFFSET} suppliers only; search by name, "
                                 "country or product group")
    # WP-81: a country or product-group filter lists every supplier it selects, however few (the WP-39 "withheld"
    # answer for a group of fewer than 3 is lifted by the owner; `withheld` stays in the answer, always false)
    where, params = _filters(q, country, cpv, buyerCountry)
    cond = " AND ".join([scope()] + where)
    order = "canonical_name, id" if sort == "name" else "n DESC, canonical_name, id"
    # The page is cut first and the shown spelling asked for its 20 rows only (asked before the cut it took a
    # second at page 40: 4,188 suppliers on 18 October 2026). `n`: procurements won (`award_set.KEY`).
    rows = conn.execute(
        f"""WITH base AS (
              SELECT org.id, org.country, org.canonical_name,
                     count(DISTINCT {KEY_HASH}) AS n,
                     extract(year FROM min(COALESCE(o.published_at, o.notice_date)))::int AS first_year,
                     extract(year FROM max(COALESCE(o.published_at, o.notice_date)))::int AS last_year,
                     array_agg(DISTINCT left(a.cpv_main, 2)) AS divisions
                {FROM} WHERE {cond}
               GROUP BY org.id, org.country, org.canonical_name),
            m AS (SELECT base.*, count(*) OVER () AS total_rows FROM base ORDER BY {order}
                  LIMIT %(limit)s OFFSET %(offset)s)
            SELECT m.*, {shown()} AS shown FROM m ORDER BY {order}""",
        {**params, "limit": min(pageSize, MAX_OFFSET - offset), "offset": offset}).fetchall()
    total = rows[0]["total_rows"] if rows else 0
    if not rows and page > 1:
        total = conn.execute(
            f"SELECT count(DISTINCT org.id) AS n {FROM} WHERE {cond}", params).fetchone()["n"]
    return {"items": [_item(r) for r in rows], "total": total, "page": page, "pageSize": pageSize,
            "maxOffset": MAX_OFFSET, "withheld": False}


@router.get("/v1/suppliers/summary", response_model=Summary)
@cache_list("suppliers-summary", ttl=30 * 60)
def supplier_summary(conn=Depends(get_conn)):
    # One pass over the set's rows for the head and every group (WP-75: five passes cost 1.5 s with the PLACSP
    # winners on). A win is a supplier and a procurement (`KEY`), as the list counts it. WP-85: the list's CPV
    # filter reads every code of a notice, so the groups do too: a row is in every division its notice has a code
    # in (a win in two divisions is in both). g (GROUPING bits) 3: the head, over every row; 1: by CPV division;
    # 2: by country; 0: the cells. The groups count the rows with a CPV only (c_*). A win is counted by one bigint,
    # `pair` (a distinct over a (org, key) record sorted three times slower: 1.3 s against 0.4 s on 67,000 rows).
    # ponytail: a 64-bit hash of the pair; a collision (about 1 in 10^10 at 100,000 wins) would undercount one win.
    since_day = since()
    rows = conn.execute(
        f"""WITH r AS MATERIALIZED (
                SELECT org.id AS org, {KEY_HASH} AS key, hashtextextended(org.id || ' ' || {KEY}, 0) AS pair,
                       a.supplier_country AS country, o.cpv_codes, COALESCE(o.published_at, o.notice_date) AS day
                  {FROM} WHERE {scope()})
            SELECT GROUPING(x.division, r.country) AS g, x.division, r.country,
                   count(DISTINCT r.key) AS notices, count(DISTINCT r.org) AS suppliers,
                   count(DISTINCT r.pair) AS awards, min(r.day) AS first_p, max(r.day) AS last_p,
                   count(DISTINCT r.org) FILTER (WHERE x.division IS NOT NULL) AS c_suppliers,
                   count(DISTINCT r.pair) FILTER (WHERE x.division IS NOT NULL) AS c_awards
              FROM r LEFT JOIN LATERAL (SELECT DISTINCT left(c, 2) AS division FROM unnest(r.cpv_codes) c) x ON TRUE
             GROUP BY GROUPING SETS ((), (x.division), (r.country), (x.division, r.country))
             ORDER BY g, CASE WHEN GROUPING(x.division, r.country) = 0
                              THEN count(DISTINCT r.org) FILTER (WHERE x.division IS NOT NULL) END DESC,
                      c_awards DESC, division, country""", {"since": since_day}).fetchall()
    [head] = [r for r in rows if r["g"] == 3]
    sets = {g: [{"key": r["division"] if g == 1 else r["country"], "division": r["division"],
                 "country": r["country"], "suppliers": r["c_suppliers"], "awards": r["c_awards"]}
                for r in rows if r["g"] == g and r["c_awards"]] for g in (0, 1, 2)}
    public = settings().placsp_awards_public
    if public:
        # A person skipped in both the TED and the PLACSP publication of one procedure is one person: per procedure
        # the larger of the two counts, not their sum (WP-61).
        read = conn.execute(
            """SELECT COALESCE(sum(n), 0) AS n, COALESCE(sum(persons), 0) AS persons FROM (
                 SELECT count(*) AS n,
                        greatest(sum(n.skipped_person) FILTER (WHERE s.code = 'ted'),
                                 sum(n.skipped_person) FILTER (WHERE s.code <> 'ted')) AS persons
                   FROM award_notice n JOIN opportunity o ON o.id = n.opportunity_id
                   JOIN source s ON s.id = o.source_id
                  GROUP BY coalesce(o.procedure_identifier, 'notice ' || o.id)) g""").fetchone()
    else:
        read = conn.execute(
            f"""SELECT count(*) AS n, COALESCE(sum(n.skipped_person), 0) AS persons FROM award_notice n
                  JOIN opportunity o ON o.id = n.opportunity_id
                 WHERE {NOT_PLACSP}""").fetchone()

    def groups(g: int) -> tuple[list[dict[str, Any]], int]:
        kept = [r for r in sets[g] if r["suppliers"] >= K_MIN and r["key"]]
        return kept, len(sets[g]) - len(kept)

    by_cpv, hidden_cpv = groups(1)
    by_country, hidden_country = groups(2)
    cells = [{k: r[k] for k in ("division", "country", "suppliers", "awards")}
             for r in sets[0] if r["suppliers"] >= K_MIN][:300]
    total_cells = len(sets[0])
    note = placsp_note(conn) if public else None
    return {
        "kMin": K_MIN, "since": since_day.isoformat(), "noticesRead": read["n"],
        "noticesWithSupplier": head["notices"], "suppliers": head["suppliers"],
        "awards": head["awards"], "skippedNaturalPersons": int(read["persons"]),
        "firstPublished": _day(head["first_p"]), "lastPublished": _day(head["last_p"]),
        "byCpv": [{"key": r["key"], "suppliers": r["suppliers"], "awards": r["awards"]} for r in by_cpv],
        "byCountry": [{"key": r["key"], "suppliers": r["suppliers"], "awards": r["awards"]} for r in by_country],
        "cells": [dict(r) for r in cells],
        "suppressedGroups": hidden_cpv + hidden_country + (total_cells - len(cells)),
        # PLACSP is named once a PLACSP award result is behind the map, not merely because the switch is on.
        "coverage": COVERAGE_WITH_PLACSP if note else COVERAGE,
        "sources": [TED_NOTE] + ([note] if note else []),
    }


@router.get("/v1/suppliers/{slug}", response_model=Supplier)
def get_supplier(slug: str, cpv: str | None = Query(None, max_length=200),
                 buyerCountry: str | None = Query(None, max_length=200), conn=Depends(get_conn)):
    org_id = _id_of(slug, "supplier")
    # WP-89: read (and refused when unreadable) before anything is counted
    under_where, under_params = _filters(None, None, cpv, buyerCountry) if cpv else ([], {})
    org = conn.execute(
        "SELECT id, canonical_name, display_name, country, suppressed, merged_into, individual_reason FROM organisation WHERE id = %s",
        (org_id,)).fetchone()
    if org and org["merged_into"] is not None:
        org_id = org["merged_into"]
        org = conn.execute(
            "SELECT id, canonical_name, display_name, country, suppressed, merged_into, individual_reason FROM organisation "
            "WHERE id = %s", (org_id,)).fetchone()
    if org and org["suppressed"]:
        raise removed()
    if org and org["individual_reason"]:
        raise not_published()
    # The award rows of the organisation and of those merged into it, read by index (WP-75): `org.id` alone is
    # a join result, and every award was read to find a supplier's (0.1 s a statement, nine statements).
    base = (f"{FROM} WHERE {scope()} AND org.id = %(org)s AND a.organisation_id = ANY(ARRAY("
            "SELECT %(org)s::bigint UNION ALL SELECT id FROM organisation WHERE merged_into = %(org)s))")
    p = {"org": org_id, "since": since()}
    twins = "TRUE" if settings().placsp_awards_public else "FALSE"     # WP-81: value a twin pair from either copy
    head = conn.execute(
        f"""SELECT count(DISTINCT {KEY_HASH}) AS n,
                   extract(year FROM min(COALESCE(o.published_at, o.notice_date)))::int AS first_year,
                   extract(year FROM max(COALESCE(o.published_at, o.notice_date)))::int AS last_year
              {base}""", p).fetchone()
    if not org or not head["n"]:
        raise HTTPException(404, "no such supplier")
    # WP-85: a procurement counts once (`award_set.KEY`), in the year and main CPV division of its newest notice, so
    # the years and the divisions each add up to the count
    per = conn.execute(
        f"""SELECT DISTINCT ON ({KEY_HASH}) extract(year FROM COALESCE(o.published_at, o.notice_date))::int AS year,
                   left(a.cpv_main, 2) AS division
              {base} ORDER BY {KEY_HASH}, COALESCE(o.published_at, o.notice_date) DESC NULLS LAST, o.id DESC""",
        p).fetchall()
    by_year = sorted(Counter(r["year"] for r in per).items(), key=lambda x: -(x[0] or 0))
    by_cpv = sorted(Counter(r["division"] for r in per if r["division"]).items(), key=lambda x: (-x[1], x[0]))
    # WP-87: per buyer family (the buyer list's unit): two organisation rows of one body were two rows of the table
    # ("Intendente de las Palmas" twice)
    buyer_rows = conn.execute(
        f"""SELECT dgate_buyer_head(o.buyer_org_id) AS id, count(DISTINCT {KEY_HASH}) AS awards
              {base} AND o.buyer_org_id IS NOT NULL AND NOT o.buyer_withheld
             GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {PROFILE_BUYERS}""", p).fetchall()
    # WP-87: one row per contract (`KEY`), as the count is: a second notice of the same procurement (Hensoldt Sensors:
    # 474829-2024 and 467138-2024, one Lithuanian contract) is listed under the first, not as a 13th row of 12.
    # WP-95: every row of the supplier in one statement: the newest notices, the sums by kind and the largest contracts
    rows = conn.execute(
        f"""SELECT o.id, o.native_id, o.title_en, o.title_original, o.buyer_name_raw, o.buyer_withheld, o.country,
                   COALESCE(o.published_at, o.notice_date) AS published_at, a.cpv_main, a.winners_in_notice, v.va, v.vc, v.vk, v.vp,
                   a.winners_in_notice > 1 AS shared, o.source_url, a.id AS award_id,
                   (SELECT code FROM source WHERE id = o.source_id) AS source_code, {KEY_HASH} AS k,
                   (SELECT n.framework_id FROM award_notice n WHERE n.opportunity_id = o.id) AS framework_id
              {FROM} {value_of("a.id", twins)} {base.removeprefix(FROM)} ORDER BY 8 DESC NULLS LAST, o.id DESC""",
        p).fetchall()
    notices: list[dict[str, Any]] = []
    same: dict[int, list[dict[str, Any]]] = {}
    first: dict[int, dict[str, Any]] = {}
    for r in rows:
        if r["k"] in first:
            if r["native_id"] != first[r["k"]]["native_id"]:
                same[first[r["k"]]["award_id"]].append(
                    {"source": r["source_code"], "noticeId": r["native_id"], "sourceUrl": r["source_url"]})
            continue
        if len(notices) < PROFILE_NOTICES:
            first[r["k"]] = r
            same[r["award_id"]] = []
            notices.append(r)
    # WP-81: each procurement once (the profile's count), valued by `value_of` (the notice rows use the same)
    sums = list(best(rows).values())
    frameworks = framework_refs(conn, [r["framework_id"] for r in notices if r["framework_id"]])
    stated = conn.execute(
        f"""SELECT a.name_as_stated AS v, count(*) AS n {base} GROUP BY 1
             ORDER BY 2 DESC, (a.name_as_stated = upper(a.name_as_stated)), 1 LIMIT 5""",
        p).fetchall()
    idents = conn.execute(
        f"""SELECT a.identifier_as_stated AS v, count(*) AS n {base} AND a.identifier_as_stated IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 30""", p).fetchall()
    numbers: dict[str, str] = {}              # one spelling of each number: "DE 129 415 943" is "DE129415943"
    for r in idents:
        # Only a number-shaped value is a registration number. A telephone number or an address typed into the
        # field is contact data (verify2-abuse N1), a word is nothing: neither is shown, whatever is stored.
        key = None if looks_like_contact(r["v"]) else normalise_identifier(r["v"], org["country"])
        if key:
            numbers.setdefault(key, redact_emails(r["v"]))
    buyer_ids = [r["id"] for r in buyer_rows]
    names = _buyer_names(conn, buyer_ids)
    countries = {r["id"]: r["country"] for r in conn.execute(
        "SELECT id, country FROM organisation WHERE id = ANY(%s)", (buyer_ids,)).fetchall()} if buyer_ids else {}
    item = _item({**org, "n": head["n"], "first_year": head["first_year"], "last_year": head["last_year"],
                  "shown": stated[0]["v"], "divisions": [d for d, _ in by_cpv]})
    public = settings().placsp_awards_public
    also: dict[int, list[dict[str, Any]]] = {}
    attribution = TED_NOTE["attribution"] + " Winners as named in each result notice."
    if public:
        # Provenance of an award counted once: the other publication of it, under the one shown. A notice removed
        # on request is not named.
        for r in conn.execute(
                """SELECT tw.preferred_id, s.code, o.native_id, o.source_url FROM award_twin_set tw
                     JOIN award d ON d.id = tw.award_id JOIN opportunity o ON o.id = d.opportunity_id
                     JOIN source s ON s.id = o.source_id
                    WHERE tw.preferred_id = ANY(%s) AND NOT o.suppressed
                      AND d.superseded_at IS NULL AND d.excluded_reason IS NULL    -- as the view: current rows only
                    ORDER BY o.published_at NULLS LAST, o.id""", ([r["award_id"] for r in notices],)).fetchall():
            also.setdefault(r["preferred_id"], []).append(
                {"source": r["code"], "noticeId": r["native_id"], "sourceUrl": r["source_url"]})
        note = placsp_note(conn, f"""o.id IN (SELECT a.opportunity_id {base})""", p)
        if note:
            # TED is named either way: a win shown from PLACSP lists its TED publication under it.
            day = f", as last updated on {note['lastUpdated']:%Y-%m-%d}" if note["lastUpdated"] else ""
            attribution = (TED_NOTE["attribution"] + " " + note["attribution"].rstrip(".")
                           + f"{day}. Winners as named in each notice; natural persons are never named.")
    out_notices = []
    for r in notices:
        title = redact_emails(r["title_en"] or r["title_original"]) or ""
        out_notices.append({
            "id": str(r["id"]), "slug": make_slug(r["id"], title), "noticeId": r["native_id"], "title": title,
            "buyerName": None if r["buyer_withheld"] else r["buyer_name_raw"], "buyerCountry": r["country"],
            "publishedAt": _day(r["published_at"]), "cpv": r["cpv_main"], "winnersInNotice": r["winners_in_notice"],
            "valueAmount": float(r["va"]) if r["va"] is not None else None,
            "valueCurrency": r["vc"].strip() if r["va"] is not None else None,
            "valueSuspect": is_suspect(r["va"], r["vk"], bool(r["vp"])),
            "valueKind": r["vk"] if r["va"] is not None else None,
            "framework": frameworks.get(r["framework_id"]),
            "sourceUrl": r["source_url"], "source": r["source_code"],
            "alsoPublished": also.get(r["award_id"], []) + [
                x for x in same.get(r["award_id"], [])
                if x["noticeId"] not in {y["noticeId"] for y in also.get(r["award_id"], [])}]})
    under = None
    if under_where:
        n = conn.execute(f"SELECT count(DISTINCT {KEY_HASH}) AS n {base} AND {' AND '.join(under_where)}",
                         {**p, **{k: v for k, v in under_params.items() if k != "since"}}).fetchone()["n"]
        under = {"cpv": under_params["prefixes"], "buyerCountries": under_params.get("buyer", []), "contracts": n}
    return {
        **item,
        "underCodes": under,
        "values": value_totals(sums, head["n"], largest=True),
        "byYear": [{"year": y, "awards": n} for y, n in by_year],
        "byCpv": [{"division": d, "awards": n} for d, n in by_cpv],
        "buyers": [{"slug": make_slug(i, names.get(i) or ""), "name": names.get(i) or "Buyer",
                    "country": countries.get(i), "awards": r["awards"]}
                   for r in buyer_rows for i in [r["id"]] if names.get(i)],
        "notices": out_notices, "noticeCount": head["n"],
        "namesAsStated": [redact_emails(r["v"]) for r in stated], "identifiers": list(numbers.values())[:3],
        "attribution": attribution,
    }


def framework_refs(conn, ids: list[int]) -> dict[int, dict[str, Any]]:
    """WP-95: the framework notices of call-offs, by id, as `NoticeRef`s with their page."""
    if not ids:
        return {}
    return {r["id"]: {"source": r["code"], "noticeId": r["native_id"], "sourceUrl": r["source_url"],
                      "slug": make_slug(r["id"], redact_emails(r["title_en"] or r["title_original"]) or "")}
            for r in conn.execute(
                """SELECT o.id, o.native_id, o.source_url, o.title_en, o.title_original, s.code FROM opportunity o
                     JOIN source s ON s.id = o.source_id
                    WHERE o.id = ANY(%s) AND o.is_defence AND NOT o.suppressed""", (sorted(set(ids)),)).fetchall()}


# ----------------------------------------------------------------- WP-90: a buyer's top suppliers

BUYER_TOP = 10


class BuyerSupplier(BaseModel):
    slug: str
    name: str
    country: str | None
    awards: int


class BuyerSuppliers(BaseModel):
    items: list[BuyerSupplier]
    # Suppliers (legal entities) and contracts (`award_set.KEY`) of the buyer in the award set, all of them.
    suppliers: int
    contracts: int
    attribution: str


@router.get("/v1/buyers/{slug}/suppliers", response_model=BuyerSuppliers)
@cache_list("buyer-suppliers", ttl=30 * 60)
def buyer_suppliers(slug: str, conn=Depends(get_conn)):
    """Who won this buyer's contracts (WP-90, the analyst's "top suppliers of this buyer"): the award set of the
    supplier map (`award_set.scope`: defence scope, last three years, legal entities only, a TED+PLACSP twin once),
    under the buyer's family (every organisation row of the body, migration 0055), most contracts first, at most
    BUYER_TOP. A natural person is never named (`award_set.WINNERS`); a buyer removed on request has none."""
    org_id = _id_of(slug, "buyer")
    ids = conn.execute("SELECT dgate_family_ids(%s) AS ids", (org_id,)).fetchone()["ids"] or [org_id]
    p = {"since": since(), "ids": list(ids), "limit": BUYER_TOP}
    own = "o.buyer_org_id = ANY(%(ids)s) AND NOT o.buyer_withheld"
    rows = conn.execute(
        f"""WITH base AS (
              SELECT org.id, org.country, org.canonical_name, count(DISTINCT {KEY_HASH}) AS n
                {FROM} WHERE {scope()} AND {own}
               GROUP BY org.id, org.country, org.canonical_name),
            m AS (SELECT base.*, count(*) OVER () AS total_rows FROM base ORDER BY n DESC, canonical_name, id
                  LIMIT %(limit)s)
            SELECT m.*, {shown()} AS shown FROM m ORDER BY n DESC, canonical_name, id""", p).fetchall()
    contracts = conn.execute(f"SELECT count(DISTINCT {KEY_HASH}) AS n {FROM} WHERE {scope()} AND {own}",
                             p).fetchone()["n"]
    note =placsp_note(conn, f"o.id IN (SELECT a.opportunity_id {FROM} WHERE {scope()} AND {own})", p) if (
        settings().placsp_awards_public) else None
    day = f", as last updated on {note['lastUpdated']:%Y-%m-%d}" if note and note["lastUpdated"] else ""
    attribution = (TED_NOTE["attribution"] + (f" {note['attribution'].rstrip('.')}{day}." if note else "")
                   + " Winners as named in each notice; natural persons are never named.")
    return {"items": [{"slug": make_slug(r["id"], _name(r)), "name": _name(r), "country": r["country"],
                       "awards": r["n"]} for r in rows],
            "suppliers": rows[0]["total_rows"] if rows else 0, "contracts": contracts, "attribution": attribution}
