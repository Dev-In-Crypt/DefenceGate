"""WP-52 (UX audit of 19 October 2026, tenders backend), against a real Postgres.

T2/T3 search and deep pages with bounded work, T8 a planned notice is not closed, T9 the calendar's whole range,
T10 the digest lists a repeated notice once and /v1/changes reaches a week, T11 which time `retrievedAt` is,
T13 the counts beside a list are the list's, T14 a buyer link that resolves and counts that equal the list,
T15 the slugs, T16/T18 a source's rhythm, why a run is partial, and the names with their accents."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, config, db, stats, tenders
from dgate import weekly_digest as W
from dgate.listcache import snapshot_key, stored
from dgate.ops import warm_lists
from tests.integration.test_changes import age, opp, store

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=30)
PAST = NOW - timedelta(days=30)


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def cache_on(monkeypatch):
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()
    yield
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    config.reset_cache()
    stats.reset_cache()


def put(conn, native_id: str, *, status: str = "open", deadline=FUTURE, tag: str = "a", **kw) -> int:
    return store(conn, replace(opp(native_id, deadline=deadline, **kw), status=status), tag)


def ids(client, **params) -> list[str]:
    body = client.get("/v1/tenders", params={"scope": "all", **params}).json()
    return [t["noticeId"] for t in body["items"]]


def listing(client, **params) -> dict:
    r = client.get("/v1/tenders", params={"scope": "all", **params})
    assert r.status_code == 200, r.text
    return r.json()


# ======================================================================= T8: a planned notice is not closed

def test_a_planned_notice_is_neither_open_nor_closed_until_its_deadline_passes(client, conn):
    put(conn, "PLANNED-AHEAD", status="forthcoming")
    put(conn, "PLANNED-NO-DEADLINE", status="forthcoming", deadline=None)
    put(conn, "PLANNED-LAPSED", status="forthcoming", deadline=PAST)
    put(conn, "AWARDED", status="awarded", deadline=PAST)
    put(conn, "OPEN")
    assert ids(client, status="open") == ["OPEN"]
    assert sorted(ids(client, status="closed")) == ["AWARDED", "PLANNED-LAPSED"]
    assert sorted(ids(client, status="planned")) == ["PLANNED-AHEAD", "PLANNED-NO-DEADLINE"]
    assert len(ids(client, status="all")) == 5
    by_id = {t["noticeId"]: t for t in listing(client, status="all")["items"]}
    assert by_id["PLANNED-AHEAD"]["statusNative"] == "forthcoming"
    assert by_id["PLANNED-LAPSED"]["statusNative"] == "expired"


def test_the_counts_of_the_statuses_add_up_to_all(client, conn):
    for n, status in enumerate(("open", "forthcoming", "awarded", "cancelled", "forthcoming")):
        put(conn, f"S-{n}", status=status, deadline=FUTURE if status != "awarded" else PAST)
    totals = {s: listing(client, status=s)["total"] for s in ("open", "closed", "planned", "all")}
    assert totals["open"] + totals["closed"] + totals["planned"] == totals["all"] == 5


# ======================================================================= T2 / T3: bounded work

def test_a_search_word_finds_the_open_notices_with_the_status_and_country_filters(client, conn):
    put(conn, "BW-1", title="Bundeswehr uniforms", country="DE")
    put(conn, "BW-2", title="Boots for the Bundeswehr", country="DE", deadline=PAST)
    put(conn, "BW-3", title="Bundeswehr vehicles", country="PL")
    put(conn, "OTHER", title="Radar", country="DE")
    assert sorted(ids(client, q="Bundeswehr")) == ["BW-1", "BW-3"]
    assert ids(client, q="Bundeswehr", country="DE") == ["BW-1"]
    assert sorted(ids(client, q="Bundeswehr", status="all")) == ["BW-1", "BW-2", "BW-3"]
    assert ids(client, q="Bundeswehr", status="closed") == ["BW-2"]
    assert sorted(ids(client, q="Bundeswehr", **{"from": (FUTURE - timedelta(days=1)).date().isoformat()})) == ["BW-1", "BW-3"]
    assert ids(client, q="Bundeswehr", **{"from": (FUTURE + timedelta(days=2)).date().isoformat()}) == []


def test_a_page_past_the_depth_limit_has_no_items_and_says_so(client, conn, monkeypatch):
    for n in range(8):
        put(conn, f"C-{n}", status="awarded", deadline=PAST - timedelta(days=n))
    monkeypatch.setattr(tenders, "MAX_OFFSET", 6)
    served = listing(client, status="closed", pageSize=2, page=3)
    assert [t["noticeId"] for t in served["items"]] == ["C-4", "C-5"]
    past = listing(client, status="closed", pageSize=2, page=4)
    assert past["items"] == [] and past["total"] == 8 and past["maxOffset"] == 6 and past["page"] == 4


def test_a_long_list_counts_up_to_a_cap_and_says_it_stopped(client, conn, monkeypatch):
    for n in range(8):
        put(conn, f"C-{n}", status="awarded", deadline=PAST - timedelta(days=n))
    assert listing(client, status="closed")["totalCapped"] is False
    monkeypatch.setattr(tenders, "SMALL_CAP", 2)
    monkeypatch.setattr(tenders, "TOTAL_CAP", 3)
    body = listing(client, status="closed", pageSize=2)
    assert body["totalCapped"] is True and body["total"] == 3 and len(body["items"]) == 2
    # a short last page is exact whatever the cap: the end of the list was read
    last = listing(client, status="closed", pageSize=5, page=2)
    assert last["totalCapped"] is False and last["total"] == 8 and len(last["items"]) == 3


def test_a_count_that_runs_out_of_time_leaves_a_lower_bound_not_an_error(client, conn, monkeypatch):
    for n in range(4):
        put(conn, f"C-{n}", status="awarded", deadline=PAST - timedelta(days=n))
    monkeypatch.setattr(tenders, "_count_up_to", lambda *a, **k: None)
    body = listing(client, status="closed", pageSize=2)
    assert body["totalCapped"] is True and body["total"] == 3 and len(body["items"]) == 2     # "at least": another page
    assert client.get("/v1/tenders/scope-counts", params={"status": "closed"}).status_code == 503


def test_an_at_least_total_of_all_is_never_below_the_open_list(client, conn, monkeypatch):
    """WP-59 (re-audit of the data pages, NEW-2): Bundeswehr, `all` read "at least 112" while Open alone was 116. The
    open part of `all` counts fewer (an open notice whose twin is closed is in the rest) and the rest ran out of time."""
    for n in range(5):
        put(conn, f"O-{n}", deadline=FUTURE + timedelta(days=n))
    put(conn, "C-0", status="awarded", deadline=PAST)
    real = tenders._count
    parts = iter([(3, False), (0, True)])      # the open part of `all` (collapsed against closed twins), then the rest

    def count(conn_, where, params, extra=None):
        return next(parts) if extra else real(conn_, where, params, extra)

    open_total = listing(client, status="open")["total"]
    monkeypatch.setattr(tenders, "_count", count)
    body = listing(client, status="all", pageSize=2)
    assert open_total == 5 and body["totalCapped"] is True and body["total"] >= open_total


def test_the_count_gives_up_after_its_time_box_and_the_connection_is_usable(conn):
    put(conn, "ONE")
    where, params, _ = tenders._tender_filters(None, None, None, "open", "all", None, None, None, None, None, None, None)
    before = conn.execute("SELECT current_setting('statement_timeout') AS t").fetchone()["t"]
    slow = " AND ".join([*where, "pg_sleep(0.3) IS NOT NULL"])
    assert tenders._count_up_to(conn, slow, where, params, 10, 20) is None
    assert conn.execute("SELECT 1 AS n").fetchone()["n"] == 1                       # rolled back, usable
    quick = tenders._count_up_to(conn, " AND ".join(where), where, params, 10, 5000)
    assert quick == 1
    assert conn.execute("SELECT current_setting('statement_timeout') AS t").fetchone()["t"] == before


def test_a_deep_page_repeats_the_exact_total_the_worker_stored(client, conn, monkeypatch):
    for n in range(12):
        put(conn, f"C-{n}", status="awarded", deadline=PAST - timedelta(days=n))
    monkeypatch.setattr(tenders, "SMALL_CAP", 2)
    monkeypatch.setattr(tenders, "TOTAL_CAP", 3)
    live = listing(client, status="closed", page=2, pageSize=2)
    assert live["totalCapped"] is True and live["total"] == 5     # at least: this page, and one more
    empty = listing(client, status="closed", page=2, pageSize=20)   # a page past the end claims nothing it did not read
    assert empty["items"] == [] and empty["total"] == 3 and empty["totalCapped"] is True
    kw = {**warm_lists._defaults(tenders.list_tenders.__wrapped__), "with_meta": True, "status": "closed",
          "scope": "all", "page": 1, "pageSize": 10}
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())",
                 (snapshot_key("tenders", kw), Jsonb({"total": 287634, "totalCapped": False})))
    conn.commit()
    got = listing(client, status="closed", page=2, pageSize=2)
    assert got["total"] == 287634 and got["totalCapped"] is False
    # a snapshot that was itself only "at least" is no better than a live count
    conn.execute("UPDATE list_snapshot SET body = %s", (Jsonb({"total": 10000, "totalCapped": True}),))
    conn.commit()
    assert listing(client, status="closed", page=2, pageSize=2)["totalCapped"] is True


def test_the_worker_keeps_exact_totals_whatever_the_cap(client, conn, monkeypatch):
    for n in range(12):
        put(conn, f"C-{n}", status="awarded", deadline=PAST - timedelta(days=n))
    monkeypatch.setattr(tenders, "SMALL_CAP", 2)
    monkeypatch.setattr(tenders, "TOTAL_CAP", 3)
    result = warm_lists.run(conn, write=True)
    assert result["failed"] == 0 and result["written"] == result["views"]
    kw = {**warm_lists._defaults(tenders.list_tenders.__wrapped__), "with_meta": True, "status": "closed",
          "page": 1, "pageSize": 10}
    body = conn.execute("SELECT body FROM list_snapshot WHERE key = %s", (snapshot_key("tenders", kw),)).fetchone()["body"]
    assert body["total"] == 12 and body["totalCapped"] is False and body["maxOffset"] == tenders.MAX_OFFSET
    keys = {r["key"] for r in conn.execute("SELECT key FROM list_snapshot").fetchall()}
    assert {"tender-slugs?", "buyer-slugs?", tenders.BUYER_BASE_KEY} <= keys
    # the open lists and their counts are not kept: they are read live, together
    assert not any(k.startswith("tender-scope-counts?") and "status=open" in k for k in keys)


def test_all_is_the_open_notices_and_then_the_rest_and_a_page_can_hold_both(client, conn):
    for n in range(3):
        put(conn, f"O-{n}", deadline=FUTURE + timedelta(days=n))
    for n in range(4):
        put(conn, f"C-{n}", status="awarded", deadline=PAST - timedelta(days=n))
    # WP-106 (p02, p04, p07): the rest newest deadline first, as the Closed list (it ran oldest first: 2017 under the open ones)
    pages = [ids(client, status="all", pageSize=2, page=p) for p in (1, 2, 3, 4)]
    assert pages == [["O-0", "O-1"], ["O-2", "C-0"], ["C-1", "C-2"], ["C-3"]]
    # the oldest first when asked for, still with the open ones first
    asc = [ids(client, status="all", sort="deadline-asc", pageSize=2, page=p) for p in (1, 2, 3, 4)]
    assert asc == [["O-0", "O-1"], ["O-2", "C-3"], ["C-2", "C-1"], ["C-0"]]
    assert all(listing(client, status="all", pageSize=2, page=p)["total"] == 7 for p in (1, 2, 3, 4, 5))
    assert ids(client, status="all", pageSize=2, page=5) == []
    # explicit sorts are honoured on the whole list, with no open-first rule
    assert ids(client, status="all", sort="deadline-desc", pageSize=3) == ["O-2", "O-1", "O-0"]


# ======================================================================= T13: the counts are the list's

def test_the_counts_beside_the_list_are_the_totals_of_the_lists_they_lead_to(client, conn):
    put(conn, "700-2026", source="ted", country="PL")
    put(conn, "NL-1", source="nl_tenderned", country="PL", kind="supply", ted_ref="700-2026")
    put(conn, "SUP", kind="supply", country="PL")
    got = client.get("/v1/tenders/scope-counts").json()
    for scope in ("relevant", "core", "supply"):
        assert got[scope] == client.get("/v1/tenders", params={"scope": scope}).json()["total"], scope
    assert (got["relevant"], got["core"], got["supply"]) == (2, 1, 2)
    # the union shows the national copy once: the two lists add up to one more than the union
    assert got["overlap"] == 1 and got["capped"] is False
    assert datetime.fromisoformat(got["asOf"]) <= datetime.now(timezone.utc)


def test_a_list_says_when_it_was_worked_out(client, conn):
    put(conn, "ONE")
    body = client.get("/v1/tenders").json()
    assert datetime.fromisoformat(body["asOf"]) > NOW - timedelta(minutes=5)


# ======================================================================= T9: the calendar

def test_the_calendar_holds_every_open_notice_and_not_the_first_five_hundred(client, conn):
    base = NOW + timedelta(days=1)
    for n in range(130):
        put(conn, f"D-{n:03d}", deadline=base + timedelta(days=n))
    put(conn, "NO-DEADLINE", deadline=None)
    put(conn, "CLOSED", status="awarded", deadline=PAST)
    body = client.get("/v1/tenders/calendar", params={"scope": "all"}).json()
    assert body["total"] == 130 and body["truncated"] is False and len(body["items"]) == 130
    stamps = [i["deadline"] for i in body["items"]]
    assert stamps == sorted(stamps) and body["items"][-1]["noticeId"] == "D-129"
    first = body["items"][0]
    assert set(first) >= {"id", "slug", "title", "buyerName", "country", "deadline", "scope", "status", "sourceName"}
    narrowed = client.get("/v1/tenders/calendar", params={"scope": "all", "from": (base + timedelta(days=100)).date().isoformat()}).json()
    assert [i["noticeId"] for i in narrowed["items"]][0] >= "D-100"
    short = client.get("/v1/tenders/calendar", params={"scope": "all", "maxItems": 5}).json()
    assert short["truncated"] is True and len(short["items"]) == 5 and short["total"] == 130


def test_the_calendar_shows_the_deadline_the_notices_page_shows(client, conn):
    put(conn, "TED-1", source="ted", country="FR", deadline=NOW + timedelta(days=20))
    put(conn, "ES-1", source="es_placsp", country="ES", deadline=NOW + timedelta(days=400), ted_ref="TED-1")
    # the TED notice is outside the country filter, so the national one is not hidden under it
    item = [i for i in client.get("/v1/tenders/calendar", params={"scope": "all", "country": "ES"}).json()["items"]
            if i["noticeId"] == "ES-1"][0]
    page = client.get(f"/v1/tenders/{item['id']}").json()
    assert item["deadline"] == page["deadline"] and item["deadlineFrom"] == page["deadlineFrom"] == "ted_twin"


# ======================================================================= T10: the digest and the changes of a week

def _last_week_event(conn, native_id: str, *, title: str = "Armoured vehicles", country: str = "PL", day: int = 1):
    start, _ = W.week_bounds(W.last_complete_week(NOW))
    when = start + timedelta(days=day, hours=6)
    oid = store(conn, opp(native_id, country=country, title=title, published=when.date()))
    age(conn, oid, (NOW - when).total_seconds() / 86400)
    return oid


def test_the_digest_lists_identical_notices_once_and_counts_them_all(conn):
    week = W.last_complete_week(NOW)
    for n in range(5):
        _last_week_event(conn, f"SAME-{n}", title="Lease of a transformer station")
    _last_week_event(conn, "OTHER", title="Boots")
    issue = W.build_all(conn, week, only=[])[""]
    assert issue["counts"]["tendersNew"] == 6
    rows = {r["title"]: r for r in issue["tendersNew"]}
    assert len(issue["tendersNew"]) == 2
    assert rows["Lease of a transformer station"]["repeats"] == 5 and rows["Boots"]["repeats"] == 1


def test_changes_can_be_asked_for_a_week_and_a_kind(client, conn):
    week = W.last_complete_week(NOW)
    for n in range(3):
        _last_week_event(conn, f"W-{n}", title=f"Armoured vehicles {n}")   # WP-95: one title thrice would be one row
    store(conn, opp("TODAY"))
    this = client.get("/v1/changes", params={"week": week}).json()
    assert this["total"] == 3 and this["windowDays"] == 7 and this["counts"] == {"new": 3, "amended": 0, "awards": 0}
    assert sorted(i["tender"]["noticeId"] for i in this["items"]) == ["W-0", "W-1", "W-2"]
    assert client.get("/v1/changes", params={"week": week, "kind": "amended"}).json()["total"] == 0
    assert client.get("/v1/changes", params={"kind": "new"}).json()["total"] == 4       # the last 14 days: the week's and TODAY
    assert client.get("/v1/changes", params={"week": "2026-W01"}).status_code == 404         # before the archive
    # WP-90: the week under way is listed up to now ("this week so far", from the digest); a week to come is not
    so_far = client.get("/v1/changes", params={"week": W.week_id(NOW.date())}).json()
    assert [i["tender"]["noticeId"] for i in so_far["items"]] == ["TODAY"]
    assert client.get("/v1/changes", params={"week": W.week_id(NOW.date() + timedelta(days=7))}).status_code == 404
    assert client.get("/v1/changes", params={"kind": "other"}).status_code == 422


# ======================================================================= T11: which time `retrievedAt` is

def test_the_source_stamp_says_whether_it_is_a_change_or_our_first_sight(client, conn):
    put(conn, "T11-1")
    one = client.get("/v1/tenders", params={"scope": "all"}).json()["items"][0]
    assert one["source"]["lastChangeKind"] == "first_seen"
    put(conn, "T11-1", deadline=FUTURE + timedelta(days=14), tag="b")
    two = client.get("/v1/tenders", params={"scope": "all"}).json()["items"][0]
    assert two["source"]["lastChangeKind"] == "amendment" and two["amended"] is True
    detail = client.get(f"/v1/tenders/{two['id']}").json()
    assert detail["source"]["lastChangeKind"] == "amendment"


# ======================================================================= T14: buyers

def test_a_buyer_that_has_only_supply_notices_has_no_link_and_one_with_a_core_notice_has(client, conn):
    put(conn, "CORE-1", country="PL")                           # buyer "Ministry PL": a core notice
    put(conn, "SUP-1", kind="supply", country="PL")              # the same buyer, a supply notice
    store(conn, replace(opp("SUP-2", kind="supply", country="ES"), buyer_name_raw="Cuartel sin avisos"))
    by_id = {t["noticeId"]: t for t in listing(client)["items"]}
    assert by_id["CORE-1"]["buyerSlug"] and by_id["SUP-1"]["buyerSlug"] == by_id["CORE-1"]["buyerSlug"]
    # WP-96: a buyer page counts the list's default scope, so a buyer with only other purchases has a page and a link
    assert by_id["SUP-2"]["buyerSlug"] and by_id["SUP-2"]["buyerName"] == "Cuartel sin avisos"
    assert by_id["SUP-2"]["buyerId"]                                    # the id still filters the list
    assert client.get(f"/v1/buyers/{by_id['CORE-1']['buyerSlug']}").status_code == 200
    # every link on the list resolves
    for t in by_id.values():
        if t["buyerSlug"]:
            assert client.get(f"/v1/buyers/{t['buyerSlug']}").status_code == 200


def _store_exact_base(conn, stale_open: int | None = None) -> None:
    base = tenders.compute_buyer_base(conn, exact=True)
    if stale_open is not None:
        base[2] = [stale_open for _ in base[2]]
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now()) "
                 "ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, computed_at = EXCLUDED.computed_at",
                 (tenders.BUYER_BASE_KEY, Jsonb(stored(jsonable_encoder(base)))))
    conn.commit()


def test_tenders_in_archive_equals_the_buyers_own_list(client, conn):
    put(conn, "700-2026", source="ted", country="PL")
    put(conn, "701-2026", source="ted", country="PL", ted_ref="700-2026")      # a copy of the first, which the list shows once
    put(conn, "OTHER", source="ted", country="PL", status="awarded", deadline=PAST)
    tender = client.get("/v1/tenders", params={"status": "all"}).json()["items"][0]
    slug, buyer_id = tender["buyerSlug"], tender["buyerId"]
    assert {t["buyerId"] for t in listing(client, status="all")["items"]} == {buyer_id}
    # without the worker's result the count is the plain one (a twin counted twice), as it always was
    assert client.get(f"/v1/buyers/{slug}").json()["tenderCount"] == 3
    _store_exact_base(conn)
    got = client.get(f"/v1/buyers/{slug}").json()
    listed = listing(client, status="all", scope="core", buyer=buyer_id)["total"]
    listed_open = listing(client, status="open", scope="core", buyer=buyer_id)["total"]
    assert (got["tenderCount"], got["openCount"]) == (listed, listed_open) == (2, 1)
    directory = client.get("/v1/buyers").json()["items"][0]
    assert (directory["tenderCount"], directory["openCount"]) == (2, 1)


def test_open_now_is_read_live_whatever_the_stored_totals_say(client, conn):
    put(conn, "A-1", country="PL")
    put(conn, "A-2", country="PL", deadline=PAST, status="awarded")
    slug = client.get("/v1/tenders").json()["items"][0]["buyerSlug"]
    _store_exact_base(conn, stale_open=99)
    got = client.get(f"/v1/buyers/{slug}").json()
    assert got["openCount"] == 1 and got["tenderCount"] == 2


# ======================================================================= T15: the sitemap's slugs

def test_the_slugs_come_from_the_snapshot_when_there_is_one(client, conn, cache_on):
    put(conn, "SLUG-1", country="PL")
    live = client.get("/v1/tenders/slugs").json()
    assert len(live) == 1 and live[0]["slug"].startswith(f"{client.get('/v1/tenders').json()['items'][0]['id']}-")
    stats.reset_cache()
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())",
                 (snapshot_key("tender-slugs", {}),
                  Jsonb(stored([{"slug": "1-from-the-snapshot", "updatedAt": "2026-10-19T00:00:00Z"}]))))
    conn.commit()
    assert client.get("/v1/tenders/slugs").json()[0]["slug"] == "1-from-the-snapshot"


def test_a_slug_is_dated_by_its_last_version_in_the_workers_answer_and_by_publication_in_the_apis(client, conn):
    published = (NOW - timedelta(days=3)).date()
    put(conn, "DATED-1", published=published)
    put(conn, "DATED-1", deadline=FUTURE + timedelta(days=9), tag="b", published=published)       # a second version
    live = client.get("/v1/tenders/slugs").json()[0]["updatedAt"]
    assert live.startswith(published.isoformat())
    token = tenders.EXACT_TOTALS.set(True)                                    # what the worker's run sets
    try:
        worker = tenders.tender_slugs.__wrapped__(conn=conn)[0]["updatedAt"]
    finally:
        tenders.EXACT_TOTALS.reset(token)
    assert worker > NOW - timedelta(minutes=5)                                          # observed just now


def test_the_slugs_of_the_buyers_are_the_ones_with_an_open_notice_and_a_page(client, conn):
    put(conn, "B-1", country="PL")
    put(conn, "B-2", country="ES", status="awarded", deadline=PAST)
    put(conn, "B-3", kind="supply", country="FR")
    slugs = [s["slug"] for s in client.get("/v1/buyers/slugs").json()]
    # WP-96: the open supply notice's buyer has a page too (the list's default scope); the awarded one's has no open notice
    assert len(slugs) == 2 and any(s.endswith("ministry-pl") for s in slugs) and any(s.endswith("ministry-fr") for s in slugs)
    for s in slugs:
        assert client.get(f"/v1/buyers/{s}").status_code == 200


# ======================================================================= T16 / T18: sources

def _run(conn, code: str, *, days_ago: float, status: str = "success", fetched: int = 100, floor: int | None = 10,
         message: str | None = None) -> None:
    source = db.source_id(conn, code)
    conn.execute(
        "INSERT INTO ingest_run (source_id, started_at, finished_at, status, records_fetched, expected_min, error_message) "
        "VALUES (%s, now() - make_interval(secs => %s) - interval '1 minute', now() - make_interval(secs => %s), %s, %s, %s, %s)",
        (source, days_ago * 86400, days_ago * 86400, status, fetched, floor, message))
    conn.commit()


def _activate(conn, *codes: str) -> None:
    """A few sources are switched on by an operator, not by a migration (they are on in production)."""
    conn.execute("UPDATE source SET active = TRUE WHERE code = ANY(%s)", (list(codes),))
    conn.commit()


def test_a_source_is_late_by_its_own_rhythm_and_a_partial_run_says_why(client, conn):
    _activate(conn, "cordis", "edf_factsheets", "pl_atlas")
    _run(conn, "ted", days_ago=5)                                            # daily: late after 3 days
    _run(conn, "cordis", days_ago=5, fetched=551237, floor=400000)           # monthly: not late at 5 days
    _run(conn, "edf_factsheets", days_ago=50, status="partial", fetched=284, floor=150,
         message="1 factsheets could not be read")                           # monthly: late at 50 days
    _run(conn, "pl_atlas", days_ago=30, floor=None)                          # one-off: never late
    _run(conn, "es_placsp", days_ago=0.1, status="partial", fetched=19648, floor=400,
         message="live feed stale: newest entry 2026-10-17T19:50:06+02:00, older than 36h")
    sources = {s["id"]: s for s in client.get("/v1/sources").json()["sources"]}
    assert (sources["ted"]["updateFreq"], sources["ted"]["staleAfterHours"], sources["ted"]["stale"]) == ("daily", 72, True)
    assert (sources["cordis"]["updateFreq"], sources["cordis"]["stale"]) == ("monthly", False)
    assert sources["edf_factsheets"]["stale"] is True
    assert sources["pl_atlas"]["stale"] is None and sources["pl_atlas"]["staleAfterHours"] is None
    placsp = sources["es_placsp"]
    assert placsp["status"] == "partial" and placsp["coverage"] == 1.0           # the minimum is met ...
    assert placsp["statusReasonKind"] == "stale_feed" and "newest entry" not in placsp["statusReason"]   # ... and why it is partial
    assert sources["edf_factsheets"]["statusReasonKind"] == "unreadable"
    assert sources["ted"]["statusReason"] is None


def test_the_sources_carry_the_names_their_operators_give_them(client, conn):
    _activate(conn, "de_bkms", "pl_atlas", "pl_ncbr", "fr_aid", "fr_boamp", "pl_ezam", "es_placsp")
    sources = {s["id"]: s for s in client.get("/v1/sources").json()["sources"]}
    assert sources["es_placsp"]["name"] == "Plataforma de Contratación del Sector Público"
    assert sources["pl_ezam"]["name"] == "Biuletyn Zamówień Publicznych (e-Zamówienia)"
    assert sources["de_bkms"]["name"] == "Bekanntmachungsservice (Datenservice Öffentlicher Einkauf)"
    assert sources["fr_boamp"]["name"].startswith("Bulletin officiel des annonces de marchés publics")
    assert sources["fr_aid"]["name"] == "Agence de l'innovation de défense (AID), appels à projets"
    assert "Atlas Przetargów" in sources["pl_atlas"]["name"] and "Badań i Rozwoju" in sources["pl_ncbr"]["name"]
    assert "Contratación" in sources["es_placsp"]["attribution"]
    assert sources["ted"]["name"] == "Tenders Electronic Daily"          # the others are left as they were


def test_the_open_counts_are_read_live_and_the_closed_ones_from_the_snapshot(client, conn, cache_on):
    put(conn, "LIVE-1")
    for status in ("open", "closed"):
        kw = {**warm_lists._defaults(tenders.tender_scope_counts.__wrapped__), "status": status}
        conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())",
                     (snapshot_key("tender-scope-counts", kw),
                      Jsonb({"relevant": 777, "core": 777, "supply": 0, "overlap": 0, "capped": False})))
    conn.commit()
    assert client.get("/v1/tenders/scope-counts").json()["relevant"] == 1                       # open: the notice there is
    assert client.get("/v1/tenders/scope-counts", params={"status": "closed"}).json()["relevant"] == 777
