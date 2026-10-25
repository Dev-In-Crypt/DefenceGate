"""What changed: the real changes of the last 14 days across the site (`GET /v1/changes`).

Three kinds of entry, each about a notice that is in scope:

  - `new`      the notice was first collected in the window and was published in it (or a
               day or two before: TED notices are collected after their publication date).
               An older notice read in by a history load is not news
  - `award`    the same, for a notice that is an award (WP-95, persona p04: "New" stood on new
               tenders and award results alike): its status is awarded, or the source calls
               the notice an award or a formalisation
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

WP-95: entries that look the same are one row (`group_events`): the lots of one notice
published as notices of their own ("Część II: ..."), and the same notice from two sources
of one country. Same buyer, same title once the lot number is taken off, same main code, same publication and deadline
date, kind, day and changes; the row says how many notices it stands for (`repeats`).

A national notice shown under its TED twin in `/v1/tenders` is shown once here too (the
list's own collapse rules, `tenders.collapse_clauses`). Only titles, buyers, countries,
dates and statuses are served, as everywhere else: no personal data, no specifications.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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
    kind: str                          # new | award | amended
    day: date                          # the UTC day it was observed
    detectedAt: datetime               # the latest observation of that day
    changes: list[T.FieldChange]       # empty for a new notice
    tender: T.Tender
    # WP-95: how many notices this row stands for (lots of one notice, one notice from two sources); 1 for itself
    repeats: int = 1


class ChangeCounts(BaseModel):
    new: int
    amended: int
    awards: int = 0                    # WP-95: new award notices, apart from `new` tenders


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
    # A call is new when it was first collected in the window AND the source published it (or opened it)
    # no earlier than the window, give or take PUBLISHED_SLACK_DAYS. The first load of a source reads in
    # calls published months ago: they are not news (V-B D1: 50 of W39's 74 had opened before the week).
    published_from = (since - timedelta(days=PUBLISHED_SLACK_DAYS)).date()
    first = conn.execute(
        f"{CALL_SELECT} WHERE NOT c.suppressed AND NOT c.out_of_scope AND c.first_seen_at >= %s"
        f"{' AND c.first_seen_at < %s' if bounded else ''} "
        f"AND (COALESCE(c.published_at, c.opens_at) IS NULL OR COALESCE(c.published_at, c.opens_at) >= %s) "
        f"AND {EFFECTIVE_STATUS} NOT IN ('closed', 'unlisted'){country_sql}",
        [since, *([now] if bounded else []), published_from, *extra]).fetchall()
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
            f"{CALL_SELECT} WHERE NOT c.suppressed AND NOT c.out_of_scope AND c.id = ANY(%s){country_sql}",
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


# WP-95: a notice first collected that is an award, not a call: its status is awarded, or the source names it an award
# or a formalisation (PLACSP, `notice_kind`)
AWARD_NOTICE_SQL = "(o.status = 'awarded' OR o.notice_kind IN ('award', 'formalisation'))"


def _candidates(conn, scope_sql: str, country_sql: str, params: list[Any],
                since: datetime, until: datetime | None = None
                ) -> tuple[dict[int, datetime], list[int], set[int]]:
    """(notices first seen in the window with when, notices with a candidate amendment, the first seen that are
    award notices: WP-95).

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
        f"""SELECT o.id, v.observed_at, {AWARD_NOTICE_SQL} AS is_award
              FROM opportunity o
              JOIN opportunity_version v ON v.opportunity_id = o.id AND v.version = 1
             WHERE o.is_defence AND NOT o.suppressed AND {scope_sql}{country_sql}
               AND o.published_at >= %s AND v.observed_at >= %s{upper_new}""",
        params + [published_from, since] + upper_args).fetchall()
    amended = None if until else _snapshot_candidates(conn, since)
    if amended is None:
        amended = set(amended_candidates(conn, since, until))
    return ({r["id"]: r["observed_at"] for r in new_rows}, sorted(amended),
            {r["id"] for r in new_rows if r["is_award"]})


def amended_candidates(conn, since: datetime, until: datetime | None = None) -> dict[int, datetime]:
    """The notices with a candidate amendment observed in [since, until), with the newest such observation: the
    archive scan of `_candidates`. 5.3-5.7 s over the 14 days on production (24 October 2026: 313k versions of the
    window touch a listed field, 397k remap notes to hash), so `/changes` reads it from the worker's snapshot
    (`CANDIDATES_KEY`) and scans only what was observed since (1-3 ms)."""
    upper = " AND v.observed_at < %s" if until else ""
    rows = conn.execute(
        f"""WITH annotated AS MATERIALIZED (
                SELECT opportunity_version_id AS vid FROM opportunity_version_note
                 WHERE kind = ANY(%s) AND created_at >= %s)
            SELECT v.opportunity_id AS id, max(v.observed_at) AS at
              FROM opportunity_version v
             WHERE v.observed_at >= %s AND v.version > 1 AND v.changed_fields && %s::text[]
               AND NOT EXISTS (SELECT 1 FROM annotated a WHERE a.vid = v.id){upper}
             GROUP BY v.opportunity_id
             LIMIT {CANDIDATE_LIMIT}""",
        [list(NOT_A_CHANGE), since, since, list(CHANGE_FIELDS)] + ([until] if until else [])).fetchall()
    return {r["id"]: r["at"] for r in rows}


# WP-114: the amendment candidates of the last CANDIDATES_SPAN_DAYS, kept by the worker in `list_snapshot`
# (ops/warm_lists, every four hours and at its start). A candidate is only a pre-filter: `_amendments` reads each
# notice's timeline with its notes again, so a note written after the snapshot can only make one candidate too many.
CANDIDATES_KEY = "changes-candidates"
CANDIDATES_SPAN_DAYS = WINDOW_DAYS + 1
# The scan after the snapshot starts this much before it: a load commits its versions in batches, and a version stamped
# (clock_timestamp) shortly before the snapshot may not have been visible to it.
# ponytail: a single transaction holding versions for longer than this would be missed until the next snapshot (4 h).
CANDIDATES_OVERLAP = timedelta(hours=1)


def compute_candidates(conn) -> dict[str, Any]:
    """The body of the `CANDIDATES_KEY` snapshot: the span it covers and [notice id, newest observation (epoch s)]."""
    upto = conn.execute("SELECT now() AS t").fetchone()["t"]
    since = upto - timedelta(days=CANDIDATES_SPAN_DAYS)
    found = amended_candidates(conn, since)
    return {"from": since.isoformat(), "upto": upto.isoformat(),
            "ids": [[oid, at.timestamp()] for oid, at in sorted(found.items())]}


def _snapshot_candidates(conn, since: datetime) -> set[int] | None:
    """The candidates since `since` from the snapshot plus the scan of what came after it; None when there is no usable
    snapshot (none, older than `listcache.SNAPSHOT_HOURS`, or not reaching back to `since`): the caller scans."""
    from .listcache import SNAPSHOT_HOURS

    try:
        with conn.transaction():        # a savepoint: a role that may not read the table loses nothing else
            row = conn.execute(
                "SELECT body FROM list_snapshot WHERE key = %s AND computed_at > now() - make_interval(hours => %s)",
                (CANDIDATES_KEY, SNAPSHOT_HOURS)).fetchone()
    except Exception:  # noqa: BLE001 - a snapshot is a shortcut, never a failure
        return None
    body = row["body"] if row else None
    if not body or datetime.fromisoformat(body["from"]) > since:
        return None
    upto = datetime.fromisoformat(body["upto"])
    edge = since.timestamp()
    out = {int(oid) for oid, at in body["ids"] if at >= edge}
    return out | set(amended_candidates(conn, max(since, upto - CANDIDATES_OVERLAP)))


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
        # What the publisher changed before we first read the notice is not an amendment we observed: PLACSP
        # feeds a notice once per modification, so a second version minutes after the first was written
        # earlier by the publisher (V-B D2: all 30 "amended" of W37).
        first_day = group[0]["observed_at"].astimezone(timezone.utc).date()
        for entry in T.timeline(group):
            at = entry["detectedAt"].astimezone(timezone.utc)
            if (at < since or (until is not None and at >= until) or entry["version"] in corrected
                    or entry.get("historic") or at.date() == first_day):
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

    first_seen, amended_ids, awards = _candidates(conn, scope_sql, country_sql, params, since,
                                                  now if bounded else None)
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
            events[(oid, at.date())] = {"id": oid, "kind": "award" if oid in awards else "new", "day": at.date(),
                                        "at": at, "changes": []}
    out = sorted(events.values(), key=lambda e: (e["day"], e["at"], e["id"]), reverse=True)
    return out, since, now


# The lot or part number a title carries ("Część II:", "Lote 3 -", "Los 2", "Lot n°1", "část 4"), taken off before two
# titles are compared (`group_key`).
_LOT_NUMBER = re.compile(
    r"\b(?:lot[eo]?s?|los|lotto|cz[eę][sś][cć]|[cč][aá]st|teil|pakiet|zadanie|part(?:ie)?|cz\.)\s*"
    r"(?:n[º°o]\.?\s*|nr\.?\s*|no\.?\s*)?(?:[ivxlcdm]+|\d+)\b[\s:.\-–—)]*", re.IGNORECASE)


def base_title(title: str | None) -> str:
    """A title with its lot number taken off, lower case, single-spaced: two lots of one notice compare equal."""
    text = _LOT_NUMBER.sub(" ", (title or "").lower())
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def group_key(row: dict[str, Any], event: dict[str, Any]) -> tuple:
    """WP-95: what two events must share to be one row: buyer, title without its lot number, main CPV code, publication
    date, deadline, kind, day and the changes. The source is not in it: one notice from two sources of a country is one row."""
    return (row.get("buyer_org_id") or row.get("buyer_name_raw"), base_title(row.get("title_original")),
            (row.get("cpv_codes") or [None])[0], row.get("published_at"), row.get("deadline_at"), event["kind"], event["day"],
            tuple((c["field"], c["before"], c["after"]) for c in event["changes"]))


def group_events(conn, events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """The events with identical-looking ones merged, in order: (the first of them, how many). They stay separate
    notices, each with its own page (WP-52 T10 for the digest; WP-95 for /changes)."""
    if not events:
        return []
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, buyer_org_id, buyer_name_raw, title_original, cpv_codes, published_at, deadline_at FROM opportunity "
        "WHERE id = ANY(%s)",
        ([e["id"] for e in events],)).fetchall()}
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for e in events:
        key = group_key(rows[e["id"]], e) if e["id"] in rows else (e["id"],)
        groups.setdefault(key, []).append(e)
    return [(g[0], len(g)) for g in groups.values()]


def week_end(week: str, now: datetime | None = None) -> tuple[datetime, float]:
    """(where a week's window ends, how many days it spans): the next Monday, or now for the week under way (WP-90)."""
    from .weekly_digest import week_bounds

    start, end = week_bounds(week)
    end = min(end, now or datetime.now(timezone.utc))
    return end, (end - start) / timedelta(days=1)


def window_events(conn, scope: str | None, countries: list[str], goods: str | None,
                  week: str | None = None):
    """`build_events` for the page endpoints, kept five minutes per (scope, countries, goods, week): the 14-day
    window costs 1.2-2.1 s on a miss (verify2-abuse N4, 18 October 2026), and the page, the page size and the
    Atom feed (page 1 of 100) all read the same window, so each used to compute it again. `week` (an ISO week,
    `2026-W42`) is that week of the digest instead of the last 14 days: the same events the issue counts, which
    is where the digest's "the list has the rest" leads (WP-52, T10)."""
    from . import stats
    from .config import settings

    def compute():
        if week is None:
            return build_events(conn, scope=scope, countries=countries, goods=goods)
        end, days = week_end(week)
        return build_events(conn, scope=scope, countries=countries, goods=goods, now=end, days=days, bounded=True)

    ttl = settings().list_cache_seconds
    return stats.cached(("changes-window", scope, tuple(countries), goods, week), compute,
                        0 if ttl <= 0 else 5 * 60, store=stats._list_cache, limit=stats.LIST_CACHED)


def _matching(conn, ids: list[int], *, q, cpv, from_, to, min_, max_, currency, cpv_main: bool = False,
              not_cpv: str | None = None, status: str = "all") -> set[int]:
    """WP-87: of these notices, the ones the tender list's own filters keep (`tenders._tender_filters`, any status):
    the search words, CPV prefixes, deadline range and value range read exactly as the list reads them. The scope,
    the goods filter and the country are applied by `build_events` already. WP-90: the main-code reading, the
    excluded codes and the list's status (as of now: a feed of "Open" holds what is open today) too."""
    if not ids:
        return set()
    where, params, _ = T._tender_filters(q, None, cpv, status, "all", None, None, from_, to, min_, max_, currency,
                                         cpv_main=cpv_main, not_cpv=not_cpv)
    return {r["id"] for r in conn.execute(
        f"SELECT o.id FROM opportunity o WHERE o.id = ANY(%s) AND {' AND '.join(where)}", [ids, *params]).fetchall()}


# WP-90: the kinds a list can be narrowed to: new notices, every amendment, or the amendments that moved one thing
# (the deadline; the value or its currency; the status). A procedure change is an amendment and nothing more.
# WP-95: `award`, the new award notices (`new` is the new calls and other notices).
KIND_FIELDS = {"deadline": ("deadline_at",), "value": ("value_amount", "value_currency"), "status": ("status",)}
KIND_PATTERN = "^(new|award|amended|deadline|value|status)$"


def of_kind(event: dict[str, Any], kind: str) -> bool:
    """Whether an event is of a kind of `KIND_PATTERN`."""
    if kind in ("new", "award", "amended"):
        return event["kind"] == kind
    return event["kind"] == "amended" and any(c["field"] in KIND_FIELDS[kind] for c in event["changes"])


@router.get("/v1/changes", response_model=ChangePage, dependencies=[Depends(T.known_params)])
@cache_list("changes", ttl=5 * 60, snapshot=True)
def list_changes(
    country: str | None = Query(None, max_length=200),
    scope: str | None = Query(None, pattern="^(relevant|core|supply|all)$"),
    goods: str | None = Query(None, pattern="^defence$"),
    q: str | None = Query(None, max_length=100),
    cpv: str | None = Query(None, max_length=400),
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    min_: float | None = Query(None, alias="min", ge=0, le=1e13),
    max_: float | None = Query(None, alias="max", ge=0, le=1e13),
    currency: str | None = Query(None, pattern="^[A-Za-z]{3}$"),
    page: int = Query(1, ge=1, le=100),
    pageSize: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    week: str | None = Query(None, pattern=r"^\d{4}-W\d{2}$"),
    kind: str | None = Query(None, pattern=KIND_PATTERN),
    status: str | None = Query(None, pattern=T.STATUS_PATTERN),
    cpvMain: bool = Query(False),
    notCpv: str | None = Query(None, max_length=400),
    conn=Depends(get_conn),
    with_meta=Depends(serves_meta),
):
    """`week` is an ISO week of the archive (`2026-W42`, as the digest's) instead of the last 14 days; `kind`
    lists only the new or only the amended notices. `counts` always count both kinds of the window.

    WP-87: the tender list's other filters as well (`q`, `cpv`, deadline `from`/`to`, value `min`/`max`/`currency`),
    so a filtered list and its feed of changes hold the same notices; `counts` are then of the filtered window.
    Funding calls have no CPV code, value range or tender search, so with any of them the funding part is empty.
    An unknown parameter is a 422 (`/v1/changes?cpv=` was ignored before)."""
    countries = T._split(country, "country", upper=True, max_length=2)
    if week is not None:
        from .weekly_digest import all_weeks, week_bounds, week_id

        try:
            week_bounds(week)
        except ValueError:
            raise HTTPException(404, "no such week") from None
        now = datetime.now(timezone.utc)
        # WP-90: the week under way too ("this week so far", from the digest): its events up to now
        if week not in all_weeks(now) and week != week_id(now.date()):
            raise HTTPException(404, "no such week")      # not in the archive, or in the future
    events, since, until = window_events(conn, scope, countries, goods, week)
    narrowed = any(v is not None for v in (q, cpv, from_, to, min_, max_, currency, notCpv, status)) or (
        cpvMain and cpv is not None)
    if narrowed:
        keep = _matching(conn, sorted({e["id"] for e in events}), q=q, cpv=cpv, from_=from_, to=to,
                         min_=min_, max_=max_, currency=currency, cpv_main=cpvMain, not_cpv=notCpv,
                         status=status or "all")
        events = [e for e in events if e["id"] in keep]
    # WP-95: the lots of one notice and one notice from two sources are one row
    grouped = group_events(conn, events)
    everything = grouped
    if kind:
        grouped = [(e, n) for e, n in grouped if of_kind(e, kind)]
    start = (page - 1) * pageSize
    shown_rows = grouped[start:start + pageSize]
    shown = [e for e, _ in shown_rows]
    repeats = {id(e): n for e, n in shown_rows}
    ids = [e["id"] for e in shown]
    rows = conn.execute(f"{T.TENDER_SELECT} WHERE o.id = ANY(%s)", (ids,)).fetchall() if ids else []
    # WP-106 (p04): an award row says its winners and its value, as the tender list does (an HTTP request: see `serves_meta`)
    present = T._present(conn, rows, checked=with_meta is True)
    tenders = {t["id"]: t for t in (T.list_item_fields(conn, present) if with_meta is True else present)}
    # The tender scope filters do not apply to funding calls; a country does (the funder's).
    if scope in (None, "core", "all") and not goods and not kind and not narrowed:
        calls = (funding_events(conn, countries=countries) if week is None else
                 funding_events(conn, countries=countries, now=until, days=(until - since) / timedelta(days=1),
                                bounded=True))
    else:
        calls = []
    funding = [{
        "id": f"call-{e['row']['id']}-{e['day']:%Y%m%d}", "kind": e["kind"], "day": e["day"],
        "detectedAt": e["at"], "changes": e["changes"], "call": to_call(e["row"]),
    } for e in calls[:FUNDING_LIMIT]] if page == 1 else []
    items = [{
        "id": f"{e['id']}-{e['day']:%Y%m%d}", "kind": e["kind"], "day": e["day"],
        "detectedAt": e["at"], "changes": e["changes"], "tender": tenders[str(e["id"])], "repeats": repeats[id(e)],
    } for e in shown if str(e["id"]) in tenders]
    from .stats import list_meta  # stats imports tenders

    return {
        "items": items, "total": len(grouped), "page": page, "pageSize": pageSize,
        "windowDays": WINDOW_DAYS if week is None else 7, "windowFrom": since, "windowTo": until,
        "counts": {"new": sum(1 for e, _ in everything if e["kind"] == "new"),
                   "awards": sum(1 for e, _ in everything if e["kind"] == "award"),
                   "amended": sum(1 for e, _ in everything if e["kind"] == "amended")},
        "funding": funding, "fundingTotal": len(calls),
        "meta": list_meta(conn, "tender") if with_meta is True else {},
    }
