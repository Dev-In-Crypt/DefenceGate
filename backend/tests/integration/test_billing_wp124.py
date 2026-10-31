"""WP-124: payments through Creem (merchant of record), against docs/SECURITY_REQUIREMENTS.md B1-B5 and D3.

Creem is never called: `billing._creem` is replaced by a recorder that answers as Creem's API does
(docs.creem.io: POST /checkouts -> id, checkout_url; POST /customers/billing -> customer_portal_link).
Webhook events are signed here with the test secret, exactly as Creem signs them (HMAC-SHA256 of the
raw body, lowercase hex, header `creem-signature`)."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

import pytest

from dgate import accounts, billing, config
from tests.integration.test_accounts import H, _put, client, sent, sign_in  # noqa: F401

pytestmark = pytest.mark.integration

SECRET = "whsec_test_only_not_a_real_secret"
PRODUCTS = {k: f"prod_{k}" for k in ("pro_monthly", "pro_yearly", "team_monthly", "team_yearly",
                                     "consultant_monthly", "consultant_yearly", "founding_yearly")}


def _billing_env(monkeypatch, *, key=True, secret=True, products=True) -> None:
    if key:
        monkeypatch.setenv("DGATE_CREEM_API_KEY", "creem_test_key_only")
    if secret:
        monkeypatch.setenv("DGATE_CREEM_WEBHOOK_SECRET", SECRET)
    if products:
        for k, v in PRODUCTS.items():
            monkeypatch.setenv(f"DGATE_CREEM_PRODUCT_{k.upper()}", v)
    config.reset_cache()


@pytest.fixture()
def creem(monkeypatch):
    """Creem's API, recorded. `answer` can be changed by a test (a bad URL from the provider)."""
    calls: list[tuple[str, dict]] = []
    state = {"n": 0, "checkout_url": "https://checkout.creem.io/ch_{n}"}

    def fake(path: str, body: dict) -> dict:
        calls.append((path, body))
        if path == "/checkouts":
            state["n"] += 1
            return {"id": f"ch_{state['n']}", "checkout_url": state["checkout_url"].format(n=state["n"])}
        if path == "/customers/billing":
            return {"customer_portal_link": f"https://creem.io/my-orders/login/{body['customer_id']}"}
        raise AssertionError(path)

    monkeypatch.setattr(billing, "_creem", fake)
    fake.calls, fake.state = calls, state
    return fake


@pytest.fixture()
def on(client, sent, creem, monkeypatch):
    """Billing open: the key, the webhook secret and every product id set (test mode)."""
    _billing_env(monkeypatch)
    return client


def _event(kind: str, obj: dict, *, at: datetime | None = None, eid: str | None = None) -> dict:
    at = at or datetime.now(timezone.utc)
    return {"id": eid or f"evt_{secrets.token_hex(8)}", "eventType": kind,
            "created_at": int(at.timestamp() * 1000), "object": obj}


def deliver(client, event: dict, *, secret: str = SECRET, headers: dict | None = None, raw: bytes | None = None):
    body = raw if raw is not None else json.dumps(event).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/v1/billing/webhook", content=body,
                       headers={"creem-signature": sig, "content-type": "application/json", **(headers or {})})


def checkout(client, session: str, plan="pro", period="monthly"):
    return client.post("/v1/account/billing/checkout", json={"plan": plan, "billing": period}, headers=H(session))


def completed(creem, n: int = -1, *, sub="sub_1", cust="cust_1", status="active",
              end: datetime | None = None, at: datetime | None = None, eid: str | None = None) -> dict:
    """checkout.completed for the n-th checkout the API created, as Creem sends it."""
    made = [body for path, body in creem.calls if path == "/checkouts"]
    index = n if n >= 0 else len(made) + n
    body, cid = made[index], f"ch_{index + 1}"         # the fake numbers its checkouts ch_1, ch_2, ...
    end = end or datetime.now(timezone.utc) + timedelta(days=30)
    at = at or datetime.now(timezone.utc) - timedelta(minutes=5)
    return _event("checkout.completed", {
        "id": cid, "object": "checkout", "status": "completed", "request_id": body["request_id"],
        "order": {"id": "ord_1", "customer": cust, "product": body["product_id"], "status": "paid"},
        "product": {"id": body["product_id"], "billing_type": "recurring"},
        "customer": {"id": cust, "email": "someone@example.com"},
        "subscription": {"id": sub, "status": status, "current_period_end_date": end.isoformat()},
        "metadata": dict(body["metadata"]),
    }, at=at, eid=eid)


def sub_event(kind: str, sub="sub_1", cust="cust_1", product="prod_pro_monthly", *, status=None,
              end: datetime | None = None, at: datetime | None = None, metadata: dict | None = None,
              eid: str | None = None) -> dict:
    obj = {"id": sub, "object": "subscription", "product": {"id": product}, "customer": {"id": cust},
           "metadata": metadata or {}}
    if status:
        obj["status"] = status
    if end:
        obj["current_period_end_date"] = end.isoformat().replace("+00:00", "Z")
    return _event(kind, obj, at=at, eid=eid)


def subscribe(client, sent, creem, email="ann@example.com", plan="pro", period="monthly", **kw) -> str:
    session, _ = sign_in(client, sent, email)
    r = checkout(client, session, plan, period)
    assert r.status_code == 200, r.text
    assert deliver(client, completed(creem, **kw)).status_code == 200
    return session


def me_of(client, session) -> dict:
    return client.get("/v1/account/me", headers=H(session)).json()


def me_plan(client, session) -> dict:
    return client.get("/v1/account/me", headers=H(session)).json()["plan"]


def search_body(name="Vehicles"):
    return {"name": name, "kind": "tender", "filters": {"q": "vehicles"}}


# ---------------------------------------------------------------- closed by default

def test_billing_is_closed_by_default_and_no_checkout_is_created(client, sent, creem, conn):
    assert client.get("/v1/account/status").json()["billing"] is False
    session, _ = sign_in(client, sent)
    r = checkout(client, session)
    assert (r.status_code, r.json()["error"]) == (503, "billing_not_open")
    assert creem.calls == []
    assert conn.execute("SELECT count(*) AS n FROM billing_checkout").fetchone()["n"] == 0
    state = client.get("/v1/account/billing", headers=H(session)).json()
    assert state["open"] is False and state["foundingLeft"] is None and state["plan"] == "free"
    # nothing is for sale, so nothing is withheld: saved searches and alerts as WP-123 built them
    # WP-155: every built feature but the two behind the company report's switch (off here)
    assert set(me_of(client, session)["features"]) == {"saved_searches", "email_alerts", "competitors_full", "signals_full",
                                                       "signals_csv", "consortium_gaps", "eligibility_export", "supplier_map_csv",   # WP-156
                                                       "team_workspace", "client_profiles",            # WP-157
                                                       "expiring_contracts", "expiring_contracts_csv"}  # WP-160
    assert client.post("/v1/account/searches", json=search_body(), headers=H(session)).status_code == 201


@pytest.mark.parametrize("missing", ["key", "secret", "products"])
def test_billing_stays_closed_while_any_setting_is_missing(client, sent, creem, monkeypatch, missing):
    _billing_env(monkeypatch, **{missing: False})
    assert billing.billing_problem()
    assert client.get("/v1/account/status").json()["billing"] is False
    session, _ = sign_in(client, sent)
    assert checkout(client, session).status_code == 503
    assert creem.calls == []


def test_the_webhook_refuses_everything_while_no_secret_is_set(client, sent):
    r = deliver(client, _event("checkout.completed", {"id": "ch_1"}))
    assert (r.status_code, r.json()["error"]) == (503, "billing_not_open")


def test_billing_needs_open_accounts_as_well(on, monkeypatch):
    assert on.get("/v1/account/status").json()["billing"] is True
    monkeypatch.setattr(accounts, "PASSWORD_PRIVACY_VERSION", "99.0")
    assert on.get("/v1/account/status").json()["billing"] is False


# ---------------------------------------------------------------- checkout (B3, B4)

def test_a_checkout_is_created_server_side_with_the_account_in_its_metadata_and_grants_nothing(on, sent, creem, conn):
    session, _ = sign_in(on, sent)
    r = checkout(on, session, "team", "yearly")
    assert r.status_code == 200
    assert r.json() == {"url": "https://checkout.creem.io/ch_1"}
    path, body = creem.calls[0]
    row = conn.execute("SELECT * FROM billing_checkout").fetchone()
    user_id = conn.execute("SELECT id FROM app_user").fetchone()["id"]
    assert path == "/checkouts"
    assert body["product_id"] == "prod_team_yearly"
    assert body["metadata"] == {"account_id": str(user_id), "checkout_ref": str(row["id"])}
    assert body["request_id"] == str(row["id"])
    assert body["success_url"] == "https://site.test/app/billing?checkout=done"
    assert "customer" not in body                       # no address is sent: Creem asks for it itself
    assert (row["creem_checkout_id"], row["plan"], row["period"], row["completed_at"]) == ("ch_1", "team", "yearly", None)
    assert "creem_test_key_only" not in r.text
    assert me_plan(on, session)["current"] == "free"   # B4: nothing before a verified event
    assert conn.execute("SELECT count(*) AS n FROM billing_subscription").fetchone()["n"] == 0


def test_a_provider_answer_pointing_off_creem_is_refused_and_leaves_no_checkout(on, sent, creem, conn):
    creem.state["checkout_url"] = "https://evil.example/ch_{n}"
    session, _ = sign_in(on, sent)
    r = checkout(on, session)
    assert (r.status_code, r.json()["error"]) == (502, "payment_provider")
    assert conn.execute("SELECT count(*) AS n FROM billing_checkout").fetchone()["n"] == 0


def test_founding_has_no_monthly_price_and_unknown_plans_are_refused(on, sent, creem):
    session, _ = sign_in(on, sent)
    assert checkout(on, session, "founding", "monthly").status_code == 422
    assert checkout(on, session, "platinum", "monthly").status_code == 422
    assert creem.calls == []


def test_an_account_with_a_plan_gets_no_second_checkout(on, sent, creem):
    session = subscribe(on, sent, creem)
    r = checkout(on, session, "team", "monthly")
    assert (r.status_code, r.json()["error"]) == (409, "already_subscribed")


def test_checkouts_are_capped_per_account_and_hour(on, sent, creem):
    session, _ = sign_in(on, sent)
    for _ in range(billing.CHECKOUTS_PER_HOUR):
        assert checkout(on, session).status_code == 200
    r = checkout(on, session)
    assert r.status_code == 429 and r.headers["retry-after"]


# ---------------------------------------------------------------- webhook: signature, age, replay (B1, B2, B5)

def test_a_verified_checkout_event_opens_the_plan(on, sent, creem, conn):
    session, _ = sign_in(on, sent)
    checkout(on, session, "pro", "yearly")
    end = datetime(2027, 10, 25, 12, 0, tzinfo=timezone.utc)
    assert deliver(on, completed(creem, end=end)).json() == {"ok": True}
    plan = me_plan(on, session)
    # WP-155: Pro's features (the company report is behind its switch, off here)
    assert plan["current"] == "pro" and set(me_of(on, session)["features"]) == {"saved_searches", "email_alerts",
                                                                                "competitors_full", "signals_full", "eligibility_export",
                                                                                "expiring_contracts"}       # WP-160
    row = conn.execute("SELECT * FROM billing_subscription").fetchone()
    assert (row["plan"], row["period"], row["status"], row["creem_customer_id"], row["creem_subscription_id"],
            row["current_period_end"]) == ("pro", "yearly", "active", "cust_1", "sub_1", end)
    assert conn.execute("SELECT plan FROM app_user").fetchone()["plan"] == "pro"
    assert conn.execute("SELECT completed_at FROM billing_checkout").fetchone()["completed_at"] is not None
    state = on.get("/v1/account/billing", headers=H(session)).json()
    assert state["subscription"]["status"] == "active" and state["subscription"]["canManage"] is True


def test_a_wrong_secret_or_a_malformed_signature_is_refused_and_changes_nothing(on, sent, creem, conn):
    session, _ = sign_in(on, sent)
    checkout(on, session)
    event = completed(creem)
    assert deliver(on, event, secret="whsec_someone_else").status_code == 401
    raw = json.dumps(event).encode()
    for sig in ("", "nothex", hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest().upper(), "0" * 64):
        r = on.post("/v1/billing/webhook", content=raw, headers={"creem-signature": sig})
        assert r.status_code == 401, sig
    assert on.post("/v1/billing/webhook", content=raw).status_code == 401           # no header
    # the body is what is signed: the same signature over a changed body fails
    tampered = raw.replace(b'"completed"', b'"completed" ')
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert on.post("/v1/billing/webhook", content=tampered, headers={"creem-signature": sig}).status_code == 401
    assert me_plan(on, session)["current"] == "free"
    assert conn.execute("SELECT count(*) AS n FROM billing_event").fetchone()["n"] == 0


def test_a_stale_or_future_event_is_refused_and_changes_nothing(on, sent, creem, conn):
    session, _ = sign_in(on, sent)
    checkout(on, session)
    now = datetime.now(timezone.utc)
    for at in (now - timedelta(hours=26), now + timedelta(minutes=10)):
        r = deliver(on, completed(creem, at=at))
        assert (r.status_code, r.json()["error"]) == (400, "stale_event")
    assert me_plan(on, session)["current"] == "free"
    assert conn.execute("SELECT count(*) AS n FROM billing_event").fetchone()["n"] == 0
    # a retry by Creem within its 24 hours is accepted
    assert deliver(on, completed(creem, at=now - timedelta(hours=6))).status_code == 200
    assert me_plan(on, session)["current"] == "pro"


def test_a_replayed_event_is_acknowledged_and_changes_state_once(on, sent, creem, conn):
    session = subscribe(on, sent, creem)
    now = datetime.now(timezone.utc)
    paid = sub_event("subscription.paid", at=now - timedelta(minutes=2), eid="evt_paid_1")
    assert deliver(on, paid).status_code == 200
    assert deliver(on, sub_event("subscription.canceled", status="canceled", at=now - timedelta(minutes=1))).status_code == 200
    assert me_plan(on, session)["current"] == "free"
    # the same paid event again, even re-sent with a newer time, is one event: nothing reopens
    paid["created_at"] = int(now.timestamp() * 1000)
    assert deliver(on, paid).json() == {"ok": True}
    assert me_plan(on, session)["current"] == "free"
    assert conn.execute("SELECT outcome FROM billing_event WHERE event_id = 'evt_paid_1'").fetchone()["outcome"] == "applied"


def test_the_previous_webhook_secret_verifies_during_a_rotation(on, sent, creem, monkeypatch):
    """B5: with the new secret in DGATE_CREEM_WEBHOOK_SECRET and the old one in ..._PREVIOUS, both verify."""
    monkeypatch.setenv("DGATE_CREEM_WEBHOOK_SECRET", "whsec_new_one")
    monkeypatch.setenv("DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS", SECRET)
    config.reset_cache()
    session, _ = sign_in(on, sent)
    checkout(on, session)
    assert deliver(on, completed(creem), secret=SECRET).status_code == 200
    assert deliver(on, sub_event("subscription.paid"), secret="whsec_new_one").status_code == 200
    monkeypatch.setenv("DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS", "")
    config.reset_cache()
    assert deliver(on, sub_event("subscription.paid"), secret=SECRET).status_code == 401


def test_the_webhook_is_internal_like_the_account_routes(on):
    """It is reached through the site's server only: a browser's Origin or a proxied request is refused."""
    for headers in ({"Origin": "https://evil.test"}, {"X-Forwarded-For": "198.51.100.9"}):
        assert deliver(on, sub_event("subscription.paid"), headers=headers).status_code == 403


def test_the_webhook_takes_a_large_event_and_refuses_one_over_64_kib(on, sent, creem):
    session, _ = sign_in(on, sent)
    checkout(on, session)
    big = completed(creem)
    big["object"]["product"]["description"] = "x" * 30_000          # over the 16 KiB of the account routes
    assert deliver(on, big).status_code == 200
    huge = sub_event("subscription.paid")
    huge["object"]["padding"] = "x" * (70 * 1024)
    assert deliver(on, huge).status_code == 413


def test_a_malformed_event_is_a_400(on):
    for raw in (b"not json", b"[]", json.dumps({"id": "evt_1", "eventType": "x"}).encode(),
                json.dumps({"id": "evt 1", "eventType": "x", "created_at": 1, "object": {}}).encode()):
        assert deliver(on, {}, raw=raw).status_code == 400, raw


# ---------------------------------------------------------------- event mapping

@pytest.mark.parametrize("kind,status,plan", [
    ("subscription.active", "active", "pro"),
    ("subscription.paid", "active", "pro"),
    ("subscription.trialing", "trialing", "pro"),
    ("subscription.past_due", "past_due", "pro"),             # Creem retries: its grace period
    ("subscription.unpaid", "unpaid", "free"),
    ("subscription.paused", "paused", "free"),
    ("subscription.expired", "expired", "free"),
    ("subscription.canceled", "canceled", "free"),
    ("subscription.scheduled_cancel", "scheduled_cancel", "pro"),   # until the end of the paid period
])
def test_every_subscription_event_maps_to_its_documented_state(on, sent, creem, conn, kind, status, plan):
    session = subscribe(on, sent, creem)
    assert deliver(on, sub_event(kind, end=datetime.now(timezone.utc) + timedelta(days=10))).status_code == 200
    assert conn.execute("SELECT status FROM billing_subscription").fetchone()["status"] == status
    assert me_plan(on, session)["current"] == plan
    assert on.get("/v1/account/billing", headers=H(session)).json()["subscription"]["status"] == status


def test_a_cancellation_at_the_end_of_the_period_ends_the_plan_then_without_another_event(on, sent, creem, conn):
    session = subscribe(on, sent, creem)
    end = datetime.now(timezone.utc) + timedelta(days=3)
    deliver(on, sub_event("subscription.scheduled_cancel", end=end))
    assert me_plan(on, session)["current"] == "pro"
    conn.execute("UPDATE billing_subscription SET current_period_end = now() - interval '1 minute'")
    conn.commit()
    assert me_plan(on, session)["current"] == "free"


def test_subscription_update_takes_the_new_product_and_status(on, sent, creem, conn):
    session = subscribe(on, sent, creem)
    deliver(on, sub_event("subscription.update", product="prod_team_yearly", status="active"))
    row = conn.execute("SELECT plan, period, status FROM billing_subscription").fetchone()
    assert (row["plan"], row["period"], row["status"]) == ("team", "yearly", "active")
    assert me_plan(on, session)["current"] == "team"


def test_a_refund_records_its_time_and_ends_the_plan_only_with_the_subscription(on, sent, creem, conn):
    session = subscribe(on, sent, creem)
    partial = _event("refund.created", {"id": "ref_1", "object": "refund", "status": "succeeded",
                                        "transaction": {"id": "tran_1", "subscription": "sub_1"},
                                        "customer": {"id": "cust_1"}})
    assert deliver(on, partial).status_code == 200
    row = conn.execute("SELECT status, refunded_at FROM billing_subscription").fetchone()
    assert row["status"] == "active" and row["refunded_at"] is not None
    assert me_plan(on, session)["current"] == "pro"
    full = _event("refund.created", {"id": "ref_2", "object": "refund", "status": "succeeded",
                                     "subscription": {"id": "sub_1", "status": "canceled"}})
    assert deliver(on, full).status_code == 200
    assert me_plan(on, session)["current"] == "free"


def test_a_dispute_suspends_the_plan(on, sent, creem, conn, monkeypatch):
    told = []
    monkeypatch.setattr(billing, "notify", lambda text: told.append(text))
    session = subscribe(on, sent, creem)
    deliver(on, _event("dispute.created", {"id": "dis_1", "subscription": "sub_1"}))
    assert me_plan(on, session)["current"] == "free"
    assert told and "dispute" in told[0]


def test_an_unknown_event_type_is_acknowledged_and_ignored(on, sent, creem, conn):
    session = subscribe(on, sent, creem)
    assert deliver(on, _event("credits.granted", {"id": "x"})).status_code == 200
    assert conn.execute("SELECT outcome FROM billing_event WHERE event_type = 'credits.granted'").fetchone()["outcome"] == "ignored"
    assert me_plan(on, session)["current"] == "pro"


def test_an_older_event_arriving_later_changes_nothing(on, sent, creem, conn):
    """B2: by the event's own time, not by arrival."""
    now = datetime.now(timezone.utc)
    session = subscribe(on, sent, creem, at=now - timedelta(minutes=10))
    deliver(on, sub_event("subscription.paid", at=now - timedelta(minutes=1)))
    r = deliver(on, sub_event("subscription.past_due", at=now - timedelta(minutes=5)))
    assert r.status_code == 200
    assert conn.execute("SELECT status FROM billing_subscription").fetchone()["status"] == "active"
    assert conn.execute("SELECT outcome FROM billing_event WHERE event_type = 'subscription.past_due'").fetchone()["outcome"] == "older"
    deliver(on, sub_event("subscription.canceled", status="canceled", at=now - timedelta(seconds=30)))
    assert me_plan(on, session)["current"] == "free"


def test_a_subscription_event_before_the_checkout_event_is_matched_by_our_checkout(on, sent, creem, conn):
    session, _ = sign_in(on, sent)
    checkout(on, session, "consultant", "monthly")
    meta = creem.calls[0][1]["metadata"]
    now = datetime.now(timezone.utc)
    assert deliver(on, sub_event("subscription.active", product="prod_consultant_monthly", metadata=meta,
                                 at=now - timedelta(seconds=5))).status_code == 200
    assert me_plan(on, session)["current"] == "consultant"
    assert deliver(on, completed(creem, at=now - timedelta(seconds=10))).status_code == 200      # later, older
    assert me_plan(on, session)["current"] == "consultant"


# ---------------------------------------------------------------- B3: keyed on our checkout and Creem's ids

def test_an_event_naming_another_account_or_product_changes_nothing(on, sent, creem, conn):
    session_a, _ = sign_in(on, sent, "ann@example.com")
    session_b, _ = sign_in(on, sent, "bob@example.com")
    checkout(on, session_a)
    bob = str(conn.execute("SELECT id FROM app_user WHERE email_canonical = 'bob@example.com'").fetchone()["id"])
    forged = completed(creem)
    forged["object"]["metadata"]["account_id"] = bob                  # the checkout is Ann's
    assert deliver(on, forged).status_code == 200
    wrong_product = completed(creem)
    wrong_product["object"]["product"]["id"] = "prod_team_yearly"
    assert deliver(on, wrong_product).status_code == 200
    stranger = completed(creem)
    stranger["object"]["id"] = "ch_someone_elses"
    assert deliver(on, stranger).status_code == 200
    assert me_plan(on, session_a)["current"] == "free" and me_plan(on, session_b)["current"] == "free"
    outcomes = [r["outcome"] for r in conn.execute("SELECT outcome FROM billing_event")]
    assert outcomes == ["unmatched"] * 3


def test_an_event_with_an_accounts_email_but_not_its_ids_changes_nothing(on, sent, creem, conn):
    session = subscribe(on, sent, creem)                               # Ann: sub_1 / cust_1
    session_b, _ = sign_in(on, sent, "bob@example.com")
    other = sub_event("subscription.active", sub="sub_9", cust="cust_9")
    other["object"]["customer"]["email"] = "bob@example.com"
    assert deliver(on, other).status_code == 200
    assert me_plan(on, session_b)["current"] == "free"
    # Ann's subscription id with another customer id: refused too
    deliver(on, sub_event("subscription.canceled", cust="cust_9", status="canceled"))
    assert me_plan(on, session)["current"] == "pro"


def test_a_second_paid_subscription_is_not_overwritten_and_the_operator_is_told(on, sent, creem, conn, monkeypatch):
    told = []
    monkeypatch.setattr(billing, "notify", lambda text: told.append(text))
    session, _ = sign_in(on, sent)
    checkout(on, session)
    checkout(on, session)                                              # two tabs
    assert deliver(on, completed(creem, 0, sub="sub_1")).status_code == 200
    assert deliver(on, completed(creem, 1, sub="sub_2")).status_code == 200
    assert conn.execute("SELECT creem_subscription_id FROM billing_subscription").fetchone()["creem_subscription_id"] == "sub_1"
    assert told and "refund" in told[0]


# ---------------------------------------------------------------- entitlement gate

def test_once_plans_are_on_sale_free_cannot_save_searches_and_a_plan_can(on, sent, creem, conn):
    session, _ = sign_in(on, sent)
    assert me_of(on, session)["features"] == []
    r = on.post("/v1/account/searches", json=search_body(), headers=H(session))
    assert (r.status_code, r.json()["error"]) == (402, "plan_required")
    checkout(on, session)
    deliver(on, completed(creem))
    r = on.post("/v1/account/searches", json=search_body(), headers=H(session))
    assert r.status_code == 201 and r.json()["paused"] is False


def test_a_downgrade_keeps_the_searches_and_stops_the_feature(on, sent, creem, conn):
    _put(conn, "1-2026")
    session = subscribe(on, sent, creem)
    sid = on.post("/v1/account/searches", json=search_body(), headers=H(session)).json()["id"]
    assert on.get("/v1/account/dashboard", headers=H(session)).json()["matches"]
    deliver(on, sub_event("subscription.canceled", status="canceled"))
    listed = on.get("/v1/account/searches", headers=H(session)).json()["items"]
    assert [(s["id"], s["paused"], s["matchCount"]) for s in listed] == [(sid, True, None)]
    assert on.get("/v1/account/dashboard", headers=H(session)).json()["matches"] == []
    assert on.post("/v1/account/searches", json=search_body("Another"), headers=H(session)).status_code == 402
    assert on.patch(f"/v1/account/searches/{sid}", json={"cadence": "weekly"}, headers=H(session)).status_code == 402
    assert on.get("/v1/account/export", headers=H(session)).json()["searches"][0]["id"] == sid   # still held
    assert on.delete(f"/v1/account/searches/{sid}", headers=H(session)).status_code == 204       # and removable


def test_alert_digests_go_only_to_accounts_whose_plan_has_them(on, sent, creem, conn):
    from dgate.ops.digest import run_digests

    _put(conn, "2-2026")
    pro = subscribe(on, sent, creem, "pro@example.com")
    on.post("/v1/account/searches", json=search_body(), headers=H(pro))
    # a free account with a search kept from before the plans went on sale
    sign_in(on, sent, "free@example.com")
    free_id = conn.execute("SELECT id FROM app_user WHERE email_canonical = 'free@example.com'").fetchone()["id"]
    conn.execute("INSERT INTO app_saved_search (owner_id, name, kind, filters, cadence) "
                 "VALUES (%s, 'Kept', 'tender', '{\"q\": \"vehicles\"}', 'daily')", (free_id,))
    conn.execute("UPDATE app_saved_search SET created_at = now() - interval '2 days'")
    conn.commit()
    sent.clear()
    counts = run_digests(conn)
    assert counts["mails"] == 1 and counts["skipped"] == 1
    assert [m["to"] for m in sent] == ["pro@example.com"]
    kept = conn.execute("SELECT last_alerted_at FROM app_saved_search WHERE owner_id = %s", (free_id,)).fetchone()
    assert kept["last_alerted_at"] is not None                     # not due again every hour


# ---------------------------------------------------------------- founding cap

def _founding_rows(conn, n: int) -> None:
    for i in range(n):
        uid = conn.execute("INSERT INTO app_user (email_canonical, email_display) VALUES (%s, %s) RETURNING id",
                           (f"f{i}@example.com", f"f{i}@example.com")).fetchone()["id"]
        conn.execute("INSERT INTO billing_subscription (account_id, plan, period, status, last_event_id, last_event_at) "
                     "VALUES (%s, 'founding', 'yearly', 'active', %s, now())", (uid, f"evt_seed_{i}"))
    conn.commit()


def test_founding_customer_is_capped_at_20_live_subscriptions(on, sent, creem, conn):
    _founding_rows(conn, 20)
    session, _ = sign_in(on, sent)
    assert on.get("/v1/account/billing", headers=H(session)).json()["foundingLeft"] == 0
    r = checkout(on, session, "founding", "yearly")
    assert (r.status_code, r.json()["error"]) == (409, "founding_full")
    assert creem.calls == []
    conn.execute("UPDATE billing_subscription SET status = 'canceled' WHERE last_event_id = 'evt_seed_0'")
    conn.commit()
    assert on.get("/v1/account/billing", headers=H(session)).json()["foundingLeft"] == 1
    assert checkout(on, session, "founding", "yearly").status_code == 200


def test_an_open_founding_checkout_holds_the_last_place_for_an_hour(on, sent, creem, conn):
    _founding_rows(conn, 19)
    ann, _ = sign_in(on, sent, "ann@example.com")
    bob, _ = sign_in(on, sent, "bob@example.com")
    assert checkout(on, ann, "founding", "yearly").status_code == 200
    assert on.get("/v1/account/billing", headers=H(ann)).json()["foundingLeft"] == 1     # her own does not count
    assert on.get("/v1/account/billing", headers=H(bob)).json()["foundingLeft"] == 0
    assert checkout(on, bob, "founding", "yearly").status_code == 409
    conn.execute("UPDATE billing_checkout SET created_at = now() - interval '61 minutes'")
    conn.commit()
    assert checkout(on, bob, "founding", "yearly").status_code == 200


# ---------------------------------------------------------------- portal and deletion

def test_manage_subscription_opens_creems_portal_for_the_accounts_customer(on, sent, creem):
    session, _ = sign_in(on, sent)
    r = on.post("/v1/account/billing/portal", headers=H(session))
    assert (r.status_code, r.json()["error"]) == (404, "no_subscription")
    checkout(on, session)
    deliver(on, completed(creem, cust="cust_42"))
    r = on.post("/v1/account/billing/portal", headers=H(session))
    assert r.json() == {"url": "https://creem.io/my-orders/login/cust_42"}
    assert creem.calls[-1] == ("/customers/billing", {"customer_id": "cust_42"})


def test_an_account_with_a_running_subscription_is_deleted_only_after_it_is_cancelled(on, sent, creem, conn):
    from tests.integration.test_accounts import PW

    session = subscribe(on, sent, creem)
    body = {"confirm": "ann@example.com", "password": PW}
    r = on.request("DELETE", "/v1/account/me", json=body, headers=H(session))
    assert (r.status_code, r.json()["error"]) == (409, "subscription_active")
    assert conn.execute("SELECT count(*) AS n FROM app_user").fetchone()["n"] == 1
    deliver(on, sub_event("subscription.canceled", status="canceled"))
    assert on.request("DELETE", "/v1/account/me", json=body, headers=H(session)).status_code == 204
    assert conn.execute("SELECT count(*) AS n FROM billing_subscription").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM billing_checkout").fetchone()["n"] == 0


def test_the_export_holds_the_subscription_and_no_secret(on, sent, creem):
    session = subscribe(on, sent, creem)
    out = on.get("/v1/account/export", headers=H(session))
    sub = out.json()["subscription"][0]
    assert (sub["plan"], sub["status"], sub["creemCustomerId"]) == ("pro", "active", "cust_1")
    assert "creem_test_key_only" not in out.text and SECRET not in out.text


def test_the_plan_is_changed_by_no_other_route(on, sent, creem):
    """D3: no route sets the plan; the profile patch refuses the field."""
    session, _ = sign_in(on, sent)
    assert on.patch("/v1/account/me", json={"plan": "pro"}, headers=H(session)).status_code == 422
    paths = {getattr(r, "path", "") for r in on.app.routes}
    assert not any("plan" in p for p in paths)
