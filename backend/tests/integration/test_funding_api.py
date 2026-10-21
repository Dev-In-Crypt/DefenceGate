"""The funding hub's API: the contract of docs/design/API_CONTRACT.md.

Each test is one decision the owner took on 12 October 2026, or one way the design's
own assumptions would have misled a reader of the data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db
from dgate.funding import make_slug, programme_of
from dgate.normalise import Call

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _put(conn, native_id: str, *, programme: str = "HORIZON", source: str = "eu_portal",
         days: int | None = 20, status: str = "open", budget: float | None = None,
         currency: str | None = None, country: str | None = None, title: str | None = None,
         regime: str = "defence", opens: date | None = None, conditions: dict | None = None,
         issuer: str | None = None, eligibility_text: str | None = None) -> None:
    call = Call(
        programme_code=programme, native_id=native_id, title=title or f"Call {native_id}",
        topic_code=f"{programme}-{native_id}",
        deadline_at=(NOW + timedelta(days=days)) if days is not None else None,
        status=status, regime=regime, budget=budget, currency=currency,
        budget_scope="call" if budget is not None else None, country=country, issuer=issuer,
        opens_at=opens, conditions_raw=conditions, eligibility_text=eligibility_text)
    db.upsert_call(conn, call, f"hash-{programme}-{native_id}", db.source_id(conn, source))
    conn.commit()


def _ids(client, **params) -> list[str]:
    body = client.get("/v1/funding", params={"status": "all", **params}).json()
    return [c["topicId"].rsplit("-", 1)[1] for c in body["items"]]


def test_a_page_has_a_total_so_a_reader_can_count_what_it_did_not_show(client, conn):
    for n in range(5):
        _put(conn, f"c{n}", days=10 + n)
    body = client.get("/v1/funding", params={"status": "all", "pageSize": 2, "page": 2}).json()
    assert (body["total"], body["page"], body["pageSize"]) == (5, 2, 2)
    assert [c["topicId"] for c in body["items"]] == ["HORIZON-c2", "HORIZON-c3"]


def test_a_call_that_has_not_opened_is_forthcoming_not_open(client, conn):
    _put(conn, "now", status="open")
    _put(conn, "later", status="forthcoming", opens=date.today() + timedelta(days=5))
    assert _ids(client, status="open") == ["now"]
    assert _ids(client, status="forthcoming") == ["later"]
    later = client.get("/v1/funding", params={"status": "forthcoming"}).json()["items"][0]
    assert later["status"] == "forthcoming" and later["openingDate"].startswith(
        (date.today() + timedelta(days=5)).isoformat())


def test_an_open_call_whose_deadline_has_passed_is_closed_when_served(client, conn):
    _put(conn, "lapsed", status="open", days=-2)
    assert _ids(client, status="open") == []
    assert _ids(client, status="closed") == ["lapsed"]


def test_a_rolling_call_past_its_cut_off_is_open_and_says_it_is_rolling(client, conn):
    """HORIZON-EIC-2026-STEP style: the stored deadline is the latest cut-off, the
    portal still says Open. The site words it as rolling submission, not as closed."""
    _put(conn, "rolling", status="open", days=-2, conditions={"deadline_model": "multiple cut-off"})
    _put(conn, "single", status="open", days=20, conditions={"deadline_model": "single-stage"})
    by_id = {c["topicId"]: c for c in client.get(
        "/v1/funding", params={"status": "all"}).json()["items"]}
    assert by_id["HORIZON-rolling"]["status"] == "open" and by_id["HORIZON-rolling"]["rolling"] is True
    assert by_id["HORIZON-single"]["rolling"] is False


def test_closing_soon_is_open_with_a_deadline_within_thirty_days(client, conn):
    _put(conn, "soon", days=5)
    _put(conn, "far", days=90)
    _put(conn, "standing", days=None)
    assert _ids(client, status="closing-soon") == ["soon"]


def test_a_call_with_no_deadline_has_null_and_sorts_after_those_with_one(client, conn):
    _put(conn, "standing", days=None, source="fr_aid", programme="FR-AID", country="FR")
    _put(conn, "dated", days=60)
    body = client.get("/v1/funding", params={"status": "open"}).json()["items"]
    assert [c["topicId"] for c in body] == ["HORIZON-dated", "FR-AID-standing"]
    assert body[1]["deadline"] is None


def test_a_budget_range_compares_one_currency_and_never_converts(client, conn):
    _put(conn, "eur", budget=5_000_000, currency="EUR")
    _put(conn, "pln", programme="PL-NCBR", source="pl_ncbr", country="PL", budget=350_000_000,
         currency="PLN")
    _put(conn, "none")
    assert _ids(client, min="1000000") == ["eur"]                       # EUR is the default
    assert _ids(client, min="1000000", currency="PLN") == ["pln"]
    assert _ids(client, max="1000000") == []                            # 350 million PLN is not EUR


def test_budget_order_puts_the_chosen_currency_first_and_never_mixes_amounts(client, conn):
    _put(conn, "small_eur", budget=1_000_000, currency="EUR", days=30)
    _put(conn, "big_pln", programme="PL-NCBR", source="pl_ncbr", country="PL",
         budget=900_000_000, currency="PLN", days=10)
    _put(conn, "big_eur", budget=9_000_000, currency="EUR", days=40)
    assert _ids(client, sort="budget-desc") == ["big_eur", "small_eur", "big_pln"]
    assert _ids(client, sort="budget-desc", currency="PLN")[0] == "big_pln"


def test_budget_order_keeps_each_other_currency_in_amount_order_and_puts_no_budget_last(client, conn):
    """UX audit T24 (F-06): amounts in other currencies used to rank as "no budget" and came out in deadline order."""
    _put(conn, "nobudget", days=5)
    _put(conn, "pln_small", programme="PL-NCBR", source="pl_ncbr", country="PL", budget=15_000_000, currency="PLN", days=1)
    _put(conn, "sek_big", programme="SE-VINNOVA", source="se_vinnova", country="SE", budget=90_000_000, currency="SEK", days=2)
    _put(conn, "pln_big", programme="PL-NCBR", source="pl_ncbr", country="PL", budget=350_000_000, currency="PLN", days=30)
    _put(conn, "sek_small", programme="SE-VINNOVA", source="se_vinnova", country="SE", budget=20_000_000, currency="SEK", days=3)
    _put(conn, "eur", budget=1_000, currency="EUR", days=60)
    assert _ids(client, sort="budget-desc") == ["eur", "pln_big", "pln_small", "sek_big", "sek_small", "nobudget"]
    # a currency in the request selects the calls that state a budget in it
    assert _ids(client, sort="budget-desc", currency="SEK") == ["sek_big", "sek_small"]


def test_a_national_call_is_national_and_eu_is_the_funder_when_there_is_no_country(client, conn):
    _put(conn, "eu")
    _put(conn, "es", programme="ES-BDNS", source="es_bdns", country="ES",
         issuer="MINISTERIO DE CIENCIA", title="Resolución de 11 de junio")
    by_id = {c["topicId"]: c for c in client.get(
        "/v1/funding", params={"status": "all"}).json()["items"]}
    assert (by_id["HORIZON-eu"]["programme"], by_id["HORIZON-eu"]["funderCountry"]) == ("HORIZON", "EU")
    es = by_id["ES-BDNS-es"]
    assert (es["programme"], es["funderCountry"], es["issuer"]) == ("NATIONAL", "ES", "MINISTERIO DE CIENCIA")
    assert (es["titleLanguage"], es["originalTitle"]) == ("es", None)
    assert _ids(client, programme="NATIONAL") == ["es"]
    assert _ids(client, country="EU") == ["eu"]
    assert programme_of("EDIDP") == "EDF" and programme_of("FI-MATINE") == "NATIONAL"


def test_vinnova_gives_the_english_heading_and_keeps_the_swedish_title_beneath(client, conn):
    _put(conn, "r1", programme="SE-VINNOVA", source="se_vinnova", country="SE",
         title="Strengthened ecosystem for civil-military innovation collaboration",
         conditions={"title_sv": "Stärkt ekosystem för civil-militär innovationssamverkan"})
    item = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]
    assert (item["title"], item["titleLanguage"]) == (
        "Strengthened ecosystem for civil-military innovation collaboration", "en")
    assert (item["originalTitle"], item["originalLanguage"]) == (
        "Stärkt ekosystem för civil-militär innovationssamverkan", "sv")


def test_the_detail_is_found_by_its_leading_number_so_a_new_title_keeps_the_link(client, conn):
    _put(conn, "a", title="Original wording")
    listed = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]
    assert listed["slug"] == make_slug(int(listed["id"]), "Original wording")
    assert client.get(f"/v1/funding/{listed['id']}-some-older-words").json()["id"] == listed["id"]
    assert client.get("/v1/funding/999999-nothing").status_code == 404
    assert client.get("/v1/funding/not-a-number").status_code == 404
    assert {s["slug"] for s in client.get("/v1/funding/slugs").json()} == {listed["slug"]}


def test_eligibility_is_structured_rows_and_the_source_text_only_where_it_is_the_sources(
        client, conn):
    _put(conn, "eu", conditions={"expected_grants": 2, "min_contribution": 1_000_000,
                                 "max_contribution": 3_000_000, "for_smes": True,
                                 "deadline_model": "single-stage"},
         eligibility_text="General conditions 1. Admissibility conditions ...")
    _put(conn, "pl", programme="PL-NCBR", source="pl_ncbr", country="PL",
         conditions={"applicant_types": ["large_enterprise", "sme"]},
         eligibility_text="Applicants: large enterprise, sme.")
    by_id = {c["topicId"]: c for c in client.get(
        "/v1/funding", params={"status": "all"}).json()["items"]}
    rows = {r["label"]: r["value"] for r in by_id["HORIZON-eu"]["eligibility"]}
    assert rows == {"Expected number of grants": "2",
                    "Contribution per grant": "EUR 1,000,000 to EUR 3,000,000",
                    "SME-focused": "Yes", "Deadline model": "Single-stage"}
    assert {r["label"]: r["value"] for r in by_id["PL-NCBR-pl"]["eligibility"]} == \
        {"Applicants": "Large enterprise, SME"}
    detail = {t: client.get(f"/v1/funding/{c['slug']}").json() for t, c in by_id.items()}
    assert detail["HORIZON-eu"]["conditionsText"].startswith("General conditions")
    assert detail["PL-NCBR-pl"]["conditionsText"] is None      # assembled by us, not the source's


@pytest.mark.parametrize("flag", [None, False])
def test_a_source_text_is_withdrawn_when_its_licence_row_stops_saying_commercial_ok(
        client, conn, flag):
    """`commercial_ok` is data the owner controls; it must be read, not decorative."""
    _put(conn, "eu", eligibility_text="General conditions 1. Admissibility conditions ...")
    slug = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]["slug"]
    assert client.get(f"/v1/funding/{slug}").json()["conditionsText"]
    try:
        conn.execute("UPDATE source SET commercial_ok = %s WHERE code = 'eu_portal'", (flag,))
        conn.commit()
        assert client.get(f"/v1/funding/{slug}").json()["conditionsText"] is None
    finally:
        conn.execute("UPDATE source SET commercial_ok = TRUE WHERE code = 'eu_portal'")
        conn.commit()


def test_every_fact_carries_its_source_licence_and_retrieval_time(client, conn):
    _put(conn, "a")
    source = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]["source"]
    assert source["sourceId"] == "eu_portal"
    assert source["licence"] and source["attribution"] and source["retrievedAt"]


def test_search_matches_title_and_identifier_and_not_a_wildcard(client, conn):
    _put(conn, "drone", title="Counter-drone systems")
    _put(conn, "other", title="Biodiversity")
    assert _ids(client, q="drone") == ["drone"]
    assert _ids(client, q="HORIZON-oth") == ["other"]
    assert _ids(client, q="%") == []


def test_sources_report_a_floor_relative_coverage_and_never_a_made_up_one(client, conn):
    body = client.get("/v1/sources").json()
    by_id = {s["id"]: s for s in body["sources"]}
    assert by_id["eu_portal"]["type"] == "grants" and by_id["ted"]["type"] == "tenders"
    assert by_id["eu_portal"]["status"] == "never" and by_id["eu_portal"]["coverage"] is None


def test_a_project_start_that_is_one_day_is_not_written_as_a_range(client, conn):
    _put(conn, "v", programme="SE-VINNOVA", source="se_vinnova", country="SE",
         conditions={"project_start_earliest": "2026-11-20T00:00:00",
                     "project_start_latest": "2026-11-20T00:00:00"})
    rows = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]["eligibility"]
    assert {"label": "Project start", "value": "2026-11-20"} in rows


# ------------------------------------------- unknown filter values (audit M11, 14 October 2026)

def test_an_unknown_programme_or_regime_is_a_422_not_every_call(client, conn):
    _put(conn, "a")
    for params in ({"programme": "FOO"}, {"programme": "EDF,NOPE"}, {"regime": "defense"},
                   {"regime": "defence,other"}):
        r = client.get("/v1/funding", params={"status": "all", **params})
        assert r.status_code == 422, params
        assert "unknown value" in r.json()["detail"][0]["msg"]


def test_known_values_are_accepted_in_any_case(client, conn):
    _put(conn, "d", regime="defence")
    _put(conn, "u", regime="dual_use", days=21)
    assert _ids(client, programme="horizon") == ["d", "u"]
    assert _ids(client, regime="Dual-Use") == ["u"]
    assert _ids(client, regime="dual_use") == ["u"]


def test_a_programme_the_label_table_does_not_know_is_found_by_the_chip_it_is_labelled_with(client, conn):
    """The one CEF call was shown as HORIZON and never returned by programme=HORIZON: the
    label and the filter now read the same table, and CEF has a chip of its own."""
    _put(conn, "cef", programme="CEF2027", regime="dual_use")
    assert programme_of("CEF2027") == "CEF"
    assert _ids(client, programme="CEF") == ["cef"]
    assert _ids(client, programme="HORIZON") == []
    item = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]
    assert item["programme"] == "CEF"
    # A stored programme the table has no entry for is labelled HORIZON and filtered as HORIZON.
    conn.execute("INSERT INTO programme (code, name) VALUES ('NEWPROG', 'A new programme') "
                 "ON CONFLICT (code) DO NOTHING")
    conn.commit()
    _put(conn, "new", programme="NEWPROG")
    assert programme_of("NEWPROG") == "HORIZON"
    assert _ids(client, programme="HORIZON") == ["new"]


def test_the_call_page_serves_the_verified_facts_read_from_its_call_document(client, conn):
    from psycopg.types.json import Jsonb

    url = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/call-fiche_demo_en.pdf"
    _put(conn, "elig", conditions={"documents": [{"label": "Call document", "url": url}]})
    fields = {
        "consortium_required": {"value": True, "confidence": 1.0, "quote": "Minimum 3 applicants.",
                                "note": None, "verified": True},
        "sme_only": {"value": False, "confidence": 0.9, "quote": "Open to all legal entities.",
                     "note": "SMEs get a bonus.", "verified": True},
        "min_entities": {"value": 3, "confidence": 0.3, "quote": "made up", "note": None, "verified": False},
        "eligible_countries": {"value": None, "confidence": 0, "quote": None, "note": None, "verified": False},
    }
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES (%s, 'x', 1, 1, 'x')", (url,))
    conn.execute("INSERT INTO call_eligibility (url, fields, model, prompt_version, input_tokens, output_tokens, cost_usd)"
                 " VALUES (%s, %s, 'm', 3, 1, 1, 0)", (url, Jsonb(fields)))
    conn.commit()
    item = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]
    detail = client.get(f"/v1/funding/{item['slug']}").json()
    elig = detail["documentEligibility"]
    assert elig["documentUrl"] == url
    assert set(elig["facts"]) == {"consortium_required", "sme_only"}, "unverified and unstated facts are never served"
    assert elig["facts"]["sme_only"]["note"] == "SMEs get a bonus."
    assert "documentEligibility" not in item, "the list does not carry it"


def test_a_call_without_a_read_document_has_no_eligibility(client, conn):
    _put(conn, "plain")
    item = client.get("/v1/funding", params={"status": "all"}).json()["items"][0]
    assert client.get(f"/v1/funding/{item['slug']}").json()["documentEligibility"] is None
