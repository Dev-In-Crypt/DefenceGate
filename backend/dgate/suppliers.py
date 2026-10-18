"""The supplier map: who has won the defence-relevant result notices of TED (WP-37).

    GET /v1/suppliers?country=&cpv=&q=     the suppliers, most awards first
    GET /v1/suppliers/summary              the public aggregate: by CPV division and country
    GET /v1/suppliers/{slug}               one supplier: wins by year and CPV, buyers, the notices

What this is, and is not. It is the open segment: the winners that a buyer published in a TED result
notice of the defence-relevant core scope, from 2023 on (the first year in which eForms notices name
a winner as data). TED holds only part of European defence spending (a 2025 ECIPE policy brief puts it at about a tenth; not re-checked);
most defence contracts are awarded outside it, and a supplier absent here is not a supplier that wins
nothing. Every figure on a profile is a fact from a notice, with its link; nothing is derived from several
notices into a ranking, a share or a dependency score.

The mosaic effect, and what stops it: separate facts that are each public can add up to a picture
nobody published. The map therefore (1) shows supplier-level detail only as the notices state it
(name, country, buyer, date, CPV, value of a notice with one winner), (2) publishes aggregates only
for groups of at least `K_MIN` suppliers, so that no figure describes one supplier's position,
(3) states no ranking of suppliers by contract value, no "sole source" or "single point of failure"
label and no sum of values per supplier, and (4) honours a removal request: an organisation or a
notice removed on request (`suppression`) is out of every answer here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .classify import CORE_SQL
from .funding import get_conn, make_slug
from .listcache import cache_list
from .normalise import PLACEHOLDER_AMOUNT_MAX, normalise_identifier, redact_emails
from .suppress import removed
from .tenders import _buyer_names, _day, _id_of, _split, search_words

router = APIRouter()

K_MIN = 3                      # an aggregate group needs this many suppliers to be published
MAX_BIGINT = 9_223_372_036_854_775_807
SINCE = "2023-01-01"
PROFILE_NOTICES = 50
PROFILE_BUYERS = 20

FROM = """FROM award a
          JOIN opportunity o ON o.id = a.opportunity_id
          JOIN organisation raw_org ON raw_org.id = a.organisation_id
          JOIN organisation org ON org.id = COALESCE(raw_org.merged_into, raw_org.id)"""
SCOPE = f"o.is_defence AND NOT o.suppressed AND {CORE_SQL} AND NOT org.suppressed AND NOT raw_org.suppressed"


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


class Count(BaseModel):
    year: int | None = None
    division: str | None = None
    awards: int


class SupplierBuyer(BaseModel):
    slug: str
    name: str
    country: str | None
    awards: int


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
    sourceUrl: str | None


class Supplier(SupplierItem):
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


COVERAGE = ("Winners named in TED result notices of the defence-relevant scope, from 2023. TED holds only part of "
            "European defence spending (a 2025 ECIPE policy brief puts it at about a tenth; we have not re-checked "
            "that figure); contracts awarded outside TED are not in this map, and a supplier absent here may win many.")


def _name(row: dict[str, Any]) -> str:
    return (row.get("shown") or row["canonical_name"]).strip()


# The spelling of a supplier's name we show: the one most notices use, a mixed-case one before a
# capitals-only one, then alphabetical. Only the page's rows are asked.
SHOWN = """(SELECT x.name_as_stated FROM award x
             WHERE x.organisation_id = m.id
                OR x.organisation_id IN (SELECT id FROM organisation WHERE merged_into = m.id)
             GROUP BY 1 ORDER BY count(*) DESC, (x.name_as_stated = upper(x.name_as_stated)), 1 LIMIT 1)"""


def _filters(q: str | None, country: str | None, cpv: str | None) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    words = search_words((q or "").replace("\x00", "").strip())
    if words:
        # Each word begins a word of the supplier's normalised name or of a name as stated.
        like = ("(dg_fold(org.canonical_name) LIKE dg_word_pattern(%s) "
                "OR dg_fold(a.name_as_stated) LIKE dg_word_pattern(%s))")
        where.append(" AND ".join([like] * len(words)))
        for w in words:
            params += [w, w]
    countries = _split(country, "country", upper=True, max_length=2)
    if countries:
        where.append("a.supplier_country = ANY(%s)")
        params.append(countries)
    prefixes = _split(cpv, "cpv", max_length=8)
    if prefixes:
        where.append("(" + " OR ".join(["a.cpv_main LIKE %s"] * len(prefixes)) + ")")
        params += [f"{p}%" for p in prefixes]
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
    sort: str = Query("awards", pattern="^(awards|name)$"),
    page: int = Query(1, ge=1, le=1000),
    pageSize: int = Query(20, ge=1, le=100),
    conn=Depends(get_conn),
):
    where, params = _filters(q, country, cpv)
    cond = " AND ".join([SCOPE] + where)
    order = "canonical_name, id" if sort == "name" else "n DESC, canonical_name, id"
    # The page is cut first and the shown spelling asked for its 20 rows only (asked before the cut it took a
    # second at page 40: 4,188 suppliers on 18 October 2026).
    rows = conn.execute(
        f"""WITH base AS (
              SELECT org.id, org.country, org.canonical_name,
                     count(DISTINCT a.opportunity_id) AS n,
                     extract(year FROM min(o.published_at))::int AS first_year,
                     extract(year FROM max(o.published_at))::int AS last_year,
                     array_agg(DISTINCT left(a.cpv_main, 2)) AS divisions
                {FROM} WHERE {cond}
               GROUP BY org.id, org.country, org.canonical_name),
            m AS (SELECT base.*, count(*) OVER () AS total_rows FROM base ORDER BY {order} LIMIT %s OFFSET %s)
            SELECT m.*, {SHOWN} AS shown FROM m ORDER BY {order}""",
        params + [pageSize, (page - 1) * pageSize]).fetchall()
    total = rows[0]["total_rows"] if rows else 0
    if not rows and page > 1:
        total = conn.execute(
            f"SELECT count(DISTINCT org.id) AS n {FROM} WHERE {cond}", params).fetchone()["n"]
    return {"items": [_item(r) for r in rows], "total": total, "page": page, "pageSize": pageSize}


@router.get("/v1/suppliers/summary", response_model=Summary)
@cache_list("suppliers-summary", ttl=30 * 60)
def supplier_summary(conn=Depends(get_conn)):
    head = conn.execute(
        f"""SELECT count(DISTINCT a.opportunity_id) AS notices, count(DISTINCT org.id) AS suppliers,
                   count(*) AS awards, min(o.published_at) AS first_p, max(o.published_at) AS last_p
              {FROM} WHERE {SCOPE}""").fetchone()
    read = conn.execute(
        """SELECT count(*) AS n, COALESCE(sum(skipped_person), 0) AS persons FROM award_notice""").fetchone()

    def groups(expr: str) -> tuple[list[dict[str, Any]], int]:
        rows = conn.execute(
            f"""SELECT {expr} AS key, count(DISTINCT org.id) AS suppliers, count(*) AS awards
                  {FROM} WHERE {SCOPE} AND a.cpv_main IS NOT NULL
                 GROUP BY 1 ORDER BY 3 DESC, 1""").fetchall()
        kept = [r for r in rows if r["suppliers"] >= K_MIN and r["key"]]
        return kept, len(rows) - len(kept)

    by_cpv, hidden_cpv = groups("left(a.cpv_main, 2)")
    by_country, hidden_country = groups("a.supplier_country")
    cells = conn.execute(
        f"""SELECT left(a.cpv_main, 2) AS division, a.supplier_country AS country,
                   count(DISTINCT org.id) AS suppliers, count(*) AS awards
              {FROM} WHERE {SCOPE} AND a.cpv_main IS NOT NULL
             GROUP BY 1, 2 HAVING count(DISTINCT org.id) >= %s
             ORDER BY 3 DESC, 4 DESC, 1, 2 LIMIT 300""", (K_MIN,)).fetchall()
    total_cells = conn.execute(
        f"""SELECT count(*) AS n FROM (SELECT 1 {FROM} WHERE {SCOPE} AND a.cpv_main IS NOT NULL
             GROUP BY left(a.cpv_main, 2), a.supplier_country) t""").fetchone()["n"]
    return {
        "kMin": K_MIN, "since": SINCE, "noticesRead": read["n"],
        "noticesWithSupplier": head["notices"], "suppliers": head["suppliers"],
        "awards": head["awards"], "skippedNaturalPersons": int(read["persons"]),
        "firstPublished": _day(head["first_p"]), "lastPublished": _day(head["last_p"]),
        "byCpv": [{"key": r["key"], "suppliers": r["suppliers"], "awards": r["awards"]} for r in by_cpv],
        "byCountry": [{"key": r["key"], "suppliers": r["suppliers"], "awards": r["awards"]} for r in by_country],
        "cells": [dict(r) for r in cells],
        "suppressedGroups": hidden_cpv + hidden_country + (total_cells - len(cells)),
        "coverage": COVERAGE,
    }


@router.get("/v1/suppliers/{slug}", response_model=Supplier)
def get_supplier(slug: str, conn=Depends(get_conn)):
    org_id = _id_of(slug, "supplier")
    org = conn.execute(
        "SELECT id, canonical_name, display_name, country, suppressed, merged_into FROM organisation WHERE id = %s",
        (org_id,)).fetchone()
    if org and org["merged_into"] is not None:
        org_id = org["merged_into"]
        org = conn.execute(
            "SELECT id, canonical_name, display_name, country, suppressed, merged_into FROM organisation "
            "WHERE id = %s", (org_id,)).fetchone()
    if org and org["suppressed"]:
        raise removed()
    base = f"{FROM} WHERE {SCOPE} AND org.id = %s"
    head = conn.execute(
        f"""SELECT count(DISTINCT a.opportunity_id) AS n,
                   extract(year FROM min(o.published_at))::int AS first_year,
                   extract(year FROM max(o.published_at))::int AS last_year
              {base}""", (org_id,)).fetchone()
    if not org or not head["n"]:
        raise HTTPException(404, "no such supplier")
    by_year = conn.execute(
        f"""SELECT extract(year FROM o.published_at)::int AS year, count(DISTINCT a.opportunity_id) AS awards
              {base} GROUP BY 1 ORDER BY 1 DESC""", (org_id,)).fetchall()
    by_cpv = conn.execute(
        f"""SELECT left(a.cpv_main, 2) AS division, count(DISTINCT a.opportunity_id) AS awards
              {base} AND a.cpv_main IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1""", (org_id,)).fetchall()
    buyer_rows = conn.execute(
        f"""SELECT o.buyer_org_id AS id, count(DISTINCT a.opportunity_id) AS awards
              {base} AND o.buyer_org_id IS NOT NULL AND NOT o.buyer_withheld
             GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {PROFILE_BUYERS}""", (org_id,)).fetchall()
    notices = conn.execute(
        f"""SELECT o.id, o.native_id, o.title_en, o.title_original, o.buyer_name_raw, o.buyer_withheld, o.country,
                   o.published_at, a.cpv_main, a.winners_in_notice, o.value_amount, o.value_currency,
                   o.value_kind, o.source_url
              {base} ORDER BY o.published_at DESC NULLS LAST, o.id DESC LIMIT {PROFILE_NOTICES}""",
        (org_id,)).fetchall()
    stated = conn.execute(
        f"""SELECT a.name_as_stated AS v, count(*) AS n {base} GROUP BY 1
             ORDER BY 2 DESC, (a.name_as_stated = upper(a.name_as_stated)), 1 LIMIT 5""",
        (org_id,)).fetchall()
    idents = conn.execute(
        f"""SELECT a.identifier_as_stated AS v, count(*) AS n {base} AND a.identifier_as_stated IS NOT NULL
             GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 8""", (org_id,)).fetchall()
    numbers: dict[str, str] = {}              # one spelling of each number: "DE 129 415 943" is "DE129415943"
    for r in idents:
        numbers.setdefault(normalise_identifier(r["v"], org["country"]) or r["v"], r["v"])
    buyer_ids = [r["id"] for r in buyer_rows]
    names = _buyer_names(conn, buyer_ids)
    countries = {r["id"]: r["country"] for r in conn.execute(
        "SELECT id, country FROM organisation WHERE id = ANY(%s)", (buyer_ids,)).fetchall()} if buyer_ids else {}
    item = _item({**org, "n": head["n"], "first_year": head["first_year"], "last_year": head["last_year"],
                  "shown": stated[0]["v"], "divisions": [r["division"] for r in by_cpv]})
    out_notices = []
    for r in notices:
        single = r["winners_in_notice"] == 1 and r["value_kind"] in ("total", "lot_sum")
        has_value = single and r["value_amount"] is not None and float(r["value_amount"]) > PLACEHOLDER_AMOUNT_MAX
        title = redact_emails(r["title_en"] or r["title_original"]) or ""
        out_notices.append({
            "id": str(r["id"]), "slug": make_slug(r["id"], title), "noticeId": r["native_id"], "title": title,
            "buyerName": None if r["buyer_withheld"] else r["buyer_name_raw"], "buyerCountry": r["country"],
            "publishedAt": _day(r["published_at"]), "cpv": r["cpv_main"], "winnersInNotice": r["winners_in_notice"],
            "valueAmount": float(r["value_amount"]) if has_value else None,
            "valueCurrency": r["value_currency"].strip() if has_value and r["value_currency"] else None,
            "sourceUrl": r["source_url"]})
    return {
        **item,
        "byYear": [{"year": r["year"], "awards": r["awards"]} for r in by_year],
        "byCpv": [{"division": r["division"], "awards": r["awards"]} for r in by_cpv],
        "buyers": [{"slug": make_slug(i, names.get(i) or ""), "name": names.get(i) or "Buyer",
                    "country": countries.get(i), "awards": r["awards"]}
                   for r in buyer_rows for i in [r["id"]] if names.get(i)],
        "notices": out_notices, "noticeCount": head["n"],
        "namesAsStated": [r["v"] for r in stated], "identifiers": list(numbers.values())[:3],
        "attribution": "Source: TED (Tenders Electronic Daily), © European Union. Winners as named in each result notice.",
    }
