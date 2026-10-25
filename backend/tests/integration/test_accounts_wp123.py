"""WP-123: what changed on top of WP-79 (test_accounts_passwords.py). When accounts open (a relay
that passed its health check, the published privacy notice for password accounts, the API's own
key in production), the plan chosen on the pricing page, deletion with the password, the full
export, the security log without secrets, the account key the site's server does not hold, and
the mails as text plus HTML through the real mailer (development catcher)."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import logging
import re
import time
from email import message_from_bytes, policy

import pytest

from dgate import accounts, config, credentials
from dgate.ops import mailer
from tests.integration.test_accounts import PW, H, _token, client, login, register, sent, sign_in  # noqa: F401
from tests.integration.test_accounts_passwords import NEW_PW, _enable_totp

pytestmark = pytest.mark.integration
REAL_SEND = mailer.send_mail          # before any fixture replaces it


def _status(client) -> bool:
    return client.get("/v1/account/status").json()["open"]


# ---------------------------------------------------------------- when accounts open

def test_accounts_stay_closed_until_the_privacy_notice_for_passwords_is_published(client, sent, monkeypatch):
    assert _status(client) is True                      # the fixture's state: as after publication
    monkeypatch.setattr(accounts, "PASSWORD_PRIVACY_VERSION", "1.7")
    monkeypatch.setattr(accounts, "PRIVACY_VERSION", "1.6")   # the notice in force on 25 October 2026
    assert _status(client) is False
    r = register(client)
    assert (r.status_code, r.json()["error"]) == (503, "not_open")
    monkeypatch.setattr(accounts, "PRIVACY_VERSION", "1.7")
    assert _status(client) is True


def test_the_shipped_versions_keep_accounts_closed():
    """The constants as committed: the published notice (1.6) predates password accounts, so
    no relay can open them until the owner publishes 1.7 (docs/legal/drafts/)."""
    assert accounts._version(accounts.PRIVACY_VERSION) < accounts._version(accounts.PASSWORD_PRIVACY_VERSION)


def test_a_relay_that_fails_its_health_check_keeps_accounts_closed(client, sent, monkeypatch):
    assert _status(client) is True
    monkeypatch.setattr(mailer, "check_relay", lambda: False)
    mailer.reset_check()
    assert _status(client) is False
    assert login(client).status_code == 503


def test_in_production_accounts_need_the_apis_own_key(client, sent, monkeypatch):
    monkeypatch.setenv("DGATE_ENV", "production")
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", "site-and-api-share-this")
    config.reset_cache()
    assert accounts.accounts_problem() == "DGATE_ACCOUNT_KEY"
    monkeypatch.setenv("DGATE_ACCOUNT_KEY", "only-the-api-holds-this")
    config.reset_cache()
    assert accounts.accounts_problem() is None


def test_the_totp_key_is_sealed_with_the_account_key_not_the_shared_secret(client, sent, conn, monkeypatch):
    monkeypatch.setenv("DGATE_ACCOUNT_KEY", "only-the-api-holds-this")
    config.reset_cache()
    shared = (config.settings().internal_secret or config.settings().app_password).encode()   # what the site holds too
    session, _ = sign_in(client, sent)
    secret, codes = _enable_totp(client, session)
    row = conn.execute("SELECT id, totp_secret_enc FROM app_user").fetchone()
    blob, uid = bytes(row["totp_secret_enc"]), str(row["id"])
    assert credentials.unseal(blob, b"only-the-api-holds-this", uid) == secret
    assert credentials.unseal(blob, shared, uid) is None
    stored = {bytes(r["code_hash"]) for r in conn.execute("SELECT code_hash FROM app_recovery_code")}
    assert credentials.recovery_code_hash(codes[0], b"only-the-api-holds-this") in stored
    assert credentials.recovery_code_hash(codes[0], shared) not in stored


# ---------------------------------------------------------------- the plan from the pricing page

def test_the_chosen_plan_is_remembered_through_confirmation_and_grants_nothing(client, sent, conn):
    assert register(client, plan="pro", billing="monthly").status_code == 202
    v = client.post("/v1/account/auth/verify", json={"token": _token(sent)})
    assert v.json() == {"ok": True, "plan": "pro", "billing": "monthly"}
    session = login(client).json()["session"]
    assert client.get("/v1/account/me", headers=H(session)).json()["plan"] == \
        {"current": "free", "chosen": "pro", "billing": "monthly"}
    assert conn.execute("SELECT plan FROM app_user").fetchone()["plan"] == "free"


def test_free_has_no_billing_period_and_an_unknown_plan_is_refused(client, sent, conn):
    assert register(client, plan="free", billing="yearly").status_code == 202
    row = conn.execute("SELECT plan_choice, billing_choice FROM app_user").fetchone()
    assert (row["plan_choice"], row["billing_choice"]) == ("free", None)
    assert register(client, "b@example.com", plan="platinum").status_code == 422
    assert register(client, "c@example.com", plan="pro", billing="weekly").status_code == 422


def test_registering_again_with_a_plan_changes_nothing_on_a_confirmed_account(client, sent, conn):
    sign_in(client, sent)
    again = register(client, plan="team", billing="yearly", ip="198.51.100.40")
    assert (again.status_code, again.text) == (202, '{"ok":true}')
    assert conn.execute("SELECT plan_choice FROM app_user").fetchone()["plan_choice"] is None


# ---------------------------------------------------------------- deletion and export

def test_deleting_needs_the_password_and_removes_every_owned_row(client, sent, conn):
    session, _ = sign_in(client, sent)
    _enable_totp(client, session)
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"})
    me = {"confirm": "ann@example.com"}
    assert client.request("DELETE", "/v1/account/me", headers=H(session), json=me).status_code == 403
    wrong = client.request("DELETE", "/v1/account/me", headers=H(session), json={**me, "password": NEW_PW})
    assert (wrong.status_code, wrong.json()["error"]) == (403, "wrong_password")
    assert client.request("DELETE", "/v1/account/me", headers=H(session), json={**me, "password": PW}).status_code == 204
    for table in ("app_user", "app_session", "app_saved_search", "app_shortlist", "app_follow",
                  "app_auth_token", "app_recovery_code"):
        assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0, table


def test_the_export_holds_everything_about_the_account_and_no_secret(client, sent, conn):
    session, _ = sign_in(client, sent)
    _enable_totp(client, session)
    body = client.get("/v1/account/export", headers=H(session))
    data = body.json()
    assert set(data) >= {"exportedAt", "account", "security", "sessions", "searches", "shortlist", "follows"}
    assert data["security"]["emailConfirmedAt"] and data["security"]["passwordChangedAt"]
    assert data["security"]["twoStepOnSince"] and data["security"]["recoveryCodesLeft"] == 10
    assert len(data["sessions"]) == 1 and data["sessions"][0]["lastSeenAt"]
    assert data["account"]["plan"]["current"] == "free"
    row = conn.execute("SELECT password_hash FROM app_user").fetchone()
    assert "argon2" not in body.text and row["password_hash"] not in body.text
    assert session not in body.text and "secret" not in body.text.lower()


# ---------------------------------------------------------------- security log

def test_audit_lines_hold_no_secret(client, sent, caplog):
    caplog.set_level(logging.INFO, logger="accounts")
    session, _ = sign_in(client, sent)
    confirm_token = re.findall(r"token=([A-Za-z0-9_-]{43})", " ".join(m["body"] for m in sent))
    client.post("/v1/account/me/password", headers=H(session), json={"currentPassword": PW, "newPassword": NEW_PW})
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"})
    reset = _token(sent, "/auth/reset")
    client.post("/v1/account/auth/reset/confirm", json={"token": reset, "password": PW})
    login(client, password="not the password at all")
    session = login(client).json()["session"]
    _, codes = _enable_totp(client, session)
    client.get("/v1/account/export", headers=H(session))
    client.request("DELETE", "/v1/account/me", headers=H(session), json={"confirm": "ann@example.com", "password": PW})
    text = "\n".join(r.getMessage() for r in caplog.records)
    for event in ("registered", "confirmed", "signed_in", "password_changed", "reset_requested",
                  "password_reset", "sign_in_failed", "totp_on", "export", "deleted"):
        assert f"event={event}" in text, event
    for secret in [PW, NEW_PW, session, reset, *confirm_token, *codes, "ann@example.com", "ann@"]:
        assert secret not in text, secret[:6]


# ---------------------------------------------------------------- mails through the real mailer

def test_account_mails_are_text_and_html_from_defencegate_with_the_same_link(client, sent, monkeypatch, tmp_path):
    monkeypatch.setattr(mailer, "send_mail", REAL_SEND)            # the real mailer, not the fixture's list ...
    monkeypatch.setenv("DGATE_MAIL_CATCHER_DIR", str(tmp_path))   # ... into the development catcher
    config.reset_cache()
    mailer.reset_check()
    assert _status(client) is True
    assert register(client).status_code == 202
    for _ in range(50):
        if list(tmp_path.glob("*.eml")):
            break
        time.sleep(0.05)
    (eml,) = tmp_path.glob("*.eml")
    msg = message_from_bytes(eml.read_bytes(), policy=policy.default)
    assert msg["From"] == "DefenceGate <no-reply@example.test>"
    assert msg["Subject"] == "Confirm your DefenceGate account"
    plain = msg.get_body(("plain",)).get_content()
    html = msg.get_body(("html",)).get_content()
    link = re.search(r"https://site\.test/auth/verify\?token=[A-Za-z0-9_-]{43}", plain).group(0)
    assert f'href="{link}"' in html and "<img" not in html
    assert client.post("/v1/account/auth/verify", json={"token": link.rsplit("=", 1)[1]}).status_code == 200
    config.reset_cache()
    mailer.reset_check()
