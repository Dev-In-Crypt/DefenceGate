"""WP-112 (persona round 4 of 24 October 2026): who to approach by the trade of the codes (a winner matched only by an additional
code of its notice is listed apart, the primes at the same buyers are of the same trade, the Indra mark for vehicle codes only), the
supplier list's PLACSP credit per page, the supplier file's name and numbers as on its page, and the market's all-defence count
with its CPV groups under the codes asked."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, stats
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

RECENT = date.today() - timedelta(days=30)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
    config.reset_cache()
    stats.reset_cache()
    yield
    stats.reset_cache()


def org(conn, name: str, country: str) -> int:
    return conn.execute("INSERT INTO organisation (canonical_name, country) VALUES (%s, %s) RETURNING id",
                        (name, country)).fetchone()["id"]


def notice(conn, native: str, *, buyer: int, country: str = "ES", cpv: list[str], source: str = "ted") -> int:
    return conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_org_id, buyer_name_raw, country, title_original, published_at,
                                    cpv_codes, is_defence, buyer_class, procedure_identifier)
           VALUES ((SELECT id FROM source WHERE code = %s), %s, %s, %s, %s, %s, %s, %s, true, 'defence', %s) RETURNING id""",
        (source, native, buyer, f"Buyer {buyer}", country, f"Order {native}", RECENT, cpv, f"p-{native}")).fetchone()["id"]


def award(conn, opp: int, winner: int, name: str, country: str = "ES", identifier: str | None = None) -> int:
    return conn.execute(
        """INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice, cpv_main,
                              identifier_as_stated, resolution_method, resolution_confidence)
           VALUES (%s, %s, %s, %s, 1, '34330000', %s, 'exact_name', 1.0) RETURNING id""",
        (opp, winner, country, name, identifier)).fetchone()["id"]


def post(body: dict) -> dict:
    r = TestClient(api.app).post("/v1/readiness/demand", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_winner_matched_only_by_an_additional_code_is_listed_after_the_trade(conn):
    mal = org(conn, "jae mando de apoyo logistico", "ES")
    parts = org(conn, "talleres norte", "ES")
    award(conn, notice(conn, "A-1", buyer=mal, cpv=["34330000"]), parts, "Talleres Norte SL")
    # O-rings and gaskets in a pipeline order: the vehicle-parts code only among the additional codes (p01)
    pipes = org(conn, "tubos y juntas", "ES")
    for k in range(3):
        award(conn, notice(conn, f"P-{k}", buyer=mal, cpv=["44160000", "34312500"]), pipes, "Tubos y Juntas SA")
    # a catch-all supply contract of 23 codes, its main code under the codes, won by a vehicle maker (p02)
    uro = org(conn, "uro vehiculos especiales", "ES")
    codes = ["34330000"] + [f"{18100000 + i * 1000}" for i in range(22)]
    award(conn, notice(conn, "U-1", buyer=mal, cpv=codes), uro, "URO Vehículos Especiales SA")
    conn.commit()
    a = post({"cpv": ["34300000"], "countries": ["ES"]})["approach"]
    order = [(w["name"], w["byOtherCodeOnly"]) for w in a["winners"]]
    assert order[0] == ("Talleres Norte SL", False)                  # one contract, but of the trade: first
    assert set(order[1:]) == {("Tubos y Juntas SA", True), ("URO Vehículos Especiales SA", True)}
    assert a["byOtherCodeOnly"] == {"winners": 2, "awards": 4}
    by = {c["country"]: c for c in post({"cpv": ["34300000"], "countries": ["ES"]})["byCountry"]}
    assert by["ES"]["topWinners"][0]["name"] == "Talleres Norte SL"   # the per-country list too


def test_the_indra_mark_is_for_vehicle_codes_only(conn):
    mal = org(conn, "jae mando de apoyo logistico", "ES")
    indra = org(conn, "indra sistemas", "ES")
    award(conn, notice(conn, "IT-1", buyer=mal, cpv=["72000000"]), indra, "INDRA SISTEMAS SA")
    award(conn, notice(conn, "V-1", buyer=mal, cpv=["34330000"]), indra, "INDRA SISTEMAS SA")
    navantia = org(conn, "navantia sa sme", "ES")
    award(conn, notice(conn, "IT-2", buyer=mal, cpv=["72000000"]), navantia, "NAVANTIA SA SME")
    conn.commit()
    it = {w["name"]: w["prime"] for w in post({"cpv": ["72000000"], "countries": ["ES"]})["approach"]["winners"]}
    assert it["INDRA SISTEMAS SA"] is None                           # the elDiario.es source is about vehicle makers
    assert it["NAVANTIA SA SME"]["group"] == "Navantia"              # SIPRI Top 100, any trade
    cars = {w["name"]: w["prime"] for w in post({"cpv": ["34300000"], "countries": ["ES"]})["approach"]["winners"]}
    assert cars["INDRA SISTEMAS SA"]["group"] == "Indra"


def test_the_supplier_list_credits_placsp_only_for_a_page_with_its_wins(conn):
    mon = org(conn, "agencja uzbrojenia", "PL")
    pl = org(conn, "zaklady mechaniczne", "PL")
    award(conn, notice(conn, "PL-1", buyer=mon, country="PL", cpv=["35300000"]), pl, "Zakłady Mechaniczne SA", "PL")
    mal = org(conn, "jae mando de apoyo logistico", "ES")
    es = org(conn, "talleres norte", "ES")
    award(conn, notice(conn, "ES-1", buyer=mal, cpv=["35300000"], source="es_placsp"), es, "Talleres Norte SL")
    conn.commit()
    c = TestClient(api.app)
    assert c.get("/v1/suppliers", params={"country": "PL"}).json()["placsp"] is False
    assert c.get("/v1/suppliers", params={"country": "ES"}).json()["placsp"] is True
    assert c.get("/v1/suppliers", params={"country": "ES", "source": "ted"}).json()["placsp"] is False


def test_the_supplier_file_carries_the_page_name_and_its_numbers(conn):
    mon = org(conn, "ministero della difesa", "IT")
    leo = org(conn, "leonardo societa per azioni", "IT")
    for k, name in enumerate(["Leonardo S.p.A.", "Leonardo S.p.A.", "LEONARDO - SOCIETA PER AZIONI"]):
        award(conn, notice(conn, f"L-{k}", buyer=mon, country="IT", cpv=["35600000"]), leo, name, "IT",
              identifier="IT00881841001")
    conn.commit()
    c = TestClient(api.app)
    page = c.get(f"/v1/suppliers/{leo}").json()
    file = c.get(f"/v1/suppliers/{leo}/contracts").json()
    assert file["name"] == page["name"] == "Leonardo S.p.A."
    assert file["identifiers"] == page["identifiers"] == ["IT00881841001"]


def _put(conn, native: str, *, cpv: list[str], sig_buyer: bool = False) -> int:
    published = date.today() - timedelta(days=20)
    opp = Opportunity(source_code="ted", native_id=native, buyer_name_raw="Ministerie van Defensie", title_original="Notice",
                      country="NL", published_at=published,
                      deadline_at=datetime.combine(published, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=30),
                      cpv_codes=cpv, status="open", is_defence=True, sig_cpv=True, sig_buyer=sig_buyer)
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, "Ministerie van Defensie", "NL", src_id=src)
    opp_id, _ = db.upsert_opportunity(conn, opp, f"hash-{native}", src)
    conn.commit()
    return opp_id


def test_the_market_counts_all_defence_on_request_with_the_groups_under_the_codes(conn):
    _put(conn, "M-1", cpv=["35400000", "18800000"])                  # a military vehicle, with a jewellery code beside it
    for k in range(3):
        _put(conn, f"T-{k}", cpv=["60100000"], sig_buyer=True)       # transport bought by the ministry: all defence only
    conn.execute("UPDATE opportunity SET sig_cpv_military = (cpv_codes[1] LIKE '354%%')")
    conn.commit()
    c = TestClient(api.app)
    core = c.get("/v1/stats/market", params={"country": "NL", "cpv": "60"}).json()
    every = c.get("/v1/stats/market", params={"country": "NL", "cpv": "60", "scope": "relevant"}).json()
    assert core["scope"] == "core" and core["countries"]["total"] == 0
    assert every["scope"] == "relevant" and every["countries"]["total"] == 3
    assert "services and supplies that defence buyers buy" in every["basis"]["months"]
    assert c.get("/v1/stats/market", params={"scope": "relevant"}).status_code == 422     # the whole market: not in this scope
    stats.reset_cache()
    groups = {g["group"] for g in c.get("/v1/stats/market", params={"country": "NL", "cpv": "354"}).json()["cpvGroups"]}
    assert groups == {"354"}                                          # the jewellery code of the same notice is not a group here
    stats.reset_cache()
    assert {g["group"] for g in c.get("/v1/stats/market", params={"country": "NL"}).json()["cpvGroups"]} >= {"354", "188"}
