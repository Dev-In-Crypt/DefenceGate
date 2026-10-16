"""WP-23 through the API: every tender carries `confidence`, the `confidence` filter of
/v1/tenders keeps exactly the notices of those levels (the SQL twin agrees with the Python
function), and the detail page and the export say the same."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.confidence import confidence
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)

# name, legal basis, military CPV, listed buyer, buyer class, expected level
ROWS = [
    ("HI-BOTH", True, True, True, "defence", "high"),
    ("HI-CPV", False, True, True, "defence", "high"),
    ("MED-BUYER", False, False, True, "defence", "medium"),
    ("MED-LB-BUYER", True, False, True, "defence", "medium"),
    ("MED-LB-CPV", True, True, False, "other", "medium"),
    ("LOW-LB-CPV-POLICE", True, True, False, "security", "low"),
    ("LOW-DIRECTIVE", True, False, False, "municipal", "low"),
    ("LOW-CPV", False, True, False, "other", "low"),
    ("LOW-POLICE", False, True, False, "security", "low"),
]


@pytest.fixture()
def client(conn):
    stats.reset_cache()
    with TestClient(api.app) as c:
        yield c
    stats.reset_cache()


def _fill(conn):
    src = db.source_id(conn, "ted")
    for i, (nid, lb, cpv, buyer, cls, _) in enumerate(ROWS):
        opp = Opportunity(
            source_code="ted", native_id=nid, buyer_name_raw=f"Buyer {i}", title_original=f"Notice {nid}",
            country="PL", published_at=date(2026, 10, 1), deadline_at=FUTURE,
            cpv_codes=["35400000" if cpv else "45000000"], status="open", is_defence=True,
            sig_cpv=cpv, sig_cpv_military=cpv, sig_legal_basis=lb, sig_buyer=buyer, buyer_class=cls,
            legal_basis="32009L0081" if lb else "32014L0024")
        opp.buyer_org_id = db.resolve_organisation(conn, f"Buyer {i}", "PL", src_id=src)
        db.upsert_opportunity(conn, opp, f"h-{nid}", src)
    conn.commit()


def _by_id(client, **params):
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params}).json()
    return {t["noticeId"]: t for t in body["items"]}


def test_every_tender_carries_its_level_and_the_reason(client, conn):
    _fill(conn)
    got = _by_id(client)
    assert set(got) == {r[0] for r in ROWS}
    for nid, lb, cpv, buyer, cls, level in ROWS:
        c = got[nid]["confidence"]
        assert c["level"] == level, nid
        assert c == {"level": level, "basis": confidence(
            legal_basis=lb, military_cpv=cpv, buyer=buyer, buyer_class=cls)[1]}
    # the detail page and the export say the same as the list
    tid = got["HI-BOTH"]["id"]
    assert client.get(f"/v1/tenders/{tid}").json()["confidence"]["level"] == "high"
    exported = client.get("/v1/tenders/export", params={"status": "all", "scope": "all"}).json()
    assert {t["noticeId"]: t["confidence"]["level"] for t in exported["items"]} == {r[0]: r[5] for r in ROWS}


@pytest.mark.parametrize("wanted", ["high", "medium", "low", "high,medium", "low,high", "medium,low"])
def test_the_filter_keeps_exactly_the_notices_of_those_levels(client, conn, wanted):
    _fill(conn)
    levels = wanted.split(",")
    assert set(_by_id(client, confidence=wanted)) == {r[0] for r in ROWS if r[5] in levels}


def test_all_three_levels_or_none_is_no_filter_and_a_bad_level_is_refused(client, conn):
    _fill(conn)
    everything = {r[0] for r in ROWS}
    assert set(_by_id(client, confidence="high,medium,low")) == everything
    assert set(_by_id(client, confidence="")) == everything
    assert set(_by_id(client, confidence=" HIGH ")) == {r[0] for r in ROWS if r[5] == "high"}
    assert client.get("/v1/tenders", params={"confidence": "certain"}).status_code == 422
    assert client.get("/v1/tenders", params={"confidence": "high,certain"}).status_code == 422
