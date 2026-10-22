"""WP-80, "who to approach": the winners of the demand map across the countries asked (`approach` of POST /v1/readiness/demand)
on a real Postgres: counted across countries, every legal entity named (WP-81), a TED+PLACSP twin once, the sum of values per currency (WP-81) only where
a notice names this one winner, the buyers they win from, the prime mark and the EDF projects, the supplier-page link only where a page exists."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, demand

pytestmark = pytest.mark.integration

RECENT = date.today() - timedelta(days=30)


def org(conn, name: str, country: str, **extra) -> int:
    cols = ["canonical_name", "country", *extra]
    return conn.execute(f"INSERT INTO organisation ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                        [name, country, *extra.values()]).fetchone()["id"]


def notice(conn, source: str, native: str, *, buyer: int, country: str, buyer_name: str, core: bool = False,
           value: tuple[float, str, str] | None = None, procedure: str | None = None, withheld: bool = False,
           published: date = RECENT, cpv: str = "34330000") -> int:
    amount, currency, kind = value or (None, None, None)
    opp = conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_org_id, buyer_name_raw, country, title_original, published_at,
                                    cpv_codes, is_defence, sig_legal_basis, buyer_class, procedure_identifier, value_amount,
                                    value_currency, value_kind)
           VALUES ((SELECT id FROM source WHERE code = %s), %s, %s, %s, %s, %s, %s, ARRAY[%s], true, %s, 'defence', %s,
                   %s, %s, %s) RETURNING id""",
        (source, native, buyer, buyer_name, country, f"Parts {native}", published, cpv, core, procedure, amount, currency,
         kind)).fetchone()["id"]
    conn.execute("UPDATE opportunity SET buyer_withheld = %s WHERE id = %s", (withheld, opp))
    return opp


def award(conn, opp: int, winner: int, name: str, country: str = "ES", winners: int = 1) -> int:
    return conn.execute(
        """INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice, cpv_main,
                              resolution_method, resolution_confidence)
           VALUES (%s, %s, %s, %s, %s, '34330000', 'exact_name', 1.0) RETURNING id""",
        (opp, winner, country, name, winners)).fetchone()["id"]


@pytest.fixture()
def world(conn):
    mal = org(conn, "jae mando de apoyo logistico", "ES", is_defence_buyer=True)
    baainbw = org(conn, "bundesamt fur ausrustung", "DE", is_defence_buyer=True)
    secret = org(conn, "unidad reservada", "ES")
    w = {}
    # A Spanish company with two Spanish and one German procurement (below the old K_MIN of 3 in each country).
    # Its values: one TED result notice with it as the only winner (counted), one with two winners and one PLACSP estimate (not).
    w["talleres"] = t = org(conn, "talleres norte", "ES")
    award(conn, notice(conn, "ted", "1-2026", buyer=mal, country="ES", buyer_name="JAE MALE", core=True,
                       value=(100000.0, "EUR", "total")), t, "Talleres Norte SL")
    award(conn, notice(conn, "ted", "2-2026", buyer=mal, country="ES", buyer_name="JAE MALE", value=(50000.0, "EUR", "total")),
          t, "Talleres Norte SL", winners=2)
    award(conn, notice(conn, "ted", "DE-1", buyer=baainbw, country="DE", buyer_name="BAAINBw",
                       value=(70000.0, "EUR", None)), t, "Talleres Norte SL")
    # A prime by name, in an EDF project: three procurements, one from a withheld buyer (counted, never named)
    w["rheinmetall"] = r = org(conn, "rheinmetall landsysteme", "DE")
    for n in range(3):
        award(conn, notice(conn, "ted", f"DE-R{n}", buyer=secret if n == 0 else baainbw, country="DE",
                           buyer_name="Unidad reservada" if n == 0 else "BAAINBw", withheld=n == 0), r, "Rheinmetall Landsysteme GmbH", "DE")
    edf = conn.execute("SELECT id FROM programme WHERE code = 'EDF'").fetchone()["id"]
    proj = conn.execute("""INSERT INTO project (source_id, programme_id, native_id, title)
                           VALUES ((SELECT id FROM source WHERE code = 'edf_factsheets'), %s, '2023:X', 'X') RETURNING id""",
                        (edf,)).fetchone()["id"]
    conn.execute("""INSERT INTO participation (project_id, organisation_id, role, resolution_method, resolution_confidence)
                    VALUES (%s, %s, 'participant', 'pic', 1.0)""", (proj, r))
    # A company with two procurements: counted, never named
    w["small"] = s = org(conn, "recambios sur", "ES")
    for n in range(2):
        award(conn, notice(conn, "es_placsp", f"ES-S{n}", buyer=mal, country="ES", buyer_name="JAE MALE"), s, "Recambios Sur SL")
    # One procurement that TED and PLACSP publish under two numbers, won by one company resolved to two organisation rows:
    # `award_twin_set` pairs them, so the PLACSP row's organisation is no winner; the TED row's has three procurements.
    w["twin_ted"] = tt = org(conn, "suministros mera", "ES")
    w["twin_placsp"] = tp = org(conn, "suministros mera 2", "ES")
    keep = award(conn, notice(conn, "ted", "9-2026", buyer=mal, country="ES", buyer_name="JAE MALE"), tt, "Suministros Mera SL")
    for n in range(2):
        award(conn, notice(conn, "es_placsp", f"ES-M{n}", buyer=mal, country="ES", buyer_name="JAE MALE"), tt, "Suministros Mera SL")
    twin = award(conn, notice(conn, "es_placsp", "ES-M9", buyer=mal, country="ES", buyer_name="JAE MALE"), tp, "Suministros Mera")
    # Mera's supplier page exists through a core-scope award under another code, outside this answer
    award(conn, notice(conn, "ted", "8-2026", buyer=mal, country="ES", buyer_name="JAE MALE", core=True, cpv="35000000"), tt,
          "Suministros Mera SL")
    conn.execute("""INSERT INTO award_twin_set (award_id, preferred_id, procedure_method, winner_method)
                    VALUES (%s, %s, 'procedure_id', 'identifier')""", (twin, keep))
    conn.commit()
    return w


@pytest.fixture()
def post(conn, monkeypatch):
    def make(countries=("ES", "DE"), public: bool = True) -> dict:
        monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true" if public else "false")
        config.reset_cache()
        r = TestClient(api.app).post("/v1/readiness/demand", json={"cpv": ["34300000"], "countries": list(countries)})
        assert r.status_code == 200, r.text
        return r.json()
    return make


def by_name(d: dict) -> dict[str, dict]:
    return {w["name"]: w for w in d["approach"]["winners"]}


def test_every_legal_entity_winner_is_named_across_countries(world, post):
    # WP-81 (owner decision of 22 October 2026): the WP-80 rule "named from K_MIN = 3 procurements" is lifted for legal
    # entities; the two-procurement company is named now, and nothing is left as an anonymous count
    d = post()
    a = d["approach"]
    names = by_name(d)
    assert set(names) == {"Talleres Norte SL", "Rheinmetall Landsysteme GmbH", "Suministros Mera SL", "Recambios Sur SL"}
    t = names["Talleres Norte SL"]
    assert (t["contracts"], t["countries"], t["country"]) == (3, ["DE", "ES"], "ES")
    assert t["lastAward"] == RECENT.isoformat()
    # each country names it too now: two awards in Spain, one in Germany
    assert {c["country"]: [w["awards"] for w in c["topWinners"] if w["name"] == "Talleres Norte SL"] for c in d["byCountry"]} == {
        "ES": [2], "DE": [1]}
    assert a["below"] == {"winners": 0, "awards": 0}
    assert a["more"] == {"winners": 0, "awards": 0}
    assert names["Recambios Sur SL"]["contracts"] == 2
    # most contracts first (ties by name); the twin row's organisation is no winner at all
    assert [w["name"] for w in a["winners"]] == ["Rheinmetall Landsysteme GmbH", "Suministros Mera SL", "Talleres Norte SL",
                                                 "Recambios Sur SL"]


def test_a_twin_pair_counts_once_and_only_while_the_preferred_row_is_in_the_answer(world, post, conn):
    d = post()
    assert by_name(d)["Suministros Mera SL"]["contracts"] == 3
    assert d["total"]["winners"] == 4          # talleres, rheinmetall, recambios, mera: the twin's organisation is no winner
    assert d["byCountry"][0]["winners"] == 3   # Spain: talleres, recambios, mera
    # with the PLACSP winners off, the TED row alone is left (one procurement): Mera is not named, and the TED twin stays
    off = post(public=False)
    assert by_name(off)["Suministros Mera SL"]["contracts"] == 1   # mera's TED award alone, named since WP-81
    assert off["approach"]["below"]["winners"] == 0


def test_values_are_summed_only_where_a_notice_names_this_one_winner(world, post):
    # WP-81 (owner decision of 22 October 2026, replacing WP-80's "no sum of values per supplier"): Talleres' TED total
    # of 100,000 is its own; 2-2026 names two winners (shared, attributed to none); DE-1 states no total or lot sum
    t = by_name(post())["Talleres Norte SL"]
    assert t["values"] == {"byCurrency": [{"currency": "EUR", "amount": 100000.0, "count": 1, "lotEstimates": 0}],
                           "of": 3, "withoutValue": 2, "shared": 1}
    assert by_name(post())["Rheinmetall Landsysteme GmbH"]["values"] == {"byCurrency": [], "of": 3, "withoutValue": 3,
                                                                         "shared": 0}


def set_value(conn, native: str, amount: float, currency: str, kind: str | None) -> None:
    conn.execute("UPDATE opportunity SET value_amount = %s, value_currency = %s, value_kind = %s WHERE native_id = %s",
                 (amount, currency, kind, native))
    conn.commit()


def test_values_are_summed_per_currency_never_converted_and_lot_estimates_are_counted_apart(world, post, conn):
    set_value(conn, "DE-R0", 1000.0, "EUR", "total")
    set_value(conn, "DE-R1", 2500.5, "EUR", "lot_sum")
    set_value(conn, "DE-R2", 300.0, "PLN", "total")
    v = by_name(post())["Rheinmetall Landsysteme GmbH"]["values"]
    assert v["byCurrency"] == [{"currency": "EUR", "amount": 3500.5, "count": 2, "lotEstimates": 1},
                               {"currency": "PLN", "amount": 300.0, "count": 1, "lotEstimates": 0}]
    assert (v["of"], v["withoutValue"], v["shared"]) == (3, 0, 0)


def test_a_placeholder_an_estimate_and_a_national_value_are_no_value(world, post, conn):
    set_value(conn, "DE-R0", 1.0, "EUR", "total")              # TED's placeholder
    set_value(conn, "DE-R1", 9000.0, "EUR", "estimated")       # the procedure's estimate, not the award
    set_value(conn, "ES-M0", 8000.0, "EUR", None)              # PLACSP states the call's estimate, with no kind
    d = post()
    assert by_name(d)["Rheinmetall Landsysteme GmbH"]["values"]["byCurrency"] == []
    assert by_name(d)["Suministros Mera SL"]["values"]["byCurrency"] == []


def test_a_twin_pair_is_valued_once(world, post, conn):
    # the TED row of the pair states a value; its PLACSP twin is the same contract and adds nothing
    set_value(conn, "9-2026", 5000.0, "EUR", "total")
    set_value(conn, "ES-M9", 5000.0, "EUR", "total")
    v = by_name(post())["Suministros Mera SL"]["values"]
    assert v["byCurrency"] == [{"currency": "EUR", "amount": 5000.0, "count": 1, "lotEstimates": 0}]
    assert (v["of"], v["withoutValue"]) == (3, 2)
    # the PLACSP twin's awarded amount (without VAT) is preferred over the TED value; still one contract
    conn.execute("UPDATE award SET value_amount = 4200, value_currency = 'EUR' WHERE name_as_stated = 'Suministros Mera'")
    conn.commit()
    v = by_name(post())["Suministros Mera SL"]["values"]
    assert v["byCurrency"] == [{"currency": "EUR", "amount": 4200.0, "count": 1, "lotEstimates": 0}]
    # off: PLACSP is not read, so the TED value stands
    v = by_name(post(public=False))["Suministros Mera SL"]["values"]
    assert v["byCurrency"] == [{"currency": "EUR", "amount": 5000.0, "count": 1, "lotEstimates": 0}]


def test_a_placsp_awarded_amount_counts_for_its_winner_even_with_several_winners_in_the_folder(world, post, conn):
    # WP-81: the amount is per result (lot) naming this one winner, so the notice's count of winners does not void it
    conn.execute("UPDATE award SET value_amount = 900, value_currency = 'EUR', winners_in_notice = 2 "
                 "WHERE opportunity_id = (SELECT id FROM opportunity WHERE native_id = 'ES-S0')")
    conn.commit()
    v = by_name(post())["Recambios Sur SL"]["values"]
    assert v == {"byCurrency": [{"currency": "EUR", "amount": 900.0, "count": 1, "lotEstimates": 0}],
                 "of": 2, "withoutValue": 1, "shared": 0}


def test_a_natural_person_is_never_named_and_never_given_a_sum(world, post, conn):
    mal = conn.execute("SELECT id FROM organisation WHERE canonical_name = 'jae mando de apoyo logistico'").fetchone()["id"]
    p = org(conn, "juan perez garcia", "ES", individual_reason="natural_person")
    for n in range(3):
        award(conn, notice(conn, "ted", f"P-{n}", buyer=mal, country="ES", buyer_name="JAE MALE",
                           value=(777777.0, "EUR", "total")), p, "Juan Perez Garcia")
    conn.commit()
    d = post()
    assert "Perez" not in str(d) and "777777" not in str(d)
    assert d["approach"]["below"]["winners"] == 0 and d["total"]["winners"] == 4   # the person is no winner here at all


def test_a_request_that_matches_too_many_notices_is_refused_without_echoing_it(world, conn, monkeypatch):
    monkeypatch.setattr(demand, "MAX_ROWS", 3)
    monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
    config.reset_cache()
    r = TestClient(api.app).post("/v1/readiness/demand", json={"cpv": ["34330000"], "countries": ["ES", "DE"]})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "too_broad"
    assert "more specific codes" in r.json()["detail"]["message"] and "34330000" not in r.text
    # at the cap itself the answer is served: Germany alone matches 4 notices, more than 3; with the cap at 4 it is served
    monkeypatch.setattr(demand, "MAX_ROWS", 4)
    ok = TestClient(api.app).post("/v1/readiness/demand", json={"cpv": ["34300000"], "countries": ["DE"]})
    assert ok.status_code == 200


def test_buyers_they_win_from_never_name_a_withheld_buyer(world, post):
    names = by_name(post())
    assert [(b["name"], b["country"], b["contracts"]) for b in names["Talleres Norte SL"]["buyers"]] == [
        ("JAE MALE", "ES", 2), ("BAAINBw", "DE", 1)]
    r = names["Rheinmetall Landsysteme GmbH"]
    assert [(b["name"], b["contracts"]) for b in r["buyers"]] == [("BAAINBw", 2)]
    assert "reservada" not in str(post()).lower()


def test_a_prime_is_marked_with_its_source_and_its_edf_projects(world, post):
    names = by_name(post())
    r = names["Rheinmetall Landsysteme GmbH"]
    assert r["prime"]["group"] == "Rheinmetall" and not r["prime"]["jointVenture"]
    assert r["prime"]["sourceUrl"].startswith("https://www.sipri.org/")
    assert r["edfProjects"] == 1
    t = names["Talleres Norte SL"]
    assert t["prime"] is None and t["edfProjects"] == 0 and t["defenceBuyer"] is False


@pytest.mark.parametrize("public", [True, False])
def test_every_named_winner_has_a_supplier_page_with_the_same_count_for_the_same_filters(world, post, public):
    # WP-85 (owner decision of 22 October 2026): the supplier map counts the demand answer's award set (`award_set`).
    # Before, Rheinmetall (no core-scope notice) had no page; now every winner named has one, and the map filtered by the
    # answer's codes and buyer countries gives each the answer's number of contracts, per country too
    d = post(public=public)
    c = TestClient(api.app)
    names = by_name(d)
    assert names["Rheinmetall Landsysteme GmbH"]["slug"] == f"{world['rheinmetall']}-rheinmetall-landsysteme-gmbh"

    def listed(**params) -> dict[str, int]:
        body = c.get("/v1/suppliers", params={"cpv": "34300000", "pageSize": 100, **params}).json()
        return {i["slug"]: i["awardCount"] for i in body["items"]}

    assert listed(buyerCountry="ES,DE") == {w["slug"]: w["contracts"] for w in d["approach"]["winners"]}
    for block in d["byCountry"]:
        assert sorted(listed(buyerCountry=block["country"]).values(), reverse=True) == [w["awards"] for w in block["topWinners"]]
    for w in d["approach"]["winners"]:
        profile = c.get(f"/v1/suppliers/{w['slug']}")
        assert profile.status_code == 200 and profile.json()["name"] == w["name"]
        # a profile counts every notice of the set, outside these codes too: Mera's 8-2026 (CPV 35000000) is one more
        assert profile.json()["noticeCount"] == w["contracts"] + (w["name"] == "Suministros Mera SL")
    # the winners page links the same pages
    page = c.post("/v1/readiness/winners", json={"cpv": ["34300000"], "countries": ["ES", "DE"]}).json()
    assert {w["slug"] for w in page["winners"]} == set(listed(buyerCountry="ES,DE"))


def test_a_twin_pair_is_matched_by_the_codes_of_the_publication_that_stands_for_it(world, post, conn):
    # WP-85: which of two twins stands is decided over the whole award set, never by a filter (`award_set.NOT_TWIN`), so the
    # map and the answer agree. A pair whose TED copy (the one that stands) carries other codes than its PLACSP copy is
    # matched by the TED copy's codes: Mera's 9-2026 moved to 35000000 takes its PLACSP twin ES-M9 out of this answer
    conn.execute("UPDATE opportunity SET cpv_codes = ARRAY['35000000'] WHERE native_id = '9-2026'")
    conn.commit()
    mera = by_name(post())["Suministros Mera SL"]
    assert mera["contracts"] == 2
    listed = TestClient(api.app).get("/v1/suppliers", params={"cpv": "34300000", "buyerCountry": "ES,DE"}).json()["items"]
    assert {i["slug"]: i["awardCount"] for i in listed}[mera["slug"]] == 2


def test_a_prime_is_listed_past_the_end_of_the_list(world, post, monkeypatch):
    monkeypatch.setattr(demand, "APPROACH", 1)
    d = post()
    assert [w["name"] for w in d["approach"]["winners"]] == ["Rheinmetall Landsysteme GmbH"]
    monkeypatch.setattr(demand, "APPROACH", 0)
    d = post()
    assert [w["name"] for w in d["approach"]["winners"]] == ["Rheinmetall Landsysteme GmbH"]
    assert d["approach"]["more"] == {"winners": 3, "awards": 8}   # Mera 3, Talleres 3, Recambios 2 (named since WP-81)


def test_only_the_countries_asked(world, post):
    d = post(countries=("DE",))
    names = by_name(d)
    assert set(names) == {"Rheinmetall Landsysteme GmbH", "Talleres Norte SL"}   # Talleres' one German award: named
    assert d["approach"]["below"] == {"winners": 0, "awards": 0}


def test_every_winner_a_page_at_a_time_in_the_order_of_who_to_approach(world, post, monkeypatch):
    # WP-81: the report's list stops at 30 (and the primes); POST /v1/readiness/winners lists every winner of the answer
    monkeypatch.setattr(demand, "WINNERS_PAGE", 3)
    d = post()
    c = TestClient(api.app)
    first = c.post("/v1/readiness/winners", json={"cpv": ["34300000"], "countries": ["ES", "DE"]}).json()
    second = c.post("/v1/readiness/winners", json={"cpv": ["34300000"], "countries": ["ES", "DE"], "page": 2}).json()
    assert first["total"] == d["total"]["winners"] == 4 and (first["page"], first["pageSize"]) == (1, 3)
    assert [w["name"] for w in first["winners"] + second["winners"]] == [w["name"] for w in d["approach"]["winners"]]
    assert first["winners"][0] == d["approach"]["winners"][0]          # the same entry, values included
    assert c.post("/v1/readiness/winners", json={"cpv": ["34300000"], "page": 0}).status_code == 422
    one = c.post("/v1/readiness/winners", json={"cpv": ["34300000"], "countries": ["DE"]}).json()
    assert {w["name"] for w in one["winners"]} == {"Rheinmetall Landsysteme GmbH", "Talleres Norte SL"}
