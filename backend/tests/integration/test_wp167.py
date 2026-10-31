"""WP-167: the EDF calls under Ukraine's association (in force since 16 October 2026) and the call document's budget total, against a
real Postgres. No network: the call documents' text is a row written by the test (the sentences of the two Ukraine Support Instrument
documents as stored)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, stats, ukraine
from dgate.ops import call_budgets
from tests.integration.test_wp31 import doc, put

pytestmark = pytest.mark.integration

DOC = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/edf/wp-call/2026/call-fiche_edf-edip-usi-2026-ls-ira_en.pdf"
TEXT = ("3. Available budget The estimated available call budget is EUR 184 500 0008. Specific budget information per topic can be found "
        "in the table below: 8 including EUR 180 000 000 from voted EU budget, in line with Commission Implementing Decision")


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


def test_the_edf_flags_follow_the_day_the_association_entered_into_force_and_the_report_lists_them(conn):
    open_call = put(conn, "open", programme="EDF", topic="EDF-2027-DA-X", days=60)
    closed = put(conn, "closed", programme="EDF", topic="EDF-2026-DA-Y")
    conn.execute("UPDATE call SET deadline_at = %s, status = 'closed' WHERE id = %s", (datetime(2026, 9, 29, 15, tzinfo=timezone.utc), closed))
    # production before WP-167: the 28 closed EDF calls carry the old reason
    conn.execute("UPDATE call SET open_to_ukraine_reason = 'edf_association_unconfirmed', open_to_ukraine_evidence = 'old' WHERE id = %s",
                 (closed,))
    conn.commit()
    changes: list[dict] = []
    report = ukraine.run(conn, write=False, changes=changes)
    assert report["changed"] == 2 and {c["id"] for c in changes} == {open_call, closed}
    assert next(c for c in changes if c["id"] == closed) == {
        "id": closed, "topic": "EDF-2026-DA-Y", "before": (None, "edf_association_unconfirmed"), "after": (None, "edf_closed_before_association")}
    assert conn.execute("SELECT open_to_ukraine_reason AS r FROM call WHERE id = %s", (open_call,)).fetchone()["r"] is None, "a report writes nothing"
    ukraine.run(conn, write=True)
    got = {r["id"]: r for r in conn.execute("SELECT id, open_to_ukraine AS flag, open_to_ukraine_reason AS reason, open_to_ukraine_evidence AS ev "
                                            "FROM call").fetchall()}
    assert (got[open_call]["flag"], got[open_call]["reason"]) == (True, "edf_association") and ukraine.EDF_IN_FORCE in got[open_call]["ev"]
    assert (got[closed]["flag"], got[closed]["reason"]) == (None, "edf_closed_before_association")
    assert ukraine.run(conn, write=True)["changed"] == 0

    with TestClient(api.app) as client:
        items = client.get("/v1/fit/facts", params={"ids": f"{open_call},{closed}"}).json()["items"]
        assert items[str(closed)].get("ukraineBeforeAssociation") is True and "ukraineBeforeAssociation" not in items[str(open_call)]


def test_the_call_document_total_is_read_from_the_stored_document_and_served_next_to_the_portal_figure(conn):
    cid = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-MAB", days=10, documents=[doc(DOC)])
    plain = put(conn, "plain", programme="EDF", topic="EDF-2027-DA-Z", days=10)
    conn.execute("UPDATE call SET budget = 180000000, budget_scope = 'topic', currency = 'EUR' WHERE id IN (%s, %s)", (cid, plain))
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES (%s, 'x', 1, %s, %s)", (DOC, len(TEXT), TEXT))
    conn.commit()

    changes: list[dict] = []
    assert call_budgets.run(conn, write=False, changes=changes) == {"calls": 2, "with_total": 1, "with_voted": 1, "changed": 1}
    assert changes == [{"id": cid, "topic": "EDF-EDIP-USI-2026-LS-IRA-MAB", "before": None,
                        "after": {"total": 184_500_000, "voted": 180_000_000, "url": DOC}}]
    assert conn.execute("SELECT document_budget FROM call WHERE id = %s", (cid,)).fetchone()["document_budget"] is None, "a report writes nothing"
    assert call_budgets.run(conn, write=True)["changed"] == 1
    assert call_budgets.run(conn, write=True)["changed"] == 0, "a second run writes nothing"

    with TestClient(api.app) as client:
        body = client.get(f"/v1/funding/{cid}").json()
        assert body["budget"] == {"amount": 180_000_000.0, "currency": "EUR"}, "the portal's figure stays the budget"
        assert body["documentBudget"] == {"amount": 184_500_000.0, "votedEu": 180_000_000.0, "currency": "EUR", "documentUrl": DOC}
        assert client.get(f"/v1/funding/{plain}").json()["documentBudget"] is None
        listed = {c["id"]: c for c in client.get("/v1/funding", params={"status": "all"}).json()["items"]}
        assert listed[str(cid)]["documentBudget"]["amount"] == 184_500_000.0, "the list item carries it too"

    # the document is gone from the call's detail: the value goes with it
    conn.execute("UPDATE call SET conditions_raw = conditions_raw - 'documents' WHERE id = %s", (cid,))
    conn.commit()
    assert call_budgets.run(conn, write=True)["changed"] == 1
    assert conn.execute("SELECT document_budget FROM call WHERE id = %s", (cid,)).fetchone()["document_budget"] is None
