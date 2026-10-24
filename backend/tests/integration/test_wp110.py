"""WP-110 (round-4 re-check of 24 October 2026, search precision and stability), against a real Postgres: the main code's
heads kept by the trigger (migration 0122), the false positives of the round (a canteen as a wiring harness, a pollution
vessel as a drone, a cyberspace centre's every notice as cyber), the CPV hints, and the global search's parts running at once."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dgate import search
from tests.integration.test_changes import opp, store
from tests.integration.test_wp98 import _fresh_cache, client, get, ids, put  # noqa: F401 (fixtures)

pytestmark = pytest.mark.integration


def test_the_trigger_keeps_the_heads_of_the_main_code(conn):
    o = replace(opp("MAIN-1", country="PL", title="Budowa stołówki"), cpv_codes=["45000000", "45311000"])
    oid = store(conn, o)
    row = conn.execute("SELECT main_heads, cpv_heads FROM opportunity_search WHERE id = %s", (oid,)).fetchone()
    assert "4531" in row["cpv_heads"] and "4531" not in row["main_heads"] and "45000000" in row["main_heads"]
    store(conn, replace(o, cpv_codes=["31611000"]), "b")
    assert "31611" in conn.execute("SELECT main_heads FROM opportunity_search WHERE id = %s", (oid,)).fetchone()["main_heads"]


def test_a_product_is_found_by_its_title_or_its_main_code_never_a_secondary_one(client, conn):  # noqa: F811
    put(conn, "W-CANTEEN", "Budowa stołówki z kuchnią", country="PL", cpv=["45000000", "45315300", "45311100"])
    put(conn, "W-FOUND", "Budowa fundamentu betonowego", country="PL", cpv=["45000000", "45311000"])
    put(conn, "W-NET", "Renovación de cableado de red", country="ES", cpv=["50324100", "32421000"])
    put(conn, "W-SETS", "Dostawa wiązek do pojazdów", country="PL", cpv=["31611000"])          # by its main code
    put(conn, "W-EN", "Wiring harnesses for the Leopard 2", cpv=["34300000"])                   # by its title
    put(conn, "D-VESSEL", "Nabava plovila za uklanjanje onečišćenja", country="HR",
        cpv=["34513600", "34512000", "34711200", "35512400"])
    put(conn, "D-UAV", "Dostawa bezzałogowych statków", country="PL", cpv=["35613000"])
    put(conn, "D-EN", "Counter-drone systems", country="NO", cpv=["35720000"])
    page = get(client, "/v1/tenders", q="wiring harness")
    assert ids(page) == ["W-EN", "W-SETS"]
    assert page["cpvHints"][0] == {"code": "31611000", "title": "Wiring sets", "prefix": "31611"}
    assert ids(get(client, "/v1/tenders", q="drone")) == ["D-EN", "D-UAV"]
    assert "D-VESSEL" not in ids(get(client, "/v1/tenders", q="drone", status="all"))
    # "wiring" alone is a word of its own: titles, and the codes it names by their main code ("Wiring sets")
    assert ids(get(client, "/v1/tenders", q="wiring")) == ["W-EN", "W-SETS"]


def test_a_product_word_never_matches_a_buyer_name_and_the_buyer_stays_searchable(client, conn):  # noqa: F811
    put(conn, "C-POL-1", "Dostawa sprzętu biurowego", country="PL", buyer="Centrum Operacji Cybernetycznych")
    put(conn, "C-POL-2", "Usługi transportowe", country="PL", buyer="Centrum Operacji Cybernetycznych")
    put(conn, "C-FR", "Prestations de cybersécurité", country="FR")
    put(conn, "C-SSI", "Maintenance des systèmes SSI", country="FR")               # fire alarms
    assert ids(get(client, "/v1/tenders", q="cyber")) == ["C-FR"]
    assert ids(get(client, "/v1/tenders", q="Centrum Operacji")) == ["C-POL-1", "C-POL-2"]
    assert ids(get(client, "/v1/tenders", q="cybersécurité")) == ["C-FR"]


def test_machining_finds_machining_and_the_german_spare_parts_word_points_to_the_vehicle_parts_code(client, conn):  # noqa: F811
    put(conn, "M-CNC", "CNC-Bearbeitung von Gehäusen")
    put(conn, "M-ERS", "Ersatzteile Leopard 2")
    put(conn, "M-BAAINBW", "6003121709-BAAINBw E2.3Y_E23Y003367", cpv=["35400000"])
    assert ids(get(client, "/v1/tenders", q="Zerspanung CNC")) == ["M-CNC"]
    page = get(client, "/v1/tenders", q="Ersatzteile")
    assert ids(page) == ["M-ERS"]                     # a notice titled by its order number is not read as spare parts ...
    assert any(h["code"] == "35400000" for h in page["cpvHints"])     # ... the hint leads to its code
    assert "M-BAAINBW" in ids(get(client, "/v1/tenders", cpv="354"))


def test_the_global_search_answers_every_part_at_once_within_the_budget(client, conn, monkeypatch):  # noqa: F811
    def sleepy(**kw):
        kw["conn"].execute("SELECT pg_sleep(1.2)")
        return {"items": [], "total": 0}

    groups = dict(search.GROUPS)
    groups["funding"] = groups["buyers"] = sleepy
    monkeypatch.setattr(search, "GROUPS", groups)
    monkeypatch.setattr(search, "BUDGET_MS", 2000)
    body = get(client, "/v1/search", q="radar")
    # one after the other, the two parts of 1.2 s each were 2.4 s: the second "slow"
    assert body["funding"]["total"] == 0 and body["buyers"]["total"] == 0
    assert body["tenders"]["error"] is None and body["tookMs"] < 2000
    assert "cpvHints" in body
