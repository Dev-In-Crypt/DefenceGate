"""WP-90 (UX audit of 22 October 2026, section 5: the analyst path), against a real Postgres.

1. the calendar and the change feed hold exactly the list's filters, the new ones too (main CPV only, an excluded
   code, the status); 2. the search reads the English titles of a notice's own CPV codes; 3. `cpvMain` and `notCpv`
   on the list, its export, its scope counts; 4. a tender page states the first sentence of its description when it
   is a commercial subject, and the procurement documents a source names; 5. a buyer's top suppliers, from the award
   set, natural persons never named; 7. the change list by kind of change, and the week under way."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, awards, config, db, stats
from dgate import weekly_digest as W
from dgate.normalise import Opportunity
from tests.integration.test_changes import LATER, age, amend, opp, store
from tests.integration.test_supplier_map import FakeTed, rec

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path
    config.reset_cache()


def get(client, path: str, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def ids(page: dict) -> list[str]:
    return sorted(i["noticeId"] for i in page["items"])


def put(conn, native_id: str, cpv: list[str], **kw) -> int:
    return store(conn, replace(opp(native_id, country=kw.pop("country", "DE")), cpv_codes=cpv, **kw))


# ======================================================================= 2. the search reads the CPV titles

def test_a_search_word_finds_a_notice_by_the_english_title_of_its_own_codes(client, conn):
    put(conn, "RAD-1", ["35722000"], title_original="Beschaffung Rundsichtanlage")
    put(conn, "RAD-2", ["38115000", "45000000"], title_original="Suministro de equipos")
    put(conn, "SON-1", ["38113000"], title_original="Leveringen")
    put(conn, "TRK-1", ["34100000"], title_original="Lkw", title_en="Radar-free trucks")
    assert ids(get(client, "/v1/tenders", q="radar")) == ["RAD-1", "RAD-2", "TRK-1"]   # codes, and the English title
    assert ids(get(client, "/v1/tenders", q="sonars")) == ["SON-1"]
    # every word must match: one by a code's title, one by the notice's own title
    assert ids(get(client, "/v1/tenders", q="radar suministro")) == ["RAD-2"]
    # a word in thousands of titles narrows nothing by code (`cpv_labels.MAX_CODES`): only titles answer it
    assert ids(get(client, "/v1/tenders", q="services")) == []
    # the export, the scope counts and the calendar read the search the same way
    export = get(client, "/v1/tenders/export", q="radar")
    assert sorted(i["noticeId"] for i in export["items"]) == ["RAD-1", "RAD-2", "TRK-1"]
    assert get(client, "/v1/tenders/scope-counts", q="radar")["core"] == 3
    assert sorted(i["noticeId"] for i in get(client, "/v1/tenders/calendar", q="radar")["items"]) == [
        "RAD-1", "RAD-2", "TRK-1"]


# ======================================================================= 3. main CPV only, an excluded code

def test_main_cpv_only_and_an_excluded_code(client, conn):
    put(conn, "MAIN", ["35400000", "44000000"])
    put(conn, "SECOND", ["44000000", "35400000"])
    put(conn, "FIRE", ["35110000", "35400000"])
    assert ids(get(client, "/v1/tenders", cpv="354")) == ["FIRE", "MAIN", "SECOND"]
    assert ids(get(client, "/v1/tenders", cpv="354", cpvMain="true")) == ["MAIN"]
    assert ids(get(client, "/v1/tenders", cpv="354", notCpv="3511")) == ["MAIN", "SECOND"]
    assert ids(get(client, "/v1/tenders", notCpv="3511,44")) == []
    assert ids(get(client, "/v1/tenders", notCpv="35110000-1")) == ["MAIN", "SECOND"]      # a check digit is dropped
    assert get(client, "/v1/tenders/scope-counts", cpv="354", cpvMain="true")["core"] == 1
    assert sorted(i["noticeId"] for i in get(client, "/v1/tenders/export", notCpv="3511")["items"]) == ["MAIN", "SECOND"]
    for bad in ("abc", "3", "123456789"):
        r = client.get("/v1/tenders", params={"notCpv": bad})
        assert r.status_code == 422 and "2 to 8 digits" in r.text, bad


# ======================================================================= 1. the feeds of a search are its list

def test_the_calendar_and_the_change_feed_hold_exactly_the_lists_notices(client, conn):
    put(conn, "MAIN", ["35400000"])
    put(conn, "FIRE", ["35110000", "35400000"])
    put(conn, "PAST", ["35400000"], deadline_at=NOW - timedelta(days=2))
    put(conn, "OTHER", ["44000000", "35400000"])
    asked = {"cpv": "354", "cpvMain": "true", "notCpv": "3511"}
    listed = ids(get(client, "/v1/tenders", status="all", **asked))
    assert listed == ["MAIN", "PAST"]
    # the calendar holds the open ones with a deadline, of the same filters
    cal = get(client, "/v1/tenders/calendar", **asked)
    assert [i["noticeId"] for i in cal["items"]] == ["MAIN"] and cal["truncated"] is False
    # the change feed: the same filters, and the list's status as of now
    assert sorted(i["tender"]["noticeId"] for i in get(client, "/v1/changes", **asked)["items"]) == ["MAIN", "PAST"]
    assert [i["tender"]["noticeId"] for i in get(client, "/v1/changes", status="open", **asked)["items"]] == ["MAIN"]
    assert [i["tender"]["noticeId"] for i in get(client, "/v1/changes", status="closed", **asked)["items"]] == ["PAST"]
    assert client.get("/v1/changes", params={"status": "soon"}).status_code == 422
    assert client.get("/v1/tenders/calendar", params={"status": "open"}).status_code == 422   # the calendar is open-only


# ======================================================================= 7. kinds of change, the week under way

def test_the_change_list_by_kind_of_change(client, conn):
    moved = opp("DEADLINE")
    age(conn, store(conn, moved), 20)
    amend(conn, moved, "b", deadline_at=LATER)
    priced = opp("VALUE", value=100000.0)
    age(conn, store(conn, priced), 20)
    amend(conn, priced, "b", value_amount=250000.0)
    done = opp("STATUS")
    age(conn, store(conn, done), 20)
    amend(conn, done, "b", status="awarded")
    store(conn, opp("NEW"))
    every = get(client, "/v1/changes", scope="all")
    assert every["counts"] == {"new": 1, "amended": 3}

    def kind(k: str) -> list[str]:
        page = get(client, "/v1/changes", scope="all", kind=k)
        assert page["counts"] == every["counts"]                  # the counts are the window's, whatever the kind
        return sorted(i["tender"]["noticeId"] for i in page["items"])
    assert kind("deadline") == ["DEADLINE"]
    assert kind("value") == ["VALUE"]
    assert kind("status") == ["STATUS"]
    assert kind("new") == ["NEW"]
    assert kind("amended") == ["DEADLINE", "STATUS", "VALUE"]


def test_the_week_under_way_is_listed_up_to_now(client, conn):
    store(conn, opp("TODAY"))
    current = W.week_id(NOW.date())
    got = get(client, "/v1/changes", week=current)
    assert [i["tender"]["noticeId"] for i in got["items"]] == ["TODAY"]
    start, _ = W.week_bounds(current)
    assert datetime.fromisoformat(got["windowFrom"]) == start
    assert datetime.fromisoformat(got["windowTo"]) <= datetime.now(timezone.utc)
    nxt = W.week_id(NOW.date() + timedelta(days=7))
    assert client.get("/v1/changes", params={"week": nxt}).status_code == 404       # a week to come is not there
    assert client.get("/v1/digest", params={"week": current}).status_code == 404    # nor an issue of the digest


# ======================================================================= 4. the tender page

def test_the_tender_page_states_a_commercial_subject_and_the_documents(client, conn):
    ted = replace(opp("100-2026"), description="Supply of spare parts for military trucks. Engines of 450 kW.")
    tid = store(conn, ted)
    conn.execute("UPDATE source SET active = TRUE WHERE code = 'de_bkms'")    # seeded inactive (migration 0050)
    de = replace(opp("DE-1", source="de_bkms", ted_ref="100-2026"), source_url="https://www.evergabe-online.de/x?id=1",
                 description="Lieferung von Ersatzteilen.")
    did = store(conn, de)
    spec = store(conn, replace(opp("SPEC"), description="Radar with a range of 300 km and 5 MHz bandwidth."))
    person = store(conn, replace(opp("CONTACT"), description="Questions to Mr Huber, tel. +49 30 1234 5678."))
    got = get(client, f"/v1/tenders/{tid}")
    assert got["subject"] == "Supply of spare parts for military trucks."          # the first sentence only
    assert got["documentsUrl"] == "https://www.evergabe-online.de/x?id=1"          # its German twin's BT-15 address
    twin = got["sameNotice"][0]
    assert twin["source"] == "de_bkms" and twin["id"] == str(did)
    assert get(client, f"/v1/tenders/{twin['id']}")["documentsUrl"] == "https://www.evergabe-online.de/x?id=1"
    assert get(client, f"/v1/tenders/{spec}")["subject"] is None                   # a specification is not shown
    assert get(client, f"/v1/tenders/{person}")["subject"] is None                 # nor a contact
    # the list serves neither (the notice's page only)
    assert all(i["subject"] is None and i["documentsUrl"] is None for i in get(client, "/v1/tenders", scope="all")["items"])


# ======================================================================= 5. a buyer's top suppliers

def _award_notice(conn, native_id: str, buyer: str = "Bundesamt BAAINBw") -> int:
    o = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original="Ersatzteile",
                    title_en="Spare parts", country="DE", published_at=date(2026, 3, 1), cpv_codes=["35400000"],
                    status="awarded", is_defence=True, sig_legal_basis=True, sig_cpv=True, notice_subtype="29",
                    procedure_identifier=f"p-{native_id}", source_url=f"https://ted.example/{native_id}")
    src = db.source_id(conn, "ted")
    o.buyer_org_id = db.resolve_organisation(conn, o.buyer_name_raw, "DE", src_id=src)
    oid, _ = db.upsert_opportunity(conn, o, f"hash-{native_id}", src)
    conn.commit()
    return o.buyer_org_id


def test_a_buyers_top_suppliers_from_the_award_set_and_never_a_person(client, conn, env):
    buyer = _award_notice(conn, "1-2026")
    for n in ("2-2026", "3-2026", "4-2026"):
        _award_notice(conn, n)
    _award_notice(conn, "9-2026", buyer="Ministerio de Defensa")
    hensoldt = ("Hensoldt Sensors GmbH", "DEU", "DE111")
    rohde = ("Rohde & Schwarz GmbH & Co. KG", "DEU", "DE222")
    person = ("Huber Technik", "DEU", "DE333")   # a sole trader the rule of `individuals.py` marks
    awards.run_awards(client=FakeTed([
        rec("1-2026", [hensoldt]), rec("2-2026", [hensoldt]), rec("3-2026", [rohde]), rec("4-2026", [person]),
        rec("9-2026", [rohde]),
    ]).client(), pause=0, sleep=lambda s: None)
    conn.execute("UPDATE organisation SET individual_reason = 'given name' WHERE canonical_name ILIKE '%huber%'")
    conn.commit()
    got = get(client, f"/v1/buyers/{buyer}/suppliers")
    assert [(s["name"], s["awards"]) for s in got["items"]] == [
        ("Hensoldt Sensors GmbH", 2), ("Rohde & Schwarz GmbH & Co. KG", 1)]
    assert got["suppliers"] == 2 and got["contracts"] == 3
    assert "Huber" not in str(got) and "natural persons are never named" in got["attribution"]
    # each name links to its supplier page, whose count of this buyer is the same
    page = get(client, f"/v1/suppliers/{got['items'][0]['slug']}")
    assert [b["awards"] for b in page["buyers"] if b["name"] == "Bundesamt BAAINBw"] == [2]
    assert client.get("/v1/buyers/abc/suppliers").status_code == 404
