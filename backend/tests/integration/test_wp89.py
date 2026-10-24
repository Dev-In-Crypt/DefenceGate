"""WP-89 (UX audit of 22 October 2026, section 4: the supplier path), against a real Postgres.

3. /v1/buyers and /v1/stats/market take a CPV filter (the tender list's reading: any code of the notice under a prefix),
   the search's buyers group stays the list's default; 6. a supplier page asked with the report's codes and countries says
   how many of its contracts are under them, the number the supplier list gives for the same filters."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from dgate import api, awards, config, db, search, stats, tenders
from dgate.normalise import Opportunity
from tests.integration.test_changes import opp, store
from tests.integration.test_supplier_map import FakeTed, rec

pytestmark = pytest.mark.integration


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
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path
    config.reset_cache()


def get(client, path: str, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def put(conn, native_id: str, country: str, cpv: list[str]) -> int:
    return store(conn, replace(opp(native_id, country=country), cpv_codes=cpv))


# ======================================================================= 3. CPV filter on buyers and market

def test_buyers_take_a_cpv_filter_and_keep_all_their_counts(client, conn):
    put(conn, "ES-1", "ES", ["34320000"])
    put(conn, "ES-2", "ES", ["35400000"])
    put(conn, "DE-1", "DE", ["35400000", "44470000"])
    put(conn, "PL-1", "PL", ["35400000"])
    every = get(client, "/v1/buyers")
    assert every["total"] == 3
    parts = get(client, "/v1/buyers", cpv="343")
    assert [b["country"] for b in parts["items"]] == ["ES"]
    # the buyer's count is all of its notices (the card's number), not only those under the codes
    assert parts["items"][0]["tenderCount"] == 2
    assert [b["country"] for b in get(client, "/v1/buyers", cpv="34320000")["items"]] == ["ES"]
    assert sorted(b["country"] for b in get(client, "/v1/buyers", cpv="343,4447")["items"]) == ["DE", "ES"]
    assert get(client, "/v1/buyers", cpv="35120000-1")["total"] == 0          # a check digit is dropped, not refused
    assert get(client, "/v1/buyers", cpv="343", country="DE")["total"] == 0
    for bad in ("abc", "3", "123456789"):
        r = client.get("/v1/buyers", params={"cpv": bad})
        assert r.status_code == 422 and "2 to 8 digits" in r.text, bad
    # the site search's buyers group is the list on its defaults: the new filter is off there
    assert search._defaults(tenders.list_buyers)["cpv"] is None
    found = get(client, "/v1/search", q="ministry")
    assert found["buyers"]["total"] == get(client, "/v1/buyers", q="ministry")["total"] == 3


def test_the_market_takes_a_cpv_filter(client, conn):
    put(conn, "ES-1", "ES", ["34320000"])
    put(conn, "DE-1", "DE", ["35400000"])
    put(conn, "DE-2", "DE", ["34330000", "35400000"])
    every = get(client, "/v1/stats/market")
    assert every["countries"]["total"] == 3 and every["cpv"] is None
    parts = get(client, "/v1/stats/market", cpv="343")
    assert parts["cpv"] == ["343"]
    assert parts["countries"]["total"] == 2
    assert {c["country"]: c["count"] for c in parts["countries"]["items"]} == {"DE": 1, "ES": 1}
    assert sum(m["count"] for m in parts["months"]) == 2
    # WP-112 (p04): with codes asked, only the groups under them (DE-2's 354 is another product of the same notice)
    assert {g["group"] for g in parts["cpvGroups"]} == {"343"}
    assert {g["group"] for g in every["cpvGroups"]} == {"343", "354"}         # without codes a notice counts in each of its groups
    assert get(client, "/v1/stats/market", cpv="343", country="ES")["countries"]["total"] == 1
    assert client.get("/v1/stats/market", params={"cpv": "x1"}).status_code == 422


# ======================================================================= 6. the supplier page under the report's codes

def _award_notice(conn, native_id: str, country: str, cpv: list[str]) -> int:
    o = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=f"Ministerio de Defensa {country}",
                    title_original="Repuestos", title_en="Spare parts", country=country, published_at=date(2026, 3, 1),
                    cpv_codes=cpv, status="awarded", is_defence=True, sig_legal_basis=True, sig_cpv=True,
                    notice_subtype="29", procedure_identifier=f"p-{native_id}", source_url=f"https://ted.example/{native_id}")
    src = db.source_id(conn, "ted")
    o.buyer_org_id = db.resolve_organisation(conn, o.buyer_name_raw, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, o, f"hash-{native_id}", src)
    conn.commit()
    return oid


def test_a_supplier_page_with_the_reports_codes_says_how_many_are_under_them(conn, env, client):
    _award_notice(conn, "1-2026", "ES", ["34320000"])
    _award_notice(conn, "2-2026", "ES", ["34330000", "35400000"])
    _award_notice(conn, "3-2026", "ES", ["35400000"])
    _award_notice(conn, "4-2026", "PT", ["34320000"])
    who = ("Suyfa Defence, S.L.", "ESP", "B12345678")
    awards.run_awards(client=FakeTed([rec(n, [who]) for n in ("1-2026", "2-2026", "3-2026", "4-2026")]).client(),
                      pause=0, sleep=lambda s: None)
    slug = get(client, "/v1/suppliers", q="suyfa")["items"][0]["slug"]
    plain = get(client, f"/v1/suppliers/{slug}")
    assert plain["noticeCount"] == 4 and plain["underCodes"] is None
    asked = {"cpv": "34300000,44470000", "buyerCountry": "ES,DE,FR,PL,NL"}
    prof = get(client, f"/v1/suppliers/{slug}", **asked)
    assert prof["noticeCount"] == 4                                  # the total stays the total
    assert prof["underCodes"] == {"cpv": ["343", "4447"], "buyerCountries": ["ES", "DE", "FR", "PL", "NL"], "contracts": 2}
    # the number the supplier list (and so the report's "who to approach") gives for the same codes and countries
    listed = get(client, "/v1/suppliers", **asked)["items"]
    assert [i["awardCount"] for i in listed if i["slug"] == slug] == [2]
    assert get(client, f"/v1/suppliers/{slug}", cpv="34300000")["underCodes"]["contracts"] == 3      # every buyer country
    assert client.get(f"/v1/suppliers/{slug}", params={"cpv": "abc"}).status_code == 422
