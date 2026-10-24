"""WP-106 (persona round of 24 October 2026: tender pages, lists and exports) against a real Postgres.

1. the list by value (per currency) and by code, and `all` with the rest newest first; 2. a list item and an export row carry
the award's winners and value as the notice's page does (`award_summaries` equal to `awarded`), its subject and its main code's
title; 3. a notice's page links the other notices of its procedure; 4. the digest narrowed to CPV codes; 5. a change row of an
award says its winners."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, stats, tenders
from tests.integration.test_changes import opp, store
from tests.integration.test_wp31 import make_week, place
from tests.integration.test_wp95 import award, award_notice, notice, org

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("DGATE_PLACSP_AWARDS_PUBLIC", "true")
    config.reset_cache()
    stats.reset_cache()
    yield
    stats.reset_cache()
    config.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def get(client, path: str, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def numbers(page: dict) -> list[str]:
    return [i["noticeId"] for i in page["items"]]


# ============================================================== 1. orders

def test_the_list_sorts_by_value_per_currency_and_by_main_code(client, conn):
    buyer = org(conn, "mando de apoyo logistico", "ES", is_defence_buyer=True)
    for native, value, cpv in (("V-SMALL", (10.0, "EUR", "total"), "35420000"), ("V-NONE", None, "18000000"),
                               ("V-PLN", (9000.0, "PLN", "total"), "35110000"), ("V-BIG", (500.0, "EUR", "total"), "34330000"),
                               ("V-PLACEHOLDER", (1.0, "EUR", "total"), "30000000")):
        notice(conn, "ted", native, buyer=buyer, value=value, cpv=(cpv,))
    conn.commit()
    by_value = numbers(get(client, "/v1/tenders", status="all", scope="all", sort="value-desc"))
    assert by_value[:3] == ["V-BIG", "V-SMALL", "V-PLN"]                 # EUR largest first, then PLN by itself
    assert set(by_value[3:]) == {"V-NONE", "V-PLACEHOLDER"}               # a placeholder is "not stated"
    in_pln = numbers(get(client, "/v1/tenders", status="all", scope="all", sort="value-desc", currency="PLN"))
    assert in_pln == ["V-PLN"]
    by_code = numbers(get(client, "/v1/tenders", status="all", scope="all", sort="cpv-asc"))
    assert by_code == ["V-NONE", "V-PLACEHOLDER", "V-BIG", "V-PLN", "V-SMALL"]
    assert client.get("/v1/tenders", params={"sort": "value"}).status_code == 422


def test_all_lists_the_open_notices_then_the_newest_deadline_first(client, conn):
    store(conn, opp("OPEN", deadline=NOW + timedelta(days=20)))
    store(conn, opp("OLD-2017", deadline=datetime(2017, 3, 1, tzinfo=timezone.utc), published=datetime(2017, 1, 5).date()))
    store(conn, opp("RECENT", deadline=NOW - timedelta(days=10), published=(NOW - timedelta(days=40)).date()))
    assert numbers(get(client, "/v1/tenders", status="all")) == ["OPEN", "RECENT", "OLD-2017"]
    assert numbers(get(client, "/v1/tenders", status="all", sort="open-first")) == ["OPEN", "RECENT", "OLD-2017"]
    # the oldest first only when asked for
    assert numbers(get(client, "/v1/tenders", status="all", sort="deadline-asc")) == ["OPEN", "OLD-2017", "RECENT"]


# ============================================================== 2. list items: award, subject, code title

@pytest.fixture
def awards(conn):
    jae = org(conn, "jae mando de apoyo logistico", "ES", is_defence_buyer=True)
    m, indra = org(conn, "madzeal", "ES"), org(conn, "indra sistemas", "ES")
    fw = notice(conn, "ted", "389204-2026", title="ACUERDO MARCO repuestos", buyer=jae, cpv=("34330000",))
    award(conn, fw, m, "Madzeal, S.L.", value=(1250000.0, "EUR", "framework"))
    award(conn, fw, indra, "INDRA SISTEMAS S.A.")
    award_notice(conn, fw, value_amount=1250000, value_currency="EUR", value_kind="framework", skipped_person=1)
    one = notice(conn, "es_placsp", "2026/ETSAE0906/00003787E", title="Baterias", buyer=jae)
    award(conn, one, m, "MADZEAL S.L.", value=(743802.0, "EUR", "contract"))
    plain = notice(conn, "ted", "1-2026", title="No award read", buyer=jae)
    conn.commit()
    return {"framework": fw, "one": one, "plain": plain}


def test_a_list_item_carries_the_awards_winners_and_value_as_its_page_does(client, conn, awards):
    page = get(client, "/v1/tenders", status="all", scope="all")
    items = {i["id"]: i for i in page["items"]}
    assert set(items) == {str(v) for v in awards.values()}
    for tid, item in items.items():
        own = get(client, f"/v1/tenders/{tid}")
        assert (item["awardedTo"], item["awardedPersons"], item["awardValue"]) == (
            own["awardedTo"], own["awardedPersons"], own["awardValue"]), tid
    fw = items[str(awards["framework"])]
    assert [w["name"] for w in fw["awardedTo"]] == ["INDRA SISTEMAS S.A.", "Madzeal, S.L."] and fw["awardedPersons"] == 1
    assert fw["awardValue"] == {"amount": 1250000.0, "currency": "EUR", "kind": "framework"}
    assert items[str(awards["one"])]["awardValue"]["kind"] == "contract"
    assert items[str(awards["plain"])]["awardedTo"] == [] and items[str(awards["plain"])]["awardValue"] is None
    # the main code's official title, from the full vocabulary (34330000 had none on cards)
    assert fw["cpvTitles"] == {"34330000": tenders.cpv_titles(["34330000"])["34330000"]}
    # the batch and the page's function agree for a notice and its copies as well
    keys = {awards["framework"]: [awards["one"]]}
    assert tenders.award_summaries(conn, keys)[awards["framework"]] == tenders.awarded(conn, [awards["framework"], awards["one"]])


def test_an_export_row_carries_the_winners(client, conn, awards):
    got = get(client, "/v1/tenders/export", status="all", scope="all")
    rows = {i["id"]: i for i in got["items"]}
    assert [w["name"] for w in rows[str(awards["framework"])]["awardedTo"]] == ["INDRA SISTEMAS S.A.", "Madzeal, S.L."]
    assert rows[str(awards["one"])]["awardValue"]["kind"] == "contract"


def test_a_list_item_states_the_subject_without_the_part_number(client, conn):
    tid = store(conn, replace(opp("37631-LIKE"), description="GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE 2520410039852"))
    change = store(conn, replace(opp("269322-LIKE"), description="Modification de la date limite de réception des offres"))
    items = {i["id"]: i for i in get(client, "/v1/tenders")["items"]}
    assert items[str(tid)]["subject"] == "GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE"
    assert items[str(change)]["subject"] is None
    assert get(client, f"/v1/tenders/{tid}")["subject"] == "GELENKWELLE MIT AUSGLEICHSGELENK, FAHRZE"


# ============================================================== 3. the procedure's other notices

def test_a_call_and_its_award_link_each_other(client, conn):
    call = store(conn, opp("355017-2025", deadline=NOW - timedelta(days=30)))
    award_id = store(conn, opp("58911-2026", deadline=None))
    other = store(conn, opp("OTHER-PROC"))
    conn.execute("UPDATE opportunity SET procedure_identifier = '0107af11' WHERE id IN (%s, %s)", (call, award_id))
    conn.execute("UPDATE opportunity SET status = 'awarded' WHERE id = %s", (award_id,))
    conn.commit()
    stages = get(client, f"/v1/tenders/{call}")["stages"]
    assert [(s["noticeId"], s["status"]) for s in stages] == [("58911-2026", "awarded")]
    assert stages[0]["slug"].startswith(f"{award_id}-")
    assert [s["noticeId"] for s in get(client, f"/v1/tenders/{award_id}")["stages"]] == ["355017-2025"]
    assert get(client, f"/v1/tenders/{other}")["stages"] == []


# ============================================================== 4. the digest by CPV code

def test_the_digest_narrows_its_tender_sections_to_cpv_codes(client, conn):
    week, start, _end, _ids = make_week(conn)
    inside = start + timedelta(days=2, hours=4)
    bread = store(conn, opp("W-BREAD", country="FR", kind="supply", published=inside.date()))
    place(conn, bread, inside)
    whole = get(client, "/v1/digest", week=week)
    assert whole["cpv"] == [] and whole["counts"]["tendersNew"] == 3
    military = get(client, "/v1/digest", week=week, cpv="354")
    assert military["cpv"] == ["354"] and military["counts"]["tendersNew"] == 2
    assert str(bread) not in {t["id"] for t in military["tendersNew"]}
    assert military["counts"]["tendersAmended"] == whole["counts"]["tendersAmended"]     # the amended notice is 35400000
    assert military["counts"]["callsNew"] == whole["counts"]["callsNew"]                 # calls have no code: unchanged
    supplies = get(client, "/v1/digest", week=week, cpv="45", country="FR")
    assert supplies["counts"]["tendersNew"] == 1 and supplies["counts"]["tendersAmended"] == 0
    assert client.get("/v1/digest", params={"week": week, "cpv": "bread"}).status_code == 422


# ============================================================== 5. an award in the change list

def test_a_change_row_of_an_award_says_its_winners(client, conn):
    n = store(conn, opp("AWD-1", deadline=None))
    conn.execute("UPDATE opportunity SET status = 'awarded' WHERE id = %s", (n,))
    award(conn, n, org(conn, "madzeal", "ES"), "Madzeal, S.L.", value=(500000.0, "EUR", "contract"))
    conn.commit()
    rows = {i["tender"]["id"]: i["tender"] for i in get(client, "/v1/changes", scope="all")["items"]}
    assert [w["name"] for w in rows[str(n)]["awardedTo"]] == ["Madzeal, S.L."]
    assert rows[str(n)]["awardValue"] == {"amount": 500000.0, "currency": "EUR", "kind": "contract"}
