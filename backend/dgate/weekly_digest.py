"""The weekly digest (`GET /v1/digest`, `/v1/digest/weeks`): the free, public lead magnet. WP-31.

One issue per ISO week (Monday 00:00 to the next Monday 00:00, UTC). It is built from the
same functions as `/v1/changes` and the funding list, not from queries of its own:

  tenders   new and amended defence-relevant notices of the week (`changes.build_events`
            over exactly that window, so the counts are the ones /changes gives for it)
  calls     funding calls first collected in the week and published (or opened) no earlier than two
            days before it (a source's first load of old calls is not news), calls whose opening or
            closing date the source moved, calls that opened in it (`opens_at`), and calls closing in the 14 days
            after it. Where the eligibility rules of a call were read, one line says what they
            are; where not, the issue says "not read".
  cascade   the calls of the lists above that have cascade funding (financial support to third
            parties), and how many open calls have it now.

Every section lists at most `SECTION_LIMIT` items and always gives the full count. Titles,
buyers, funders, countries, dates, statuses and the eligibility line only, as everywhere else:
no contact data, nothing about what is built.

An issue is stored once a week has ended (`digest_issue`, written by the worker, one row per
country that had something in the week and one for all of them); a week with no row is computed
on the spot. The current week is not an issue until it ends. The country is the notice's buyer
country or the call's funder country; the slice is made from the week's one event list, so the
rule that shows a national notice once may differ at the edges from /changes?country=.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from . import changes, eligibility
from . import tenders as T
from .funding import EFFECTIVE_STATUS, ROLLING_MODELS, ListMeta, get_conn, serves_meta, to_call
from .funding import SELECT as CALL_SELECT
from .listcache import cache_list

router = APIRouter()

SECTION_LIMIT = 30
CLOSING_DAYS = 14
# The first Monday of the archive: nothing earlier can be reproduced from what it holds.
ARCHIVE_START = date(2026, 9, 7)
WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


# ------------------------------------------------------------------ weeks

def week_id(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_bounds(week: str) -> tuple[datetime, datetime]:
    """[start, end) of an ISO week in UTC. ValueError for anything that is not a week."""
    m = WEEK_RE.match(week or "")
    if not m:
        raise ValueError(f"not a week: {week!r}")
    monday = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    start = datetime.combine(monday, time(0, 0), tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def last_complete_week(now: datetime) -> str:
    today = now.astimezone(timezone.utc).date()
    return week_id(today - timedelta(days=today.weekday() + 7))


def all_weeks(now: datetime) -> list[str]:
    """Every issue there can be, newest first: the archive's first week to the last complete one."""
    weeks, monday, last = [], ARCHIVE_START, last_complete_week(now)
    while week_id(monday) <= last:
        weeks.append(week_id(monday))
        monday += timedelta(days=7)
    return weeks[::-1]


# ------------------------------------------------------------------ the shape

class DigestTender(BaseModel):
    id: str
    slug: str
    kind: str                          # new | amended
    day: date
    title: str
    buyerName: str
    country: str | None
    deadline: datetime | None
    estimatedValue: dict[str, Any] | None
    changes: list[T.FieldChange] = []
    # How many notices of the week this row stands for: several notices of one buyer with the same title,
    # publication date and kind (a Polish unit's 13 notices for 13 sites, 12 Czech lots) are listed once.
    # 1 for a row that stands for itself. The counts above still count every notice.
    repeats: int = 1


class DigestCall(BaseModel):
    id: str
    slug: str
    kind: str                          # call-new | call-amended | call-opened | call-closing
    title: str
    funder: str
    programmeName: str
    funderCountry: str
    status: str
    openingDate: datetime | None
    deadline: datetime | None
    deadlineIsDate: bool = False
    cascade: bool | None = None
    # One line from the facts read from the call's document (never a verdict); null when none were read.
    eligibility: str | None = None
    # read | not_read | no_source (funding.FundingCallDetail.eligibilityState)
    eligibilityState: str = "no_source"
    # WP-87: defence | dual-use. Each list holds the defence calls first; the site heads the dual-use ones apart
    # (a stored issue from before has none: the site then shows the list as it is)
    regime: str | None = None
    changes: list[T.FieldChange] = []


class DigestCounts(BaseModel):
    tendersNew: int
    tendersAmended: int
    callsNew: int
    callsAmended: int
    callsOpened: int
    callsClosing: int
    cascade: int


class Digest(BaseModel):
    week: str
    weekFrom: datetime
    weekTo: datetime                   # exclusive: the next Monday
    closingUntil: datetime             # calls closing before this are listed
    generatedAt: datetime
    sectionLimit: int
    counts: DigestCounts
    tendersNew: list[DigestTender]
    tendersAmended: list[DigestTender]
    callsNew: list[DigestCall]
    callsAmended: list[DigestCall]
    callsOpened: list[DigestCall]
    callsClosing: list[DigestCall]
    cascadeCalls: list[DigestCall]
    # Open calls with cascade funding today (not the week's).
    cascadeOpenNow: int
    country: str | None = None
    # WP-106: the CPV prefixes the tender sections were narrowed to (`with_cpv`); empty for the whole issue
    cpv: list[str] = []
    previousWeek: str | None = None
    nextWeek: str | None = None
    meta: ListMeta = ListMeta()


class WeekSummary(BaseModel):
    week: str
    weekFrom: datetime
    weekTo: datetime
    counts: DigestCounts | None        # null for a week not stored yet (computed when opened)
    computedAt: datetime | None


# ------------------------------------------------------------------ building an issue

def distinct_events(conn, events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """The events with identical-looking ones merged, in order: (the first of them, how many). Notices of one
    buyer with the same title, publication date, kind and changes read as one row (the digest of week 42 listed
    one Polish title 13 times). They stay separate notices: each has its own page, and the counts of the issue
    count them all (WP-52, T10). WP-95: the rule of /changes (`changes.group_events`): the lot number is taken off
    the title, and one notice from two sources is one row."""
    return changes.group_events(conn, events)


def _tenders(conn, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shown = distinct_events(conn, events)[:SECTION_LIMIT]
    ids = [e["id"] for e, _ in shown]
    rows = conn.execute(f"{T.TENDER_SELECT} WHERE o.id = ANY(%s)", (ids,)).fetchall() if ids else []
    by_id = {t["id"]: t for t in T._present(conn, rows, checked=False)}
    out = []
    for e, repeats in shown:
        t = by_id.get(str(e["id"]))
        if t:
            # WP-95: the digest's tenders stay new | amended (a new award notice is a new notice of the week here)
            out.append({"id": t["id"], "slug": t["slug"], "kind": "new" if e["kind"] == "award" else e["kind"],
                        "day": e["day"], "title": t["title"],
                        "buyerName": t["buyerName"], "country": t["country"], "deadline": t["deadline"],
                        "estimatedValue": t["estimatedValue"], "changes": e["changes"], "repeats": repeats})
    return out


def _call(row: dict[str, Any], kind: str, changes_: list[dict[str, Any]], read: dict[str, Any]) -> dict[str, Any]:
    c = to_call(row)
    return {
        "id": c["id"], "slug": c["slug"], "kind": kind, "title": c["title"], "funder": c["funder"],
        "programmeName": c["programmeName"], "funderCountry": c["funderCountry"], "status": c["status"],
        "openingDate": c["openingDate"], "deadline": c["deadline"], "deadlineIsDate": c["deadlineIsDate"],
        "cascade": c["cascade"], "changes": changes_,
        "eligibility": eligibility.summary_line(read["facts"]) if read["state"] == "read" else None,
        "eligibilityState": read["state"],
        "regime": c["regime"],
    }


def build_all(conn, week: str, *, now: datetime | None = None,
              only: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """The issue of one week for every country that has something in it: {'' : all countries,
    'ES': ...}. `only` asks for just these countries (and always ''), empty ones included. The
    week's events are worked out once, for every country (`changes.build_events` over exactly the
    week), and sliced by the notice's buyer country or the call's funder country. `now` is only
    the stamp."""
    now = now or datetime.now(timezone.utc)
    start, end = week_bounds(week)
    events, _, _ = changes.build_events(conn, scope=None, countries=[], now=end, days=7, bounded=True)
    t_country = {r["id"]: r["country"] for r in conn.execute(
        "SELECT id, country FROM opportunity WHERE id = ANY(%s)", ([e["id"] for e in events],)).fetchall()} if events else {}

    cal = changes.funding_events(conn, countries=[], now=end, days=7, bounded=True)
    opened = conn.execute(
        f"{CALL_SELECT} WHERE NOT c.suppressed AND NOT c.out_of_scope AND c.opens_at >= %s AND c.opens_at < %s "
        f"AND c.id <> ALL(%s) ORDER BY c.opens_at DESC, c.id",
        (start.date(), end.date(), [e["row"]["id"] for e in cal])).fetchall()
    closing_until = end + timedelta(days=CLOSING_DAYS)
    closing = conn.execute(
        f"{CALL_SELECT} WHERE NOT c.suppressed AND NOT c.out_of_scope AND c.deadline_at >= %s AND c.deadline_at < %s "
        f"AND c.first_seen_at < %s AND c.status IN ('open', 'forthcoming') "
        f"AND COALESCE(lower(c.conditions_raw->>'deadline_model'), '') NOT IN {ROLLING_MODELS} "
        f"ORDER BY c.deadline_at, c.id", (end, closing_until, end)).fetchall()
    lists = {"call-new": [(e["row"], e["changes"]) for e in cal if e["kind"] == "call-new"],
             "call-amended": [(e["row"], e["changes"]) for e in cal if e["kind"] == "call-amended"],
             "call-opened": [(r, []) for r in opened], "call-closing": [(r, []) for r in closing]}
    # WP-87: the defence calls first in each list, the dual-use ones after them (kept, in their own order): Biotechnology
    # for Healthy Ageing headed the week's new calls. The section limit cuts the dual-use calls first.
    lists = {k: sorted(v, key=lambda x: x[0].get("regime") == "dual_use") for k, v in lists.items()}
    every = {r["id"]: r for items in lists.values() for r, _ in items}
    read = eligibility.read_many(
        conn, [(i, r.get("conditions_raw") or {}, r.get("eligibility_text"), r.get("topic_code"), r.get("type_of_action"))
               for i, r in every.items()])
    cascade_open = conn.execute(
        f"SELECT count(*) AS n FROM call c WHERE NOT c.suppressed AND NOT c.out_of_scope AND c.cascade IS TRUE "
        f"AND {EFFECTIVE_STATUS} = 'open'").fetchone()["n"]

    def funder_country(row: dict[str, Any]) -> str:
        return row.get("country") or "EU"

    def issue(country: str) -> dict[str, Any]:
        kept = {k: [(r, ch) for r, ch in v if not country or funder_country(r) == country] for k, v in lists.items()}
        cascade, seen = [], set()
        for kind, items in kept.items():
            for row, ch in items:
                if row.get("cascade") is True and row["id"] not in seen:
                    seen.add(row["id"])
                    cascade.append((kind, row, ch))
        # WP-95: a new award notice is a new notice of the week here, as before (/changes lists it apart)
        new_t = [e for e in events if e["kind"] in ("new", "award") and (not country or t_country.get(e["id"]) == country)]
        amended_t = [e for e in events if e["kind"] == "amended" and (not country or t_country.get(e["id"]) == country)]
        shown = {k: [_call(r, k, ch, read[r["id"]]) for r, ch in v[:SECTION_LIMIT]] for k, v in kept.items()}
        return {
            "week": week, "weekFrom": start, "weekTo": end, "closingUntil": closing_until, "generatedAt": now,
            "sectionLimit": SECTION_LIMIT, "country": country or None,
            "counts": {"tendersNew": len(new_t), "tendersAmended": len(amended_t),
                       "callsNew": len(kept["call-new"]), "callsAmended": len(kept["call-amended"]),
                       "callsOpened": len(kept["call-opened"]), "callsClosing": len(kept["call-closing"]),
                       "cascade": len(cascade)},
            "tendersNew": _tenders(conn, new_t), "tendersAmended": _tenders(conn, amended_t),
            "callsNew": shown["call-new"], "callsAmended": shown["call-amended"],
            "callsOpened": shown["call-opened"], "callsClosing": shown["call-closing"],
            "cascadeCalls": [_call(row, kind, ch, read[row["id"]]) for kind, row, ch in cascade[:SECTION_LIMIT]],
            "cascadeOpenNow": cascade_open,
        }

    if only is None:
        only = sorted({c for c in t_country.values() if c} | {funder_country(r) for r in every.values()})
    return {"": issue(""), **{c: issue(c) for c in only}}


def with_cpv(conn, body: dict[str, Any], week: str, country: str, prefixes: list[str]) -> dict[str, Any]:
    """WP-106 (p04: Poland week 42 was 408 notices of bread, paint and sanitary cabins): the issue with its tender sections
    narrowed to notices with a code under one of the CPV prefixes, read as the tender list reads `cpv`. The week's events of
    /changes (`changes.window_events`, the same window as the issue) filtered by the list's own rule (`changes._matching`).
    Funding calls have no product code: their sections stay as they are, and the page says so."""
    events, _, _ = changes.window_events(conn, None, [country] if country else [], None, week)
    keep = changes._matching(conn, sorted({e["id"] for e in events}), q=None, cpv=",".join(prefixes), from_=None,
                             to=None, min_=None, max_=None, currency=None)
    events = [e for e in events if e["id"] in keep]
    new_t = [e for e in events if e["kind"] in ("new", "award")]
    amended_t = [e for e in events if e["kind"] == "amended"]
    return {**body, "cpv": prefixes, "tendersNew": _tenders(conn, new_t), "tendersAmended": _tenders(conn, amended_t),
            "counts": {**body["counts"], "tendersNew": len(new_t), "tendersAmended": len(amended_t)}}


def empty_for(body: dict[str, Any], country: str) -> dict[str, Any]:
    """The issue of a country that had nothing in a stored week: the same week, nothing listed."""
    out = dict(body)
    for key in ("tendersNew", "tendersAmended", "callsNew", "callsAmended", "callsOpened", "callsClosing", "cascadeCalls"):
        out[key] = []
    out["counts"] = {k: 0 for k in body["counts"]}
    out["country"] = country
    return out


# ------------------------------------------------------------------ storing (the worker)

def _plain(body: dict[str, Any]) -> dict[str, Any]:
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(body)


def refresh_week(conn, week: str, *, now: datetime | None = None) -> int:
    """Build one week for every country and store it. Returns the rows written."""
    now = now or datetime.now(timezone.utc)
    start, end = week_bounds(week)
    issues = build_all(conn, week, now=now)
    for country, body in issues.items():
        conn.execute(
            """INSERT INTO digest_issue (week, country, week_from, week_to, body, computed_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (week, country) DO UPDATE SET body = EXCLUDED.body, computed_at = EXCLUDED.computed_at""",
            (week, country, start, end, Jsonb(_plain(body)), now))
    # A country that had something at the last build and nothing now must not keep serving it.
    conn.execute("DELETE FROM digest_issue WHERE week = %s AND country <> ALL(%s)", (week, list(issues)))
    conn.commit()
    return len(issues)


def refresh(conn, *, now: datetime | None = None, max_builds: int = 8, recompute_last: int = 2) -> dict[str, int]:
    """Store the issues: every missing week (newest first, at most `max_builds` per run) and the
    last `recompute_last` weeks again, each for every country that has something in it."""
    now = now or datetime.now(timezone.utc)
    weeks = all_weeks(now)
    held = {r["week"] for r in conn.execute("SELECT DISTINCT week FROM digest_issue").fetchall()}
    todo = [w for i, w in enumerate(weeks) if w not in held or i < recompute_last][:max_builds]
    rows = sum(refresh_week(conn, week, now=now) for week in todo)
    return {"weeks": len(weeks), "built": len(todo), "rows": rows, "missing": len([w for w in weeks if w not in held])}


# ------------------------------------------------------------------ endpoints

@router.get("/v1/digest", response_model=Digest)
@cache_list("digest", ttl=5 * 60)
def get_digest(
    week: str | None = Query(None, pattern=r"^\d{4}-W\d{2}$"),
    country: str | None = Query(None, pattern="^[A-Za-z]{2}$"),
    cpv: str | None = Query(None, max_length=400),
    conn=Depends(get_conn),
    with_meta=Depends(serves_meta),
):
    prefixes = T.cpv_prefixes(cpv)            # 422 for anything that is not a CPV prefix, as the list
    now = datetime.now(timezone.utc)
    weeks = all_weeks(now)
    chosen = week or last_complete_week(now)
    if chosen not in weeks:
        # Not in the archive, not a real ISO week, or a week that has not ended.
        raise HTTPException(404, "no such issue")
    code = (country or "").upper()
    row = conn.execute("SELECT body FROM digest_issue WHERE week = %s AND country = %s", (chosen, code)).fetchone()
    if row:
        body = row["body"]
    elif code:
        whole = conn.execute("SELECT body FROM digest_issue WHERE week = %s AND country = ''", (chosen,)).fetchone()
        # Stored: the country had nothing that week. Not stored yet: work it out.
        body = (empty_for(whole["body"], code) if whole
                else _plain(build_all(conn, chosen, now=now, only=[code])[code]))
    else:
        body = _plain(build_all(conn, chosen, now=now, only=[])[""])
    if prefixes:
        body = _plain(with_cpv(conn, body, chosen, code, prefixes))
    i = weeks.index(chosen)
    from .stats import list_meta  # stats imports tenders

    return {**body, "previousWeek": weeks[i + 1] if i + 1 < len(weeks) else None,
            "nextWeek": weeks[i - 1] if i > 0 else None,
            "meta": list_meta(conn, "tender") if with_meta is True else {}}


@router.get("/v1/digest/weeks", response_model=list[WeekSummary])
def list_weeks(limit: int = Query(52, ge=1, le=200), conn=Depends(get_conn)):
    """The issues there are, newest first, with the counts of the stored ones."""
    weeks = all_weeks(datetime.now(timezone.utc))[:limit]
    stored = {r["week"]: r for r in conn.execute(
        "SELECT week, body->'counts' AS counts, computed_at FROM digest_issue WHERE week = ANY(%s) AND country = ''",
        (weeks,)).fetchall()}
    out = []
    for w in weeks:
        start, end = week_bounds(w)
        s = stored.get(w)
        out.append({"week": w, "weekFrom": start, "weekTo": end,
                    "counts": s["counts"] if s else None, "computedAt": s["computed_at"] if s else None})
    return out
