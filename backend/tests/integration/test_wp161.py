"""WP-161: the launch-day rehearsal on a real Postgres (docs/verification/features/wp161-selfcheck.md). One test per breakage
found with every switch on and the plans on sale: a subscription that is over (expired, or cancelled at the end of a period
that has ended) no longer blocks deleting the account or buying a plan again; an alert mail can be stopped without signing in;
a forged or unsigned billing event changes nothing."""

# ruff: noqa: F811 - the fixtures `client`, `sent`, `creem` and `on` come from the files they are imported from
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from dgate import accounts
from tests.integration.test_accounts import PW, H, _put, client, sent, sign_in  # noqa: F401
from tests.integration.test_billing_wp124 import (  # noqa: F401
    checkout,
    completed,
    creem,
    deliver,
    on,
    sub_event,
    subscribe,
)

pytestmark = pytest.mark.integration


def _plan(client, session: str) -> str:
    return client.get("/v1/account/billing", headers=H(session)).json()["plan"]


def test_an_account_whose_subscription_expired_can_be_deleted(on, sent, creem, conn):
    session = subscribe(on, sent, creem)
    assert deliver(on, sub_event("subscription.expired")).status_code == 200
    assert _plan(on, session) == "free"
    r = on.request("DELETE", "/v1/account/me", json={"confirm": "ann@example.com", "password": PW}, headers=H(session))
    assert r.status_code == 204, r.text
    assert conn.execute("SELECT count(*) AS n FROM billing_subscription").fetchone()["n"] == 0


def test_a_cancellation_whose_period_ran_out_lets_the_account_buy_again_and_be_deleted(on, sent, creem, conn):
    session = subscribe(on, sent, creem)
    gone = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert deliver(on, sub_event("subscription.scheduled_cancel", end=gone)).status_code == 200
    assert _plan(on, session) == "free"
    # before WP-161 the new subscription was taken for a second one and not applied: paid, and still Free
    assert checkout(on, session, "pro", "monthly").status_code == 200
    assert deliver(on, completed(creem, sub="sub_2", cust="cust_1")).status_code == 200
    assert _plan(on, session) == "pro"
    # a cancellation whose period still runs keeps the account (Creem may charge nothing more, but the plan is in force)
    assert deliver(on, sub_event("subscription.scheduled_cancel", sub="sub_2",
                                 end=datetime.now(timezone.utc) + timedelta(days=3))).status_code == 200
    body = {"confirm": "ann@example.com", "password": PW}
    assert on.request("DELETE", "/v1/account/me", json=body, headers=H(session)).status_code == 409
    conn.execute("UPDATE billing_subscription SET current_period_end = now() - interval '1 minute'")
    conn.commit()
    assert on.request("DELETE", "/v1/account/me", json=body, headers=H(session)).status_code == 204


def test_a_forged_or_unsigned_billing_event_changes_nothing(on, sent, creem, conn):
    session, _ = sign_in(on, sent)
    assert checkout(on, session).status_code == 200
    event = completed(creem)
    raw = json.dumps(event).encode()
    unsigned = on.post("/v1/billing/webhook", content=raw, headers={"content-type": "application/json"})
    forged = deliver(on, event, secret="whsec_somebody_else")
    assert (unsigned.status_code, forged.status_code) == (401, 401)
    assert _plan(on, session) == "free"
    assert conn.execute("SELECT count(*) AS n FROM billing_event").fetchone()["n"] == 0


def test_an_alert_mail_can_be_stopped_without_signing_in(client, sent, conn):
    from dgate.ops.digest import run_digests

    _put(conn, "STOP-1", title="Armoured vehicle lot", published=date.today())
    session, _ = sign_in(client, sent)
    sign_in(client, sent, "bob@example.com")
    client.post("/v1/account/searches", headers=H(session),
                json={"name": "armour", "kind": "tender", "filters": {"q": "armoured"}, "cadence": "daily"})
    conn.execute("UPDATE app_saved_search SET created_at = now() - interval '2 days', last_alerted_at = now() - interval '2 days'")
    conn.commit()
    accounts._cache.clear()
    assert run_digests(conn)["mails"] == 1
    mail = sent[-1]
    token = conn.execute("SELECT alerts_stop_token FROM app_user WHERE email_canonical = 'ann@example.com'").fetchone()[
        "alerts_stop_token"]
    stop = f"https://site.test/unsubscribe?kind=alerts&token={token}"
    assert f"Stop all these alerts: {stop}" in mail["body"]
    assert mail["headers"] == {"List-Unsubscribe": f"<{stop}>"}
    # the tokens are random and the account's own
    other = conn.execute("SELECT alerts_stop_token FROM app_user WHERE email_canonical = 'bob@example.com'").fetchone()
    assert len(token) == 64 and other["alerts_stop_token"] != token
    # an unknown token: the same answer, nothing stopped
    assert client.post("/v1/account/alerts/unsubscribe", json={"token": "0" * 64}).json() == {"done": True}
    assert conn.execute("SELECT cadence FROM app_saved_search").fetchone()["cadence"] == "daily"
    assert client.post("/v1/account/alerts/unsubscribe", json={"token": "short"}).status_code == 422
    # no session needed; the searches stay, their alerts stop, and the next run sends nothing
    r = client.post("/v1/account/alerts/unsubscribe", json={"token": token})
    assert r.json() == {"done": True}
    rows = conn.execute("SELECT cadence FROM app_saved_search").fetchall()
    assert [x["cadence"] for x in rows] == ["off"]
    conn.execute("UPDATE app_saved_search SET last_alerted_at = now() - interval '2 days'")
    conn.commit()
    assert run_digests(conn)["mails"] == 0
    # the token is not in the account export
    assert token not in json.dumps(client.get("/v1/account/export", headers=H(session)).json(), default=str)
