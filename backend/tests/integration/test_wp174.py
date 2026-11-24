"""WP-174 (full QA of 24 November 2026, tenders and feeds) against a real Postgres.

B-1 `all` leads with the notices open now, not with a stored page's; B-3 a closed notice whose stated deadline is ahead does
not lead the Closed list; B-4 the total of a list does not depend on its order; B-7 Everything leads with the military goods
and works; B-20 Closed holds no Planned and no unknown status; B-21 an open notice with no deadline and no date is unknown;
A-6 the change pages are slices of one live window (no stored first page)."""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, config, stats, tenders
from dgate.listcache import snapshot_key
from dgate.ops import warm_lists
from tests.integration.test_changes import opp, store

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def client(conn):
    stats.reset_cache()
    with TestClient(api.app) as c:
        yield c
    stats.reset_cache()


@pytest.fixture()
def cache_on(monkeypatch):
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()
    yield
    for t in threading.enumerate():     # the background reads of a kept list (`warm_next`, a renewal) end before the next test
        if t.name in ("warm", "renew"):
            t.join(10)
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    config.reset_cache()
    stats.reset_cache()


def get(client, path: str, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def numbers(page: dict) -> list[str]:
    return [i["noticeId"] for i in page["items"]]


def test_all_is_read_live_and_keeps_the_stored_total(client, conn, cache_on):
    """B-1, B-4: a stored `all` page led "Open first" with notices closed since; its total stays the stored (exact) one, and
    another order of the same list says the same total."""
    store(conn, opp("OPEN-NOW", deadline=NOW + timedelta(days=5)))
    store(conn, opp("CLOSED", deadline=NOW - timedelta(days=3)))
    assert warm_lists.run(conn, write=True)["failed"] == 0
    base = {**warm_lists._defaults(tenders.list_tenders.__wrapped__), "with_meta": True, "status": "all",
            "page": 1, "pageSize": 10}
    key = snapshot_key("tenders", base)
    body = conn.execute("SELECT body FROM list_snapshot WHERE key = %s", (key,)).fetchone()["body"]
    body["items"] = list(reversed(body["items"]))          # a stale page: the closed notice first
    body["total"] = 4242
    conn.execute("UPDATE list_snapshot SET body = %s WHERE key = %s", (Jsonb(body), key))
    conn.commit()
    page = get(client, "/v1/tenders", status="all", pageSize=10)
    assert numbers(page) == ["OPEN-NOW", "CLOSED"], "the open part is of now"
    assert page["total"] == 2, "the end of the list was read: its own count"
    # a page that does not reach the end takes the stored (exact) total instead of counting the rest again
    assert get(client, "/v1/tenders", status="all", pageSize=1)["total"] == 4242
    # B-4: the stored total answers for any order of the same filters when the live count is "at least"
    assert tenders._snapshot_total(conn, {**{k: v for k, v in base.items() if k not in ("page", "pageSize", "with_meta")},
                                          "sort": "deadline-desc"}) == (4242, False)
    # the worker keeps only the first page of `all`
    keys = [k for _, k, _ in warm_lists.views([])]
    assert key in keys and snapshot_key("tenders", {**base, "page": 2}) not in keys
    assert snapshot_key("tenders", {**base, "status": "closed", "page": 2}) in keys


def test_a_notice_closed_before_its_stated_deadline_does_not_lead_the_closed_list(client, conn):
    """B-3: Intendente de Cartagena, awarded, "deadline 31 Jul 2027", first of 293,317 closed notices."""
    store(conn, opp("PASSED-RECENT", deadline=NOW - timedelta(days=1)))
    store(conn, opp("PASSED-OLD", deadline=NOW - timedelta(days=90)))
    ahead = store(conn, replace(opp("AWARDED-AHEAD", deadline=NOW + timedelta(days=250)), status="awarded"))
    assert ahead
    closed = get(client, "/v1/tenders", status="closed")
    assert numbers(closed) == ["PASSED-RECENT", "PASSED-OLD", "AWARDED-AHEAD"] and closed["total"] == 3
    assert numbers(get(client, "/v1/tenders", status="closed", sort="deadline-desc"))[0] == "PASSED-RECENT"
    # page 2 of a page of 2 is the rest, in the same order
    assert numbers(get(client, "/v1/tenders", status="closed", pageSize=2, page=2)) == ["AWARDED-AHEAD"]
    # asked for the other way, the order is the deadline's
    assert numbers(get(client, "/v1/tenders", status="closed", sort="deadline-asc"))[0] == "PASSED-OLD"


def test_everything_leads_with_the_military_goods_and_works(client, conn):
    """B-7: scope Everything, sort box "Military goods and works first", list soonest deadline first."""
    store(conn, opp("SUPPLY-SOON", kind="supply", deadline=NOW + timedelta(days=2)))
    store(conn, opp("CORE-LATER", deadline=NOW + timedelta(days=20)))
    assert numbers(get(client, "/v1/tenders", scope="all")) == ["CORE-LATER", "SUPPLY-SOON"]
    assert numbers(get(client, "/v1/tenders", scope="all", sort="deadline-asc")) == ["SUPPLY-SOON", "CORE-LATER"]
    assert numbers(get(client, "/v1/tenders", scope="supply")) == ["SUPPLY-SOON"]


def test_closed_holds_neither_planned_nor_unknown(client, conn):
    """B-20: the Closed CSV of NL had "Planned" (published a year ago to the day) and "Status unknown" rows."""
    store(conn, opp("EXPIRED", deadline=NOW - timedelta(days=2)))
    store(conn, replace(opp("UNKNOWN", deadline=None), status="unknown"))
    store(conn, replace(opp("PIN-YEAR", deadline=None, published=(NOW - timedelta(days=365)).date()), status="forthcoming"))
    closed = numbers(get(client, "/v1/tenders", status="closed"))
    assert "UNKNOWN" not in closed and "EXPIRED" in closed
    # the anniversary notice is closed in the filter and on its card alike
    shown = {i["noticeId"]: i for i in get(client, "/v1/tenders", status="all")["items"]}
    assert ("PIN-YEAR" in closed) == (shown["PIN-YEAR"]["statusNative"] == "expired")
    assert shown["UNKNOWN"]["statusNative"] == "unknown"


def test_an_open_notice_with_no_deadline_and_no_date_is_not_open(client, conn):
    """B-21: 51 BKMS notices "Open" with no deadline and no date at all (285904)."""
    store(conn, opp("UNDATED", deadline=None))
    conn.execute("UPDATE opportunity SET published_at = NULL, notice_date = NULL WHERE native_id = 'UNDATED'")
    store(conn, opp("DATED-BY-NOTICE", deadline=None))
    conn.execute("UPDATE opportunity SET published_at = NULL, notice_date = current_date - 10 "
                 "WHERE native_id = 'DATED-BY-NOTICE'")
    store(conn, opp("OLD-BY-NOTICE", deadline=None))
    conn.execute("UPDATE opportunity SET published_at = NULL, notice_date = current_date - 400 "
                 "WHERE native_id = 'OLD-BY-NOTICE'")
    conn.commit()
    assert numbers(get(client, "/v1/tenders")) == ["DATED-BY-NOTICE"]
    shown = {i["noticeId"]: i["statusNative"] for i in get(client, "/v1/tenders", status="all")["items"]}
    assert shown == {"DATED-BY-NOTICE": "open", "UNDATED": "unknown", "OLD-BY-NOTICE": "expired"}


def test_the_change_pages_are_not_stored(client, conn, cache_on):
    """A-6: changes.atom page 2 repeated 171 entries of page 1: a stored first page, a live second one."""
    store(conn, opp("CH-1"))
    assert warm_lists.run(conn, write=True)["failed"] == 0
    assert not conn.execute("SELECT 1 FROM list_snapshot WHERE key LIKE 'changes?%%'").fetchone()
    from dgate import changes

    base = {**warm_lists._defaults(changes.list_changes.__wrapped__), "with_meta": True, "pageSize": 25}
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())",
                 (snapshot_key("changes", base), Jsonb({"total": 4242, "items": []})))
    conn.commit()
    assert get(client, "/v1/changes", pageSize=25)["total"] != 4242


def test_contracts_ending_leaves_one_off_deliveries_out(client, conn):
    """B-11, F18: /tenders/ending led with one-day periods ("24-25 Nov", KNDS); a contract with no stated start stays."""
    from datetime import date

    from tests.integration.test_wp160 import contract

    today = date.today()
    one_day = contract(conn, "one-day", contract_start=today, contract_end=today + timedelta(days=1))
    year = contract(conn, "year", contract_start=today - timedelta(days=300), contract_end=today + timedelta(days=60))
    no_start = contract(conn, "no-start", contract_end=today + timedelta(days=5))
    got = [int(i["id"]) for i in get(client, "/v1/tenders/ending")["items"]]
    assert got == [no_start, year] and one_day not in got
