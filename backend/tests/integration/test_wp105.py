"""WP-105 (persona round of 24 October 2026): the supplier report's own-country winners and its Portugal and Italy blocks, the primes
that win other contracts from the same buyers, a buyer's top suppliers under its CPV filter with their contract values, and the
market overview's contract-value sums (`money`), each equal to the supplier pages' own sums."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, demand, money, stats, suppliers
from dgate.ops import suppress

pytestmark = pytest.mark.integration

RECENT = date.today() - timedelta(days=30)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
    config.reset_cache()
    stats.reset_cache()
    yield
    stats.reset_cache()


def org(conn, name: str, country: str, **extra) -> int:
    cols = ["canonical_name", "country", *extra]
    return conn.execute(f"INSERT INTO organisation ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                        [name, country, *extra.values()]).fetchone()["id"]


def notice(conn, native: str, *, buyer: int, country: str, value: tuple[float, str, str] | None = None,
           cpv: str = "34330000", source: str = "ted", published: date = RECENT) -> int:
    amount, currency, kind = value or (None, None, None)
    return conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_org_id, buyer_name_raw, country, title_original, published_at,
                                    cpv_codes, is_defence, buyer_class, procedure_identifier, value_amount, value_currency,
                                    value_kind)
           VALUES ((SELECT id FROM source WHERE code = %s), %s, %s, %s, %s, %s, %s, ARRAY[%s], true, 'defence', %s, %s, %s, %s)
           RETURNING id""",
        (source, native, buyer, f"Buyer {buyer}", country, f"Parts {native}", published, cpv, f"p-{native}", amount,
         currency, kind)).fetchone()["id"]


def award(conn, opp: int, winner: int, name: str, country: str = "ES", winners: int = 1) -> int:
    return conn.execute(
        """INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice, cpv_main,
                              resolution_method, resolution_confidence)
           VALUES (%s, %s, %s, %s, %s, '34330000', 'exact_name', 1.0) RETURNING id""",
        (opp, winner, country, name, winners)).fetchone()["id"]


def post(body: dict) -> dict:
    r = TestClient(api.app).post("/v1/readiness/demand", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_own_country_winners_are_named_past_the_first_thirty(conn):
    mal = org(conn, "jae mando de apoyo logistico", "ES")
    baainbw = org(conn, "bundesamt fur ausrustung", "DE")
    for i in range(demand.APPROACH + 1):              # 31 Spanish winners with two contracts each
        w = org(conn, f"talleres {i:02d}", "ES")
        for k in range(2):
            award(conn, notice(conn, f"ES-{i}-{k}", buyer=mal, country="ES"), w, f"Talleres {i:02d} SL")
    brueggemann = org(conn, "bruggemann", "DE")
    award(conn, notice(conn, "DE-1", buyer=baainbw, country="DE"), brueggemann, "Brüggemann GmbH", "DE")
    conn.commit()
    plain = post({"cpv": ["34300000"], "countries": ["ES", "DE"]})["approach"]
    assert "Brüggemann GmbH" not in {w["name"] for w in plain["winners"]}       # 32nd: past the list
    assert plain["more"]["winners"] == 2
    home = post({"cpv": ["34300000"], "countries": ["ES", "DE"], "home": "DE"})["approach"]
    assert "Brüggemann GmbH" in {w["name"] for w in home["winners"]}            # a German company sees its own
    assert home["more"]["winners"] == 1 and len(home["winners"]) == demand.APPROACH + 1


def test_portugal_and_italy_are_map_countries(conn):
    army = org(conn, "estado maior do exercito", "PT")
    difesa = org(conn, "direzione degli armamenti terrestri", "IT")
    award(conn, notice(conn, "PT-1", buyer=army, country="PT", cpv="35811000"), org(conn, "texteis sul", "PT"), "Têxteis Sul Lda", "PT")
    award(conn, notice(conn, "IT-1", buyer=difesa, country="IT", cpv="35811000"), org(conn, "tessile nord", "IT"), "Tessile Nord Srl", "IT")
    conn.commit()
    d = post({"cpv": ["35811000"], "home": "PT"})
    assert d["countries"] == ["ES", "DE", "FR", "PL", "NL", "PT", "IT"]
    by = {c["country"]: c for c in d["byCountry"]}
    assert by["PT"]["procurements"] == 1 and by["PT"]["topWinners"][0]["name"] == "Têxteis Sul Lda"
    assert by["IT"]["awarded"] == 1 and by["PT"]["openNow"]["href"].startswith("/tenders?country=PT&cpv=35811")
    assert "Portugal and Italy from TED only" in d["coverage"]


def test_primes_that_win_other_contracts_from_the_same_buyers(conn):
    mal = org(conn, "jae mando de apoyo logistico", "ES")
    award(conn, notice(conn, "A-1", buyer=mal, country="ES"), org(conn, "talleres norte", "ES"), "Talleres Norte SL")
    indra = org(conn, "indra sistemas", "ES")
    for k in range(3):                                  # radar, not under the automotive code
        award(conn, notice(conn, f"R-{k}", buyer=mal, country="ES", cpv="35720000"), indra, "INDRA SISTEMAS SA")
    ute = org(conn, "ute indra sistemas thales", "ES")  # a joint venture is not the way in on its own
    award(conn, notice(conn, "R-9", buyer=mal, country="ES", cpv="35720000"), ute, "UTE Indra Thales")
    idv = org(conn, "idv defensa vehicles espana s l u antes iveco espana", "ES")
    award(conn, notice(conn, "V-1", buyer=mal, country="ES", cpv="34100000"), idv, "IDV Defensa Vehicles España SLU")
    iveco = org(conn, "iveco espana", "ES")             # the civil truck maker: no prime
    award(conn, notice(conn, "V-2", buyer=mal, country="ES", cpv="34100000"), iveco, "Iveco España SL")
    other = org(conn, "unidad lejana", "ES")            # a prime at a buyer that is not in the answer: not listed
    award(conn, notice(conn, "X-1", buyer=other, country="ES", cpv="35720000"), org(conn, "thales espana", "ES"), "Thales España")
    conn.commit()
    got = post({"cpv": ["34300000"], "countries": ["ES"]})["approach"]["primesAtBuyers"]
    assert [(p["name"], p["contracts"], p["prime"]["group"]) for p in got] == [
        ("INDRA SISTEMAS SA", 3, "Indra"), ("IDV Defensa Vehicles España SLU", 1, "Iveco Defence Vehicles (Leonardo)")]


def _buyer_world(conn):
    mal = org(conn, "jae mando de apoyo logistico", "ES")
    w = org(conn, "talleres norte", "ES")
    award(conn, notice(conn, "B-1", buyer=mal, country="ES", value=(100000.0, "EUR", "total")), w, "Talleres Norte SL")
    award(conn, notice(conn, "B-2", buyer=mal, country="ES", value=(40000.0, "EUR", "total"), cpv="18100000"), w, "Talleres Norte SL")
    # a framework ceiling and a value two winners share: never in a sum
    award(conn, notice(conn, "B-3", buyer=mal, country="ES", value=(9e6, "EUR", "total")), w, "Talleres Norte SL")
    conn.execute("UPDATE award SET value_amount = 9e6, value_currency = 'EUR', value_kind = 'framework' WHERE opportunity_id = "
                 "(SELECT id FROM opportunity WHERE native_id = 'B-3')")
    t = org(conn, "textiles sur", "ES")
    shared = notice(conn, "B-4", buyer=mal, country="ES", value=(70000.0, "EUR", "total"), cpv="18100000")
    award(conn, shared, t, "Textiles Sur SL", winners=2)
    award(conn, shared, w, "Talleres Norte SL", winners=2)
    award(conn, notice(conn, "B-5", buyer=mal, country="ES", value=(5000.0, "EUR", "total"), cpv="18100000"), t, "Textiles Sur SL")
    conn.commit()
    return mal, w, t


def test_a_buyers_top_suppliers_follow_its_cpv_filter_with_the_supplier_pages_sums(conn):
    mal, w, t = _buyer_world(conn)
    c = TestClient(api.app)
    every = c.get(f"/v1/buyers/{mal}/suppliers").json()
    assert [(s["name"], s["awards"]) for s in every["items"]] == [("Talleres Norte SL", 4), ("Textiles Sur SL", 2)]
    assert every["contracts"] == 5 and every["awardsWithSupplier"] == 6 and every["valued"] == 3
    assert every["contractValues"] == [{"currency": "EUR", "amount": 145000.0, "count": 3, "lotEstimates": 0}]
    top = {s["name"]: s["contractValues"] for s in every["items"]}
    profile = c.get(f"/v1/suppliers/{every['items'][0]['slug']}").json()["values"]["byCurrency"]
    assert top["Talleres Norte SL"] == profile == [{"currency": "EUR", "amount": 140000.0, "count": 2, "lotEstimates": 0}]
    clothing = c.get(f"/v1/buyers/{mal}/suppliers", params={"cpv": "181"}).json()
    assert clothing["cpv"] == ["181"]
    assert [(s["name"], s["awards"]) for s in clothing["items"]] == [("Talleres Norte SL", 2), ("Textiles Sur SL", 2)]
    assert clothing["contracts"] == 3 and clothing["contractValues"][0]["amount"] == 45000.0
    assert c.get(f"/v1/buyers/{mal}/suppliers", params={"cpv": "1x"}).status_code == 422


def test_the_market_sums_contract_values_from_the_stored_snapshot(conn):
    mal, w, t = _buyer_world(conn)
    army = org(conn, "estado maior do exercito", "PT")
    award(conn, notice(conn, "PT-1", buyer=army, country="PT", value=(25000.0, "EUR", "total"), cpv="35811000"), t,
          "Textiles Sur SL", "ES")
    conn.commit()
    c = TestClient(api.app)
    assert c.get("/v1/stats/market").json()["money"] is None               # nothing stored yet: no money, no failure
    suppliers.store_value_orders(conn)                                     # the worker's round writes it with the orders
    conn.commit()
    stats.reset_cache()
    m = c.get("/v1/stats/market").json()["money"]
    assert m["total"]["byCurrency"] == [{"currency": "EUR", "amount": 170000.0, "count": 4, "lotEstimates": 0}]
    assert m["total"]["of"] == 7 and m["total"]["withoutValue"] == 3        # the ceiling and the shared value are not summed
    assert [(x["country"], x["byCurrency"][0]["amount"]) for x in m["byCountry"]] == [("ES", 145000.0), ("PT", 25000.0)]
    groups = {g["group"]: g["byCurrency"][0]["amount"] for g in m["byCpvGroup"]}
    assert groups == {"343": 100000.0, "181": 45000.0, "358": 25000.0}
    assert m["byBuyer"][0]["slug"].startswith(f"{mal}-") and m["byBuyer"][0]["byCurrency"][0]["amount"] == 145000.0
    # the sums of each supplier equal its page's
    for x in (w, t):
        page = c.get(f"/v1/suppliers/{x}").json()["values"]["byCurrency"]
        body, _ = money.stored(conn)
        mine = money.totals(body, [i for i, o in enumerate(body["org"]) if o == x])["byCurrency"]
        assert mine == page
    stats.reset_cache()
    pt = c.get("/v1/stats/market", params={"country": "PT"}).json()["money"]
    assert pt["byCountry"] == [{"country": "PT", "byCurrency": [{"currency": "EUR", "amount": 25000.0, "count": 1,
                                                                  "lotEstimates": 0}], "of": 1, "withoutValue": 0}]
    stats.reset_cache()
    assert c.get("/v1/stats/market", params={"cpv": "181"}).json()["money"]["total"]["byCurrency"][0]["amount"] == 45000.0
    # a removal on request drops the snapshot with the other derived tables: no stale money
    suppress.drop_derived(conn)
    conn.commit()
    stats.reset_cache()
    assert c.get("/v1/stats/market").json()["money"] is None


def test_the_worker_round_writes_the_contract_values(conn):
    from dgate.ops import warm_lists

    assert money.MONEY_KEY in [k for _, k, _ in warm_lists.views([])]
    assert "contract-values" in warm_lists.FIRST_VIEWS
