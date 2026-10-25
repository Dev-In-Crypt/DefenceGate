"""Market overview, buyer profile and the span of what each source holds.

Everything here is a count of notices published. Never spend, never market size, never a
row per company: the market figures are over all core-scope notices, the profile is the
buyer's own core-scope notices and says so. The scope is the one the tenders list uses
(`tenders.CORE`: the 2009/81/EC legal basis, or a military CPV a buyer's own needs do not
explain).

Decisions that shape it:

  - every aggregate is cached in this process for an hour (`CACHE_SECONDS`) and computed
    once per key (single flight, no lock held while a query runs), so a cold cache runs
    each query once and not once per visitor; a cache hit does not open a database
    connection
  - each aggregate is a query of its own, over indexed columns: the 36-month series reads
    `opp_core_published` (migration 0038), a buyer's figures read `opp_buyer_org`
  - "amended" is the timeline's own rule (`tenders.timeline`), not an SQL approximation:
    SQL only narrows to the notices that have a version which could count, and the
    timeline decides. On 13 October 2026 that was 69 candidates among 9,741 notices
  - a median is the middle observed number of days (`percentile_disc`), so it is a whole
    number of days that some notice actually had
  - a deadline before the publication date, or more than three years after it, is a
    data fault (`funding.anomalies`) and is left out of the response window, as the
    notice page flags it
  - a CPV group is the first three digits of a code; a notice with codes in several groups
    counts once in each. The vocabulary's titles live in the site (`web/lib/data/cpv.json`),
    not here: the API answers with the code
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import ExitStack, contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from . import db, money
from .config import settings
from .suppliers import ValueSum
from .suppress import removed
from .tenders import (
    CORE,
    FIELD_LABELS,
    PLACEHOLDER_VALUE_MAX,
    TIMELINE_SQL,
    _api,
    collapse_clauses,
    live_id_of,
    timeline,
)

router = APIRouter()

CACHE_SECONDS = 3600
LAST_RUN_SECONDS = 300       # `meta.updatedAt` of the lists: a run that ends is shown within 5 minutes
RETRY_SECONDS = 60           # how long a failed source-span read is not tried again
MAX_CACHED = 1000
MONTHS = 36
WINDOW_DAYS = 365
TOP_COUNTRIES = 15
TOP_CPV_MARKET = 12
TOP_CPV_BUYER = 5
BUYER_YEARS = 6
RESPONSE_HORIZON_DAYS = 3 * 365      # funding.DEADLINE_HORIZON_DAYS
TIMELINE_CHUNK = 500

# Exactly the predicate of the partial index `opp_core_published` (migration 0038), so
# the planner can use it.
CORE_NOTICES = f"o.is_defence AND NOT o.suppressed AND {CORE}"


def scope_notices(scope: str = "core") -> str:
    """WP-112 (p06: /market?country=NL&cpv=60 counted 17 transport notices, the tender list 137): the notices the market counts,
    military goods and works (`core`, the default) or all defence (`relevant`: also the services and supplies the armed forces
    buy, as the tender list opens)."""
    if scope == "relevant":
        return f"o.is_defence AND NOT o.suppressed AND {_api().SCOPE_SQL['relevant']}"
    return CORE_NOTICES

# A version that changed only the publication date is not an amendment (tenders.timeline);
# nor is one annotated with a `db.NOT_AMENDMENT_NOTES` kind.
CHANGING_FIELDS = [f for f in FIELD_LABELS if f != "published_at"]


# ------------------------------------------------------------------ cache

_cache: dict[Any, tuple[float, Any]] = {}
# Whole list responses (tenders, buyers, opportunities): a store of its own so that a flood
# of distinct queries cannot evict the hourly aggregates, and a small one, because a page
# of 100 notices is the largest entry (`listcache.cache_list`).
_list_cache: dict[Any, tuple[float, Any]] = {}
LIST_SECONDS = 60
LIST_BUYERS_SECONDS = 300      # the buyer aggregate re-reads the whole table (0.46 s)
LIST_CACHED = 120
LIST_MAX_PAGE = 100            # a larger page is not kept: 120 x 100 notices bounds the memory
SINGLE_FLIGHT_WAIT = 8.0       # a follower waits for the one computing its key, at most this
_lock = threading.Lock()       # guards the dicts only; a computation never runs under it
_inflight: dict[Any, Future] = {}
_ABSENT = object()


# WP-120: the notices a text search matches (`tenders.search_ids`), and the buyers' shown names (`tenders._buyer_names`)
_search_cache: dict[Any, tuple[float, Any]] = {}
SEARCH_CACHED = 50
_name_cache: dict[int, tuple[float, str | None]] = {}
NAMES_CACHED = 20_000
# WP-120: pages over LIST_MAX_PAGE that an endpoint asks to keep (`cache_list(large=...)`: the export's 500 to 2,000 notices)
_large_cache: dict[Any, tuple[float, Any]] = {}
LARGE_CACHED = 8


def reset_cache() -> None:
    _cache.clear()
    _list_cache.clear()
    _name_cache.clear()
    _large_cache.clear()
    _search_cache.clear()


def _get(key: Any, store: dict | None = None) -> Any:
    hit = (_cache if store is None else store).get(key)
    return hit[1] if hit and hit[0] > time.monotonic() else _ABSENT


def _put(key: Any, value: Any, ttl: float = CACHE_SECONDS, store: dict | None = None,
         limit: int | None = None) -> None:
    store = _cache if store is None else store
    limit = MAX_CACHED if limit is None else limit
    if key not in store and len(store) >= limit:
        del store[min(store, key=lambda k: store[k][0])]
    store[key] = (time.monotonic() + ttl, value)


def cached(key: Any, compute, ttl: float = CACHE_SECONDS, *,
           store: dict | None = None, limit: int | None = None):
    """`compute()` once an hour (or `ttl`) per key, single flight: concurrent callers of one
    key share the one computation (the first computes, the others wait for its value or its
    error), and different keys never wait for each other (internal audit M1: one lock round
    every computation stalled the list pages behind a buyer profile).

    A None result is "no such buyer" and is not stored, so arbitrary ids cannot fill the
    store (which is bounded all the same). A computation that raises is never stored, and
    the figures cached before it stay."""
    value = _get(key, store)
    if value is not _ABSENT:
        return value
    with _lock:
        value = _get(key, store)
        if value is not _ABSENT:
            return value
        flight = _inflight.get(key)
        leader = flight is None
        if leader:
            flight = _inflight[key] = Future()
    if not leader:
        try:
            return flight.result(timeout=SINGLE_FLIGHT_WAIT)
        except FutureTimeout:
            return compute()                  # the leader is stuck: do not wait on it for ever
    try:
        value = compute()
    except BaseException as exc:
        with _lock:
            _inflight.pop(key, None)
        flight.set_exception(exc)
        raise
    with _lock:
        if value is not None:
            _put(key, value, ttl, store, limit)
        _inflight.pop(key, None)
    flight.set_result(value)
    return value


log = logging.getLogger("dgate.stats")
_refreshing: set[Any] = set()


RENEWALS = 2                   # background renewals at once (each holds a connection of the API's pool)
_renewal_gate = threading.BoundedSemaphore(RENEWALS)


def cached_stale(key: Any, compute, conn: Any, ttl: float, stale: float, *,
                 store: dict | None = None, limit: int | None = None) -> Any:
    """WP-120: `cached(key, compute(conn), ttl)`, except that for `stale` seconds after the value expired it is answered at
    once while one background thread renews it with a connection of its own (`compute(c)`): no request waits for a
    renewal. At most RENEWALS run at once; one that cannot start now is tried by the next request. Older than that (or
    never computed, or evicted), the caller computes it as `cached` does. A renewal that fails leaves the old value."""
    hit = (_cache if store is None else store).get(key)
    now = time.monotonic()
    if hit is not None and now < hit[0]:
        return hit[1]
    if hit is not None and now < hit[0] + stale:
        with _lock:
            start = key not in _refreshing and key not in _inflight and _renewal_gate.acquire(blocking=False)
            if start:
                _refreshing.add(key)
        if start:
            threading.Thread(target=_renew, args=(key, compute, ttl, store, limit), daemon=True,
                             name="renew").start()
        return hit[1]
    return cached(key, lambda: compute(conn), ttl, store=store, limit=limit)


def _renew(key: Any, compute, ttl: float, store: dict | None, limit: int | None) -> None:
    try:
        with _connection() as c:
            value = compute(c)
        if value is not None:
            with _lock:
                _put(key, value, ttl, store, limit)
    except Exception:  # noqa: BLE001 - the old value stays; a background renewal never fails a request
        log.exception("background renewal of %r failed", key[0] if isinstance(key, tuple) else key)
    finally:
        with _lock:
            _refreshing.discard(key)
        _renewal_gate.release()


@contextmanager
def _connection():
    """The API's own role, opened only when something has to be computed."""
    cfg = settings()
    with db.bounded_connect(cfg.api_dsn or cfg.dsn, cfg.api_connections, cfg.pool_wait_ms / 1000) as conn:
        yield conn


class _Lazy:
    """The connection, opened the first time a query needs it (a request the cache can
    answer opens none) and closed when the request ends."""

    def __init__(self) -> None:
        self._stack = ExitStack()
        self._conn: Any = None

    def __call__(self) -> Any:
        if self._conn is None:
            self._conn = self._stack.enter_context(_connection())
        return self._conn

    def __enter__(self) -> "_Lazy":
        return self

    def __exit__(self, *exc: Any) -> Any:
        return self._stack.__exit__(*exc)


# ----------------------------------------------------------- pure helpers

def month_starts(today: date, n: int = MONTHS) -> list[date]:
    """The first day of each of the `n` months ending with the one `today` is in."""
    out: list[date] = []
    year, month = today.year, today.month
    for _ in range(n):
        out.append(date(year, month, 1))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return out[::-1]


def _scope(since: date, today: date, country: str | None = None,
           cpv: list[str] | None = None, scope: str = "core") -> tuple[str, list[Any]]:
    """Core-scope notices published from `since` to `today` (a date in the future is
    not a publication), of one buyer country when asked, and (WP-89) with a CPV code under one of the
    prefixes `cpv` when asked (the tender list's reading, over the GIN index of migration 0099)."""
    where = f"{scope_notices(scope)} AND o.published_at >= %s AND o.published_at <= %s"
    params: list[Any] = [since, today]
    if country:
        where += " AND o.country = %s"
        params.append(country)
    if cpv:
        where += " AND dgate_cpv_heads(o.cpv_codes) && %s::text[]"
        params.append(list(cpv))
    return where, params


def _buyer_scope(org_id: int) -> tuple[str, list[Any]]:
    # The buyer's whole family: any member id gives the head's family (migration 0055). WP-96: the tender list's default
    # scope (All defence), as the buyer page's counts and lists are; it was the core scope, and a ministry's transport,
    # catering and storage tenders were in no figure of its page.
    return (f"o.is_defence AND NOT o.suppressed AND {_api().SCOPE_SQL['relevant']} AND NOT o.buyer_withheld "
            "AND o.buyer_org_id = ANY(ARRAY(SELECT unnest(dgate_family_ids(%s))))", [org_id])


# ------------------------------------------------------------ aggregates
# Each takes a connection and a (where, params) scope over `opportunity o` and returns
# plain data. The same helpers serve the market and a buyer.

def notices_per_month(conn, today: date, months: int = MONTHS, *,
                      starts: list[date] | None = None, country: str | None = None,
                      cpv: list[str] | None = None, scope: str = "core") -> list[dict[str, Any]]:
    """Notices published per calendar month, all sources and TED alone, zero-filled.
    The month `today` is in is incomplete and says so. `starts` (the months of one calendar
    year) replaces the trailing `months`; `country` keeps one buyer country."""
    starts = starts or month_starts(today, months)
    extra, args = ("", [])
    if country:
        extra, args = " AND o.country = %s", [country]
    if cpv:
        extra, args = extra + " AND dgate_cpv_heads(o.cpv_codes) && %s::text[]", [*args, list(cpv)]
    rows = conn.execute(
        f"""SELECT date_trunc('month', o.published_at)::date AS month, count(*) AS n,
                   count(*) FILTER (
                       WHERE o.source_id = (SELECT id FROM source WHERE code = 'ted')) AS ted
              FROM opportunity o
             WHERE {scope_notices(scope)} AND o.published_at >= %s AND o.published_at <= %s{extra}
             GROUP BY 1""", (starts[0], min(today, _month_end(starts[-1])), *args)).fetchall()
    found = {r["month"]: r for r in rows}
    return [{"month": f"{d:%Y-%m}", "count": found[d]["n"] if d in found else 0,
             "ted": found[d]["ted"] if d in found else 0,
             "partial": d.year == today.year and d.month == today.month}
            for d in starts]


def _month_end(first: date) -> date:
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def notices_per_country(conn, where: str, params: list[Any], top: int = TOP_COUNTRIES
                        ) -> dict[str, Any]:
    """The `top` countries by notices, the rest as one figure. A notice with no country
    is in `other`, never dropped."""
    rows = conn.execute(
        f"SELECT o.country, count(*) AS n FROM opportunity o WHERE {where} GROUP BY o.country",
        params).fetchall()
    total = sum(r["n"] for r in rows)
    ranked = sorted(((r["country"], r["n"]) for r in rows if r["country"]),
                    key=lambda x: (-x[1], x[0]))
    items = [{"country": c, "count": n} for c, n in ranked[:top]]
    return {"total": total, "items": items, "other": total - sum(i["count"] for i in items)}


def notices_per_source(conn, where: str, params: list[Any]) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""SELECT s.code AS id, s.name, count(*) AS n
              FROM opportunity o JOIN source s ON s.id = o.source_id
             WHERE {where} GROUP BY s.code, s.name ORDER BY n DESC, s.code""", params).fetchall()
    return [{"id": r["id"], "name": r["name"], "count": r["n"]} for r in rows]


def response_window(conn, where: str, params: list[Any]) -> dict[str, Any]:
    """Days from publication to the stated deadline: quartiles over the notices that
    state one within `RESPONSE_HORIZON_DAYS` and not before publication."""
    row = conn.execute(
        f"""SELECT count(*) AS n,
                   percentile_disc(ARRAY[0.25, 0.5, 0.75]) WITHIN GROUP (ORDER BY d) AS q
              FROM (SELECT (o.deadline_at AT TIME ZONE 'UTC')::date - o.published_at AS d
                      FROM opportunity o
                     WHERE {where} AND o.deadline_at IS NOT NULL
                       AND o.published_at IS NOT NULL) t
             WHERE d BETWEEN 0 AND %s""", params + [RESPONSE_HORIZON_DAYS]).fetchone()
    q = row["q"] or [None, None, None]
    return {"notices": row["n"], "median": q[1], "p25": q[0], "p75": q[2]}


def cpv_groups(conn, where: str, params: list[Any], top: int, prefixes: list[str] | None = None) -> list[dict[str, Any]]:
    """The 3-digit CPV groups with most notices; a notice counts once per group. WP-112 (p04: jewellery, luggage and sports
    goods under ammunition codes, the additional codes of the matched notices): with `prefixes`, only the groups under them
    (a prefix of two digits keeps its division's groups), as the contract values by group already do (`money.market_money`)."""
    under = ""
    args: list[Any] = []
    if prefixes:
        under = " AND left(c, 3) LIKE ANY(%s)"
        args = [sorted({p[:3] + "%" for p in prefixes})]
    rows = conn.execute(
        "SELECT g, count(*) AS n FROM (SELECT DISTINCT o.id, left(c, 3) AS g "
        f"FROM opportunity o, unnest(o.cpv_codes) AS c WHERE {where} AND c ~ '^[0-9]{{3}}'{under}) t "
        "GROUP BY g ORDER BY n DESC, g LIMIT %s", params + args + [top]).fetchall()
    return [{"group": r["g"], "count": r["n"]} for r in rows]


def amendments_watched(conn, where: str, params: list[Any]) -> dict[str, Any]:
    """The share (`amendment_share`) and since when the archive watched these notices (`observedFrom`: the first time
    it saw the oldest of them). A share over a few weeks of watching says nothing; the site shows it once that is
    HISTORY_DAYS old, on the market page as on a buyer page (WP-96: the market said 0 % where the buyer page said
    "not shown yet")."""
    out = amendment_share(conn, where, params)
    out["observedFrom"] = conn.execute(
        f"""SELECT min(v.observed_at) AS t FROM opportunity o
              JOIN opportunity_version v ON v.opportunity_id = o.id AND v.version = 1 WHERE {where}""",
        params).fetchone()["t"]
    return out


def amendment_share(conn, where: str, params: list[Any]) -> dict[str, Any]:
    """How many of the scope's notices have an amendment, as the tender page's timeline
    counts one. SQL names the notices with a version that could count (changed a listed
    field other than the publication date, not a re-read, out-of-order or remapped
    version); `timeline` decides."""
    total = conn.execute(f"SELECT count(*) AS n FROM opportunity o WHERE {where}",
                         params).fetchone()["n"]
    ids = [r["opportunity_id"] for r in conn.execute(
        f"""SELECT DISTINCT v.opportunity_id
              FROM opportunity o JOIN opportunity_version v ON v.opportunity_id = o.id
             WHERE {where} AND v.changed_fields && %s::text[]
               AND NOT EXISTS (SELECT 1 FROM opportunity_version_note n
                                WHERE n.opportunity_version_id = v.id AND n.kind = ANY(%s))""",
        params + [CHANGING_FIELDS, list(db.NOT_AMENDMENT_NOTES)]).fetchall()]
    amended = 0
    for i in range(0, len(ids), TIMELINE_CHUNK):
        rows = conn.execute(TIMELINE_SQL.format(where="v.opportunity_id = ANY(%s)"),
                            (ids[i:i + TIMELINE_CHUNK],)).fetchall()
        by_notice: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            by_notice.setdefault(r["opportunity_id"], []).append(r)
        # A version a history load wrote is listed on the tender page, not counted here.
        amended += sum(1 for group in by_notice.values()
                       if any(not e.get("historic") for e in timeline(group)[1:]))
    return {"notices": total, "amended": amended,
            "share": round(amended / total, 4) if total else None}


# ---------------------------------------------------------------- market

BASIS = {
    "months": "Counts of notices published per month, not contract value. Only notices that "
              "state the defence directive or carry a military CPV code are counted. The "
              "latest month is not complete. Source coverage differs by country: see source "
              "status.",
    "countries": "Counts of notices published in the last 12 months, by the buyer's country. "
                 "Source coverage differs by country: see source status.",
    "sources": "Counts of notices published in the last 12 months, by the source we collected "
               "them from.",
    "amendments": "Share of the notices published in the last 12 months that have an amendment "
                  "in the archive: a later version that changed something other than the "
                  "publication date.",
    "responseWindow": "Days from publication to the stated deadline, for notices published in "
                      "the last 12 months that state one. Award notices state none; a "
                      "deadline before publication or more than three years away is left out.",
    "cpvGroups": "Notices published in the last 12 months with at least one code in the "
                 "3-digit CPV group; a notice with codes in several groups counts once in "
                 "each. Counts of notices, not contract value.",
}


def window_words(basis: dict[str, str], year: int | None) -> dict[str, str]:
    """The basis texts say "the last 12 months"; for a calendar year they say the year."""
    if year is None:
        return dict(basis)
    return {k: v.replace("in the last 12 months", f"in {year}") for k, v in basis.items()}


def market(get_conn, today: date | None = None, *, year: int | None = None,
           country: str | None = None, cpv: list[str] | None = None, scope: str = "core") -> dict[str, Any]:
    """Each figure is cached on its own for the hour. The API role has a 5 s budget and a
    cold cache can spend it on one query (a 36-month scan took 11.7 s on a busy server on
    13 October 2026, before migration 0038): the request then fails with a 503, and the
    next one redoes only what is not cached, on pages the failed one already warmed."""
    today = today or datetime.now(timezone.utc).date()
    if year is not None:
        # A calendar year (to today when it is the current one): the figure can be quoted and
        # reproduced, which the rolling window cannot (the 12 months move every day).
        since, until = date(year, 1, 1), min(date(year, 12, 31), today)
        starts = [date(year, m, 1) for m in range(1, 13) if date(year, m, 1) <= today]
    else:
        since, until, starts = today - timedelta(days=WINDOW_DAYS), today, None
    cpv = list(cpv or []) or None
    where, params = _scope(since, until, country, cpv, scope)
    sections = {
        "months": lambda c: notices_per_month(c, today, starts=starts, country=country, cpv=cpv, scope=scope),
        "countries": lambda c: notices_per_country(c, where, params),
        "sources": lambda c: notices_per_source(c, where, params),
        "amendments": lambda c: amendments_watched(c, where, params),
        "responseWindow": lambda c: response_window(c, where, params),
        "cpvGroups": lambda c: cpv_groups(c, where, params, TOP_CPV_MARKET, cpv),
    }
    got: dict[str, dict[str, Any]] = {}
    for name, fn in sections.items():
        got[name] = cached(
            ("market", name, today, year, country, tuple(cpv or ()), scope),
            lambda fn=fn: {"at": datetime.now(timezone.utc), "data": fn(get_conn())})
    # WP-105: the contract values of the supplier map's award set in the same window, country and codes. Not kept when there
    # is no snapshot yet (None is never cached), and never the reason the overview fails.
    try:
        paid = cached(("market", "money", today, year, country, tuple(cpv or ())),
                      lambda: money.market_money(get_conn(), since, until, country, cpv))
    except Exception:  # noqa: BLE001
        paid = None
    return {
        "money": paid,
        "basisMoney": MONEY_BASIS,
        "asOf": min(part["at"] for part in got.values()),     # the oldest figure on the page
        "scope": scope,
        "unit": "notices published",
        "windowFrom": since,
        "windowTo": until,
        "year": year,
        "country": country,
        "cpv": cpv,
        "sourceCount": len(got["sources"]["data"]),
        **{name: part["data"] for name, part in got.items()},
        "basis": window_words(BASIS if scope == "core" else RELEVANT_BASIS, year),
    }


class MonthCount(BaseModel):
    month: str
    count: int
    ted: int
    partial: bool


class CountryCount(BaseModel):
    country: str
    count: int


class Countries(BaseModel):
    total: int
    items: list[CountryCount]
    other: int


class SourceCount(BaseModel):
    id: str
    name: str
    count: int


class CpvGroupCount(BaseModel):
    group: str
    count: int


class Amendments(BaseModel):
    notices: int
    amended: int
    share: float | None
    # WP-87 (buyer profile): when the archive first saw the oldest of these notices. A share over a few weeks of
    # watching says nothing about how often a buyer amends, so the page shows it once this is HISTORY_DAYS old.
    observedFrom: datetime | None = None


class ResponseWindow(BaseModel):
    notices: int
    median: int | None
    p25: int | None
    p75: int | None


class MoneyTotals(BaseModel):
    byCurrency: list[ValueSum]
    of: int                      # contracts (a contract and its winner) in the slice
    withoutValue: int            # of them, those with no contract value to sum


class MoneyCountry(MoneyTotals):
    country: str


class MoneyGroup(MoneyTotals):
    group: str


class MoneyBuyer(MoneyTotals):
    slug: str
    name: str
    country: str | None


class MarketMoney(BaseModel):
    asOf: datetime
    since: str                   # the days the sums cover: the market's window cut to the award set's three years
    until: str
    total: MoneyTotals
    byCountry: list[MoneyCountry]
    byCpvGroup: list[MoneyGroup]
    byBuyer: list[MoneyBuyer]


MONEY_BASIS = ("Sums of the contract values awarded, per currency, never converted: the contracts of the supplier map (result "
               "notices of the defence-relevant scope, the last three years, winners that are legal entities), each contract "
               "of each winner once and valued as the supplier pages value it. Framework ceilings, estimates and unit prices "
               "are never added; a contract that states no value of its own is counted as without value. A contract with "
               "codes in several CPV groups is in each. Coverage is that of the award notices we read: TED everywhere, and "
               "Spain's national portal (PLACSP) for Spanish buyers.")


class MarketStats(BaseModel):
    asOf: datetime
    scope: str
    unit: str
    windowFrom: date
    windowTo: date
    # The calendar year and the buyer country the figures were asked for, null for the
    # rolling 12 months and all countries.
    year: int | None = None
    country: str | None = None
    # WP-89: the CPV prefixes the figures were narrowed to, null for every code
    cpv: list[str] | None = None
    sourceCount: int
    months: list[MonthCount]
    countries: Countries
    sources: list[SourceCount]
    amendments: Amendments
    responseWindow: ResponseWindow
    cpvGroups: list[CpvGroupCount]
    basis: dict[str, str]
    money: MarketMoney | None = None         # WP-105: None while the worker has stored no contract values
    basisMoney: str = MONEY_BASIS


MARKET_FIRST_YEAR = 2017
RELEVANT_BASIS = {**BASIS, "months": BASIS["months"].replace(
    "Only notices that state the defence directive or carry a military CPV code are counted.",
    "Notices of all defence are counted: those that state the defence directive or carry a military CPV code, and the services "
    "and supplies that defence buyers buy (the tender list's default).")}


@router.get("/v1/stats/market", response_model=MarketStats)
def market_stats(year: int | None = Query(None, ge=MARKET_FIRST_YEAR, le=2100),
                 country: str | None = Query(None, pattern="^[A-Za-z]{2}$"),
                 cpv: str | None = Query(None, max_length=200),
                 scope: str = Query("core", pattern="^(core|relevant)$")):
    if year is not None and year > datetime.now(timezone.utc).year:
        raise HTTPException(422, "year is in the future")
    # WP-112: all defence only for one country or some codes: the whole market in that scope has no index of its own (the
    # 36-month series reads `opp_core_published`) and could spend the API's 5 s budget cold
    if scope == "relevant" and not (country or cpv):
        raise HTTPException(422, "scope=relevant needs a country or CPV codes")
    from .tenders import cpv_prefixes
    prefixes = cpv_prefixes(cpv)
    with _Lazy() as get_conn:
        return market(get_conn, year=year, country=country.upper() if country else None, cpv=prefixes, scope=scope)


# ----------------------------------------------------------- buyer profile

PROFILE_BASIS = {
    "perYear": "Counts of this buyer's notices by year of publication, not contract value. Notices published "
               "before the first year shown, and notices without a publication date, are counted on their own, "
               "so the rows add up to the total.",
    "cpvGroups": "This buyer's notices, all years, with at least one code in the 3-digit "
                 "CPV group; a notice counts once in each group it has.",
    "responseWindow": "Days from publication to the stated deadline over this buyer's "
                      "notices that state one. Award notices state none.",
    "amendments": "Share of this buyer's notices with an amendment in the archive: a later "
                  "version that changed something other than the publication date.",
    "sources": "Counts of this buyer's notices by the source we collected them from.",
}


def buyer_profile(conn, org_id: int, today: date | None = None) -> dict[str, Any] | None:
    """The buyer's own notices of the list's default scope (WP-96; it was the core scope), or None when it has none (the buyer page's
    404). `openNow` is as of now, with the status rule the tender list uses.

    WP-87: one unit everywhere, the notices the buyer's tender list shows: a notice published in TED and in a
    national portal is one (the list's collapse rules, `tenders.collapse_clauses`), so the total is the page's
    "Tenders in archive" and the sources add up to it (BAAINBw: 3,335 against "0 of 5,380 notices"). The years
    add up to it too: `earlier` and `undated` hold what the shown years do not."""
    today = today or datetime.now(timezone.utc).date()
    own, one = _buyer_scope(org_id)
    where = f"{own} AND {collapse_clauses([own])}"
    params = one * 4
    head = conn.execute(
        f"""SELECT count(*) AS n, count(*) FILTER (WHERE {_api().EFFECTIVE_STATUS_SQL} = 'open')
                   AS open_n
              FROM opportunity o WHERE {where}""", params).fetchone()
    if not head["n"]:
        return None
    head_id = conn.execute("SELECT dgate_buyer_head(%s) AS h", (org_id,)).fetchone()["h"]
    first_year = today.year - BUYER_YEARS + 1
    rows = conn.execute(
        f"""SELECT extract(year FROM o.published_at)::int AS y, count(*) AS n
              FROM opportunity o WHERE {where} AND o.published_at >= %s AND o.published_at <= %s
             GROUP BY 1""", params + [date(first_year, 1, 1), today]).fetchall()
    by_year = {r["y"]: r["n"] for r in rows}
    dated = conn.execute(
        f"""SELECT count(*) FILTER (WHERE o.published_at < %s) AS earlier,
                   count(*) FILTER (WHERE o.published_at IS NULL OR o.published_at > %s) AS undated
              FROM opportunity o WHERE {where}""", [date(first_year, 1, 1), today] + params).fetchone()
    amendments = amendments_watched(conn, where, params)
    return {
        "buyerId": str(head_id),
        "asOf": datetime.now(timezone.utc),
        "scope": "relevant",
        "unit": "notices published",
        "tenderCount": head["n"],
        "openNow": head["open_n"],
        "perYear": [{"year": y, "count": by_year.get(y, 0)}
                    for y in range(first_year, today.year + 1)],
        "perYearEarlier": dated["earlier"],
        "perYearUndated": dated["undated"],
        "cpvGroups": cpv_groups(conn, where, params, TOP_CPV_BUYER),
        "responseWindow": response_window(conn, where, params),
        "amendments": amendments,
        "sources": notices_per_source(conn, where, params),
        "basis": dict(PROFILE_BASIS),
    }


class YearCount(BaseModel):
    year: int
    count: int


class BuyerProfile(BaseModel):
    buyerId: str
    asOf: datetime
    scope: str
    unit: str
    tenderCount: int
    openNow: int
    perYear: list[YearCount]
    # WP-87: notices published before the first year of `perYear`, and without a publication date (or dated in the
    # future): with them the years add up to `tenderCount`
    perYearEarlier: int = 0
    perYearUndated: int = 0
    cpvGroups: list[CpvGroupCount]
    responseWindow: ResponseWindow
    amendments: Amendments
    sources: list[SourceCount]
    basis: dict[str, str]


@router.get("/v1/buyers/{slug}/profile", response_model=BuyerProfile)
def get_buyer_profile(slug: str):
    with _connection() as conn:
        org_id = live_id_of(conn, slug, "buyer")      # WP-133: a merged row's profile is its head's

    def build():
        with _connection() as conn:
            return buyer_profile(conn, org_id)
    found = cached(("buyer", org_id), build)
    with _connection() as conn:
        if conn.execute("SELECT 1 FROM organisation WHERE id = %s AND suppressed",
                        (org_id,)).fetchone():
            raise removed()
    if found is None:
        raise HTTPException(404, "no such buyer")
    return found


# ----------------------------------------------------------- source spans

MAX_GAP_MONTHS = 120


USUAL_MONTHS = 12


def month_gaps(per_month: dict[str, int]) -> tuple[int, list[str]]:
    """(median notices per month, the months well below it) of one source, from the
    notices held per month of publication (`YYYY-MM`). The first and the last month are
    left out (a source starts and is read part-way through a month) and a month with none
    counts as zero. "Well below" is under half of the median. Fewer than three whole months
    say nothing. What /data says about holes is read from this, not written by hand."""
    if len(per_month) < 2:
        return 0, []
    months = sorted(per_month)
    y, m = int(months[0][:4]), int(months[0][5:7])
    last = (int(months[-1][:4]), int(months[-1][5:7]))
    grid: list[str] = []
    while (y, m) <= last:
        grid.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    inner = grid[1:-1]
    if len(inner) < 3:
        return 0, []
    # WP-96: the usual month is that of the last USUAL_MONTHS whole months, what the source holds now. Over every month
    # since 2015 it said "about 21" for PLACSP, which holds 41,142 notices, most of them recent; the older, thinner
    # years show as months below half of it.
    counts = sorted(per_month.get(k, 0) for k in inner[-USUAL_MONTHS:])
    mid = len(counts) // 2
    median = counts[mid] if len(counts) % 2 else (counts[mid - 1] + counts[mid]) / 2
    if median <= 0:
        return 0, []
    return int(median), [k for k in inner if per_month.get(k, 0) < median / 2]


def source_spans(conn) -> dict[str, dict[str, Any]]:
    """For each source, how many notices (or calls) we hold and the span of their
    publication dates, so that a gap ("BOAMP from 2015, nothing before") is visible.
    A grant source's span is blank where the source gives no publication date."""
    out: dict[str, dict[str, Any]] = {}
    for table, extra in (("opportunity", "WHERE o.is_defence AND NOT o.suppressed"),
                         ("call", "WHERE NOT c.suppressed")):
        alias = table[0]
        # How many notices state a value at all (a placeholder amount is "not stated"): the
        # site says "no usable estimated value in N % of notices from this source" from it, and
        # "not collected from this source" for a connector that reads none (normalise.VALUE_NOT_READ_SOURCES).
        stated = (f", count(*) FILTER (WHERE o.value_amount > {PLACEHOLDER_VALUE_MAX}) AS stated"
                  if table == "opportunity" else "")
        rows = conn.execute(
            f"""SELECT s.code, count(*) AS n, min({alias}.published_at) AS first,
                       max({alias}.published_at) AS last{stated}
                  FROM {table} {alias} JOIN source s ON s.id = {alias}.source_id
                  {extra} GROUP BY s.code""").fetchall()
        for r in rows:
            out[r["code"]] = {"heldFrom": r["first"], "heldTo": r["last"], "heldCount": r["n"],
                              **({"valueStatedCount": r["stated"]} if "stated" in r else {})}
    return out


def source_gaps(conn) -> dict[str, dict[str, Any]]:
    """For each tender source: the usual notices per month and the months well below it
    (`month_gaps`), from the notices held by month of publication. A separate read from
    `source_spans`, whose figures it must never put at risk."""
    out: dict[str, dict[str, Any]] = {}
    by_source: dict[str, dict[str, int]] = {}
    for r in conn.execute(
            """SELECT s.code, to_char(o.published_at, 'YYYY-MM') AS month, count(*) AS n
                 FROM opportunity o JOIN source s ON s.id = o.source_id
                WHERE o.is_defence AND NOT o.suppressed AND o.published_at IS NOT NULL
                GROUP BY s.code, 2""").fetchall():
        by_source.setdefault(r["code"], {})[r["month"]] = r["n"]
    for code, per_month in by_source.items():
        median, gaps = month_gaps(per_month)
        out[code] = {"monthlyMedian": median, "gapMonths": gaps[-MAX_GAP_MONTHS:]}
    return out


def cached_source_spans(conn) -> dict[str, dict[str, Any]]:
    """For `/v1/sources`, which every page's footer reads: a read that does not finish in
    the API role's budget must not take the footer down with it. It answers with no spans,
    and is not tried again for `RETRY_SECONDS`."""
    try:
        spans = cached("source-spans", lambda: source_spans(conn))
    except psycopg.errors.QueryCanceled:
        conn.rollback()
        with _lock:
            _put("source-spans", {}, RETRY_SECONDS)
        return {}
    if not spans:
        return spans
    try:        # the gaps are worth less than the spans: a read that is cut short leaves them out
        gaps = cached("source-gaps", lambda: source_gaps(conn))
    except psycopg.errors.QueryCanceled:
        conn.rollback()
        with _lock:
            _put("source-gaps", {}, RETRY_SECONDS)
        gaps = {}
    return {code: {**span, **gaps.get(code, {})} for code, span in spans.items()}


# ---------------------------------------------------------- last collection

def last_run_finished(conn, kind: str) -> datetime | None:
    """When the newest successful or partial collection run of an active source of this
    kind (`tender` or `grant`) finished: what a list means by "updated". A failed run
    added nothing, so it does not count. `ingest_run` is a few hundred rows."""
    return last_run(conn, kind)[0]


def last_run(conn, kind: str) -> tuple[datetime | None, str | None]:
    """(`last_run_finished`, the name of the source whose run that was). WP-87: a list says which source
    its "updated" time is, so that it does not read as the footer's run of any source."""
    row = conn.execute(
        """SELECT r.finished_at AS t, s.name
             FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.kind = %s AND s.active AND r.status IN ('success', 'partial') AND r.finished_at IS NOT NULL
            ORDER BY r.finished_at DESC LIMIT 1""",
        (kind,)).fetchone()
    return (row["t"], row["name"]) if row else (None, None)


def cached_last_run(conn, kind: str) -> datetime | None:
    """`last_run_finished`, cached for `LAST_RUN_SECONDS`; None (not cached) when there is
    no such run yet, or when the read does not finish in the API role's budget: a list
    must not fail for want of its timestamp."""
    try:
        return cached(("last-run", kind), lambda: last_run_finished(conn, kind),
                      LAST_RUN_SECONDS)
    except psycopg.errors.QueryCanceled:
        conn.rollback()
        return None


def list_meta(conn, kind: str) -> dict[str, Any]:
    """The `meta` of a list: when the newest run of its sources finished, and which source that was
    (cached like `cached_last_run`; empty when the read does not finish in the API role's budget)."""
    try:
        got = cached(("last-run-by", kind), lambda: (lambda r: r if r[0] else None)(last_run(conn, kind)),
                     LAST_RUN_SECONDS)
    except psycopg.errors.QueryCanceled:
        conn.rollback()
        got = None
    at, by = got or (None, None)          # no run yet is not cached, like `cached_last_run`
    return {"updatedAt": at, "updatedBy": by}
