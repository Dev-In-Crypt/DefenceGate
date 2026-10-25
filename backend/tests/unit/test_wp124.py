"""WP-124: the parts of billing that need no database: signature, event age, the plan each state allows,
the entitlement table, closed by default, the URLs the browser may be sent to, and where the settings go."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dgate import billing, config
from dgate.accounts import AccountError

ROOT = Path(__file__).resolve().parents[3]
SECRET = "whsec_unit_test_only"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("DGATE_CREEM_") or key == "DGATE_ENV":
            monkeypatch.delenv(key)
    config.reset_cache()
    yield
    config.reset_cache()


def _set(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.reset_cache()


def _all(monkeypatch):
    _set(monkeypatch, DGATE_CREEM_API_KEY="k", DGATE_CREEM_WEBHOOK_SECRET=SECRET,
         **{f"DGATE_CREEM_PRODUCT_{k.upper()}": f"prod_{k}" for k in config.settings().creem_products})


def _sig(raw: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- closed by default

def test_billing_is_closed_with_no_settings_and_names_what_is_missing():
    problem = billing.billing_problem()
    assert problem and "DGATE_CREEM_API_KEY" in problem and "DGATE_CREEM_PRODUCT_FOUNDING_YEARLY" in problem
    assert billing.plans_on_sale() is False
    assert billing.products() == {}


def test_billing_opens_only_with_every_setting(monkeypatch):
    _all(monkeypatch)
    assert billing.billing_problem() is None
    assert billing.plans_on_sale() is True
    assert billing.plan_for_product("prod_founding_yearly") == ("founding", "yearly")
    assert billing.plan_for_product("prod_unknown") is None
    monkeypatch.setenv("DGATE_CREEM_PRODUCT_TEAM_YEARLY", "")
    config.reset_cache()
    assert billing.billing_problem() == "DGATE_CREEM_PRODUCT_TEAM_YEARLY"


def test_test_mode_is_the_default_and_the_local_stand_in_is_ignored_in_production(monkeypatch):
    assert billing.api_base() == "https://test-api.creem.io/v1"
    _set(monkeypatch, DGATE_CREEM_TEST_MODE="0")
    assert billing.api_base() == "https://api.creem.io/v1"
    _set(monkeypatch, DGATE_CREEM_API_URL="http://127.0.0.1:9999/v1")
    assert billing.api_base() == "http://127.0.0.1:9999/v1"
    _set(monkeypatch, DGATE_ENV="production")
    assert billing.api_base() == "https://api.creem.io/v1"


def test_no_creem_secret_is_in_the_settings_repr(monkeypatch):
    _set(monkeypatch, DGATE_CREEM_API_KEY="creem_key_value", DGATE_CREEM_WEBHOOK_SECRET="whsec_value",
         DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS="whsec_old_value")
    text = repr(config.settings())
    assert "creem_key_value" not in text and "whsec_value" not in text and "whsec_old_value" not in text


# ---------------------------------------------------------------- signature (B2, B5)

def test_the_signature_is_hmac_sha256_hex_of_the_raw_body(monkeypatch):
    _set(monkeypatch, DGATE_CREEM_WEBHOOK_SECRET=SECRET)
    raw = b'{"id":"evt_1"}'
    assert billing.signature_ok(raw, _sig(raw))
    assert billing.signature_ok(raw, " " + _sig(raw) + " ")
    assert not billing.signature_ok(raw, _sig(raw, "whsec_wrong"))
    assert not billing.signature_ok(raw + b" ", _sig(raw))
    assert not billing.signature_ok(raw, _sig(raw).upper())
    assert not billing.signature_ok(raw, None) and not billing.signature_ok(raw, "")
    assert not billing.signature_ok(raw, "zz" * 32)


def test_without_a_secret_nothing_verifies():
    raw = b"{}"
    assert not billing.signature_ok(raw, _sig(raw, ""))


def test_both_secrets_verify_during_a_rotation(monkeypatch):
    _set(monkeypatch, DGATE_CREEM_WEBHOOK_SECRET="whsec_new", DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS="whsec_old")
    raw = b"{}"
    assert billing.signature_ok(raw, _sig(raw, "whsec_new")) and billing.signature_ok(raw, _sig(raw, "whsec_old"))
    assert not billing.signature_ok(raw, _sig(raw, "whsec_other"))


def test_the_comparison_is_constant_time():
    source = Path(billing.__file__).read_text(encoding="utf-8")
    body = source.split("def signature_ok", 1)[1].split("\ndef ", 1)[0]
    assert "hmac.compare_digest" in body and "==" not in body


# ---------------------------------------------------------------- event age (B2)

def _raw(at: datetime, **extra) -> bytes:
    return json.dumps({"id": "evt_1", "eventType": "subscription.paid", "created_at": int(at.timestamp() * 1000),
                       "object": {"id": "sub_1"}, **extra}).encode()


def test_an_event_within_creems_retry_window_is_accepted():
    for age in (timedelta(0), timedelta(hours=6), timedelta(hours=24, minutes=50)):
        assert billing.parse_event(_raw(NOW - age), NOW)["_at"] == (NOW - age).replace(microsecond=0)


@pytest.mark.parametrize("at", [NOW - timedelta(hours=25, minutes=1), NOW + timedelta(minutes=6)])
def test_a_stale_or_future_event_is_refused(at):
    with pytest.raises(AccountError) as e:
        billing.parse_event(_raw(at), NOW)
    assert (e.value.status, e.value.code) == (400, "stale_event")


@pytest.mark.parametrize("raw", [b"", b"null", b"[1]", b'{"id": "evt_1"}',
                                 b'{"id": 5, "eventType": "x", "created_at": 1, "object": {}}',
                                 b'{"id": "evt_1", "eventType": "x", "created_at": true, "object": {}}',
                                 b'{"id": "evt_1", "eventType": "x", "created_at": 1, "object": []}'])
def test_a_malformed_event_is_refused(raw):
    with pytest.raises(AccountError) as e:
        billing.parse_event(raw, NOW)
    assert e.value.status == 400


# ---------------------------------------------------------------- what each state allows

@pytest.mark.parametrize("status,plan", [("active", "pro"), ("trialing", "pro"), ("past_due", "pro"),
                                         ("unpaid", "free"), ("paused", "free"), ("expired", "free"),
                                         ("canceled", "free"), ("disputed", "free"), ("anything", "free")])
def test_the_plan_each_state_allows(status, plan):
    assert billing.plan_in_force("pro", status, NOW + timedelta(days=1), NOW) == plan


def test_a_scheduled_cancellation_keeps_the_plan_to_the_end_of_the_period():
    assert billing.plan_in_force("team", "scheduled_cancel", NOW + timedelta(seconds=1), NOW) == "team"
    assert billing.plan_in_force("team", "scheduled_cancel", NOW - timedelta(seconds=1), NOW) == "free"
    assert billing.plan_in_force(None, None, None, NOW) == "free"


def test_paid_features_are_pro_and_up_and_free_keeps_none_of_them():
    for feature in ("saved_searches", "email_alerts"):
        assert not billing.allows("free", feature)
        assert all(billing.allows(p, feature) for p in ("pro", "team", "consultant", "founding"))
    assert set(billing.FEATURES) == {"saved_searches", "email_alerts"}     # nothing "Coming" is gated


def test_while_no_plan_is_on_sale_nothing_is_withheld_and_once_it_is_the_plan_decides(monkeypatch):
    free = {"sub_plan": None, "sub_status": None, "sub_period_end": None}
    paid = {"sub_plan": "pro", "sub_status": "active", "sub_period_end": None}
    assert billing.may(free, "saved_searches") and billing.features(free) == ["saved_searches", "email_alerts"]
    _all(monkeypatch)
    assert not billing.may(free, "saved_searches") and billing.features(free) == []
    assert billing.may(paid, "email_alerts")
    with pytest.raises(AccountError) as e:
        billing.require(free, "saved_searches")
    assert (e.value.status, e.value.code) == (402, "plan_required")


# ---------------------------------------------------------------- where the browser may be sent

def test_only_https_creem_addresses_are_handed_to_the_browser(monkeypatch):
    assert billing._provider_url("https://checkout.creem.io/ch_1") == "https://checkout.creem.io/ch_1"
    assert billing._provider_url("https://creem.io/my-orders/login/x")
    for bad in ("http://checkout.creem.io/x", "https://creem.io.evil.example/x", "https://evilcreem.io/x",
                "https://user@checkout.creem.io/x", "javascript:alert(1)", None, 5, "https://x/" + "a" * 2000):
        with pytest.raises(AccountError):
            billing._provider_url(bad)
    _set(monkeypatch, DGATE_CREEM_API_URL="http://127.0.0.1:9999/v1")
    assert billing._provider_url("http://127.0.0.1:9999/checkout/ch_1")
    _set(monkeypatch, DGATE_ENV="production")
    with pytest.raises(AccountError):
        billing._provider_url("http://127.0.0.1:9999/checkout/ch_1")


# ---------------------------------------------------------------- deployment

def _service(text: str, name: str) -> str:
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", text, re.M | re.S)
    assert m, name
    return m.group(1)


def test_the_creem_key_and_secrets_go_to_the_api_only_and_the_product_ids_to_api_and_worker():
    text = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    api, worker, web = _service(text, "api"), _service(text, "worker"), _service(text, "web")
    for key in ("DGATE_CREEM_API_KEY", "DGATE_CREEM_WEBHOOK_SECRET", "DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS"):
        assert f"{key}:" in api and key not in worker and key not in web, key
    line = re.compile(r"^\s+(DGATE_CREEM_PRODUCT_\w+): (.+)$", re.M)
    assert sorted(line.findall(api)) == sorted(line.findall(worker))
    assert len(line.findall(api)) == 7


def test_the_env_example_names_every_setting_and_holds_no_value():
    text = (ROOT / "infra" / ".env.example").read_text(encoding="utf-8")
    for name in ["DGATE_CREEM_API_KEY", "DGATE_CREEM_WEBHOOK_SECRET", "DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS"] + \
            [f"DGATE_CREEM_PRODUCT_{k.upper()}" for k in config.Settings().creem_products]:
        assert re.search(rf"^{name}=$", text, re.M), name
    assert re.search(r"^DGATE_CREEM_TEST_MODE=1$", text, re.M)


def test_caddy_lets_the_webhook_through_to_the_site_with_its_own_size_cap():
    text = (ROOT / "infra" / "Caddyfile").read_text(encoding="utf-8")
    assert re.search(r"@billing_webhook path /api/billing/webhook\s+request_body @billing_webhook \{\s+max_size 64KB", text)
    assert re.search(r"@not_billing_webhook not path /api/billing/webhook\s+request_body @not_billing_webhook \{\s+max_size 4KB", text)
    public = re.search(r"@public path (.+)", text).group(1)
    assert "billing" not in public                                      # the API's routes stay unrouted
