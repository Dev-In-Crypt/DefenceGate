"""WP-127 (ops round 8, 25 October 2026): `/v1/tenders/scope-counts?q=ammunition` answered 503 after 1.5 s on EVERY
request, because the response cache never keeps a failure. The "took too long" is now kept a few minutes per query."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, stats, tenders

pytestmark = pytest.mark.integration


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


def test_a_count_that_ran_out_of_time_is_not_tried_again_for_a_while(client, conn, cache_on, monkeypatch):
    calls: list[int] = []
    real = tenders._count_up_to

    def out_of_time(*a, **k):
        calls.append(1)
        return None

    monkeypatch.setattr(tenders, "_count_up_to", out_of_time)
    first = client.get("/v1/tenders/scope-counts", params={"status": "closed"})
    assert first.status_code == 503 and calls
    tried = len(calls)
    again = client.get("/v1/tenders/scope-counts", params={"status": "closed"})
    assert again.status_code == 503 and again.json() == first.json()
    assert len(calls) == tried                                   # answered from the memory, no count run
    # another query is counted on its own
    client.get("/v1/tenders/scope-counts", params={"status": "all"})
    assert len(calls) > tried
    # past UNAVAILABLE_SECONDS it is counted again, and a count that now succeeds is the answer
    for key in [k for k in stats._list_cache if k[0] == "tender-scope-counts-unavailable"]:
        stats._list_cache[key] = (0.0, True)
    monkeypatch.setattr(tenders, "_count_up_to", real)
    assert client.get("/v1/tenders/scope-counts", params={"status": "closed"}).status_code == 200


def test_with_the_cache_off_nothing_is_kept(client, conn, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(tenders, "_count_up_to", lambda *a, **k: calls.append(1))
    for _ in range(2):
        assert client.get("/v1/tenders/scope-counts", params={"status": "closed"}).status_code == 503
    assert len(calls) >= 2 and not stats._list_cache
