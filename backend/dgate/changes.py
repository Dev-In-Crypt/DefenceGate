"""What changed: the real changes of the last 14 days across the site (`GET /v1/changes`).

Two kinds of entry, each about a notice that is in scope:

  - `new`      the notice was first collected in the window and was published in it (or a
               day or two before: TED notices are collected after their publication date).
               An older notice read in by a history load is not news
  - `amended`  its deadline, value (or currency), status or procedure changed, as the
               archive observed it

and a third list of its own, `funding` (ux-funding F5): funding calls first collected in the
window (`call-new`) and calls whose closing or opening date the source moved
(`call-amended`, from `call_change`). It is a separate list, not mixed into `items`, so a
reader of the tender list sees no new shape; the Atom feed and the page put it beside them.

The archive is the source and nothing is invented. An amendment is a real one, by the rule
the per-notice timeline already uses (`tenders.timeline`): versions annotated `reread`,
`out_of_order` or `remapped`, and versions annotated `correction`, are not amendments; nor
is a version that moved only the publication date (the PLACSP feed stamp), nor one a
history load wrote (note kind `history`, migration 0054: the publisher made that change
long before we read it, so "seen today" would be false). The listed
fields are an allow-list (`CHANGE_FIELDS`): a field added to the archive later is not
shown until someone decides it should be.

One entry per notice per UTC day. Within a day the entry for a notice's first sighting is
`new` and wins over amendments seen the same day; several amendments of one day are one
entry whose lines run from the day's first `before` to its last `after`.

A national notice shown under its TED twin in `/v1/tenders` is shown once here too (the
list's own collapse rules, `tenders.collapse_clauses`). Only titles, buyers, countries,
dates and statuses are served, as everywhere else: no personal data, no specifications.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from . import tenders as T
from .funding import EFFECTIVE_STATUS, FundingCall, ListMeta, get_conn, serves_meta, to_call
from .funding import SELECT as CALL_SELECT
from .listcache import cache_list

router = APIRouter()

WINDOW_DAYS = 14
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
# At most this many notices with a candidate amendment are examined, before the scope and
# the country are applied. Over a 14-day window the real figure is a few thousand (2,036 on
# 15 October 2026); the bound keeps a mass event from becoming a long query.
CANDIDATE_LIMIT = 20000
# A notice first seen in the window counts as new only if it was published no earlier than
# this many days before the window opened: TED notices are collected a day or more after
# their publication date, a history load reads in years (and 11,231 "amendments" of 16
# October 2026 were deadline moves of 2022 that a load read in).
PUBLISHED_SLACK_DAYS = 2
# The fields an amendment is listed for, as the archive names them.
CHANGE_FIELDS = ("status", "deadline_at", "value_amount", "value_currency", "procedure_type")
# Version notes that mean "not something the publisher did".
NOT_A_CHANGE = ("reread", "out_of_order", "remapped", "correction", "history")


class Change(BaseModel):
    # Stable: "<notice id>-<YYYYMMDD>". The same notice on the same day is the same entry
    # whatever else is seen later, so a feed reader does not show it twice.
    id: str
    kind: str                          # new | amended
    day: date                          # the UTC day it was observed
    detectedAt: datetime               # the latest observation of that day
    changes: list[T.FieldChange]       # empty for a new notice
    tender: T.Tender


class ChangeCounts(BaseModel):
    new: int
    amended: int


class FundingChange(BaseModel):
    # Stable: "call-<call id>-<YYYYMMDD>", one per call per UTC day.
    id: str
    kind: str                          # call-new | call-amended
    day: date
    detectedAt: datetime
    changes: list[T.FieldChange]       # empty for a new call
    call: FundingCall


class ChangePage(BaseModel):
    items: list[Change]
    total: int
    page: int
    pageSize: int
    windowDays: int
    windowFrom: datetime
    windowTo: datetime
    counts: ChangeCounts
    # Funding calls new or moved in the window, newest first; page 1 only, at most FUNDING_LIMIT.
    # `fundingTotal` counts them all, whatever the page.
    funding: list[FundingChange] = []
    fundingTotal: int = 0
    meta: ListMeta = ListMeta()


FUNDING_LIMIT = 50
FUNDING_FIELD_LABELS = {"deadline_at": "Deadline", "opens_at": "Opening date"}


def funding_events(conn, *, countries: list[str], now: datetime | None = None,
                   days: int = WINDOW_DAYS, bounded: bool = False) -> list[dict[str, Any]]:
    """Funding calls new or moved in the window, newest first, as plain dicts (`row` is the
    call's serving row). A call collected in the window is one `call-new` entry, and wins over
    a date move of the same day; several moves of a day are one entry running from the day's
    first `before` to its last `after`. A call already closed is not news."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    country_sql = " AND COALESCE(c.country, 'EU') = ANY(%s)" if countries else ""
    extra = [countries] if countries else []
    # `bounded`: `now` is the end of the window, and nothing seen after it is listed (the digest of a past week).
    first = conn.execute(
        f"{CALL_SELECT} WHERE NOT c.suppressed AND c.first_seen_at >= %s"
        f"{' AND c.first_seen_at < %s' if bounded else ''} "
        f"AND {EFFECTIVE_STATUS} <> 'closed'{country_sql}", [since, *([now] if bounded else []), *extra]).fetchall()
    moves = conn.execute(
        "SELECT ch.call_id, ch.field, ch.before_value, ch.after_value, ch.observed_at "
        f"  FROM call_change ch WHERE ch.observed_at >= %s{' AND ch.observed_at < %s' if bounded else ''} "
        "ORDER BY ch.observed_at, ch.id",
        (since, *([now] if bounded else []))).fetchall()
    events: dict[tuple[int, date], dict[str, Any]] = {}
    for r in first:
        at = r["first_seen_at"].astimezone(timezone.utc)
        events[(r["id"], at.date())] = {"row": r, "kind": "call-new", "day": at.date(), "at": at,
                                        "changes": []}
    moved: dict[tuple[int, date], dict[str, Any]] = {}
    for m in moves:
        at = m["observed_at"].astimezone(timezone.utc)
        slot = moved.setdefault((m["call_id"], at.date()), {"at": at, "lines": {}})
        slot["at"] = max(slot["at"], at)
        line = slot["lines"].setdefault(m["field"], {"field": m["field"], "before": m["before_value"]})
        line["after"] = m["after_value"]
    if moved:
        rows = {r["id"]: r for r in conn.execute(
            f"{CALL_SELECT} WHERE NOT c.suppressed AND c.id = ANY(%s){country_sql}",
            [[cid for cid, _ in moved], *extra]).fetchall()}
        for (cid, day), slot in moved.items():
            if cid not in rows or (cid, day) in events:
                continue
            lines = [{"field": f, "label": FUNDING_FIELD_LABELS[f], "before": v["before"], "after": v["after"]}
                     for f, v in slot["lines"].items() if v["before"] != v["after"]]
            if lines:
                events[(cid, day)] = {"row": rows[cid], "kind": "call-amended", "day": day,
                                      "at": slot["at"], "changes": lines}
    return sorted(events.values(), key=lambda e: (e["day"], e["at"], e["row"]["id"]), reverse=True)


def _candidates(conn, scope_sql: str, country_sql: str, params: list[Any],
                since: datetime, until: datetime | None = None) -> tuple[dict[int, datetime], list[int]]:
    """(notices first seen in the window with when, notices with a candidate amendment).

    The amendment scan is written for the planner, not for the reader (EXPLAIN ANALYZE on
    production, 15 October 2026: the `dgate_api` role has a 5 s statement timeout, and the
    plain NOT EXISTS was an index scan of all 544k versions with a note lookup per row,
    4.3 s idle and 9.5 s under load, because 273k versions of the 12-13 October re-derivation
    sit in the window). The annotated versions are read once, hashed, and the versions are
    read once: 0.8-2.4 s. A note is written after the version it annotates, so a version
    observed since `since` has its notes created since `since`: that bound is exact, and
    keeps the hashed side to the window as the notes table grows. Scope and country are
    applied by the caller, on the few thousand notices left."""
    published_from = (since - timedelta(days=PUBLISHED_SLACK_DAYS)).date()
    # The digest of a past week bounds the scan above as well as below; /changes does not.
    upper_new = " AND v.observed_at < %s" if until else ""
    upper_args = [until] if until else []
    new_rows = conn.execute(
        f"""SELECT o.id, v.observed_at
              FROM opportunity o
              JOIN opportunity_version v ON v.opportunity_id = o.id AND v.version = 1
             WHERE o.is_defence AND NOT o.suppressed AND {scope_sql}{country_sql}
               AND o.published_at >= %s AND v.observed_at >= %s{upper_new}""",
        params + [published_from, since] + upper_args).fetchall()
    upper_amended = " AND v.observed_at < %s" if until else ""
    amended_rows = conn.execute(
        f"""WITH annotated AS MATERIALIZED (
                SELECT opportunity_version_id AS vid FROM opportunity_version_note
                 WHERE kind = ANY(%s) AND created_at >= %s)
            SELECT DISTINCT v.opportunity_id AS id
              FROM opportunity_version v
             WHERE v.observed_at >= %s AND v.version > 1 AND v.changed_fields && %s::text[]
               AND NOT EXISTS (SELECT 1 FROM annotated a WHERE a.vid = v.id){upper_amended}
             LIMIT {CANDIDATE_LIMIT}""",
        [list(NOT_A_CHANGE), since, since, list(CHANGE_FIELDS)] + upper_args).fetchall()
    return ({r["id"]: r["observed_at"] for r in new_rows}, [r["id"] for r in amended_rows])


def _amendments(conn, ids: list[int], since: datetime,
                until: datetime | None = None) -> dict[tuple[int, date], dict[str, Any]]:
    """The amendments of each notice since `since`, as the notice's own timeline reads
    them, one per notice per UTC day with the day's lines merged."""
    if not ids:
        return {}
    rows = conn.execute(T.TIMELINE_SQL.format(where="v.opportunity_id = ANY(%s)"),
                        (ids,)).fetchall()
    by_notice: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_notice.setdefault(r["opportunity_id"], []).append(r)
    out: dict[tuple[int, date], dict[str, Any]] = {}
    for oid, group in by_notice.items():
        corrected = {r["version"] for r in group if "correction" in (r.get("kinds") or [])}
        for entry in T.timeline(group):
            at = entry["detectedAt"].astimezone(timezone.utc)
            if at < since or (until is not None and at >= until) or entry["version"] in corrected or entry.get("historic"):
                continue
            lines = [c for c in entry["changes"] if c["field"] in CHANGE_FIELDS]
            if not lines:
                continue
            day = at.date()
            seen = out.get((oid, day))
            if seen is None:
                out[(oid, day)] = {"at": at, "changes": lines}
                continue
            merged = {c["field"]: dict(c) for c in seen["changes"]}
            for c in lines:
                if c["field"] in merged:
                    merged[c["field"]]["after"] = c["after"]
                else:
                    merged[c["field"]] = dict(c)
            seen["changes"] = [c for c in merged.values() if c["before"] != c["after"]]
            seen["at"] = max(seen["at"], at)
            if not seen["changes"]:
                del out[(oid, day)]
    return out


def build_events(conn, *, scope: str | None, countries: list[str],
                 now: datetime | None = None, goods: str | None = None,
                 days: int = WINDOW_DAYS, bounded: bool = False) -> tuple[list[dict[str, Any]], datetime, datetime]:
    """Every event of the window, newest first, as plain dicts (`id` is the notice's),
    with the window's bounds. The scope is `relevant` (the default, None too: core and supply
    together), `core`, `supply` or `all`."""
    api = T._api()
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    scope_sql = api.SCOPE_SQL[scope or "relevant"]
    if goods:
        scope_sql = f"({scope_sql} AND {api.GOODS_SQL[goods]})"
    params: list[Any] = []
    country_sql = ""
    if countries:
        country_sql = " AND o.country = ANY(%s)"
        params.append(countries)

    first_seen, amended_ids = _candidates(conn, scope_sql, country_sql, params, since, now if bounded else None)
    ids = sorted(set(first_seen) | set(amended_ids))
    if not ids:
        return [], since, now
    # The list's own rules for showing a notice once; the filters are the ones above.
    where = ["o.is_defence = TRUE", "NOT o.suppressed", scope_sql] + (["o.country = ANY(%s)"] if countries else [])
    shown = {r["id"] for r in conn.execute(
        f"SELECT o.id FROM opportunity o WHERE o.id = ANY(%s) AND {' AND '.join(where)} "
        f"AND {T.collapse_clauses(where)}", [ids] + params * 4).fetchall()}
    amendments = _amendments(conn, [i for i in amended_ids if i in shown], since, now if bounded else None)

    events: dict[tuple[int, date], dict[str, Any]] = {}
    for (oid, day), a in amendments.items():
        events[(oid, day)] = {"id": oid, "kind": "amended", "day": day, "at": a["at"],
                              "changes": a["changes"]}
    for oid, at in first_seen.items():
        if oid in shown:
            at = at.astimezone(timezone.utc)
            events[(oid, at.date())] = {"id": oid, "kind": "new", "day": at.date(), "at": at,
                                        "changes": []}
    out = sorted(events.values(), key=lambda e: (e["day"], e["at"], e["id"]), reverse=True)
    return out, since, now


@router.get("/v1/changes", response_model=ChangePage)
@cache_list("changes", ttl=5 * 60)
def list_changes(
    country: str | None = Query(None, max_length=200),
    scope: str | None = Query(None, pattern="^(relevant|core|supply|all)$"),
    goods: str | None = Query(None, pattern="^defence$"),
    page: int = Query(1, ge=1, le=100),
    pageSize: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    conn=Depends(get_conn),
    with_meta=Depends(serves_meta),
):
    countries = T._split(country, "country", upper=True, max_length=2)
    events, since, until = build_events(conn, scope=scope, countries=countries, goods=goods)
    start = (page - 1) * pageSize
    shown = events[start:start + pageSize]
    ids = [e["id"] for e in shown]
    rows = conn.execute(f"{T.TENDER_SELECT} WHERE o.id = ANY(%s)", (ids,)).fetchall() if ids else []
    tenders = {t["id"]: t for t in T._present(conn, rows, checked=with_meta is True)}
    # The tender scope filters do not apply to funding calls; a country does (the funder's).
    calls = funding_events(conn, countries=countries) if scope in (None, "core", "all") and not goods else []
    funding = [{
        "id": f"call-{e['row']['id']}-{e['day']:%Y%m%d}", "kind": e["kind"], "day": e["day"],
        "detectedAt": e["at"], "changes": e["changes"], "call": to_call(e["row"]),
    } for e in calls[:FUNDING_LIMIT]] if page == 1 else []
    items = [{
        "id": f"{e['id']}-{e['day']:%Y%m%d}", "kind": e["kind"], "day": e["day"],
        "detectedAt": e["at"], "changes": e["changes"], "tender": tenders[str(e["id"])],
    } for e in shown if str(e["id"]) in tenders]
    from .stats import cached_last_run  # stats imports tenders

    return {
        "items": items, "total": len(events), "page": page, "pageSize": pageSize,
        "windowDays": WINDOW_DAYS, "windowFrom": since, "windowTo": until,
        "counts": {"new": sum(1 for e in events if e["kind"] == "new"),
                   "amended": sum(1 for e in events if e["kind"] == "amended")},
        "funding": funding, "fundingTotal": len(calls),
        "meta": {"updatedAt": cached_last_run(conn, "tender") if with_meta is True else None},
    }
