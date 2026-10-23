"""The site search (WP-86): one query, the five lists' own answers, inside a budget."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, search
from dgate.normalise import Opportunity
from tests.integration.test_supplier_map import env, run, scenario  # noqa: F401 (env is a fixture)

pytestmark = pytest.mark.integration


@pytest.fixture
def client(conn):
    with TestClient(api.app) as c:
        yield c


def put_open(conn, native_id: str, title: str, buyer: str = "Bundesamt fuer Ausruestung") -> None:
    opp = Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=title, title_en=title,
        country="DE", published_at=date.today(), cpv_codes=["35400000"], status="open", is_defence=True,
        sig_legal_basis=True, sig_cpv=True, deadline_at=datetime.now(timezone.utc) + timedelta(days=20),
        source_url=f"https://ted.example/{native_id}")
    src_id = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, "DE", src_id=src_id)
    db.upsert_opportunity(conn, opp, f"hash-{native_id}", src_id)
    conn.commit()


LISTS = {"tenders": "/v1/tenders", "funding": "/v1/funding", "buyers": "/v1/buyers",
         "suppliers": "/v1/suppliers", "organisations": "/v1/organisations"}


def test_each_group_is_what_its_list_says_for_the_same_words(conn, env, client):  # noqa: F811
    run(scenario(conn))
    put_open(conn, "9-2026", "Rheinmetall spare parts for the Boxer")
    for q in ("Rheinmetall", "Bundesamt", "Nammo", "radar"):
        body = client.get("/v1/search", params={"q": q}).json()
        assert body["q"] == q and body["tookMs"] >= 0
        for group, path in LISTS.items():
            # the organisation directory of the site opens on the defence programmes
            extra = {"programme": "EDF,EDIDP,PADR"} if group == "organisations" else {}
            want = client.get(path, params={"q": q, "pageSize": 5, **extra}).json()
            got = body[group]
            assert got["error"] is None, (q, group)
            assert got["total"] == want["total"], (q, group)
            assert [i["slug"] for i in got["items"]] == [i["slug"] for i in want["items"]], (q, group)
    body = client.get("/v1/search", params={"q": "Rheinmetall"}).json()
    assert body["suppliers"]["total"] == 1 and body["suppliers"]["items"][0]["name"].lower().startswith("rheinmetall")
    assert body["tenders"]["total"] == 1 and body["buyers"]["total"] == 0
    assert client.get("/v1/search", params={"q": "Bundesamt"}).json()["buyers"]["total"] == 1
    assert len(client.get("/v1/search", params={"q": "Nammo", "limit": 1}).json()["suppliers"]["items"]) == 1


def test_a_short_or_missing_query_is_refused(client):
    assert client.get("/v1/search").status_code == 422
    assert client.get("/v1/search", params={"q": " a "}).status_code == 422
    assert client.get("/v1/search", params={"q": "x" * 101}).status_code == 422
    assert client.get("/v1/search", params={"q": "radar", "limit": 11}).status_code == 422


def test_a_group_that_runs_out_of_time_says_so_and_the_others_still_answer(conn, client, monkeypatch):
    def slow(**kw):
        kw["conn"].execute("SELECT pg_sleep(3)")
        return {"items": [], "total": 0}

    groups = dict(search.GROUPS)
    groups["funding"] = slow
    monkeypatch.setattr(search, "GROUPS", groups)
    monkeypatch.setattr(search, "BUDGET_MS", 2400)
    r = client.get("/v1/search", params={"q": "radar"})
    assert r.status_code == 200
    body = r.json()
    assert body["tenders"]["error"] is None and body["tenders"]["total"] == 0
    assert body["funding"] == {"total": None, "atLeast": False, "items": [], "error": "slow"}
    # the statement was cut at what was left of the budget, not at the role's 5 s
    assert body["tookMs"] < 2400
    # the groups after it still ran on the same connection (the cancelled statement was rolled back to its savepoint)
    assert body["buyers"]["error"] is None and body["organisations"]["error"] is None
