"""Contracts ending soon (WP-160): the contract periods notices state (WP-159), as a list by end date.

    GET /v1/tenders/ending                the first FREE_ROWS contracts ending within 3, 6 or 12 months, how many there are,
                                          and which countries' notices state periods (public); with `buyer`, the buyer
                                          page's block: the first BUYER_ROWS, free in full (owner, 31 October 2026)
    GET /v1/account/contracts/ending      the whole list, a page at a time (signed in, `expiring_contracts`, Pro); a page
                                          of more than PAGE_MAX rows is the site's CSV (`expiring_contracts_csv`, Team)

One end-date rule (`end_sql`, `basis_sql`), used by the list, its index (migration 0152), the notice's own period (`period`:
/v1/tenders/{slug}, /v1/opportunities), the saved searches of kind `ending` and their alerts (accounts.run_search,
ops/digest.py) and the coverage report (ops.contract_periods.coverage). Where the end comes from, `endBasis`:

  stated     the end date the notice states;
  computed   the start date it states plus the duration it states;
  estimated  an award notice that states a duration and no start: its publication date plus the duration. Listed only
             when asked for (`estimated=true`) and always labelled so;
  null       no end: a duration with no start (other than an award's), or nothing stated.

A renewal is said apart (`renewal`, `renewalsMax`), never added to the end. A duration over END_LIMITS (a century) is a typo:
no end is computed from it.

A contract is one row however many notices state its period: one per eForms procedure (its award notice before its call,
then the newest), and a national notice whose TED notice is in the same list is left out (the TED one is kept).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from . import accounts, billing, db
from .accounts import throttled
from .funding import get_conn, known_params

router = APIRouter()
account_router = APIRouter(prefix="/v1/account/contracts",
                           dependencies=[Depends(accounts.internal_only), Depends(accounts.no_store)])

FREE_ROWS = 10
BUYER_ROWS = 20                 # the buyer page's block, free in full
PAGE_MAX = 100                  # a page of the site (50); more at once is the CSV
CSV_ROWS = 2000                 # the CSV: the whole list up to this many rows
WITHIN = (3, 6, 12)             # months
FEATURE = "expiring_contracts"
CSV_FEATURE = "expiring_contracts_csv"
BASES = ("stated", "computed", "estimated")
# The longest duration an end is computed from, per unit: a century
END_LIMITS = {"DAY": 36600, "WEEK": 5220, "MONTH": 1200, "YEAR": 100}


def _interval(p: str) -> str:
    cases = " ".join(f"WHEN {p}contract_duration_unit = '{u}' AND {p}contract_duration <= {n} "
                     f"THEN make_interval({u.lower()}s => {p}contract_duration)" for u, n in END_LIMITS.items())
    return f"CASE {cases} END"


def end_sql(p: str = "o.", *, estimated: bool = True) -> str:
    """SQL: the contract's end date. `p` is the column prefix ("o.", or "" in the index definition). Without `estimated`,
    only a stated or computed end."""
    start = (f"COALESCE({p}contract_start, CASE WHEN {p}status = 'awarded' THEN {p}published_at END)" if estimated
             else f"{p}contract_start")
    return f"COALESCE({p}contract_end, ({start} + {_interval(p)})::date)"


def basis_sql(p: str = "o.") -> str:
    """SQL: where `end_sql` comes from: stated, computed, estimated, or NULL (no end)."""
    return (f"(CASE WHEN {p}contract_end IS NOT NULL THEN 'stated' "
            f"WHEN {end_sql(p, estimated=False)} IS NOT NULL THEN 'computed' "
            f"WHEN {end_sql(p)} IS NOT NULL THEN 'estimated' END)")


END_SQL = end_sql()
DATED_SQL = "(o.contract_end IS NOT NULL OR o.contract_start IS NOT NULL)"      # stated or computed, given END_SQL
PERIOD_COLUMNS = (", ".join(f"o.{c}" for c in db.CONTRACT_PERIOD_COLUMNS)
                  + f", {END_SQL} AS period_end, {basis_sql()} AS end_basis")


def period(r: dict[str, Any]) -> dict[str, Any] | None:
    """A row's period as served (the row carries PERIOD_COLUMNS); None when the notice states none."""
    if all(r.get(c) is None for c in db.CONTRACT_PERIOD_COLUMNS):
        return None
    return {"start": r.get("contract_start"), "end": r.get("period_end"), "endBasis": r.get("end_basis"),
            # what an estimate starts from: the award notice's publication date
            "estimatedFrom": "award_published" if r.get("end_basis") == "estimated" else None,
            "duration": r.get("contract_duration"), "durationUnit": r.get("contract_duration_unit"),
            "renewal": r.get("contract_renewal"), "renewalsMax": r.get("contract_renewals_max")}


BASIS_TEXT = {"stated": "stated end date", "computed": "computed from start + duration",
              "estimated": "estimated: award notice publication date + duration"}


def period_text(p: dict[str, Any] | None) -> str:
    """The period in words, with where its end comes from (the alert mail; web/lib/contract-period.ts is the site's)."""
    if not p:
        return "no contract period stated"
    if p["end"] is None:
        out = ("duration only, no start: no end date" if p["duration"] else "no end date stated")
    else:
        out = f"ends {p['end'].isoformat()} ({BASIS_TEXT[p['endBasis']]})"
    if p["renewal"]:
        n = p["renewalsMax"]
        out += f"; renewal options: up to {n} renewal{'s' if n != 1 else ''}" if n else "; renewal possible"
    return out


def periods(conn, ids: list[int]) -> dict[int, dict[str, Any] | None]:
    if not ids:
        return {}
    return {r["id"]: period(r) for r in conn.execute(
        f"SELECT o.id, {PERIOD_COLUMNS} FROM opportunity o WHERE o.id = ANY(%s)", (ids,)).fetchall()}


def today() -> date:
    return datetime.now(timezone.utc).date()


def add_months(d: date, n: int) -> date:
    """`d` plus `n` months, the day kept where the month has it (31 Aug + 6 months: 28 or 29 Feb)."""
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, min(d.day, monthrange(d.year + y, m + 1)[1]))


COVERAGE_SECONDS = 15 * 60


def coverage(conn) -> list[dict[str, Any]]:
    """Per country, the notices whose contract end we can date (stated or computed) and those we can only estimate: the
    list's honest note, from the data (once per COVERAGE_SECONDS: every buyer page asks)."""
    from . import stats
    from .config import settings

    if not settings().list_cache_seconds:          # 0 turns the list caches off (the test suite)
        return _coverage(conn)
    return stats.cached(("contract_coverage", today()), lambda: _coverage(conn), ttl=COVERAGE_SECONDS)


def _coverage(conn) -> list[dict[str, Any]]:
    return [{"country": r["country"], "dated": r["dated"], "estimated": r["estimated"]} for r in conn.execute(
        f"""SELECT o.country, count(*) FILTER (WHERE {DATED_SQL}) AS dated,
                   count(*) FILTER (WHERE NOT {DATED_SQL}) AS estimated
              FROM opportunity o
             WHERE o.is_defence AND NOT o.suppressed AND {END_SQL} IS NOT NULL AND o.country IS NOT NULL
             GROUP BY o.country ORDER BY count(*) FILTER (WHERE {DATED_SQL}) DESC, o.country""").fetchall()]


def _window(conn, within: int, country: str | None, cpv: str | None, buyer: int | None, estimated: bool
            ) -> tuple[str, list[Any], date, date]:
    """The SQL of the kept contracts (`kept`: id, period_end) ending between today and `within` months on, and its
    parameters."""
    from . import tenders as T

    if within not in WITHIN:
        raise HTTPException(422, "within: 3, 6 or 12 (months)")
    where, params, _ = T._tender_filters(None, country, cpv, "all", "relevant", None, buyer, None, None, None, None,
                                         None, conn)
    if not estimated:
        where.append(DATED_SQL)
    day = today()
    until = add_months(day, within)
    sql = f"""
        WITH m AS (
            SELECT o.id, o.native_id, o.ted_ref, o.source_id, o.status, o.published_at, {END_SQL} AS period_end,
                   COALESCE(o.procedure_identifier, 'id:' || o.id) AS contract
              FROM opportunity o
             WHERE {' AND '.join(where)} AND o.status IS DISTINCT FROM 'cancelled' AND {END_SQL} BETWEEN %s AND %s),
        kept AS (
            SELECT DISTINCT ON (m.contract) m.id, m.period_end FROM m
             WHERE NOT (m.ted_ref IS NOT NULL AND EXISTS (
                        SELECT 1 FROM m t WHERE t.source_id = (SELECT id FROM source WHERE code = 'ted')
                                            AND t.native_id = m.ted_ref))
             ORDER BY m.contract, (m.status = 'awarded') DESC, m.published_at DESC NULLS LAST, m.id DESC)"""
    return sql, [*params, day, until], day, until


def present(conn, ids: list[int]) -> list[dict[str, Any]]:
    """The rows as the site shows them: the tender card's fields, the period, the winners where known."""
    from . import tenders as T

    if not ids:
        return []
    rows = {r["id"]: r for r in conn.execute(f"{T.TENDER_SELECT} WHERE o.id = ANY(%s)", (ids,)).fetchall()}
    items = T._present(conn, [rows[i] for i in ids if i in rows])
    spans = periods(conn, ids)
    won = T.award_summaries(conn, {int(it["id"]): [int(t["id"]) for t in it["sameNotice"]] for it in items})
    for it in items:
        key = int(it["id"])
        it["contractPeriod"] = spans.get(key)
        it["awardedTo"] = won.get(key, {}).get("awardedTo", [])
        it["awardedPersons"] = won.get(key, {}).get("awardedPersons", 0)
    return items


def ending(conn, within: int, country: str | None, cpv: str | None, buyer: int | None, offset: int, limit: int,
           estimated: bool = False) -> dict[str, Any]:
    sql, args, day, until = _window(conn, within, country, cpv, buyer, estimated)
    got = conn.execute(f"{sql} SELECT id, count(*) OVER () AS total FROM kept ORDER BY period_end, id LIMIT %s OFFSET %s",
                       [*args, limit, offset]).fetchall()
    total = got[0]["total"] if got else (
        conn.execute(f"{sql} SELECT count(*) AS total FROM kept", args).fetchone()["total"] if offset else 0)
    return {"within": within, "from": day.isoformat(), "to": until.isoformat(), "estimated": estimated,
            "items": present(conn, [r["id"] for r in got]), "total": total, "offset": offset, "freeRows": FREE_ROWS,
            "coverage": coverage(conn)}


def entered(conn, within: int, country: str | None, cpv: str | None, buyer: int | None, estimated: bool = False
            ) -> list[dict[str, Any]]:
    """Every contract of the window with when it entered it (`enteredAt`), newest first: the later of the day its end came
    within `within` months and the first time we saw the notice. What an `ending` saved search counts as new and its alert
    mails (accounts.run_search).
    ponytail: a period stored later on a notice seen long ago (a backfill) whose end is already inside the window never
    counts as new: it is listed, not mailed. Keep the ids an alert reported if that ever matters."""
    sql, args, _, _ = _window(conn, within, country, cpv, buyer, estimated)
    rows = conn.execute(
        f"""{sql} SELECT k.id, k.period_end, (SELECT min(v.observed_at) FROM opportunity_version v
                                                 WHERE v.opportunity_id = k.id) AS first_seen
              FROM kept k""", args).fetchall()
    out = [{"id": r["id"], "enteredAt": entered_at(r["period_end"], within, r["first_seen"])} for r in rows]
    return sorted(out, key=lambda r: (r["enteredAt"], r["id"]), reverse=True)


def entered_at(end: date, within: int, first_seen: datetime | None) -> datetime:
    """When a contract ending on `end` entered a window of `within` months: the day its end came that close (00:00 UTC),
    or the first time we saw the notice if that is later."""
    crossed = datetime.combine(add_months(end, -within), time(0, 0), tzinfo=timezone.utc)
    return max(crossed, first_seen) if first_seen else crossed


def _flag(value: str | None) -> bool:
    if value not in (None, "", "true", "false"):
        raise HTTPException(422, "estimated: true or false")
    return value == "true"


FILTERS = {"within": Query(12), "country": Query(None, max_length=200), "cpv": Query(None, max_length=400),
           "buyer": Query(None, ge=1, le=2**63 - 1), "estimated": Query(None, max_length=5)}


@router.get("/v1/tenders/ending", dependencies=[Depends(known_params)])
def public_ending(within: int = FILTERS["within"], country: str | None = FILTERS["country"],
                  cpv: str | None = FILTERS["cpv"], buyer: int | None = FILTERS["buyer"],
                  estimated: str | None = FILTERS["estimated"], conn=Depends(get_conn)):
    """The first FREE_ROWS contracts ending soonest (a buyer's: BUYER_ROWS), and how many there are."""
    rows = BUYER_ROWS if buyer is not None else FREE_ROWS
    return {**ending(conn, within, country, cpv, buyer, 0, rows, _flag(estimated)), "public": True}


@account_router.get("/ending")
def full_ending(within: int = FILTERS["within"], country: str | None = FILTERS["country"],
                cpv: str | None = FILTERS["cpv"], buyer: int | None = FILTERS["buyer"],
                estimated: str | None = FILTERS["estimated"],
                page: int = Query(1, ge=1, le=1000), pageSize: int = Query(50, ge=1, le=CSV_ROWS),
                user=Depends(throttled), conn=Depends(get_conn)):
    """The paid part: the whole list a page at a time (Pro); more than PAGE_MAX rows at once is the CSV (Team)."""
    billing.require(user, FEATURE)
    if pageSize > PAGE_MAX:
        billing.require(user, CSV_FEATURE)
    return {**ending(conn, within, country, cpv, buyer, (page - 1) * pageSize, pageSize, _flag(estimated)),
            "public": False, "page": page, "pageSize": pageSize, "csv": billing.may(user, CSV_FEATURE)}
