"""WP-172 against a real Postgres.

1. The four sources whose commercial reuse WP-171 found unclear say so (`source.commercial_ok` NULL, migration 0161): the AID
   page lead is no longer served as a call's summary; set back to TRUE it is. Licence and attribution texts are unchanged.
2. A first page of the tender list starts its second page in the background (`cache_list(warm_next=True)`), also when the first
   page comes from memory and no count is kept, so page 2 runs no count and is answered from memory.
"""

from __future__ import annotations

import threading

import pytest

from dgate import stats
from tests.integration.test_warm_lists import cache_on  # noqa: F401 - fixture
from tests.integration.test_wp31 import put
from tests.integration.test_wp95 import client, env  # noqa: F401 - fixtures
from tests.integration.test_wp170 import _counting, _fuel

pytestmark = pytest.mark.integration

UNCLEAR = ("pl_ezam", "pl_atlas", "fr_aid", "pl_ncbr")


def test_the_four_unclear_sources_hold_null_and_keep_their_licence_texts(conn):
    rows = {r["code"]: r for r in conn.execute(
        "SELECT code, commercial_ok, licence, attribution FROM source WHERE code = ANY(%s)", (list(UNCLEAR),)).fetchall()}
    assert set(rows) == set(UNCLEAR)
    assert all(r["commercial_ok"] is None and r["licence"] and r["attribution"] for r in rows.values())
    clear = conn.execute("SELECT code FROM source WHERE commercial_ok").fetchall()
    assert {"ted", "eu_portal", "se_vinnova"} <= {r["code"] for r in clear}       # the others are untouched


def test_the_aid_page_lead_is_served_only_while_the_flag_says_yes(client, conn):  # noqa: F811
    cid = put(conn, "aid-172", programme="FR-AID", source="fr_aid",
              conditions={"summary": "L'agence finance des projets d'innovation de defense."})
    page = client.get(f"/v1/funding/{cid}").json()
    assert page["fundsSummary"] is None
    assert page["title"] == "Call aid-172" and page["source"]["licence"]           # the facts stay
    try:
        conn.execute("UPDATE source SET commercial_ok = TRUE WHERE code = 'fr_aid'")
        conn.commit()
        stats.reset_cache()
        assert client.get(f"/v1/funding/{cid}").json()["fundsSummary"] == "L'agence finance des projets d'innovation de defense."
    finally:            # `source` is reference data, not emptied between tests
        conn.rollback()
        conn.execute("UPDATE source SET commercial_ok = NULL WHERE code = 'fr_aid'")
        conn.commit()


def _settle():
    for t in threading.enumerate():
        if t.name == "warm":
            t.join(10)


def _drop_page_two():
    with stats._lock:
        for k in [k for k in stats._list_cache if k[0] == "tenders" and ("page", 2) in k[1]]:
            del stats._list_cache[k]


@pytest.mark.parametrize("status", ["closed", "all", "open"])
def test_page_two_is_ready_when_page_one_was_given_from_memory(client, conn, cache_on, monkeypatch, status):  # noqa: F811
    _fuel(conn, 5)
    _fuel(conn, 5, "open")
    calls = _counting(monkeypatch)
    ask = {"q": "fuel", "status": status, "pageSize": 2}
    first = client.get("/v1/tenders", params=ask).json()
    _settle()
    # the production case: page 1 is in memory, the counts are not (expired, or a load changed the newest notice)
    stats._count_cache.clear()
    _drop_page_two()
    calls.clear()
    assert client.get("/v1/tenders", params=ask).json() == first
    _settle()
    assert calls, "page 2 was computed in the background"
    calls.clear()
    second = client.get("/v1/tenders", params={**ask, "page": 2}).json()
    assert calls == [], "page 2 counted while the visitor waited"
    assert second["total"] == first["total"] == {"closed": 5, "all": 10, "open": 5}[status]
    assert {i["id"] for i in first["items"]}.isdisjoint(i["id"] for i in second["items"])


def test_no_second_page_is_started_for_a_list_of_one_page_or_with_the_cache_off(client, conn, cache_on, monkeypatch):  # noqa: F811
    _fuel(conn, 2)
    started = []
    monkeypatch.setattr(stats, "warm", lambda *a, **k: started.append(a[0]))
    client.get("/v1/tenders", params={"q": "fuel", "status": "closed", "pageSize": 2})
    assert started == []
    client.get("/v1/tenders", params={"q": "fuel", "status": "closed", "pageSize": 1})
    assert len(started) == 1 and ("page", 2) in started[0][1]
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    from dgate import config
    config.reset_cache()
    client.get("/v1/tenders", params={"q": "fuel", "status": "closed", "pageSize": 1, "country": "PL"})
    assert len(started) == 1
