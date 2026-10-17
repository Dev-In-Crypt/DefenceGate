"""Pre-computed list views (`list_snapshot`, `ops/warm_lists`): the worker computes them, the API
serves them before it runs the query, an old one is ignored, and the scope counts are kept."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, config, db, stats
from dgate.listcache import snapshot_key
from dgate.normalise import Opportunity
from dgate.ops import warm_lists

pytestmark = pytest.mark.integration


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


def _put(conn, native_id: str, *, status: str, country: str = "PL") -> int:
    opp = Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw="Ministry of Defence",
        title_original="Armoured vehicles", country=country, published_at=date(2026, 1, 5),
        deadline_at=datetime.now(timezone.utc) - timedelta(days=30), cpv_codes=["35400000"],
        status=status, is_defence=True, sig_cpv=True, sig_cpv_military=True, sig_legal_basis=True)
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, "Ministry of Defence", country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
    conn.commit()
    return oid


def test_the_worker_writes_the_closed_views_and_the_api_serves_them(client, conn, cache_on):
    _put(conn, "W-1", status="closed")
    result = warm_lists.run(conn, write=True)
    assert result["failed"] == 0 and result["written"] == result["views"] > 0
    snap = conn.execute("SELECT count(*) AS n FROM list_snapshot").fetchone()["n"]
    assert snap == result["views"]
    # A marker in the stored body shows the API reads the snapshot, not the table.
    kw = {**warm_lists._defaults(__import__("dgate.tenders", fromlist=["x"]).list_tenders.__wrapped__),
          "with_meta": True, "status": "closed", "country": None, "page": 1, "pageSize": 10}
    key = snapshot_key("tenders", kw)
    body = conn.execute("SELECT body FROM list_snapshot WHERE key = %s", (key,)).fetchone()["body"]
    assert body["total"] == 1
    body["total"] = 4242
    conn.execute("UPDATE list_snapshot SET body = %s WHERE key = %s", (Jsonb(body), key))
    conn.commit()
    got = client.get("/v1/tenders", params={"status": "closed", "pageSize": 10}).json()
    assert got["total"] == 4242


def test_an_old_snapshot_is_ignored(client, conn, cache_on):
    _put(conn, "W-2", status="closed")
    warm_lists.run(conn, write=True)
    conn.execute("UPDATE list_snapshot SET computed_at = now() - interval '9 hours'")
    conn.execute("UPDATE list_snapshot SET body = jsonb_set(body, '{total}', '4242')")
    conn.commit()
    got = client.get("/v1/tenders", params={"status": "closed", "pageSize": 10}).json()
    assert got["total"] == 1, "the live query answers when the snapshot is too old"


def test_a_filter_that_was_not_computed_runs_the_query(client, conn, cache_on):
    _put(conn, "W-3", status="closed")
    warm_lists.run(conn, write=True)
    conn.execute("UPDATE list_snapshot SET body = jsonb_set(body, '{total}', '4242')")
    conn.commit()
    got = client.get("/v1/tenders", params={"status": "closed", "pageSize": 10, "q": "armoured"}).json()
    assert got["total"] == 1


def test_a_rerun_removes_the_views_of_a_country_that_has_no_notices_any_more(conn):
    _put(conn, "W-4", status="closed", country="PL")
    warm_lists.run(conn, write=True)
    before = conn.execute("SELECT count(*) AS n FROM list_snapshot WHERE key LIKE '%country=PL%'").fetchone()["n"]
    assert before > 0
    conn.execute("UPDATE opportunity SET country = 'DE'")
    conn.commit()
    warm_lists.run(conn, write=True)
    assert conn.execute("SELECT count(*) AS n FROM list_snapshot WHERE key LIKE '%country=PL%'").fetchone()["n"] == 0


def test_the_scope_counts_are_kept_between_requests(client, conn, cache_on):
    _put(conn, "W-5", status="closed")
    first = client.get("/v1/tenders/scope-counts", params={"status": "closed"}).json()
    _put(conn, "W-6", status="closed")
    again = client.get("/v1/tenders/scope-counts", params={"status": "closed"}).json()
    assert again == first, "the counts are reused within the cache time"


def test_a_dry_run_writes_nothing(conn):
    _put(conn, "W-7", status="closed")
    result = warm_lists.run(conn, write=False)
    assert result["written"] == 0 and result["views"] > 0
    assert conn.execute("SELECT count(*) AS n FROM list_snapshot").fetchone()["n"] == 0
