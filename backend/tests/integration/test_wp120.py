"""WP-120 (speed and caching, round-6 system audit of 25 October 2026) against a real Postgres: with no stored order the
supplier value order is summed once in a time box of its own and kept, the planned time boxes are named and undone, the
counts of one list request share one budget, the unknown parameters of the supplier, buyer and funding lists are refused, a
304 carries the 200's Cache-Control, buyer names and export pages are kept in memory, the worker keeps the Planned list."""

from __future__ import annotations

import psycopg
import pytest

from dgate import config, stats, tenders
from dgate.listcache import snapshot_key
from dgate.ops import warm_lists
from tests.integration.test_warm_lists import _put
from tests.integration.test_wp95 import award, client, env, madzeal, notice, org  # noqa: F401 - fixtures
from tests.integration.test_wp98c import three  # noqa: F401 - fixture

pytestmark = pytest.mark.integration


def get(c, path: str, **params) -> dict:
    r = c.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()
    yield
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    config.reset_cache()
    stats.reset_cache()


# ------------------------------------------------------------------ 1. the value order with none stored

def test_with_nothing_stored_the_value_order_is_summed_once_in_its_own_time_box(client, conn, three, cache_on):  # noqa: F811
    page = get(client, "/v1/suppliers", sort="value-EUR")
    assert [i["name"].split()[0].lower().strip(",") for i in page["items"]] == ["madzeal", "small", "mesko"]
    assert page["valuesAsOf"] is None and page["valuesBehind"] is False             # summed now
    body, at = stats._cache[("supplier-values", False)][1]                          # kept for the next pages and currencies
    assert at is None and three["mesko"] in body["byCurrency"]["PLN"][0]
    assert [i["name"].split()[0].lower() for i in get(client, "/v1/suppliers", sort="value-PLN")["items"]][0] == "mesko"


# ------------------------------------------------------------------ 3. a search's matches read once

def test_a_search_read_by_its_matches_lists_what_the_per_row_test_lists(client, conn, monkeypatch):  # noqa: F811
    for i, status in enumerate(("open", "closed", "closed", "awarded")):
        _put(conn, f"W-120-A{i}", status=status)
    conn.execute("UPDATE opportunity SET title_original = 'Armoured vehicles and ammunition' WHERE native_id LIKE 'W-120-A%'")
    _put(conn, "W-120-B", status="closed")                                           # "Armoured vehicles": not a match
    conn.commit()
    asked = []
    real = tenders.search_ids
    monkeypatch.setattr(tenders, "search_ids", lambda *a: asked.append(real(*a)) or asked[-1])
    off = {s: get(client, "/v1/tenders", q="ammunition", status=s) for s in ("all", "closed", "open")}
    assert asked and all(a is None for a in asked)                                  # off by default: the per-row test
    asked.clear()
    monkeypatch.setenv("DGATE_SEARCH_IDS_MS", "2000")
    config.reset_cache()
    by_ids = {s: get(client, "/v1/tenders", q="ammunition", status=s) for s in ("all", "closed", "open")}
    assert asked and all(isinstance(a, list) and len(a) == 4 for a in asked)        # the four matches, read once a call
    monkeypatch.setattr(tenders, "SEARCH_IDS_MAX", 3)                                # more than that: the per-row test
    asked.clear()
    per_row = {s: get(client, "/v1/tenders", q="ammunition", status=s) for s in ("all", "closed", "open")}
    assert asked and all(a is None for a in asked)
    for s in off:
        assert [i["id"] for i in off[s]["items"]] == [i["id"] for i in by_ids[s]["items"]], s
    for s in by_ids:
        assert [i["id"] for i in by_ids[s]["items"]] == [i["id"] for i in per_row[s]["items"]], s
        assert by_ids[s]["total"] == per_row[s]["total"], s
    assert by_ids["all"]["total"] == 4


def test_a_slow_match_read_falls_back_and_is_not_tried_again(conn, cache_on, monkeypatch):
    monkeypatch.setenv("DGATE_SEARCH_IDS_MS", "1")
    config.reset_cache()
    match = "(pg_sleep(0.05)::text = '')"
    _put(conn, "W-120-C", status="closed")
    assert tenders.search_ids(conn, match, []) is None                               # outside a list request: never read
    assert not stats._search_cache
    token = tenders._SEARCH_MEMO.set({})
    try:
        assert tenders.search_ids(conn, match, []) is None                           # past its time box
    finally:
        tenders._SEARCH_MEMO.reset(token)
    assert stats._search_cache[("search-ids", match, "[]")][1] is False              # remembered: not tried again for a while
    monkeypatch.setenv("DGATE_SEARCH_IDS_MS", "5000")
    config.reset_cache()
    token = tenders._SEARCH_MEMO.set({})
    try:
        assert tenders.search_ids(conn, match, []) is None                           # still the per-row way
    finally:
        tenders._SEARCH_MEMO.reset(token)
    conn.execute("SELECT 1")


# ------------------------------------------------------------------ 7. planned time boxes

def test_a_time_box_is_named_cancels_alone_and_is_undone(conn):
    before = conn.execute("SELECT current_setting('statement_timeout') AS t, current_setting('application_name') AS a").fetchone()
    with tenders.time_boxed(conn, 2000):
        assert conn.execute("SELECT current_setting('application_name') AS a").fetchone()["a"] == tenders.TIME_BOX_APP
        assert conn.execute("SELECT current_setting('statement_timeout') AS t").fetchone()["t"] == "2s"
    with pytest.raises(psycopg.errors.QueryCanceled):
        with tenders.time_boxed(conn, 50):
            conn.execute("SELECT pg_sleep(1)")
    after = conn.execute("SELECT current_setting('statement_timeout') AS t, current_setting('application_name') AS a").fetchone()
    assert after == before
    conn.execute("SELECT 1")                                                         # the connection is usable


def test_the_counts_of_one_list_request_share_one_budget(conn):
    _put(conn, "W-120-1", status="closed")
    where, params, _ = tenders._tender_filters(None, None, None, "closed", "relevant", None, None, None, None, None, None,
                                               None, conn=conn)
    cond = " AND ".join(where)
    assert tenders._count_up_to(conn, cond, where, params, 10, 1000) == 1
    with tenders.count_budget(tenders.COUNT_MIN_MS - 1):
        assert tenders._count_up_to(conn, cond, where, params, 10, 1000) is None     # no time left: "at least"
    with tenders.count_budget(5000):
        assert tenders._count_up_to(conn, cond, where, params, 10, 1000) == 1
        assert tenders._COUNT_LEFT.get()[0] < 5000                                  # what it took is spent


# ------------------------------------------------------------------ 8. unknown parameters, 6. a 304's Cache-Control

@pytest.mark.parametrize("path", ["/v1/suppliers", "/v1/buyers", "/v1/funding"])
def test_an_unknown_parameter_is_refused(client, path):  # noqa: F811
    r = client.get(path, params={"foo": "bar"})
    assert r.status_code == 422 and "unknown query parameter" in r.text


def test_the_parameters_the_site_sends_are_taken(client):  # noqa: F811
    # web/lib/api.ts getSuppliers, buyersQuery (toBuyerQuery), fundingQuery (toQuery)
    assert client.get("/v1/suppliers", params={"q": "x", "country": "ES", "buyerCountry": "PL", "cpv": "35", "source": "ted",
                                               "sort": "value-EUR", "page": 1, "pageSize": 20}).status_code == 200
    assert client.get("/v1/buyers", params={"q": "x", "country": "ES", "cpv": "35", "hasOpen": "true", "sort": "cpv",
                                            "page": 1, "pageSize": 20}).status_code == 200
    assert client.get("/v1/funding", params={"q": "x", "programme": "EDF", "regime": "defence", "country": "ES", "status": "all",
                                             "from": "2026-01-01", "to": "2026-12-31", "min": 1, "max": 9, "currency": "EUR",
                                             "sort": "deadline-asc", "cascade": "true", "ukraine": "true", "who": "companies",
                                             "page": 1, "pageSize": 10}).status_code == 200


def test_a_304_repeats_the_cache_control_of_its_200(client, cache_on):  # noqa: F811 - kept: the same body twice
    first = client.get("/v1/tenders", params={"pageSize": 5})
    again = client.get("/v1/tenders", params={"pageSize": 5}, headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.headers["cache-control"] == first.headers["cache-control"] == "public, max-age=60"


# ------------------------------------------------------------------ 2. buyer names, 4. export pages and the Planned list

def test_buyer_names_are_kept_a_while_and_only_with_the_caches_on(conn, cache_on):
    _put(conn, "W-120-2", status="closed")
    org_id = conn.execute("SELECT buyer_org_id FROM opportunity WHERE native_id = 'W-120-2'").fetchone()["buyer_org_id"]
    assert tenders._buyer_names(conn, [org_id]) == {org_id: "Ministry of Defence"}
    conn.execute("UPDATE opportunity SET buyer_name_raw = 'Renamed' WHERE buyer_org_id = %s", (org_id,))
    conn.commit()
    assert tenders._buyer_names(conn, [org_id]) == {org_id: "Ministry of Defence"}  # kept
    stats.reset_cache()
    assert tenders._buyer_names(conn, [org_id]) == {org_id: "Renamed"}
    config.reset_cache()


def test_an_export_page_is_kept_for_five_minutes(client, conn, cache_on):  # noqa: F811
    _put(conn, "W-120-3", status="open")
    first = get(client, "/v1/tenders/export", status="all", limit=500)
    conn.execute("UPDATE opportunity SET suppressed = true WHERE native_id = 'W-120-3'")
    conn.commit()
    assert get(client, "/v1/tenders/export", status="all", limit=500) == first        # kept (the size is over 100)
    assert len(stats._large_cache) == 1


def test_the_worker_keeps_the_planned_list_without_a_country():
    keys = [k for _, k, _ in warm_lists.views(["PL"])]
    base = {**warm_lists._defaults(tenders.list_tenders.__wrapped__), "with_meta": True, "status": "planned", "country": None}
    for page in warm_lists.PAGES:
        assert snapshot_key("tenders", {**base, "page": page, "pageSize": warm_lists.TENDER_PAGE_SIZE}) in keys
    assert not any("status=planned" in k and "country=PL" in k for k in keys)
