"""WP-156 on a real Postgres: the two exports of the owner's plan split. Each gate in both states: while no plan is on sale
nobody signed in is refused (WP-124), once the plans are on sale `supplier_map_csv` is Team and Consultant and
`eligibility_export` Pro and up. The supplier export is the public list without its MAX_OFFSET, capped at EXPORT_MAX, legal
entities only; the eligibility answer is every open call with the badge's facts."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import logging

import pytest

from dgate import exports, suppliers
from tests.integration.test_accounts import H, client, sent, sign_in  # noqa: F401
from tests.integration.test_billing_wp124 import _billing_env
from tests.integration.test_wp31 import doc, hold, put
from tests.integration.test_wp152 import company, notice, win
from tests.integration.test_wp155 import on_plan

pytestmark = pytest.mark.integration

EXPORT = "/v1/account/suppliers/export"
CALLS = "/v1/account/eligibility/calls"


def suppliers_of(conn, n: int) -> list[int]:
    """`n` German winners of one buyer, the i-th with i + 1 wins (the last one most), and one sole trader."""
    out = []
    for i in range(n):
        org = company(conn, f"Supplier {i:03d} GmbH", "DE", f"9{i:08d}")
        for j in range(i % 3 + 1):
            win(conn, notice(conn, f"s-{i}-{j}", "Bundesamt fuer Ausruestung", "DE", "35410000", 50_000), org,
                f"Supplier {i:03d} GmbH")
        out.append(org)
    person = company(conn, "Hans Huber", "DE", "800000000")
    win(conn, notice(conn, "p-1", "Bundesamt fuer Ausruestung", "DE", "35410000"), person, "Hans Huber")
    conn.execute("UPDATE organisation SET individual_reason = 'given name' WHERE id = %s", (person,))
    conn.commit()
    return out


def test_the_supplier_export_is_the_list_without_its_offset_limit_and_legal_entities_only(conn, client, sent, monkeypatch, caplog):
    monkeypatch.setattr(suppliers, "MAX_OFFSET", 5)                  # the public list stops at 5 positions
    monkeypatch.setattr(exports, "EXPORT_MAX", 7)
    ids = suppliers_of(conn, 9)
    assert client.get(EXPORT).status_code == 401                     # a session is needed
    session, _ = sign_in(client, sent)
    caplog.set_level(logging.INFO, logger="accounts")
    r = client.get(EXPORT, params={"country": "DE", "cpv": "35"}, headers=H(session))   # no plan on sale: nobody refused
    # SECURITY_REQUIREMENTS O3: capped and logged with the account id
    uid = conn.execute("SELECT id FROM app_user").fetchone()["id"]
    assert f"account event=supplier_export user={uid} rows=7" in [x.getMessage() for x in caplog.records]
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    assert body["total"] == 9 and body["cap"] == 7 and len(body["items"]) == 7               # past MAX_OFFSET, up to the cap
    public = client.get("/v1/suppliers", params={"country": "DE", "cpv": "35", "pageSize": 5}).json()
    assert [i["slug"] for i in body["items"][:5]] == [i["slug"] for i in public["items"]]       # the same order
    assert all("Huber" not in i["name"] for i in body["items"])
    assert {i["id"] for i in body["items"]} <= {str(x) for x in ids}
    assert body["items"][0]["contractValues"][0]["currency"] == "EUR"
    # the list's own refusals hold here too
    assert client.get(EXPORT, params={"country": "Atlantis"}, headers=H(session)).status_code == 422
    assert client.get(EXPORT, params={"sort": "drop"}, headers=H(session)).status_code == 422

    _billing_env(monkeypatch)                                       # plans on sale
    for plan, ok in ((None, False), ("pro", False), ("founding", False), ("team", True), ("consultant", True)):
        on_plan(conn, plan)
        got = client.get(EXPORT, headers=H(session))
        assert got.status_code == (200 if ok else 402), plan
        if not ok:
            assert got.json()["error"] == "plan_required" and "Team and Consultant" in got.json()["message"]


def test_the_eligibility_answer_is_every_open_call_with_the_badges_facts(conn, client, sent, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="accounts")
    read = put(conn, "read", documents=[doc("https://example.test/a.pdf")])
    hold(conn, "https://example.test/a.pdf", "call_document", sme_only=(True, "Only SMEs may apply.", None))
    unread = put(conn, "unread", documents=[doc("https://example.test/b.pdf")], days=40)
    closed = put(conn, "closed", status="closed", days=-5)
    assert client.get(CALLS).status_code == 401
    session, _ = sign_in(client, sent)
    r = client.get(CALLS, headers=H(session))
    assert r.status_code == 200 and r.headers["cache-control"] == "private, no-store"
    body = r.json()
    got = {i["id"]: i for i in body["items"]}
    assert set(got) == {str(read), str(unread)} and str(closed) not in got and body["total"] == 2
    assert any(x.getMessage().startswith("account event=eligibility_export user=") and x.getMessage().endswith(" rows=2")
               for x in caplog.records)
    assert [i["id"] for i in body["items"]] == [str(read), str(unread)]           # soonest deadline first
    assert got[str(read)]["fit"]["state"] == "read"
    assert got[str(read)]["fit"]["facts"]["sme_only"] == {"value": True, "note": None, "quote": "Only SMEs may apply.",
                                                          "scope": "call_document"}
    assert got[str(unread)]["fit"]["state"] == "not_read"
    assert got[str(read)]["slug"].startswith(f"{read}-") and got[str(read)]["title"] == "Call read"
    assert set(got[str(read)]) == {"id", "slug", "title", "programme", "programmeName", "topicId", "deadline", "deadlineIsDate",
                                   "rolling", "sourceUrl", "sourceName", "fit"}

    _billing_env(monkeypatch)
    for plan, ok in ((None, False), ("pro", True), ("founding", True), ("team", True), ("consultant", True)):
        on_plan(conn, plan)
        got = client.get(CALLS, headers=H(session))
        assert got.status_code == (200 if ok else 402), plan
        if not ok:
            assert got.json()["error"] == "plan_required" and "Pro" in got.json()["message"]


def test_the_eligibility_answer_reads_past_one_page_of_the_list(conn, client, sent, monkeypatch):
    monkeypatch.setattr(exports, "_PAGE", 2)
    monkeypatch.setattr(exports, "PACK_MAX", 4)
    for i in range(5):
        put(conn, f"c{i}", days=10 + i)
    session, _ = sign_in(client, sent)
    body = client.get(CALLS, headers=H(session)).json()
    assert body["total"] == 5 and body["cap"] == 4 and len(body["items"]) == 4
