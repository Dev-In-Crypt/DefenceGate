"""WP-79: registration with a password and e-mail confirmation (A7), sign-in with a delay per
address and per client (A8), password reset and change (A9), optional TOTP with recovery
codes (A10). docs/SECURITY_REQUIREMENTS.md; the shared helpers are in test_accounts.py."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import base64
import time

import pytest

from dgate import accounts, credentials
from tests.integration.test_accounts import PW, H, _token, client, login, register, sent, sign_in  # noqa: F401

pytestmark = pytest.mark.integration

NEW_PW = "lantern orbit cobalt river"


def _verify(client, box) -> None:
    assert client.post("/v1/account/auth/verify", json={"token": _token(box)}).status_code == 200


def _users(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM app_user").fetchone()["n"]


# ---------------------------------------------------------------- A7 registration

def test_an_account_signs_in_only_once_its_address_is_confirmed(client, sent, conn):
    assert register(client).status_code == 202
    assert sent[-1]["subject"] == "Confirm your DefenceGate account" and sent[-1]["to"] == "ann@example.com"
    row = conn.execute("SELECT email_verified_at, terms_version FROM app_user").fetchone()
    assert row["email_verified_at"] is None and row["terms_version"] == accounts.TERMS_VERSION
    r = login(client)
    assert (r.status_code, r.json()["error"]) == (403, "not_verified")
    wrong = login(client, password="not the password at all")
    assert (wrong.status_code, wrong.json()["error"]) == (401, "invalid_credentials")   # no hint without it
    _verify(client, sent)
    assert login(client).status_code == 200


def test_registering_an_address_that_has_an_account_answers_the_same_and_changes_nothing(
        client, sent, conn, monkeypatch):
    sign_in(client, sent)
    hashed = []
    real = credentials.hash_password
    monkeypatch.setattr(credentials, "hash_password", lambda p: hashed.append(p) or real(p))
    again = register(client, password=NEW_PW, ip="198.51.100.31")
    fresh = register(client, "new@example.com", password=NEW_PW, ip="198.51.100.32")
    assert (again.status_code, again.text) == (fresh.status_code, fresh.text) == (202, '{"ok":true}')
    assert len(hashed) == 2                                  # the same work on both paths
    already = [m for m in sent if m["to"] == "ann@example.com"][-1]
    assert already["subject"] == "You already have a DefenceGate account"
    assert "token=" not in already["body"] and "https://site.test/reset" in already["body"]
    assert login(client).status_code == 200                  # the password did not change
    assert login(client, password=NEW_PW).status_code == 401
    assert _users(conn) == 2


def test_a_newer_registration_of_an_unconfirmed_address_replaces_the_earlier_one(client, sent, conn):
    """Someone who registered a victim's address first never proved the mailbox: the owner's
    own registration takes the address over and the stranger's link dies."""
    register(client, password="stranger's long password", ip="192.0.2.66")
    stranger_link = _token(sent)
    register(client, password=PW, ip="198.51.100.5")
    owner_link = _token(sent)
    assert client.post("/v1/account/auth/verify", json={"token": stranger_link}).status_code == 400
    assert client.post("/v1/account/auth/verify", json={"token": owner_link}).status_code == 200
    assert login(client, password="stranger's long password").status_code == 401
    assert login(client).status_code == 200
    assert _users(conn) == 1


def test_a_password_is_checked_against_the_policy_at_registration(client, sent, conn):
    for password, code in (("eleven char", "password_too_short"), ("x1" * 70, "password_too_long"),
                           ("qwerty123456", "password_common"), ("my defencegate password", "password_common")):
        r = register(client, password=password)
        assert (r.status_code, r.json()["error"]) == (422, code), password
    assert _users(conn) == 0 and sent == []


# ---------------------------------------------------------------- A8 sign-in

def test_an_unknown_address_a_wrong_password_and_an_account_without_one_get_one_answer(client, sent, conn):
    sign_in(client, sent)
    conn.execute("INSERT INTO app_user (email_canonical, email_display, email_verified_at) "
                 "VALUES ('legacy@example.com', 'legacy@example.com', now())")
    conn.commit()
    answers = [login(client, "nobody@example.com", ip="198.51.100.11"),
               login(client, password="wrong but long enough", ip="198.51.100.12"),
               login(client, "legacy@example.com", ip="198.51.100.13")]
    assert {(r.status_code, r.text) for r in answers} == {
        (401, '{"error":"invalid_credentials","message":"the e-mail address or the password is wrong"}')}


def test_failed_sign_ins_delay_the_address_doubling_and_a_success_clears_them(client, sent, conn):
    sign_in(client, sent)
    for i in range(accounts.LOGIN_FREE):
        assert login(client, password="wrong but long enough", ip=f"192.0.2.{i}").status_code == 401
    held = login(client, ip="198.51.100.80")                 # the right password, from anywhere
    assert held.status_code == 429 and 1 <= int(held.headers["retry-after"]) <= accounts.LOGIN_DELAY
    conn.execute("UPDATE app_auth_event SET at = at - interval '31 seconds' WHERE kind LIKE 'login%%'")
    conn.commit()
    assert login(client, password="wrong but long enough").status_code == 401   # the next failure
    doubled = login(client)
    assert doubled.status_code == 429 and int(doubled.headers["retry-after"]) > accounts.LOGIN_DELAY
    conn.execute("UPDATE app_auth_event SET at = at - interval '61 seconds' WHERE kind LIKE 'login%%'")
    conn.commit()
    assert login(client).status_code == 200
    for _ in range(accounts.LOGIN_FREE - 1):                 # cleared: the free attempts are back
        assert login(client, password="wrong but long enough").status_code == 401
    assert login(client).status_code == 200


def test_the_delay_is_the_same_for_an_address_with_no_account(client, sent):
    codes = [login(client, "nobody@example.com", password="wrong but long enough", ip=f"192.0.2.{i}").status_code
             for i in range(accounts.LOGIN_FREE + 1)]
    assert codes == [401] * accounts.LOGIN_FREE + [429]


def test_one_client_is_delayed_across_addresses(client, sent):
    codes = [login(client, f"u{i}@example.com", password="wrong but long enough", ip="203.0.113.99").status_code
             for i in range(accounts.LOGIN_FREE_IP + 1)]
    assert codes == [401] * accounts.LOGIN_FREE_IP + [429]
    assert login(client, "other@example.com", password="wrong but long enough",
                 ip="203.0.113.100").status_code == 401        # another client is not


def test_signing_out_everywhere_ends_every_session(client, sent):
    s1, _ = sign_in(client, sent)
    s2, _ = sign_in(client, sent)
    assert client.delete("/v1/account/sessions", headers=H(s2)).status_code == 204
    assert client.post("/v1/account/auth/logout", headers=H(s2)).status_code == 204
    assert [client.get("/v1/account/me", headers=H(s)).status_code for s in (s1, s2)] == [401, 401]


# ---------------------------------------------------------------- A9 reset and change

def test_a_reset_for_an_unknown_address_answers_the_same_and_sends_nothing(client, sent):
    sign_in(client, sent)
    before = len(sent)
    known = client.post("/v1/account/auth/reset/request", json={"email": "ANN@example.com"},
                        headers={"X-DG-Client-IP": "198.51.100.51"})
    unknown = client.post("/v1/account/auth/reset/request", json={"email": "nobody@example.com"},
                          headers={"X-DG-Client-IP": "198.51.100.52"})
    assert (known.status_code, known.text) == (unknown.status_code, unknown.text) == (202, '{"ok":true}')
    assert len(sent) == before + 1 and sent[-1]["to"] == "ann@example.com"   # the stored spelling
    assert sent[-1]["subject"] == "Set a new DefenceGate password"


def test_a_reset_link_works_once_for_an_hour_and_ends_every_session(client, sent, conn):
    s1, _ = sign_in(client, sent)
    s2, _ = sign_in(client, sent)
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"})
    token = _token(sent, "/auth/reset")
    ttl = conn.execute("SELECT expires_at - created_at AS t FROM app_auth_token WHERE purpose = 'reset'"
                       ).fetchone()["t"]
    assert ttl.total_seconds() == 3600
    weak = client.post("/v1/account/auth/reset/confirm", json={"token": token, "password": "password1234"})
    assert weak.json()["error"] == "password_common"         # refused, and the link still works
    ok = client.post("/v1/account/auth/reset/confirm", json={"token": token, "password": NEW_PW})
    assert ok.status_code == 200
    assert [client.get("/v1/account/me", headers=H(s)).status_code for s in (s1, s2)] == [401, 401]
    assert client.post("/v1/account/auth/reset/confirm",
                       json={"token": token, "password": NEW_PW}).status_code == 400
    assert login(client).status_code == 401 and login(client, password=NEW_PW).status_code == 200
    stored = conn.execute("SELECT token_hash FROM app_auth_token WHERE purpose = 'reset'").fetchall()
    assert all(token.encode() not in bytes(r["token_hash"]) for r in stored)


def test_an_expired_or_superseded_reset_link_is_refused(client, sent, conn):
    sign_in(client, sent)
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"})
    first = _token(sent, "/auth/reset")
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"})
    second = _token(sent, "/auth/reset")
    assert client.post("/v1/account/auth/reset/confirm",
                       json={"token": first, "password": NEW_PW}).status_code == 400
    conn.execute("UPDATE app_auth_token SET expires_at = now() - interval '1 second'")
    conn.commit()
    assert client.post("/v1/account/auth/reset/confirm",
                       json={"token": second, "password": NEW_PW}).status_code == 400


def test_an_account_from_before_passwords_sets_one_through_the_reset(client, sent, conn):
    """Data compatibility: the accounts made by the sign-in link (confirmed, no password)."""
    conn.execute("INSERT INTO app_user (email_canonical, email_display, email_verified_at) "
                 "VALUES ('old@example.com', 'Old@example.com', now() - interval '5 days')")
    conn.commit()
    assert login(client, "old@example.com").status_code == 401
    client.post("/v1/account/auth/reset/request", json={"email": "old@example.com"})
    assert sent[-1]["to"] == "Old@example.com"
    client.post("/v1/account/auth/reset/confirm", json={"token": _token(sent, "/auth/reset"), "password": NEW_PW})
    assert login(client, "old@example.com", password=NEW_PW).status_code == 200


def test_a_reset_confirms_an_address_that_was_not_confirmed(client, sent):
    register(client)
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"},
                headers={"X-DG-Client-IP": "198.51.100.61"})
    client.post("/v1/account/auth/reset/confirm", json={"token": _token(sent, "/auth/reset"), "password": NEW_PW})
    assert login(client, password=NEW_PW).status_code == 200


def test_reset_requests_share_the_mail_limits(client, sent):
    codes = [client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"},
                         headers={"X-DG-Client-IP": f"192.0.2.{i}"}).status_code for i in range(7)]
    assert codes == [202] * accounts.LIMIT_PER_ADDRESS + [429, 429]


def test_changing_the_password_needs_the_current_one_and_ends_the_other_sessions(client, sent):
    other, _ = sign_in(client, sent)
    here, _ = sign_in(client, sent)
    wrong = client.post("/v1/account/me/password", headers=H(here),
                        json={"currentPassword": "not it at all", "newPassword": NEW_PW})
    assert (wrong.status_code, wrong.json()["error"]) == (403, "wrong_password")
    weak = client.post("/v1/account/me/password", headers=H(here),
                       json={"currentPassword": PW, "newPassword": "short"})
    assert weak.json()["error"] == "password_too_short"
    ok = client.post("/v1/account/me/password", headers=H(here), json={"currentPassword": PW, "newPassword": NEW_PW})
    assert ok.status_code == 200
    assert client.get("/v1/account/me", headers=H(here)).status_code == 200
    assert client.get("/v1/account/me", headers=H(other)).status_code == 401
    assert sent[-1]["subject"] == "Your DefenceGate password was changed"
    assert login(client, password=NEW_PW).status_code == 200


def test_wrong_current_passwords_count_as_failed_sign_ins(client, sent):
    here, _ = sign_in(client, sent)
    codes = [client.post("/v1/account/me/password", headers=H(here),
                         json={"currentPassword": "not it at all", "newPassword": NEW_PW}).status_code
             for _ in range(accounts.LOGIN_FREE + 1)]
    assert codes == [403] * accounts.LOGIN_FREE + [429]


# ---------------------------------------------------------------- A10 TOTP

def _enable_totp(client, session) -> tuple[bytes, list[str]]:
    setup = client.post("/v1/account/me/totp/setup", headers=H(session), json={"password": PW})
    assert setup.status_code == 200, setup.text
    key = setup.json()["secret"]
    secret = base64.b32decode(key + "=" * (-len(key) % 8))
    assert setup.json()["uri"].startswith("otpauth://totp/")
    wrong = client.post("/v1/account/me/totp/enable", headers=H(session), json={"code": "000000"})
    if wrong.status_code == 200:          # one chance in a million that 000000 is the code
        return secret, wrong.json()["recoveryCodes"]
    assert (wrong.status_code, wrong.json()["error"]) == (422, "invalid_code")
    on = client.post("/v1/account/me/totp/enable", headers=H(session),
                     json={"code": credentials.totp(secret, time.time())})
    assert on.status_code == 200, on.text
    return secret, on.json()["recoveryCodes"]


def _next_code(secret: bytes) -> str:
    """A code of the next step: valid (one step of drift) and later than the one just used."""
    return credentials.hotp(secret, int(time.time() // credentials.TOTP_STEP) + 1)


def test_with_totp_on_the_password_alone_gives_no_session(client, sent, conn):
    session, _ = sign_in(client, sent)
    assert client.post("/v1/account/me/totp/setup", headers=H(session),
                       json={"password": "not it at all"}).status_code == 403
    secret, codes = _enable_totp(client, session)
    assert len(codes) == 10
    assert client.get("/v1/account/me", headers=H(session)).json()["security"] == {"hasPassword": True, "totp": True}
    first = login(client)
    assert first.status_code == 200 and first.json()["secondStep"] is True and "session" not in first.json()
    code = _next_code(secret)
    done = client.post("/v1/account/auth/login/second", json={"ticket": first.json()["ticket"], "code": code})
    assert done.status_code == 200 and client.get("/v1/account/me", headers=H(done.json()["session"])).status_code == 200
    # a ticket works once, and a code works once
    assert client.post("/v1/account/auth/login/second",
                       json={"ticket": first.json()["ticket"], "code": code}).status_code == 400
    again = login(client).json()["ticket"]
    replay = client.post("/v1/account/auth/login/second", json={"ticket": again, "code": code})
    assert (replay.status_code, replay.json()["error"]) == (401, "invalid_code")


def test_a_recovery_code_works_once_instead_of_the_code(client, sent):
    session, _ = sign_in(client, sent)
    _, codes = _enable_totp(client, session)
    ticket = login(client).json()["ticket"]
    used = client.post("/v1/account/auth/login/second", json={"ticket": ticket, "code": codes[0].upper()})
    assert used.status_code == 200
    ticket = login(client).json()["ticket"]
    assert client.post("/v1/account/auth/login/second",
                       json={"ticket": ticket, "code": codes[0]}).status_code == 401
    assert client.post("/v1/account/auth/login/second",
                       json={"ticket": ticket, "code": codes[1]}).status_code == 200


def test_the_second_step_ticket_expires_and_wrong_codes_are_delayed(client, sent, conn):
    session, _ = sign_in(client, sent)
    secret, _ = _enable_totp(client, session)
    ticket = login(client).json()["ticket"]
    conn.execute("DELETE FROM app_auth_event")          # the wrong code of the set-up does not count here
    conn.commit()
    codes = [client.post("/v1/account/auth/login/second", json={"ticket": ticket, "code": "12345x"}).status_code
             for _ in range(accounts.LOGIN_FREE + 1)]
    assert codes == [401] * accounts.LOGIN_FREE + [429]
    conn.execute("DELETE FROM app_auth_event")
    conn.execute("UPDATE app_auth_token SET expires_at = now() - interval '1 second' WHERE purpose = 'mfa'")
    conn.commit()
    assert client.post("/v1/account/auth/login/second",
                       json={"ticket": ticket, "code": _next_code(secret)}).status_code == 400


def test_a_right_password_does_not_buy_new_free_guesses_at_the_code(client, sent):
    session, _ = sign_in(client, sent)
    _enable_totp(client, session)                      # one wrong code on the way (000000)
    ticket = login(client).json()["ticket"]
    for _ in range(accounts.LOGIN_FREE - 2):
        client.post("/v1/account/auth/login/second", json={"ticket": ticket, "code": "12345x"})
    ticket = login(client).json()["ticket"]            # the password again: the count stays
    client.post("/v1/account/auth/login/second", json={"ticket": ticket, "code": "12345x"})
    held = login(client)
    assert held.status_code == 429


def test_the_totp_key_and_the_recovery_codes_are_not_stored_usable(client, sent, conn):
    session, _ = sign_in(client, sent)
    secret, codes = _enable_totp(client, session)
    row = conn.execute("SELECT totp_secret_enc FROM app_user").fetchone()
    assert secret not in bytes(row["totp_secret_enc"])
    hashes = [bytes(r["code_hash"]) for r in conn.execute("SELECT code_hash FROM app_recovery_code").fetchall()]
    assert len(hashes) == 10 and not any(c.encode() in h or c.replace("-", "").encode() in h
                                          for c in codes for h in hashes)


def test_turning_totp_off_needs_the_password_and_a_reset_does_not_turn_it_off(client, sent, conn):
    session, _ = sign_in(client, sent)
    secret, _ = _enable_totp(client, session)
    assert client.post("/v1/account/me/totp/setup", headers=H(session), json={"password": PW}).status_code == 409
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"})
    client.post("/v1/account/auth/reset/confirm", json={"token": _token(sent, "/auth/reset"), "password": NEW_PW})
    assert login(client, password=NEW_PW).json()["secondStep"] is True          # the mailbox alone is not enough
    ticket = login(client, password=NEW_PW).json()["ticket"]
    session = client.post("/v1/account/auth/login/second",
                          json={"ticket": ticket, "code": _next_code(secret)}).json()["session"]
    assert client.post("/v1/account/me/totp/disable", headers=H(session),
                       json={"password": PW}).status_code == 403
    assert client.post("/v1/account/me/totp/disable", headers=H(session),
                       json={"password": NEW_PW}).status_code == 200
    assert "session" in login(client, password=NEW_PW).json()
    assert conn.execute("SELECT count(*) AS n FROM app_recovery_code").fetchone()["n"] == 0
    assert conn.execute("SELECT totp_secret_enc FROM app_user").fetchone()["totp_secret_enc"] is None
