"""The tenders CSV export's page endpoint (/v1/tenders/export): same set as the list, bounded,
keyed by cursor, and inside the API role's five seconds however long the result is."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from dgate import api, db, migrate, stats, tenders
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@pytest.fixture()
def client(conn):
    stats.reset_cache()
    with TestClient(api.app) as c:
        yield c
    stats.reset_cache()


def _fill(conn, n: int, *, status: str = "open", start: int = 0) -> list[int]:
    src = db.source_id(conn, "ted")
    org = db.resolve_organisation(conn, "Ministry of Defence", "PL", src_id=src)
    ids = []
    for i in range(start, start + n):
        opp = Opportunity(
            source_code="ted", native_id=f"X-{status}-{i}", buyer_name_raw="Ministry of Defence",
            title_original=f"Armoured vehicles lot {i}", country="PL", published_at=date(2026, 10, 1),
            deadline_at=FUTURE if status == "open" else datetime(2026, 1, 1, tzinfo=timezone.utc),
            cpv_codes=["35400000"], status=status, is_defence=True, sig_cpv=True, buyer_org_id=org)
        oid, _ = db.upsert_opportunity(conn, opp, f"h-{status}-{i}", src)
        ids.append(oid)
    conn.commit()
    return ids


def _walk(client, limit: int, **params) -> tuple[list[str], int]:
    seen, cursor, calls = [], None, 0
    while True:
        r = client.get("/v1/tenders/export", params={**params, "limit": limit, **({"cursor": cursor} if cursor else {})})
        assert r.status_code == 200, r.text
        body = r.json()
        calls += 1
        seen += [t["id"] for t in body["items"]]
        cursor = body["nextCursor"]
        if cursor is None:
            return seen, calls


def test_the_export_pages_hold_exactly_what_the_list_holds(client, conn):
    _fill(conn, 5)
    _fill(conn, 4, status="awarded")
    for status in ("open", "closed", "all"):
        listed = client.get("/v1/tenders", params={"status": status, "pageSize": 250}).json()
        ids, calls = _walk(client, 2, status=status)
        assert sorted(ids) == sorted(t["id"] for t in listed["items"]), status
        assert len(ids) == listed["total"] == len(set(ids))
        assert calls == -(-listed["total"] // 2), "no empty trailing page"


def test_a_page_that_ends_the_result_exactly_has_no_cursor(client, conn):
    _fill(conn, 4)
    body = client.get("/v1/tenders/export", params={"limit": 4}).json()
    assert len(body["items"]) == 4 and body["nextCursor"] is None
    body = client.get("/v1/tenders/export", params={"limit": 3}).json()
    assert len(body["items"]) == 3 and body["nextCursor"] == body["items"][-1]["id"]


def test_the_page_is_bounded_and_the_cursor_is_checked(client, conn):
    assert client.get("/v1/tenders/export", params={"limit": 2001}).status_code == 422
    assert client.get("/v1/tenders/export", params={"limit": 0}).status_code == 422
    assert client.get("/v1/tenders/export", params={"cursor": "1; DROP TABLE opportunity"}).status_code == 422
    assert client.get("/v1/tenders/export", params={"status": "bogus"}).status_code == 422


def test_the_export_applies_the_list_filters(client, conn):
    _fill(conn, 3)
    assert _walk(client, 10, country="DE")[0] == []
    assert len(_walk(client, 10, country="PL", q="armoured")[0]) == 3


def test_a_long_closed_result_pages_inside_the_api_roles_five_seconds(conn, schema, monkeypatch):
    """The shape of the 15 October 2026 failure: a long closed result read page after page by the
    role that has a 5 s statement budget. Every page must come back, none may be cancelled."""
    _fill(conn, 1100, status="awarded")
    _fill(conn, 40)
    monkeypatch.setenv("DGATE_API_PASSWORD", "api-test-password-1")
    monkeypatch.setenv("DGATE_WORKER_PASSWORD", "worker-test-password-1")
    with db.connect(schema) as admin:
        migrate.set_role_passwords(admin)
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(schema)
    dsn = urlunsplit(parts._replace(netloc=f"dgate_api:api-test-password-1@{parts.hostname}:{parts.port}"))
    base = dict(q=None, country=None, cpv=None, status="closed", scope="core", goods=None, buyer=None,
                from_=None, to=None, min_=None, max_=None, currency="EUR")
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as c:
        assert c.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "5s"
        got, cursor, slowest = [], None, 0.0
        while True:
            t = time.perf_counter()
            page = tenders.export_tenders(**base, cursor=cursor, limit=500, conn=c)
            slowest = max(slowest, time.perf_counter() - t)
            got += [i["id"] for i in page["items"]]
            cursor = page["nextCursor"]
            if cursor is None:
                break
        assert len(got) == 1100 and len(set(got)) == 1100
        assert slowest < 5.0
