"""The supplier map end to end against a real Postgres, with a stand-in for the TED search API."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from dgate import api, award_set, awards, config, db
from dgate import suppliers as suppliers_module
from dgate.normalise import Opportunity
from dgate.rawstore import build_store

pytestmark = pytest.mark.integration

ID_RHEIN = "DE190270455"
ID_NORM = "190270455"


@pytest.fixture
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path
    config.reset_cache()


@pytest.fixture
def client(conn):
    with TestClient(api.app) as c:
        yield c


def put_notice(conn, native_id: str, *, buyer: str = "Bundesamt fuer Ausruestung", country: str = "DE",
               cpv: tuple[str, ...] = ("35400000",), value: float | None = None, kind: str | None = "total",
               published: date = date(2026, 3, 1), subtype: str = "29", legal: bool = True,
               defence: bool = True, title: str = "Radschlepper") -> int:
    opp = Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=title, title_en=title,
        country=country, published_at=published, cpv_codes=list(cpv), status="awarded", is_defence=defence,
        sig_legal_basis=legal, sig_cpv=True, value_amount=value, value_currency="EUR" if value else None,
        value_kind=kind if value else None, notice_subtype=subtype, source_url=f"https://ted.example/{native_id}")
    src_id = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src_id)
    opp_id, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src_id)
    conn.commit()
    return opp_id


def rec(pn: str, tenderers: list[tuple[str, str, str | None]], winners: list[str] | None = None) -> dict:
    won = winners if winners is not None else [t[0] for t in tenderers]
    return {
        "publication-number": pn,
        "winner-name": {"deu": [w for w in won for _ in range(2)]},
        "organisation-name-tenderer": {"deu": [t[0] for t in tenderers]},
        "organisation-country-tenderer": [t[1] for t in tenderers],
        "organisation-identifier-tenderer": [t[2] for t in tenderers] if all(t[2] for t in tenderers) else [],
    }


class FakeTed:
    """The search API's answer to `publication-number IN (...)`, with a log of what was asked."""

    def __init__(self, records: list[dict]):
        self.records = {r["publication-number"]: r for r in records}
        self.asked: list[list[str]] = []

    def client(self) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            numbers = re.search(r"IN \(([^)]*)\)", body["query"]).group(1).split()
            self.asked.append(numbers)
            return httpx.Response(200, json={"notices": [self.records[n] for n in numbers if n in self.records],
                                             "totalNoticeCount": len(numbers)})
        return httpx.Client(transport=httpx.MockTransport(handler))


def run(fake: FakeTed, **kw):
    return awards.run_awards(client=fake.client(), pause=0, sleep=lambda s: None, **kw)


def scenario(conn):
    """Three suppliers across four notices, a person among the winners of one."""
    put_notice(conn, "1-2026", value=1_000_000)
    put_notice(conn, "2-2026", published=date(2026, 4, 1))
    put_notice(conn, "3-2026", cpv=("35100000",), published=date(2025, 5, 1), value=5_000_000)
    put_notice(conn, "4-2026", cpv=("33100000",), published=date(2025, 6, 1))
    return FakeTed([
        rec("1-2026", [("Rheinmetall Landsysteme GmbH", "DEU", ID_RHEIN)]),
        rec("2-2026", [("RHEINMETALL LANDSYSTEME GMBH", "DEU", None), ("Radek Nečas", "CZE", "12345678")]),
        rec("3-2026", [("Nammo Raufoss AS", "NOR", "NO923456789"), ("Indra Sistemas, S.A.", "ESP", "ESA28599033")]),
        rec("4-2026", [("Nammo Raufoss AS", "NOR", "NO923456789")]),
    ])


def test_the_loader_reads_the_winners_resolves_them_and_keeps_no_person(conn, env):
    fake = scenario(conn)
    c = run(fake)
    assert c["candidates"] == 4 and c["fetched"] == 4
    assert c["awards_new"] == 5 and c["skipped_person"] == 1

    # one organisation per supplier, found by the cascade: the second Rheinmetall spelling is the same body
    rows = conn.execute(
        """SELECT o.canonical_name, o.country, o.national_reg_no, count(*) AS wins FROM award a
             JOIN organisation o ON o.id = a.organisation_id GROUP BY 1, 2, 3 ORDER BY 1""").fetchall()
    assert [(r["canonical_name"], r["country"], r["wins"]) for r in rows] == [
        ("indra sistemas", "ES", 1), ("nammo raufoss", "NO", 2), ("rheinmetall landsysteme", "DE", 2)]
    assert {r["canonical_name"]: r["national_reg_no"] for r in rows}["rheinmetall landsysteme"] == ID_NORM

    # the person: no award, no organisation, no alias, not in the raw store
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE canonical_name LIKE %s",
                        ("%necas%",)).fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM organisation_alias WHERE normalised_name LIKE %s",
                        ("%necas%",)).fetchone()["n"] == 0
    store = build_store()
    keys = [r["raw_key"] for r in conn.execute("SELECT raw_key FROM award_notice").fetchall()]
    landed = json.dumps([store.get(k) for k in keys if k], ensure_ascii=False)
    assert "Nečas" not in landed and "12345678" not in landed and "Rheinmetall Landsysteme GmbH" in landed
    notice = conn.execute("""SELECT n.* FROM award_notice n JOIN opportunity o ON o.id = n.opportunity_id
                              WHERE o.native_id = '2-2026'""").fetchone()
    assert (notice["winners_seen"], notice["winners_kept"], notice["skipped_person"]) == (2, 1, 1)
    assert conn.execute("SELECT count(*) AS n FROM raw_ingest r JOIN source s ON s.id = r.source_id "
                        "WHERE s.code = 'ted_awards'").fetchone()["n"] == 4


def test_a_second_run_asks_about_nothing_and_writes_nothing(conn, env):
    fake = scenario(conn)
    run(fake)
    before = {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"]
              for t in ("award", "award_notice", "organisation", "organisation_alias", "raw_ingest",
                        "resolution_review")}
    asked = len(fake.asked)
    again = run(fake)
    assert again["candidates"] == 0 and len(fake.asked) == asked
    after = {t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in before}
    assert after == before


def test_only_result_notices_of_the_core_scope_are_asked_for(conn, env):
    put_notice(conn, "10-2026")
    put_notice(conn, "11-2026", subtype="16")                      # a contract notice: no winner
    put_notice(conn, "12-2026", defence=False, legal=False)        # not defence at all
    put_notice(conn, "13-2026", published=date(2022, 6, 1))        # before eForms named winners
    fake = FakeTed([rec(f"{n}-2026", [("Acme GmbH", "DEU", "DE111222333")]) for n in (10, 11, 12, 13)])
    c = run(fake)
    assert c["candidates"] == 1 and fake.asked == [["10-2026"]]


def test_a_notice_that_names_no_winner_is_marked_read_and_not_asked_again(conn, env):
    put_notice(conn, "20-2026")
    fake = FakeTed([{"publication-number": "20-2026", "organisation-name-tenderer": {"deu": ["X GmbH"]}}])
    c = run(fake)
    assert c["notices_no_winner_data"] == 1 and c["awards_new"] == 0
    assert conn.execute("SELECT status FROM award_notice").fetchone()["status"] == "no_winner_data"
    assert run(fake)["candidates"] == 0


def test_a_notice_ted_does_not_return_is_asked_again_next_time(conn, env):
    put_notice(conn, "30-2026")
    c = run(FakeTed([]))
    assert c["not_returned"] == 1
    assert conn.execute("SELECT count(*) AS n FROM award_notice").fetchone()["n"] == 0
    assert run(FakeTed([rec("30-2026", [("Acme GmbH", "DEU", "DE111222333")])]))["awards_new"] == 1


def test_two_companies_of_one_name_with_different_numbers_are_two_suppliers(conn, env):
    for n in (50, 51, 52):
        put_notice(conn, f"{n}-2026")
    fake = FakeTed([
        rec("50-2026", [("Mueller Bau GmbH", "DEU", "DE123456789")]),
        rec("51-2026", [("Mueller Bau GmbH", "DEU", "DE987654321")]),
        rec("52-2026", [("Mueller Bau GmbH", "DEU", "DE987654321")]),     # the second one again, by its number
    ])
    run(fake)
    orgs = conn.execute("SELECT id, national_reg_no FROM organisation WHERE canonical_name = 'mueller bau' "
                        "ORDER BY id").fetchall()
    assert [o["national_reg_no"] for o in orgs] == ["123456789", "987654321"]
    wins = conn.execute("""SELECT o.national_reg_no, count(*) AS n FROM award a JOIN organisation o
                            ON o.id = a.organisation_id GROUP BY 1 ORDER BY 1""").fetchall()
    assert [(w["national_reg_no"], w["n"]) for w in wins] == [("123456789", 1), ("987654321", 2)]
    review = conn.execute("SELECT proposed_relation, method, status FROM resolution_review").fetchall()
    assert [(r["proposed_relation"], r["method"], r["status"]) for r in review] == [
        ("same_name_other_id", "id_conflict", "open")]                    # nothing merged, a person decides


# ------------------------------------------------------------------------------------ the API

def _slug(client, name_part: str) -> str:
    items = client.get("/v1/suppliers", params={"q": name_part}).json()["items"]
    assert len(items) == 1, items
    return items[0]["slug"]


def test_the_list_filters_and_pages_and_says_what_it_counts(conn, env, client, monkeypatch):
    run(scenario(conn))
    # WP-81: K_MIN is 1, so a filter lists every supplier it selects (tests/integration/test_wp39.py); the filters
    # themselves are tested here
    assert suppliers_module.K_MIN == 1
    body = client.get("/v1/suppliers").json()
    assert body["total"] == 3 and body["page"] == 1
    assert [(i["name"], i["country"], i["awardCount"]) for i in body["items"]] == [
        ("Nammo Raufoss AS", "NO", 2), ("Rheinmetall Landsysteme GmbH", "DE", 2),
        ("Indra Sistemas, S.A.", "ES", 1)]
    assert body["items"][0]["slug"].split("-")[0].isdigit() and body["items"][0]["cpvDivisions"] == ["33", "35"]
    assert {i["country"] for i in client.get("/v1/suppliers", params={"country": "NO,ES"}).json()["items"]} == {"NO", "ES"}
    assert [i["name"] for i in client.get("/v1/suppliers", params={"q": "landsysteme"}).json()["items"]] == [
        "Rheinmetall Landsysteme GmbH"]
    by_cpv = client.get("/v1/suppliers", params={"cpv": "331"}).json()
    assert [i["name"] for i in by_cpv["items"]] == ["Nammo Raufoss AS"]
    page2 = client.get("/v1/suppliers", params={"pageSize": 2, "page": 2}).json()
    assert page2["total"] == 3 and len(page2["items"]) == 1
    assert client.get("/v1/suppliers", params={"sort": "bogus"}).status_code == 422
    assert client.get("/v1/suppliers", params={"cpv": ",".join(["35"] * 21)}).status_code == 422


def test_the_cpv_filter_reads_every_code_of_a_notice_and_the_buyer_country_is_its_own_filter(conn, env, client):
    # WP-85: as the demand answer, a CPV filter matches any code of the notice (an 8-digit code stands for its level:
    # 34300000 is the group 343), and the buyer's country is a filter beside the supplier's
    put_notice(conn, "90-2026", cpv=("35400000", "34330000"), country="ES", buyer="Jefatura de Apoyo Logistico")
    put_notice(conn, "91-2026", cpv=("35400000",))
    run(FakeTed([rec("90-2026", [("Nammo Raufoss AS", "NOR", "NO923456789")]),
                 rec("91-2026", [("Nammo Raufoss AS", "NOR", "NO923456789"), ("Indra Sistemas, S.A.", "ESP", "ESA28599033")])]))

    def names(**params) -> list[tuple[str, int]]:
        return [(i["name"], i["awardCount"]) for i in client.get("/v1/suppliers", params=params).json()["items"]]

    assert names(cpv="34300000") == names(cpv="343") == [("Nammo Raufoss AS", 1)]      # 34330000 is not the main code
    assert names(cpv="34330000") == [("Nammo Raufoss AS", 1)]
    assert names(buyerCountry="ES") == [("Nammo Raufoss AS", 1)]
    assert names(buyerCountry="Germany") == [("Indra Sistemas, S.A.", 1), ("Nammo Raufoss AS", 1)]
    assert names(country="ES") == [("Indra Sistemas, S.A.", 1)]                          # the supplier's country
    assert names(country="ES", buyerCountry="ES") == []
    assert client.get("/v1/suppliers", params={"buyerCountry": "Atlantis"}).status_code == 422
    assert client.get("/v1/suppliers", params={"cpv": "3a"}).status_code == 422
    s = client.get("/v1/suppliers/summary").json()
    # the summary's groups read every code too: Nammo's win under 34 is in division 34, and in 35 as well
    assert [(g["key"], g["suppliers"], g["awards"]) for g in s["byCpv"]] == [("35", 2, 3), ("34", 1, 1)]
    assert s["awards"] == 3 and s["noticesWithSupplier"] == 2


def test_a_profile_states_the_notices_and_shows_a_value_only_where_one_supplier_won(conn, env, client):
    run(scenario(conn))
    rh = client.get(f"/v1/suppliers/{_slug(client, 'landsysteme')}").json()
    assert rh["name"] == "Rheinmetall Landsysteme GmbH" and rh["country"] == "DE" and rh["noticeCount"] == 2
    assert [y["year"] for y in rh["byYear"]] == [2026] and rh["byYear"][0]["awards"] == 2
    assert rh["byCpv"] == [{"year": None, "division": "35", "awards": 2}]
    assert rh["identifiers"] == [ID_RHEIN] and rh["buyers"][0]["awards"] == 2
    values = {n["noticeId"]: n["valueAmount"] for n in rh["notices"]}
    assert values == {"1-2026": 1_000_000.0, "2-2026": None}        # 2-2026 had a second winner, a person
    assert {n["noticeId"]: n["winnersInNotice"] for n in rh["notices"]}["2-2026"] == 2
    assert rh["notices"][0]["sourceUrl"].startswith("https://ted.example/")

    indra = client.get(f"/v1/suppliers/{_slug(client, 'indra')}").json()
    assert indra["notices"][0]["valueAmount"] is None               # 3-2026 had two winners: no value for either
    assert "TED" in indra["attribution"]
    # WP-81 (owner decision of 22 October 2026): the sum of values per currency, only from a notice naming this one
    # winner; 2-2026 names a person beside it, so its value would be shared, and is counted as such
    assert rh["values"] == {"byCurrency": [{"currency": "EUR", "amount": 1_000_000.0, "count": 1, "lotEstimates": 0}],
                            "of": 2, "withoutValue": 1, "shared": 1}
    # Indra's one notice states 5,000,000 for two winners: attributed to neither, no sum
    assert indra["values"] == {"byCurrency": [], "of": 1, "withoutValue": 1, "shared": 1}
    # still nothing the product must not carry: no share, no rank, no dependency score
    assert not {"share", "rank", "dependency"} & set(rh)


def test_a_profile_sums_values_per_currency_beyond_the_listed_notices_and_without_removed_ones(conn, env, client):
    # WP-81: per currency, never converted; a sum of lot estimates counted apart; a placeholder and an estimate are no
    # value; a notice removed on request is out of the sum as of every count; the sum covers every notice, not the 50 listed
    rows = [("70-2026", 1000.0, "EUR", "total"), ("71-2026", 2000.0, "EUR", "lot_sum"), ("72-2026", 500.0, "PLN", "total"),
            ("73-2026", 1.0, "EUR", "total"), ("74-2026", 9000.0, "EUR", "estimated"), ("75-2026", 4000.0, "EUR", "total")]
    for pn, *_ in rows:
        put_notice(conn, pn)
    for n in range(suppliers_module.PROFILE_NOTICES):
        put_notice(conn, f"8{n:02d}-2026", published=date(2026, 5, 1))
    for pn, amount, currency, kind in rows:
        conn.execute("UPDATE opportunity SET value_amount = %s, value_currency = %s, value_kind = %s WHERE native_id = %s",
                     (amount, currency, kind, pn))
    conn.commit()
    pns = [r[0] for r in rows] + [f"8{n:02d}-2026" for n in range(suppliers_module.PROFILE_NOTICES)]
    run(FakeTed([rec(pn, [("Rheinmetall Landsysteme GmbH", "DEU", ID_RHEIN)]) for pn in pns]))
    conn.execute("UPDATE opportunity SET suppressed = TRUE WHERE native_id = '75-2026'")
    conn.commit()
    rh = client.get(f"/v1/suppliers/{_slug(client, 'landsysteme')}").json()
    assert rh["noticeCount"] == 5 + suppliers_module.PROFILE_NOTICES
    assert all(n["noticeId"] not in {"70-2026", "71-2026", "72-2026"} for n in rh["notices"])   # older than the 50 listed
    assert rh["values"] == {"byCurrency": [{"currency": "EUR", "amount": 3000.0, "count": 2, "lotEstimates": 1},
                                           {"currency": "PLN", "amount": 500.0, "count": 1, "lotEstimates": 0}],
                            "of": rh["noticeCount"], "withoutValue": rh["noticeCount"] - 3, "shared": 0}


def test_one_registration_number_written_two_ways_is_shown_once(conn, env, client):
    put_notice(conn, "60-2026")
    put_notice(conn, "61-2026")
    run(FakeTed([rec("60-2026", [("Rheinmetall Landsysteme GmbH", "DEU", "DE190270455")]),
                 rec("61-2026", [("Rheinmetall Landsysteme GmbH", "DEU", "DE 190 270 455")])]))
    prof = client.get(f"/v1/suppliers/{_slug(client, 'landsysteme')}").json()
    assert prof["noticeCount"] == 2 and len(prof["identifiers"]) == 1


def test_an_unknown_or_malformed_supplier_is_a_404_and_a_removed_one_is_gone(conn, env, client):
    run(scenario(conn))
    assert client.get("/v1/suppliers/999999-nobody").status_code == 404
    assert client.get("/v1/suppliers/not-a-slug").status_code == 404
    slug = _slug(client, "nammo")
    org_id = int(slug.split("-")[0])
    conn.execute("UPDATE organisation SET suppressed = TRUE WHERE id = %s", (org_id,))
    conn.commit()
    assert client.get(f"/v1/suppliers/{slug}").status_code == 410
    assert "Nammo Raufoss AS" not in [i["name"] for i in client.get("/v1/suppliers").json()["items"]]


def test_a_notice_removed_on_request_leaves_the_profile(conn, env, client):
    run(scenario(conn))
    slug = _slug(client, "nammo")
    conn.execute("UPDATE opportunity SET suppressed = TRUE WHERE native_id = '4-2026'")
    conn.commit()
    prof = client.get(f"/v1/suppliers/{slug}").json()
    assert [n["noticeId"] for n in prof["notices"]] == ["3-2026"] and prof["noticeCount"] == 1


def test_a_defence_scope_notice_outside_the_core_scope_is_on_the_map_and_a_civil_one_is_not(conn, env, client):
    # WP-85 (owner decision of 22 October 2026): the map counts the demand answer's award set, the whole defence scope
    # (`is_defence`), not only its core; a notice outside the defence scope stays off it
    run(scenario(conn))
    conn.execute("UPDATE opportunity SET sig_legal_basis = FALSE, sig_cpv_military = FALSE WHERE native_id = '4-2026'")
    conn.commit()
    slug = _slug(client, "nammo")
    assert client.get(f"/v1/suppliers/{slug}").json()["noticeCount"] == 2
    conn.execute("UPDATE opportunity SET is_defence = FALSE WHERE native_id = '4-2026'")
    conn.commit()
    assert client.get(f"/v1/suppliers/{slug}").json()["noticeCount"] == 1


def test_the_map_counts_the_last_three_years(conn, env, client):
    # WP-85: the window is the demand answer's, three years back from today (`award_set.since`), not "from 2023"
    run(scenario(conn))
    old = award_set.since() - timedelta(days=1)
    conn.execute("UPDATE opportunity SET published_at = %s WHERE native_id = '4-2026'", (old,))
    conn.commit()
    slug = _slug(client, "nammo")
    assert client.get(f"/v1/suppliers/{slug}").json()["noticeCount"] == 1
    assert client.get("/v1/suppliers/summary").json()["since"] == award_set.since().isoformat()


def test_the_aggregate_publishes_every_group_of_legal_entities_however_small(conn, env, client):
    # WP-81 (owner decision of 22 October 2026): the rule "no group of fewer than three suppliers" is lifted for legal
    # entities; the person among the winners of 2-2026 is still only counted
    run(scenario(conn))          # division 35: Rheinmetall, Nammo, Indra (3). Division 33: Nammo (1)
    s = client.get("/v1/suppliers/summary").json()
    assert s["kMin"] == 1 and s["suppliers"] == 3 and s["awards"] == 5 and s["noticesWithSupplier"] == 4
    assert s["skippedNaturalPersons"] == 1 and s["noticesRead"] == 4
    assert [(g["key"], g["suppliers"]) for g in s["byCpv"]] == [("35", 3), ("33", 1)]
    assert s["suppressedGroups"] == 0 and "tenth" in s["coverage"]
    # by country: three countries with one supplier each: all published now
    assert sorted((g["key"], g["suppliers"]) for g in s["byCountry"]) == [("DE", 1), ("ES", 1), ("NO", 1)]
    assert sorted((c["division"], c["country"], c["suppliers"]) for c in s["cells"]) == [
        ("33", "NO", 1), ("35", "DE", 1), ("35", "ES", 1), ("35", "NO", 1)]
    assert "Radek" not in json.dumps(s)
    # the aggregate reveals nothing the groups hide: no supplier name anywhere in it
    assert "Nammo" not in json.dumps(s) and "Rheinmetall" not in json.dumps(s)


def test_three_suppliers_of_one_country_make_a_published_cell(conn, env, client):
    names = ("Alfa Tech GmbH", "Beta Werke GmbH", "Gamma Systems GmbH")
    for i in range(3):
        put_notice(conn, f"{40 + i}-2026")
    run(FakeTed([rec(f"{40 + i}-2026", [(n, "DEU", f"DE12345678{i}")]) for i, n in enumerate(names)]))
    s = client.get("/v1/suppliers/summary").json()
    assert s["cells"] == [{"division": "35", "country": "DE", "suppliers": 3, "awards": 3}]
    assert [(g["key"], g["suppliers"]) for g in s["byCountry"]] == [("DE", 3)]
