"""The API's own protection of its database (external audit X-1, X-8; internal audit H4, M1).

Reuse of a list response, single flight without a global lock, failures never kept, and
the archive endpoints refusing what the tender endpoints refuse.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, stats
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


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
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    config.reset_cache()
    stats.reset_cache()


def _put(conn, native_id: str, *, title: str = "Armoured vehicles", defence: bool = True) -> int:
    opp = Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw="Ministry of Defence",
        title_original=title, country="PL", published_at=date(2026, 10, 1), deadline_at=FUTURE,
        cpv_codes=["35400000"], status="open", is_defence=defence, sig_cpv=True)
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, "Ministry of Defence", "PL", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
    conn.commit()
    return oid


def test_the_same_query_is_computed_once_and_another_query_is_not_served_from_it(client, conn, cache_on):
    _put(conn, "A-1")
    first = client.get("/v1/tenders", params={"q": "armoured"}).json()
    assert first["total"] == 1
    _put(conn, "A-2")
    again = client.get("/v1/tenders", params={"q": "armoured"}).json()
    assert again["total"] == 1, "reused within the minute"
    other = client.get("/v1/tenders", params={"q": "armoured", "page": 1, "pageSize": 21}).json()
    assert other["total"] == 2, "another normalised query is its own entry"
    assert len(stats._list_cache) <= stats.LIST_CACHED


def test_a_page_larger_than_a_hundred_is_not_kept(client, conn, cache_on):
    _put(conn, "B-1")
    client.get("/v1/tenders", params={"pageSize": 250})
    assert not stats._list_cache


def test_a_failure_is_never_kept(client, conn, cache_on, monkeypatch):
    _put(conn, "C-1")
    calls = []
    real = api._tenders._present

    def boom(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("database went away")

    monkeypatch.setattr(api._tenders, "_present", boom)
    with pytest.raises(RuntimeError):
        client.get("/v1/tenders", params={"q": "armoured"})
    monkeypatch.setattr(api._tenders, "_present", real)
    ok = client.get("/v1/tenders", params={"q": "armoured"})
    assert ok.status_code == 200 and ok.json()["total"] == 1 and len(calls) == 1
    assert len(stats._list_cache) == 1


def test_the_cache_is_bounded(client, conn, cache_on, monkeypatch):
    _put(conn, "D-1")
    for n in range(stats.LIST_CACHED + 20):
        client.get("/v1/tenders", params={"q": f"term{n}"})
    assert len(stats._list_cache) <= stats.LIST_CACHED


# ----------------------------------------------- X-8: the archive endpoints refuse non-defence

def test_a_row_that_is_not_defence_is_not_served_by_the_opportunity_endpoints(client, conn):
    kept = _put(conn, "E-1")
    hidden = _put(conn, "E-2", title="Office chairs", defence=False)
    assert client.get(f"/v1/opportunities/{kept}").status_code == 200
    assert client.get(f"/v1/opportunities/{kept}/versions").status_code == 200
    assert client.get(f"/v1/opportunities/{hidden}").status_code == 404
    assert client.get(f"/v1/opportunities/{hidden}/versions").status_code == 404
    assert client.get(f"/v1/tenders/{hidden}").status_code == 404, "the same answer as the tender endpoint"


def test_goods_defence_keeps_only_notices_that_say_defence_themselves(client, conn):
    def put(native_id, **flags):
        opp = Opportunity(
            source_code="ted", native_id=native_id, buyer_name_raw="Buyer " + native_id,
            title_original="Goods " + native_id, country="PL", published_at=date(2026, 10, 1),
            deadline_at=FUTURE, cpv_codes=["35400000"], status="open", is_defence=True, **flags)
        src = db.source_id(conn, "ted")
        db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
        conn.commit()

    put("G-OWN", sig_cpv=True, sig_cpv_military=True, buyer_class="defence", sig_buyer=True)
    put("G-LISTED", sig_cpv=True, sig_cpv_military=True, buyer_class="municipal", sig_buyer=True)
    def ids(**p):
        return {i["noticeId"] for i in client.get("/v1/tenders", params=p).json()["items"]}

    assert ids() == {"G-OWN", "G-LISTED"}                       # the default is unchanged
    assert ids(goods="defence") == {"G-OWN"}
    assert client.get("/v1/tenders", params={"goods": "other"}).status_code == 422
    assert client.get("/v1/changes", params={"goods": "defence"}).status_code == 200
