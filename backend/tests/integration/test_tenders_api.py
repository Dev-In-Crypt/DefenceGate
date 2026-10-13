"""The site's tenders and buyers: the contract at the end of docs/design/API_CONTRACT.md."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
PAST = datetime.now(timezone.utc) - timedelta(days=30)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _put(conn, native_id: str, *, source: str = "ted", buyer: str = "Ministry of Defence",
         title: str = "Armoured vehicles", title_en: str | None = None, country: str = "PL",
         deadline: datetime | None = FUTURE, status: str = "open", cpv: tuple[str, ...] = ("35400000",),
         value: float | None = None, currency: str | None = None, procedure: str | None = None,
         sig_cpv: bool = True, sig_buyer: bool = False, ted_ref: str | None = None,
         published: date = date(2026, 10, 1), description: str | None = None) -> int:
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=title,
        title_en=title_en, country=country, published_at=published, deadline_at=deadline,
        cpv_codes=list(cpv), status=status, is_defence=True, sig_cpv=sig_cpv, sig_buyer=sig_buyer,
        value_amount=value, value_currency=currency, procedure_type=procedure, ted_ref=ted_ref,
        description=description)
    src_id = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src_id)
    opp_id, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}-{status}-{deadline}",
                                      src_id)
    conn.commit()
    return opp_id


def _ids(client, **params) -> list[str]:
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params}).json()
    return [t["noticeId"] for t in body["items"]]


def test_a_page_has_a_total_and_the_contract_shape(client, conn):
    for n in range(5):
        _put(conn, f"N-{n}", deadline=FUTURE + timedelta(days=n))
    body = client.get("/v1/tenders", params={"pageSize": 2, "page": 2}).json()
    assert (body["total"], body["page"], body["pageSize"]) == (5, 2, 2)
    assert [t["noticeId"] for t in body["items"]] == ["N-2", "N-3"]
    tender = body["items"][0]
    assert set(tender) >= {"id", "slug", "noticeId", "title", "buyerName", "buyerSlug", "cpv",
                           "scope", "deadline", "status", "amended", "versionCount", "source"}
    assert tender["source"]["sourceId"] == "ted" and tender["source"]["licence"]


def test_open_is_as_of_now_so_a_passed_deadline_is_closed(client, conn):
    _put(conn, "OPEN")
    _put(conn, "LAPSED", deadline=PAST)
    assert _ids(client, status="open") == ["OPEN"]
    assert _ids(client, status="closed") == ["LAPSED"]
    lapsed = [t for t in client.get("/v1/tenders", params={"status": "all", "scope": "all"}).json()["items"]
              if t["noticeId"] == "LAPSED"][0]
    assert lapsed["status"] == "closed" and lapsed["statusNative"] == "expired"


@pytest.mark.parametrize("zone", ["Asia/Tokyo", "America/New_York", "UTC"])
def test_the_to_filter_is_the_whole_utc_day_whatever_the_servers_time_zone(
        client, conn, monkeypatch, zone):
    """Review finding of 13 October 2026: `to` was `%s::date + 1` compared with a
    timestamptz in the session's zone, while `from` is read as UTC: the bound moved with
    the server (Tokyo cut the day at 15:00 UTC, New York let the next morning in)."""
    from urllib.parse import quote

    from dgate import config

    evening = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    next_morning = datetime(2026, 11, 21, 2, 0, tzinfo=timezone.utc)
    midnight = datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc)
    _put(conn, "EVENING", deadline=evening)
    _put(conn, "NEXT-MORNING", deadline=next_morning)
    _put(conn, "MIDNIGHT", deadline=midnight)
    dsn = config.settings().dsn
    joiner = "&" if "?" in dsn else "?"
    monkeypatch.setenv("DGATE_DSN", f"{dsn}{joiner}options={quote(f'-c TimeZone={zone}')}")
    config.reset_cache()
    assert sorted(_ids(client, to="2026-11-20")) == ["EVENING"]
    assert sorted(_ids(client, to="2026-11-21")) == ["EVENING", "MIDNIGHT", "NEXT-MORNING"]
    assert sorted(_ids(client, **{"from": "2026-11-21"})) == ["MIDNIGHT", "NEXT-MORNING"]


def test_a_closed_list_runs_newest_deadline_first_by_default(client, conn):
    for n, days in enumerate((90, 10, 45)):
        _put(conn, f"C-{n}", deadline=PAST - timedelta(days=days))
    assert _ids(client, status="closed") == ["C-1", "C-2", "C-0"]
    assert _ids(client, status="closed", sort="deadline-asc") == ["C-0", "C-2", "C-1"]
    assert _ids(client, status="closed", sort="deadline-desc") == ["C-1", "C-2", "C-0"]


def test_core_is_the_default_and_supply_is_only_the_buyer(client, conn):
    _put(conn, "CORE")
    _put(conn, "SUPPLY", sig_cpv=False, sig_buyer=True, cpv=("15000000",))
    assert client.get("/v1/tenders").json()["total"] == 1
    body = client.get("/v1/tenders", params={"scope": "supply"}).json()
    assert [t["noticeId"] for t in body["items"]] == ["SUPPLY"] and body["items"][0]["scope"] == "supply"


def test_an_english_title_leads_and_the_original_is_kept_beneath(client, conn):
    _put(conn, "EN", title="Pojazdy opancerzone", title_en="Armoured vehicles")
    item = client.get("/v1/tenders").json()["items"][0]
    assert (item["title"], item["titleLanguage"], item["originalTitle"]) == \
        ("Armoured vehicles", "en", "Pojazdy opancerzone")


def test_a_value_range_selects_one_currency_and_never_converts(client, conn):
    _put(conn, "EUR1", value=1_000_000, currency="EUR")
    _put(conn, "PLN1", value=9_000_000, currency="PLN")
    assert _ids(client, min=500_000) == ["EUR1"]
    assert _ids(client, min=500_000, currency="pln") == ["PLN1"]


def test_search_matches_title_buyer_and_number_and_not_a_wildcard(client, conn):
    _put(conn, "ABC-1", title="Night vision goggles", buyer="Agencja Uzbrojenia")
    _put(conn, "XYZ-2", title="Boots")
    assert _ids(client, q="goggles") == ["ABC-1"]
    assert _ids(client, q="uzbrojenia") == ["ABC-1"]
    assert _ids(client, q="XYZ") == ["XYZ-2"]
    assert _ids(client, q="%") == []


def test_a_national_twin_is_hidden_only_when_the_ted_notice_is_in_the_same_result(client, conn):
    _put(conn, "700-2026", source="ted")
    _put(conn, "NL-1", source="nl_tenderned", country="NL", ted_ref="700-2026")
    both = _ids(client)
    assert both == ["700-2026"]
    tender = client.get("/v1/tenders").json()["items"][0]
    assert [t["source"] for t in tender["sameNotice"]] == ["nl_tenderned"]
    assert _ids(client, country="NL") == ["NL-1"]       # a filter that drops the TED row keeps it


def test_the_buyer_is_a_link_target_named_the_way_its_notices_name_it(client, conn):
    _put(conn, "B-1", buyer="Ministerstwo Obrony Narodowej")
    tender = client.get("/v1/tenders").json()["items"][0]
    assert tender["buyerId"] and tender["buyerSlug"].startswith(f"{tender['buyerId']}-ministerstwo")
    buyer = client.get(f"/v1/buyers/{tender['buyerSlug']}").json()
    assert buyer["name"] == "Ministerstwo Obrony Narodowej" and buyer["tenderCount"] == 1
    assert _ids(client, buyer=int(tender["buyerId"])) == ["B-1"]


def test_a_code_is_not_a_procedure_but_a_word_is(client, conn):
    _put(conn, "P-1", procedure="16")
    _put(conn, "P-2", procedure="ContractNotice")
    by_id = {t["noticeId"]: t for t in client.get(
        "/v1/tenders", params={"status": "all", "scope": "all"}).json()["items"]}
    assert by_id["P-1"]["procedure"] is None
    assert by_id["P-2"]["procedure"] == "Contract notice"


def test_slugs_resolve_by_the_leading_integer_and_bad_ones_are_404(client, conn):
    opp_id = _put(conn, "S-1")
    listed = client.get("/v1/tenders").json()["items"][0]
    assert client.get(f"/v1/tenders/{opp_id}-anything-else").json()["id"] == str(opp_id)
    assert client.get("/v1/tenders/999999-nothing").status_code == 404
    assert client.get("/v1/tenders/not-a-number").status_code == 404
    assert client.get("/v1/tenders/%D9%A1%D9%A2").status_code == 404      # non-ASCII digits
    assert {s["slug"] for s in client.get("/v1/tenders/slugs").json()} == {listed["slug"]}


def test_the_version_timeline_lists_what_changed_newest_first(client, conn):
    opp_id = _put(conn, "V-1", deadline=FUTURE)
    _put(conn, "V-1", deadline=FUTURE + timedelta(days=14))
    versions = client.get(f"/v1/tenders/{opp_id}/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["changes"] == []
    changed = {c["field"]: c for c in versions[0]["changes"]}
    assert "deadline_at" in changed and changed["deadline_at"]["label"] == "Deadline"
    assert changed["deadline_at"]["before"] != changed["deadline_at"]["after"]
    assert client.get(f"/v1/tenders/{opp_id}").json()["amended"] is True


def test_a_description_with_an_address_is_never_part_of_a_tender(client, conn):
    _put(conn, "E-1", buyer="Defence contact@example.org", description="write to a.b@example.org")
    served = client.get("/v1/tenders").text
    assert "example.org" not in served


def test_buyers_are_listed_by_notice_count_and_can_be_narrowed(client, conn):
    for n in range(3):
        _put(conn, f"M-{n}", buyer="Big Buyer", country="PL")
    _put(conn, "L-1", buyer="Small Buyer", country="ES", deadline=PAST)
    body = client.get("/v1/buyers").json()
    assert [(b["name"], b["tenderCount"], b["openCount"]) for b in body["items"]] == \
        [("Big Buyer", 3, 3), ("Small Buyer", 1, 0)]
    assert [b["name"] for b in client.get("/v1/buyers", params={"hasOpen": "true"}).json()["items"]] == ["Big Buyer"]
    assert [b["name"] for b in client.get("/v1/buyers", params={"q": "small"}).json()["items"]] == ["Small Buyer"]
    assert [b["name"] for b in client.get("/v1/buyers", params={"country": "ES"}).json()["items"]] == ["Small Buyer"]
    assert client.get("/v1/buyers/slugs").json()[0]["slug"].endswith("big-buyer")


@pytest.mark.parametrize("query", [
    "page=0", "page=1001", "pageSize=0", "pageSize=251", "status=nope", "scope=nope",
    "currency=EURO", "sort=nope", "buyer=0", "min=-1", "q=" + "x" * 101,
])
def test_a_request_outside_the_limits_is_a_422(client, query):
    assert client.get(f"/v1/tenders?{query}").status_code == 422
