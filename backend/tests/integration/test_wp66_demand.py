"""WP-66, the demand map (`POST /v1/readiness/demand`) on a real Postgres: what is counted, what is named, the PLACSP switch,
the CPV level match through migration 0099's index, and that a request is validated and leaves nothing behind."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, demand

pytestmark = pytest.mark.integration

TODAY = date.today()
RECENT = TODAY - timedelta(days=30)


def org(conn, name: str, country: str, **extra) -> int:
    cols = ["canonical_name", "country", *extra]
    return conn.execute(f"INSERT INTO organisation ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                        [name.lower(), country, *extra.values()]).fetchone()["id"]


def notice(conn, source: str, native: str, *, buyer: int | None, country: str, cpv: tuple[str, ...], published: date = RECENT,
           buyer_class: str | None = "defence", legal: bool = False, defence: bool = True, suppressed: bool = False,
           ted_ref: str | None = None, procedure: str | None = None, buyer_name: str = "Buyer", withheld: bool = False) -> int:
    opp = conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_org_id, buyer_name_raw, country, title_original, title_en,
                                    published_at, cpv_codes, is_defence, sig_legal_basis, buyer_class, suppressed, ted_ref,
                                    procedure_identifier, buyer_withheld, source_url)
           VALUES ((SELECT id FROM source WHERE code = %s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (source, native, buyer, buyer_name, country, f"Repuestos {native}", f"Spare parts {native}", published, list(cpv),
         defence, legal, buyer_class, False, ted_ref, procedure, False, f"https://example.test/{native}")).fetchone()["id"]
    # a removal on request: the insert trigger derives both flags from `suppression`, so they are set afterwards
    conn.execute("UPDATE opportunity SET suppressed = %s, buyer_withheld = %s WHERE id = %s", (suppressed, withheld, opp))
    return opp


def award(conn, opp: int, winner: int, name: str, country: str = "ES") -> None:
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice,
                                       cpv_main, resolution_method, resolution_confidence)
                    VALUES (%s, %s, %s, %s, 1, '34330000', 'exact_name', 1.0)""", (opp, winner, country, name))


@pytest.fixture()
def world(conn):
    """Spain: a core buyer (two families under one name), a city council; Poland: one notice in both Polish sources."""
    male = org(conn, "JAE Mando de Apoyo Logistico", "ES", is_defence_buyer=True)
    male2 = org(conn, "JAE Mando de Apoyo Logistico (2)", "ES")
    city = org(conn, "Ayuntamiento de Madrid", "ES")
    wog = org(conn, "43 Wojskowy Oddzial Gospodarczy", "PL")
    w = {"male": male, "city": city}
    # one procurement published in TED and in PLACSP (the PLACSP row names the TED notice): counted once
    w["ted1"] = notice(conn, "ted", "100-2026", buyer=male, country="ES", cpv=("34330000",), legal=True, procedure="P-1",
                       buyer_name="JAE Mando de Apoyo Logístico")
    w["pl1"] = notice(conn, "es_placsp", "ES-1", buyer=male, country="ES", cpv=("34330000",), ted_ref="100-2026",
                      buyer_name="JAE Mando de Apoyo Logístico")
    # the same name under a second organisation row: one line in the top buyers, two families in the counts
    w["pl2"] = notice(conn, "es_placsp", "ES-2", buyer=male2, country="ES", cpv=("34352100",),
                      buyer_name="JAE Mando de Apoyo Logístico")
    w["pl3"] = notice(conn, "es_placsp", "ES-3", buyer=city, country="ES", cpv=("34300000",), buyer_class="other",
                      buyer_name="Ayuntamiento de Madrid")
    for n in range(4, 7):     # three more procurements of the core buyer, each won by the same company
        w[f"pl{n}"] = notice(conn, "es_placsp", f"ES-{n}", buyer=male, country="ES", cpv=("34320000",),
                             buyer_name="JAE Mando de Apoyo Logístico")
    # not counted: older than three years, another CPV group, removed, not defence, a country not asked, a withheld buyer named
    notice(conn, "es_placsp", "ES-old", buyer=male, country="ES", cpv=("34330000",), published=TODAY - timedelta(days=4 * 365))
    w["other_group"] = notice(conn, "es_placsp", "ES-341", buyer=male, country="ES", cpv=("34100000",))
    notice(conn, "es_placsp", "ES-gone", buyer=male, country="ES", cpv=("34330000",), suppressed=True)
    notice(conn, "es_placsp", "ES-civil", buyer=male, country="ES", cpv=("34330000",), defence=False)
    notice(conn, "ted", "200-2026", buyer=None, country="IT", cpv=("34330000",))
    # Poland: one bulletin notice in e-Zamowienia and in the Atlas dataset (same number): one procurement
    notice(conn, "pl_ezam", "2026/BZP 0001", buyer=wog, country="PL", cpv=("34300000",), buyer_name="43 WOG")
    notice(conn, "pl_atlas", "2026/BZP 0001", buyer=wog, country="PL", cpv=("34300000",), buyer_name="43 WOG")
    jw = org(conn, "Jednostka Wojskowa 1234", "PL")
    notice(conn, "pl_ezam", "2026/BZP 0002", buyer=jw, country="PL", cpv=("34300000", "35421000"), legal=True,
           buyer_name="Jednostka Wojskowa 1234", withheld=True)

    # winners: one company with three procurements (named), one with one (a count only), a natural person with three
    # (never counted or named), a PLACSP winner (only with the switch on), a removed company
    big = org(conn, "Talleres Norte SL", "ES")
    small = org(conn, "Recambios Sur SL", "ES")
    person = org(conn, "Juan Garcia Lopez", "ES", individual_reason="natural_person")
    gone = org(conn, "Borrado SA", "ES", suppressed=True)
    for n in (4, 5, 6):
        award(conn, w[f"pl{n}"], big, "Talleres Norte, S.L.")
        award(conn, w[f"pl{n}"], person, "Juan Garcia Lopez")
    award(conn, w["ted1"], big, "TALLERES NORTE SL")
    award(conn, w["ted1"], small, "Recambios Sur SL")
    award(conn, w["pl1"], gone, "Borrado SA")
    # the PLACSP award result read for pl4 (its date of last update is credited when the switch is on)
    conn.execute("""INSERT INTO award_notice (opportunity_id, status, payload_hash, payload_updated_at)
                    VALUES (%s, 'loaded', 'h', '2026-10-01T00:00:00Z')""", (w["pl4"],))
    conn.commit()
    return w


@pytest.fixture()
def client(conn, monkeypatch):
    def make(public: bool = False) -> TestClient:
        monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true" if public else "false")
        config.reset_cache()
        return TestClient(api.app)
    return make


def post(c: TestClient, cpv: list[str], countries: list[str] | None = None):
    body: dict = {"cpv": cpv}
    if countries is not None:
        body["countries"] = countries
    return c.post("/v1/readiness/demand", json=body)


def test_counts_one_procurement_per_procedure_and_splits_core_and_other_buyers(world, client):
    r = post(client(), ["34300000"], ["ES", "PL"])
    assert r.status_code == 200
    d = r.json()
    es, pl = d["byCountry"]
    assert (es["country"], pl["country"]) == ("ES", "PL")
    # ES: ted1 + its PLACSP twin = 1, pl2, pl3, pl4-6: 6 procurements; the old, other-group, removed, civil rows are out
    assert es["procurements"] == 6
    assert es["directive"] == 1
    assert (es["coreBuyers"], es["otherBuyers"]) == (2, 1)
    assert [(b["name"], b["core"], b["procurements"]) for b in es["topBuyers"]] == [
        ("JAE Mando de Apoyo Logístico", True, 5), ("Ayuntamiento de Madrid", False, 1)]
    # PL: the two Polish sources of one notice count once; the withheld buyer is counted, never named
    assert pl["procurements"] == 2 and pl["directive"] == 1
    assert pl["coreBuyers"] == 2 and [b["name"] for b in pl["topBuyers"]] == ["43 WOG"]
    assert "Jednostka" not in r.text
    assert d["total"]["procurements"] == 8 and d["total"]["coreBuyers"] == 4
    assert d["codes"] == [{"code": "34300000", "prefix": "343", "procurements": 8}]
    assert d["since"] == (TODAY - timedelta(days=1096)).isoformat()
    # links to the notices, newest first, one per procurement (the TED publication of the twin pair)
    assert len(es["latest"]) == demand.LATEST
    assert all(x["slug"] and x["sourceUrl"].startswith("https://example.test/") for x in es["latest"])
    assert "IT" not in str([c["country"] for c in d["byCountry"]])
    assert d["coverage"].startswith("Direct buying by defence bodies") and "tenth" in d["coverage"]


def test_names_every_legal_entity_and_never_a_person_or_a_removed_company(world, client):
    # WP-81 (owner decision of 22 October 2026): a legal entity is named from one procurement (the WP-66 rule "named only
    # with three" is lifted); the natural person and the removed company are still never counted or named
    es = post(client(), ["34300000"], ["ES"]).json()["byCountry"][0]
    # TED winners only while the switch is off: ted1 has two winners (the big company and the small one, one award each)
    assert [(w["name"], w["awards"]) for w in es["topWinners"]] == [("Recambios Sur SL", 1), ("TALLERES NORTE SL", 1)]
    assert es["winners"] == 2 and es["awarded"] == 1
    assert es["otherWinners"] == {"winners": 0, "awards": 0}
    on = post(client(public=True), ["34300000"], ["ES"]).json()
    es = on["byCountry"][0]
    assert [(w["name"], w["country"], w["awards"]) for w in es["topWinners"]] == [
        ("Talleres Norte, S.L.", "ES", 4), ("Recambios Sur SL", "ES", 1)]
    assert len(es["topWinners"][0]["notices"]) == demand.WINNER_NOTICES
    assert es["otherWinners"] == {"winners": 0, "awards": 0}
    assert es["winners"] == 2 and es["awarded"] == 4
    body = str(on)
    assert "Garcia" not in body and "Borrado" not in body
    assert "PLACSP" in on["winnersFrom"] and [s["code"] for s in on["sources"]] == ["ted", "es_placsp"]


def test_a_code_matches_by_its_level(world, client):
    c = client()
    by = {x["code"]: x["procurements"] for x in post(c, ["34330000", "34100000", "35000000", "34352100"], ["ES", "PL"]).json()["codes"]}
    assert by == {"34330000": 1, "34100000": 1, "35000000": 1, "34352100": 1}
    # duplicates and a check digit are read as one code
    d = post(c, ["34300000-0", "34300000"], ["ES"]).json()
    assert d["codes"] == [{"code": "34300000", "prefix": "343", "procurements": 6}]


def test_the_index_answers_the_prefix_match(conn, world):
    # a table of some size, most of it under other codes, so that the plan is a real choice
    conn.execute("""INSERT INTO opportunity (source_id, native_id, buyer_name_raw, country, title_original, published_at,
                                             cpv_codes, is_defence)
                    SELECT (SELECT id FROM source WHERE code = 'ted'), 'x-' || g, 'Buyer', 'DE', 'Tents', CURRENT_DATE,
                           ARRAY['39522530'], true FROM generate_series(1, 3000) g""")
    conn.execute("ANALYZE opportunity")
    plan = "\n".join(r["QUERY PLAN"] for r in conn.execute(
        "EXPLAIN SELECT id FROM opportunity o WHERE o.is_defence AND NOT o.suppressed "
        "AND dgate_cpv_heads(o.cpv_codes) && ARRAY['343']::text[]").fetchall())
    assert "opp_cpv_heads" in plan
    assert conn.execute("SELECT dgate_cpv_heads(ARRAY['34352100'])").fetchone()["dgate_cpv_heads"] == [
        "34", "343", "3435", "34352", "343521", "3435210", "34352100"]


@pytest.mark.parametrize("body", [
    {"cpv": []},
    {"cpv": [f"{30000000 + i * 100000}" for i in range(16)]},
    {"cpv": ["3430000"]},
    {"cpv": ["34300000"], "countries": ["BE"]},                     # WP-105: Italy and Portugal are map countries now
    {"cpv": ["34300000"], "countries": []},
    {"cpv": ["34300000"], "countries": ["ES", "DE", "FR", "PL", "NL", "PT", "IT", "ES"]},
    {"cpv": ["34300000"], "home": "BE"},
    {"cpv": ["34300000"], "secretField": "Talleres Norte"},
])
def test_a_wrong_request_is_refused_without_echoing_it(conn, client, body):
    r = client().post("/v1/readiness/demand", json=body)
    assert r.status_code == 422
    assert "3430000" not in r.text and "secretField" not in r.text and "Talleres" not in r.text


def test_nothing_is_stored_or_logged(world, client, conn, caplog):
    tables = ("opportunity", "award", "organisation", "app_hit_daily", "list_snapshot")
    before = {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in tables}
    with caplog.at_level(logging.DEBUG):
        assert post(client(), ["34330000", "44470000"]).status_code == 200
    assert {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in tables} == before
    assert "34330000" not in caplog.text and "44470000" not in caplog.text
