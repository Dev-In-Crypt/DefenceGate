"""The supplier map end to end against a real Postgres, with a stand-in for the TED search API."""

from __future__ import annotations

import json
import re
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from dgate import api, awards, config, db
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
        rec("50-2026", [("Mueller Bau GmbH", "DEU", "DE111111111")]),
        rec("51-2026", [("Mueller Bau GmbH", "DEU", "DE222222222")]),
        rec("52-2026", [("Mueller Bau GmbH", "DEU", "DE222222222")]),     # the second one again, by its number
    ])
    run(fake)
    orgs = conn.execute("SELECT id, national_reg_no FROM organisation WHERE canonical_name = 'mueller bau' "
                        "ORDER BY id").fetchall()
    assert [o["national_reg_no"] for o in orgs] == ["111111111", "222222222"]
    wins = conn.execute("""SELECT o.national_reg_no, count(*) AS n FROM award a JOIN organisation o
                            ON o.id = a.organisation_id GROUP BY 1 ORDER BY 1""").fetchall()
    assert [(w["national_reg_no"], w["n"]) for w in wins] == [("111111111", 1), ("222222222", 2)]
    review = conn.execute("SELECT proposed_relation, method, status FROM resolution_review").fetchall()
    assert [(r["proposed_relation"], r["method"], r["status"]) for r in review] == [
        ("same_name_other_id", "id_conflict", "open")]                    # nothing merged, a person decides


# ------------------------------------------------------------------------------------ the API

def _slug(client, name_part: str) -> str:
    items = client.get("/v1/suppliers", params={"q": name_part}).json()["items"]
    assert len(items) == 1, items
    return items[0]["slug"]


def test_the_list_filters_and_pages_and_says_what_it_counts(conn, env, client):
    run(scenario(conn))
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
    # nothing the product must not carry: no sum, no share, no rank
    assert not {"valueTotal", "share", "rank", "dependency"} & set(rh)


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


def test_a_notice_outside_the_core_scope_is_not_on_the_map(conn, env, client):
    run(scenario(conn))
    conn.execute("UPDATE opportunity SET sig_legal_basis = FALSE, sig_cpv_military = FALSE WHERE native_id = '4-2026'")
    conn.commit()
    nammo = client.get(f"/v1/suppliers/{_slug(client, 'nammo')}").json()
    assert nammo["noticeCount"] == 1


def test_the_aggregate_publishes_no_group_of_fewer_than_three_suppliers(conn, env, client):
    run(scenario(conn))          # division 35: Rheinmetall, Nammo, Indra (3). Division 33: Nammo (1)
    s = client.get("/v1/suppliers/summary").json()
    assert s["kMin"] == 3 and s["suppliers"] == 3 and s["awards"] == 5 and s["noticesWithSupplier"] == 4
    assert s["skippedNaturalPersons"] == 1 and s["noticesRead"] == 4
    assert [(g["key"], g["suppliers"]) for g in s["byCpv"]] == [("35", 3)]
    assert s["suppressedGroups"] >= 1 and "tenth" in s["coverage"]
    # by country: three countries with one supplier each: none is published
    assert s["byCountry"] == [] and s["cells"] == []
    # the aggregate reveals nothing the groups hide: no supplier name anywhere in it
    assert "Nammo" not in json.dumps(s) and "Rheinmetall" not in json.dumps(s)


def test_three_suppliers_of_one_country_make_a_published_cell(conn, env, client):
    names = ("Alfa Tech GmbH", "Beta Werke GmbH", "Gamma Systems GmbH")
    for i in range(3):
        put_notice(conn, f"{40 + i}-2026")
    run(FakeTed([rec(f"{40 + i}-2026", [(n, "DEU", f"DE10000000{i}")]) for i, n in enumerate(names)]))
    s = client.get("/v1/suppliers/summary").json()
    assert s["cells"] == [{"division": "35", "country": "DE", "suppliers": 3, "awards": 3}]
    assert [(g["key"], g["suppliers"]) for g in s["byCountry"]] == [("DE", 3)]
