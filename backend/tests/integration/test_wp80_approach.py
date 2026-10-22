"""WP-80, "who to approach": the winners of the demand map across the countries asked (`approach` of POST /v1/readiness/demand)
on a real Postgres: counted across countries, named from K_MIN, a TED+PLACSP twin once, stated values only where a TED result notice
names one winner, the buyers they win from, the prime mark and the EDF projects, the supplier-page link only where a page exists."""

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
    # A Spanish company with two Spanish and one German procurement: below K_MIN in each country, named across them.
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


def test_a_winner_is_named_across_countries_from_k_min_and_the_rest_is_counted(world, post):
    d = post()
    a = d["approach"]
    names = by_name(d)
    assert set(names) == {"Talleres Norte SL", "Rheinmetall Landsysteme GmbH", "Suministros Mera SL"}
    t = names["Talleres Norte SL"]
    assert (t["contracts"], t["countries"], t["country"]) == (3, ["DE", "ES"], "ES")
    assert t["lastAward"] == RECENT.isoformat()
    # neither country names it alone: two awards in Spain, one in Germany
    assert all(w["name"] != "Talleres Norte SL" for c in d["byCountry"] for w in c["topWinners"])
    # the two-procurement company: counted, never named (the twin row's organisation is no winner at all)
    assert a["below"] == {"winners": 1, "awards": 2}
    assert a["more"] == {"winners": 0, "awards": 0}
    assert "Recambios" not in str(a)
    # most contracts first (ties by name)
    assert [w["name"] for w in a["winners"]] == ["Rheinmetall Landsysteme GmbH", "Suministros Mera SL", "Talleres Norte SL"]


def test_a_twin_pair_counts_once_and_only_while_the_preferred_row_is_in_the_answer(world, post, conn):
    d = post()
    assert by_name(d)["Suministros Mera SL"]["contracts"] == 3
    assert d["total"]["winners"] == 4          # talleres, rheinmetall, recambios, mera: the twin's organisation is no winner
    assert d["byCountry"][0]["winners"] == 3   # Spain: talleres, recambios, mera
    # with the PLACSP winners off, the TED row alone is left (one procurement): Mera is not named, and the TED twin stays
    off = post(public=False)
    assert "Suministros Mera SL" not in by_name(off)
    assert off["approach"]["below"]["winners"] == 1   # mera's TED award; talleres has 3 TED+DE awards and is named


def test_no_sum_of_values_per_supplier(world, post):
    # the supplier map's rule: no sum of values per supplier, though Talleres' notices state values
    d = post()
    assert all("values" not in w and "amount" not in str(w) for w in d["approach"]["winners"])
    assert "100000" not in str(d["approach"])


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


def test_the_supplier_page_is_linked_only_where_the_supplier_map_has_one(world, post):
    names = by_name(post())
    # Talleres won a core-scope notice (Directive 2009/81/EC, a defence buyer): its page exists
    assert names["Talleres Norte SL"]["slug"] == f"{world['talleres']}-talleres-norte-sl"
    assert names["Rheinmetall Landsysteme GmbH"]["slug"] is None
    # Mera's core-scope award is under another code: its page exists, so the link is there
    assert names["Suministros Mera SL"]["slug"] == f"{world['twin_ted']}-suministros-mera-sl"


def test_a_prime_is_listed_past_the_end_of_the_list(world, post, monkeypatch):
    monkeypatch.setattr(demand, "APPROACH", 1)
    d = post()
    assert [w["name"] for w in d["approach"]["winners"]] == ["Rheinmetall Landsysteme GmbH"]
    monkeypatch.setattr(demand, "APPROACH", 0)
    d = post()
    assert [w["name"] for w in d["approach"]["winners"]] == ["Rheinmetall Landsysteme GmbH"]
    assert d["approach"]["more"] == {"winners": 2, "awards": 6}


def test_only_the_countries_asked(world, post):
    d = post(countries=("DE",))
    names = by_name(d)
    assert set(names) == {"Rheinmetall Landsysteme GmbH"}
    assert d["approach"]["below"] == {"winners": 1, "awards": 1}
