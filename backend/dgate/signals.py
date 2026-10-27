"""Company signals (WP-154): facts about companies from public procurement and EU defence funding, for investors and analysts.

    GET /v1/signals/{kind}               the first FREE_ROWS rows of a signal, with how many there are (public)
    GET /v1/account/signals/{kind}       the whole list, a page at a time (signed in; paid part, see below)

The three kinds:

  growing   a company whose awarded procurements of the last 12 months exceed those of the 12 months before (and are at
            least MIN_RECENT), with both counts and, where both periods state contract values in one currency, both sums;
  markets   a company's first win with the buyers of a country in the last 12 months, when it won elsewhere before: no win
            in that country in the rest of the window (the award set's three years, `award_set.since`);
  funding   a company in a project of the latest call year of the EU defence programmes (DEFENCE), its first such
            participation or not (`first`), with the projects.

Nothing here is a second definition. A procurement is the award set's (`award_set`: the rows, `KEY`, the window, the PLACSP
switch and twins), a company the supplier map's (the live organisation a row resolves to), a value `suppliers.value_of`,
`best` and `value_totals` (contract values only, per currency, never converted, a unit price in no sum), a procurement's
date its newest notice's (as the supplier page's years), a participation `network_api`'s (active, through merges). Natural
persons and organisations removed on request are in no row. Facts with their sources, never a recommendation.

Paid part (owner, 27 October 2026: the split is decided later): the rows beyond the first FREE_ROWS and the CSV the site builds
from them. Closed unless DGATE_SIGNALS_FULL_OPEN is "true"; open, they need a signed-in account whose plan is in PLANS (while
no plan is on sale every account may, as `billing.may` decides for the features that exist).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from . import accounts, billing, stats
from .accounts import AccountError, throttled
from .award_set import FROM, KEY_HASH, OF_ORGS, scope, since
from .config import settings
from .funding import get_conn, known_params, make_slug
from .network_api import YEAR, _sources
from .normalise import redact_emails
from .suppliers import (
    TED_NOTE,
    _countries,
    _filters,
    _twins,
    best,
    placsp_note,
    shown,
    value_of,
    value_totals,
)
from .tenders import _day

router = APIRouter()
account_router = APIRouter(prefix="/v1/account/signals",
                           dependencies=[Depends(accounts.internal_only), Depends(accounts.no_store)])

KINDS = ("growing", "markets", "funding")
FREE_ROWS = 10
MAX_PAGE_SIZE = 2000            # one CSV of the site: the whole list up to this many rows
MIN_RECENT = 2                  # "growing" from 2 procurements in the last 12 months: 1 against 0 is no trend
WINDOW = timedelta(days=365)
# The EU defence programmes whose participations count (classify.DEFENCE_PROGRAMMES and the EDIP)
DEFENCE = ("EDF", "EDIDP", "EDIP", "PADR")
PLANS = frozenset(billing.PAID)
RANK_SECONDS = 30 * 60
PROJECTS_PER_ROW = 5
NOTE = "Facts from public records, not investment advice."


def today() -> date:
    return datetime.now(timezone.utc).date()


def full_open() -> bool:
    return settings().signals_full_open


def may_see_full(user: dict[str, Any]) -> bool:
    """The paid part's gate: the switch, then the plan (every account while no plan is on sale, as `billing.may`)."""
    return full_open() and (not billing.plans_on_sale() or billing.plan_of(user) in PLANS)


def _company(org_id: int, name: str, country: str | None) -> dict[str, Any]:
    name = redact_emails(name).strip()
    return {"id": str(org_id), "slug": make_slug(org_id, name), "name": name, "country": country or None}


# ------------------------------------------------------------------ filters

def _procurement_filters(country: str | None, cpv: str | None, programme: str | None, start: date
                         ) -> tuple[str, dict[str, Any]]:
    """The supplier map's filters (`suppliers._filters`: the supplier's country, any CPV code of a notice under a prefix)
    over the award set from `start`."""
    if programme:
        raise HTTPException(422, "programme: a filter of the funding signal only")
    where, params = _filters(None, country, cpv)
    params["since"] = start
    return " AND ".join([scope()] + where), params


def _programmes(value: str | None) -> list[str]:
    out = [p.strip().upper() for p in (value or "").split(",") if p.strip()]
    if any(p not in DEFENCE for p in out):
        raise HTTPException(422, f"programme: one or more of {', '.join(DEFENCE)}")
    return list(dict.fromkeys(out))


# ------------------------------------------------------------------ the ranked lists (light rows, cached)

def _rank_growing(conn, country, cpv, programme, day: date) -> list[dict[str, Any]]:
    cond, p = _procurement_filters(country, cpv, programme, day - 2 * WINDOW)
    return conn.execute(
        f"""WITH per AS MATERIALIZED (
                SELECT org.id AS org, {KEY_HASH} AS k, max(COALESCE(o.published_at, o.notice_date)) AS day
                  {FROM} WHERE {cond} GROUP BY 1, 2),
            agg AS (SELECT org, count(*) FILTER (WHERE day >= %(r0)s) AS recent,
                           count(*) FILTER (WHERE day < %(r0)s) AS prior FROM per GROUP BY org)
            SELECT org, recent, prior FROM agg WHERE recent >= %(min)s AND recent > prior
             ORDER BY recent - prior DESC, recent DESC, org""",
        {**p, "r0": day - WINDOW, "min": MIN_RECENT}).fetchall()


def _rank_markets(conn, country, cpv, programme, day: date) -> list[dict[str, Any]]:
    cond, p = _procurement_filters(country, cpv, programme, since(day))
    return conn.execute(
        f"""WITH per AS MATERIALIZED (
                SELECT org.id AS org, o.country AS market, {KEY_HASH} AS k,
                       max(COALESCE(o.published_at, o.notice_date)) AS day
                  {FROM} WHERE {cond} AND o.country IS NOT NULL GROUP BY 1, 2, 3),
            earlier AS (SELECT org, count(DISTINCT k) AS n FROM per WHERE day < %(r0)s GROUP BY org),
            m AS (SELECT org, market, min(day) AS first_day, count(*) AS n FROM per GROUP BY org, market)
            SELECT m.org, m.market, m.first_day, m.n AS recent, earlier.n AS earlier
              FROM m JOIN earlier USING (org) WHERE m.first_day >= %(r0)s
             ORDER BY m.first_day DESC, m.n DESC, m.org, m.market""",
        {**p, "r0": day - WINDOW}).fetchall()


def _rank_funding(conn, country, cpv, programme, day: date) -> list[dict[str, Any]]:
    if cpv:
        raise HTTPException(422, "cpv: not a filter of the funding signal (projects have no CPV code)")
    programmes = _programmes(programme)
    countries = _countries(country, "country")
    return conn.execute(
        f"""WITH d AS MATERIALIZED (
                SELECT COALESCE(l.live_id, pa.organisation_id) AS org, p.id AS project, {YEAR} AS yr, pr.code AS prog
                  FROM participation pa JOIN project p ON p.id = pa.project_id
                  JOIN programme pr ON pr.id = p.programme_id AND pr.code = ANY(%(defence)s)
                  LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
                 WHERE pa.active),
            top AS (SELECT max(yr) AS y FROM d),
            agg AS (SELECT d.org, top.y AS year,
                           count(DISTINCT d.project) FILTER (WHERE d.yr = top.y AND (cardinality(%(progs)s::text[]) = 0
                                                                                   OR d.prog = ANY(%(progs)s))) AS new,
                           count(DISTINCT d.project) FILTER (WHERE d.yr < top.y) AS earlier
                      FROM d CROSS JOIN top GROUP BY d.org, top.y)
            SELECT agg.org, agg.year, agg.new, agg.earlier FROM agg JOIN organisation o ON o.id = agg.org
             WHERE agg.new > 0 AND NOT o.suppressed AND o.individual_reason IS NULL
               AND (cardinality(%(countries)s::text[]) = 0 OR o.country = ANY(%(countries)s))
             ORDER BY (agg.earlier = 0) DESC, agg.new DESC, agg.org""",
        {"defence": list(DEFENCE), "progs": programmes, "countries": countries}).fetchall()


RANK = {"growing": _rank_growing, "markets": _rank_markets, "funding": _rank_funding}


def ranked(conn, kind: str, country: str | None, cpv: str | None, programme: str | None) -> list[dict[str, Any]]:
    """Every row of a signal, in its order, light (ids and counts), once per RANK_SECONDS per day and filters."""
    day = today()

    def compute() -> list[dict[str, Any]]:
        return [dict(r) for r in RANK[kind](conn, country, cpv, programme, day)]

    if not settings().list_cache_seconds:          # 0 turns the list caches off (the test suite)
        return compute()
    key = ("signals", kind, country or "", cpv or "", programme or "", day, settings().placsp_awards_public)
    return stats.cached(key, compute, ttl=RANK_SECONDS)


# ------------------------------------------------------------------ the rows in full (only those served)

def _notice(r: dict[str, Any]) -> dict[str, Any]:
    title = redact_emails(r["title_en"] or r["title_original"]) or ""
    return {"id": str(r["id"]), "slug": make_slug(r["id"], title), "noticeId": r["native_id"], "title": title,
            "publishedAt": _day(r["day"]), "sourceUrl": r["source_url"], "source": r["source_code"]}


def _names(conn, ids: list[int]) -> dict[int, dict[str, Any]]:
    """The supplier map's spelling of each company (`suppliers.shown`), so the name and the slug are its page's."""
    rows = conn.execute(f"SELECT m.id, m.canonical_name, m.country, {shown()} AS shown FROM organisation m "
                        "WHERE m.id = ANY(%s)", (ids,)).fetchall()
    return {r["id"]: _company(r["id"], r["shown"] or r["canonical_name"], r["country"]) for r in rows}


def _award_rows(conn, cond: str, p: dict[str, Any], orgs: list[int], valued: bool) -> dict[int, list[dict[str, Any]]]:
    values = value_of("a.id", _twins(False)) if valued else ""
    cols = "v.va, v.vc, v.vk, v.vp" if valued else "NULL AS va"
    rows = conn.execute(
        f"""SELECT org.id AS org, {KEY_HASH} AS k, COALESCE(o.published_at, o.notice_date) AS day, o.id, o.native_id,
                   o.title_en, o.title_original, o.country AS market, o.source_url, a.winners_in_notice > 1 AS shared,
                   (SELECT code FROM source WHERE id = o.source_id) AS source_code, {cols}
              {FROM} {values} WHERE {cond} AND {OF_ORGS}
             ORDER BY 3 DESC NULLS LAST, o.id DESC""", {**p, "orgs": orgs}).fetchall()
    out: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["org"], []).append(dict(r))
    return out


def _by_procurement(rows: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
    """The rows of each procurement (`KEY`), newest notice first (the rows come so)."""
    out: dict[Any, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["k"], []).append(r)
    return out


def _sums(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    return value_totals(list(best(rows).values()), n)["byCurrency"] if rows else []


def _detail_growing(conn, items, country, cpv, programme, day):
    cond, p = _procurement_filters(country, cpv, programme, day - 2 * WINDOW)
    orgs = [r["org"] for r in items]
    rows, names = _award_rows(conn, cond, p, orgs, valued=True), _names(conn, orgs)
    r0 = datetime.combine(day - WINDOW, datetime.min.time(), tzinfo=timezone.utc)
    out = []
    for it in items:
        groups = _by_procurement(rows.get(it["org"], []))
        recent = [r for g in groups.values() if _day(g[0]["day"]) >= r0 for r in g]
        prior = [r for g in groups.values() if _day(g[0]["day"]) < r0 for r in g]
        a, b = _sums(recent, it["recent"]), _sums(prior, it["prior"])
        by_cur = {s["currency"]: s for s in b}
        # comparable: a currency with contract values in both periods, the one with most of them first
        comparable = sorted(({"currency": s["currency"], "recent": s["amount"], "recentCount": s["count"],
                              "prior": by_cur[s["currency"]]["amount"], "priorCount": by_cur[s["currency"]]["count"]}
                             for s in a if s["currency"] in by_cur),
                            key=lambda v: (-(v["recentCount"] + v["priorCount"]), v["currency"]))
        out.append({"company": names[it["org"]], "recent": it["recent"], "prior": it["prior"],
                    "recentValues": a, "priorValues": b, "comparable": comparable[0] if comparable else None,
                    "latest": _notice(recent[0]) if recent else None})
    return out


def _detail_markets(conn, items, country, cpv, programme, day):
    cond, p = _procurement_filters(country, cpv, programme, since(day))
    orgs = list(dict.fromkeys(r["org"] for r in items))
    rows, names = _award_rows(conn, cond, p, orgs, valued=False), _names(conn, orgs)
    out = []
    for it in items:
        groups = [g for g in _by_procurement(rows.get(it["org"], [])).values() if g[0]["market"] == it["market"]]
        first = min(groups, key=lambda g: (g[0]["day"], g[0]["id"]))[0] if groups else None
        out.append({"company": names[it["org"]], "market": it["market"], "firstWinAt": _day(it["first_day"]),
                    "winsThere": it["recent"], "winsBefore": it["earlier"], "firstWin": _notice(first) if first else None})
    return out


def _detail_funding(conn, items, country, cpv, programme, day):
    orgs = [r["org"] for r in items]
    names = {r["id"]: _company(r["id"], r["display_name"] or r["canonical_name"], r["country"]) for r in conn.execute(
        "SELECT id, canonical_name, display_name, country FROM organisation WHERE id = ANY(%s)", (orgs,)).fetchall()}
    programmes = _programmes(programme)
    year = items[0]["year"] if items else None
    projects: dict[int, list[dict[str, Any]]] = {}
    for r in conn.execute(
            f"""SELECT DISTINCT ON (live, p.id) COALESCE(l.live_id, pa.organisation_id) AS live, p.id, p.acronym, p.title,
                       pr.code AS programme, {YEAR} AS year, pa.role, s.code AS source_code, p.factsheet_url
                  FROM participation pa JOIN project p ON p.id = pa.project_id
                  JOIN programme pr ON pr.id = p.programme_id AND pr.code = ANY(%(progs)s)
                  JOIN source s ON s.id = p.source_id
                  LEFT JOIN organisation_merged_live l ON l.id = pa.organisation_id
                 WHERE pa.active AND {YEAR} = %(year)s
                   AND COALESCE(l.live_id, pa.organisation_id) = ANY(%(orgs)s)
                 ORDER BY live, p.id""",
            {"progs": programmes or list(DEFENCE), "year": year, "orgs": orgs}).fetchall():
        label = redact_emails(r["acronym"] or r["title"])
        projects.setdefault(r["live"], []).append(
            {"slug": make_slug(r["id"], label), "acronym": redact_emails(r["acronym"]) or None,
             "title": redact_emails(r["title"]), "programme": r["programme"], "year": r["year"], "role": r["role"],
             "source": r["source_code"], "factsheetUrl": r["factsheet_url"]})
    return [{"company": names[it["org"]], "year": it["year"], "first": it["earlier"] == 0, "newProjects": it["new"],
             "earlierProjects": it["earlier"], "projects": projects.get(it["org"], [])[:PROJECTS_PER_ROW]}
            for it in items if it["org"] in names]


DETAIL = {"growing": _detail_growing, "markets": _detail_markets, "funding": _detail_funding}


def _sources_of(conn, kind: str) -> list[dict[str, Any]]:
    if kind == "funding":
        return [{"code": s["code"], "name": s["name"], "attribution": s["attribution"] or s["note"]}
                for s in _sources(conn)]
    note = placsp_note(conn) if settings().placsp_awards_public else None
    return [TED_NOTE] + ([{k: note[k] for k in ("code", "name", "attribution")}] if note else [])


def answer(conn, kind: str, country: str | None, cpv: str | None, programme: str | None,
           offset: int, limit: int) -> dict[str, Any]:
    if kind not in KINDS:
        raise HTTPException(404, "no such signal")
    day = today()
    rows = ranked(conn, kind, country, cpv, programme)
    page = rows[offset:offset + limit]
    return {
        "kind": kind, "asOf": day.isoformat(), "recentFrom": (day - WINDOW).isoformat(),
        "priorFrom": (day - 2 * WINDOW).isoformat(), "windowFrom": since(day).isoformat(), "minRecent": MIN_RECENT,
        "items": DETAIL[kind](conn, page, country, cpv, programme, day) if page else [],
        "total": len(rows), "offset": offset, "fullOpen": full_open(), "freeRows": FREE_ROWS,
        "note": NOTE, "sources": _sources_of(conn, kind),
    }


FILTERS = {"country": Query(None, max_length=200), "cpv": Query(None, max_length=200),
           "programme": Query(None, max_length=60)}


@router.get("/v1/signals/{kind}", dependencies=[Depends(known_params)])
def public_signal(kind: str, country: str | None = FILTERS["country"], cpv: str | None = FILTERS["cpv"],
                  programme: str | None = FILTERS["programme"], conn=Depends(get_conn)):
    """The first FREE_ROWS rows of a signal and how many there are."""
    return answer(conn, kind, country, cpv, programme, 0, FREE_ROWS)


@account_router.get("/{kind}")
def full_signal(kind: str, country: str | None = FILTERS["country"], cpv: str | None = FILTERS["cpv"],
                programme: str | None = FILTERS["programme"], page: int = Query(1, ge=1, le=1000),
                pageSize: int = Query(50, ge=1, le=MAX_PAGE_SIZE), user=Depends(throttled), conn=Depends(get_conn)):
    """The paid part: the whole list a page at a time (the site's CSV asks for MAX_PAGE_SIZE rows at once)."""
    if not full_open():
        raise AccountError(404, "not_open", "the full list of signals is not open")
    if not may_see_full(user):
        raise AccountError(402, "plan_required", "the full list of signals is part of a paid plan: choose one under Billing")
    return {**answer(conn, kind, country, cpv, programme, (page - 1) * pageSize, pageSize),
            "page": page, "pageSize": pageSize}
