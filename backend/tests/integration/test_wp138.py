"""WP-138 against a real Postgres: a rate stated as a notice's total is served as no value (and the ops step and its
undo), and an organisation reviewed as a natural person is withheld as a buyer (and the undo)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.normalise import Opportunity
from dgate.ops import person_rows, tender_unit_prices

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def put(conn, native_id: str, *, source="ted", value=None, kind=None, cpv="79620000", buyer="BWI GmbH",
        ted_ref=None, country="DE") -> int:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=f"Call-off {native_id}",
                      country=country, published_at=date(2026, 10, 7), cpv_codes=[cpv], status="awarded",
                      is_defence=True, sig_buyer=True, value_amount=value, value_currency="EUR" if value else None,
                      value_kind=kind, ted_ref=ted_ref)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    conn.execute("UPDATE opportunity SET value_kind = %s WHERE id = %s", (kind, oid))
    conn.commit()
    return oid


def page(client, oid: int) -> dict:
    return client.get(f"/v1/tenders/{oid}").json()


def listed(client, **params) -> list[str]:
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params}).json()
    return sorted(t["noticeId"] for t in body["items"])


def test_an_hourly_rate_stated_as_the_total_is_no_value_and_the_undo_restores_it(conn, client):
    rate = put(conn, "689828-2026", value=74.13, kind="total")
    nat = put(conn, "NAT-1", source="fr_boamp", ted_ref="689828-2026", country="FR")
    bus = put(conn, "690000-2026", value=398.0, kind="total", cpv="60140000")
    contract = put(conn, "690001-2026", value=250000.0, kind="total")
    assert page(client, rate)["estimatedValue"] == {"amount": 74.13, "currency": "EUR"}
    assert page(client, nat)["valueFrom"] == "ted_twin"                 # the twin's rate was borrowed

    assert tender_unit_prices.run(conn, write=False) == {"ted_7962": 1, "total": 1}
    assert tender_unit_prices.run(conn, write=True)["total"] == 1
    stats.reset_cache()
    assert page(client, rate)["estimatedValue"] is None and page(client, rate)["valueKind"] is None
    assert page(client, nat)["estimatedValue"] is None and page(client, nat)["valueFrom"] is None
    assert page(client, bus)["estimatedValue"]["amount"] == 398.0       # a small contract stands
    assert page(client, contract)["estimatedValue"]["amount"] == 250000.0
    assert "689828-2026" not in listed(client, max=100)                 # no value range matches a rate
    assert "690000-2026" in listed(client, max=500)
    assert conn.execute("SELECT value_amount FROM opportunity WHERE id = %s", (rate,)).fetchone()["value_amount"] == Decimal("74.13")
    assert conn.execute("SELECT count(*) AS n FROM opportunity_version WHERE opportunity_id = %s",
                        (rate,)).fetchone()["n"] == 1                   # an attribute: no version
    assert tender_unit_prices.run(conn, write=True)["total"] == 0       # a second run finds nothing

    assert tender_unit_prices.run(conn, write=True, undo=True)["total"] == 1
    stats.reset_cache()
    assert page(client, rate)["estimatedValue"] == {"amount": 74.13, "currency": "EUR"}


def test_a_row_reviewed_as_a_person_is_withheld_as_a_buyer_and_the_undo_restores_it(conn, client):
    oid = put(conn, "495013-2020", value=2500000.0, kind="total", cpv="35320000", buyer="John Example", country="GB")
    org = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (oid,)).fetchone()["buyer_org_id"]
    other = put(conn, "495014-2020", buyer="Ministry of Defence", cpv="35320000", country="GB")
    assert page(client, oid)["buyerName"] == "John Example"

    assert person_rows.mark(conn, [org, 999999999], write=False) == {
        "asked": 2, "marked": 1, "not_live_or_already_marked": 1, "buyers_withheld": 1, "notices_buyer_withheld": 1}
    assert page(client, oid)["buyerName"] == "John Example"            # a report writes nothing
    person_rows.mark(conn, [org], write=True)
    stats.reset_cache()
    got = page(client, oid)
    assert "John Example" not in str(got) and got["buyerId"] is None
    assert conn.execute("SELECT individual_reason FROM organisation WHERE id = %s", (org,)).fetchone()[
        "individual_reason"] == person_rows.REVIEWED
    assert page(client, other)["buyerName"] == "Ministry of Defence"
    assert person_rows.mark(conn, [org], write=True)["marked"] == 0      # a second run finds nothing

    assert person_rows.undo(conn, write=True) == {"unmarked": 1, "withholdings_lifted": 1}
    stats.reset_cache()
    assert page(client, oid)["buyerName"] == "John Example"
    assert person_rows.main(["--ids", str(org)]) == 0
