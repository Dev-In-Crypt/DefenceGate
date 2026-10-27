"""WP-152 on a real Postgres: a company's competitors, where it wins and its share, read from the market's stored contract
rows (`money.store`), give the same counts as its supplier page and the supplier list's product-code filter."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from dgate import api, db, money
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def notice(conn, native_id: str, buyer: str, country: str, cpv: str, value: float | None = None) -> int:
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=f"Notice {native_id}",
                      title_en=f"Notice {native_id}", country=country, published_at=date.today() - timedelta(days=30),
                      cpv_codes=[cpv], status="awarded", is_defence=True, sig_legal_basis=True, sig_cpv=True,
                      value_amount=value, value_currency="EUR" if value else None, value_kind="total" if value else None,
                      source_url=f"https://ted.example/{native_id}")
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
    conn.commit()
    return oid


def company(conn, name: str, country: str, reg: str) -> int:
    return conn.execute("INSERT INTO organisation (canonical_name, display_name, country, national_reg_no) "
                        "VALUES (%s, %s, %s, %s) RETURNING id", (name.lower(), name, country, reg)).fetchone()["id"]


def win(conn, opp: int, org: int, name: str, winners: int = 1) -> None:
    conn.execute("""INSERT INTO award (opportunity_id, organisation_id, supplier_country, name_as_stated, winners_in_notice,
                                       cpv_main, resolution_method, resolution_confidence)
                    SELECT %s, %s, country, %s, %s, (SELECT cpv_codes[1] FROM opportunity WHERE id = %s), 'exact_name', 1.0
                      FROM organisation WHERE id = %s""", (opp, org, name, winners, opp, org))
    conn.commit()


def market(conn) -> dict[str, int]:
    acme = company(conn, "Acme Defence GmbH", "DE", "111111111")
    rival = company(conn, "Rival Systems AG", "DE", "222222222")
    other = company(conn, "Other Services GmbH", "DE", "333333333")
    twin = company(conn, "Acme Defence GmbH", "DE", "444444444")     # the same name under another number (WP-111)
    bund, pl = "Bundesamt fuer Ausruestung", "Agencja Uzbrojenia"
    win(conn, notice(conn, "1-2026", bund, "DE", "35410000", 1_000_000), acme, "Acme Defence GmbH")
    shared = notice(conn, "2-2026", bund, "DE", "35410000")
    win(conn, shared, acme, "Acme Defence GmbH", 2)
    win(conn, shared, rival, "Rival Systems AG", 2)
    win(conn, notice(conn, "3-2026", bund, "DE", "35410000", 2_000_000), rival, "Rival Systems AG")
    win(conn, notice(conn, "4-2026", pl, "PL", "35300000"), acme, "Acme Defence GmbH")
    win(conn, notice(conn, "5-2026", bund, "DE", "72000000"), other, "Other Services GmbH")     # another class
    win(conn, notice(conn, "6-2026", bund, "DE", "35410000"), twin, "Acme Defence GmbH")
    money.store(conn)
    conn.commit()
    return {"acme": acme, "rival": rival, "other": other, "twin": twin}


def test_competitors_where_it_wins_and_its_share_match_the_supplier_page_and_list(conn, client):
    ids = market(conn)
    got = client.get(f"/v1/suppliers/{ids['acme']}/competition").json()
    page = client.get(f"/v1/suppliers/{ids['acme']}").json()
    assert got["available"] is True and got["reportOpen"] is False
    assert got["contracts"] == page["noticeCount"] == 3
    assert [(c["slug"].split("-")[0], c["overlap"], c["markets"], c["ours"], c["sameName"]) for c in got["competitors"]] == [
        (str(ids["rival"]), 2, 1, 2, False), (str(ids["twin"]), 1, 1, 2, True)]
    assert got["competitorCount"] == 2
    assert got["byCountry"] == [{"key": "DE", "contracts": 2}, {"key": "PL", "contracts": 1}]
    assert got["size"] == {"currency": "EUR", "median": 1_000_000.0, "valued": 1, "otherCurrencies": 0}
    assert got["withoutValue"] == 2
    cls = {s["key"]: s for s in got["shareByClass"]}["3541"]
    listed = {s["id"]: s for s in client.get("/v1/suppliers", params={"cpv": "3541"}).json()["items"]}
    assert cls["contracts"] == listed[str(ids["acme"])]["awardCount"] == 2
    assert cls["total"] == 4            # 1, 2 (two winners, once), 3 and 6
    assert (cls["currency"], cls["value"], cls["valueTotal"], cls["valuedTotal"]) == ("EUR", 1_000_000.0, 3_000_000.0, 2)
    # its value in the slice is what its page sums
    assert page["values"]["byCurrency"][0]["amount"] == cls["value"]


def test_without_the_stored_rows_nothing_is_guessed_and_a_removed_company_is_refused(conn, client):
    ids = market(conn)
    conn.execute("DELETE FROM list_snapshot WHERE key = %s", (money.MONEY_KEY,))
    conn.commit()
    got = client.get(f"/v1/suppliers/{ids['acme']}/competition").json()
    assert got["available"] is False and got["competitors"] == []
    # a snapshot stored before WP-152 (no contract keys) is not read until the worker renews it
    body = money.compute(conn)
    del body["k"]
    conn.execute("INSERT INTO list_snapshot (key, body, computed_at) VALUES (%s, %s, now())", (money.MONEY_KEY, Jsonb(body)))
    conn.commit()
    assert client.get(f"/v1/suppliers/{ids['acme']}/competition").json()["available"] is False
    conn.execute("UPDATE organisation SET suppressed = TRUE WHERE id = %s", (ids["acme"],))
    conn.commit()
    assert client.get(f"/v1/suppliers/{ids['acme']}/competition").status_code == 410


def test_the_report_switch_is_said(conn, client, monkeypatch):
    from dgate import config

    ids = market(conn)
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "1")
    config.reset_cache()
    assert client.get(f"/v1/suppliers/{ids['acme']}/competition").json()["reportOpen"] is True
