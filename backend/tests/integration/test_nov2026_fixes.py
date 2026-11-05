"""The fixes of November 2026 on a real Postgres: account mail limits (invitations, IPv6 prefixes, the global ceiling's
reserve), the sign-in delay per address and client, confirmation with the password, two-step sign-in, the reset and the
API keys, the export, the security log, the saved-search page, the client profiles' authors, API keys refused before a
lookup, slow account routes off the accounts pool, the public caches and the worker role."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import json
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from dgate import (
    accounts,
    apikeys,
    config,
    expiring,
    hardening,
    partners,
    sell_report,
    stats,
    workspace,
)
from tests.integration.test_accounts import PW, H, _token, client, login, register, sent, sign_in  # noqa: F401
from tests.integration.test_accounts_passwords import NEW_PW, _enable_totp
from tests.integration.test_api_keys_wp153 import B, make_key
from tests.integration.test_api_keys_wp153 import sign_in as licensed_sign_in
from tests.integration.test_wp157_workspace import team

pytestmark = pytest.mark.integration


def _ask(client, email, ip):
    return client.post("/v1/account/auth/reset/request", json={"email": email}, headers={"X-DG-Client-IP": ip})


def _events(conn, kind: str, value: str, n: int) -> None:
    conn.execute("INSERT INTO app_auth_event (kind, key_hash) SELECT %s, %s FROM generate_series(1, %s)",
                 (kind, accounts._event_key(kind, value), n))
    conn.commit()


def _count(conn, kind: str, value: str) -> int:
    return conn.execute("SELECT count(*) AS n FROM app_auth_event WHERE kind = %s AND key_hash = %s",
                        (kind, accounts._event_key(kind, value))).fetchone()["n"]


def _invite(client, session, email, ip="198.51.100.200"):
    return client.post("/v1/account/workspace/invites", headers={**H(session), "X-DG-Client-IP": ip}, json={"email": email})


# ---------------------------------------------------------------- invitations: limits that a cancel cannot undo

def test_invitations_are_limited_per_account_even_when_each_is_cancelled(client, sent, conn):
    a, _ = sign_in(client, sent)
    assert client.post("/v1/account/workspace", headers=H(a)).status_code == 201
    for i in range(workspace.INVITES_PER_DAY):
        made = _invite(client, a, f"p{i}@example.com", ip=f"198.51.100.{i + 1}")
        assert made.status_code == 201, made.text
        assert client.delete(f"/v1/account/workspace/invites/{made.json()['id']}", headers=H(a)).status_code == 204
    over = _invite(client, a, "one-more@example.com", ip="192.0.2.200")
    assert (over.status_code, over.json()["error"]) == (429, "rate_limited") and int(over.headers["retry-after"]) > 3600
    # a new workspace does not start the count again
    assert client.delete("/v1/account/workspace", headers=H(a)).status_code == 204
    assert client.post("/v1/account/workspace", headers=H(a)).status_code == 201
    assert _invite(client, a, "one-more@example.com", ip="192.0.2.201").status_code == 429
    assert len([m for m in sent if "/app/team/join" in m["body"]]) == workspace.INVITES_PER_DAY


def test_one_invitation_an_hour_to_one_address_whatever_was_cancelled(client, sent):
    a, _ = sign_in(client, sent)
    client.post("/v1/account/workspace", headers=H(a))
    made = _invite(client, a, "target@example.com")
    assert made.status_code == 201
    client.delete(f"/v1/account/workspace/invites/{made.json()['id']}", headers=H(a))
    assert _invite(client, a, "target@example.com", ip="192.0.2.77").status_code == 429


def test_invitations_count_toward_the_account_mail_limits(client, sent, conn):
    a, _ = sign_in(client, sent)
    client.post("/v1/account/workspace", headers=H(a))
    before = _count(conn, "all", "all")
    assert _invite(client, a, "first@example.com").status_code == 201
    assert _count(conn, "all", "all") == before + 1                     # the global ceiling's count
    assert _count(conn, "addr", "first@example.com") == 1               # the invited address's own five an hour
    _events(conn, "all", "all", accounts.LIMIT_GLOBAL)
    r = _invite(client, a, "second@example.com", ip="192.0.2.90")
    assert r.status_code == 429
    assert len([m for m in sent if "/app/team/join" in m["body"]]) == 1


# ---------------------------------------------------------------- account mails: IPv6 prefixes and the reserve

def test_every_ipv6_prefix_inside_one_48_is_one_client(client, sent):
    """/64s and /56s of one /48 share the client's limit (hardening.client_key)."""
    ips = [f"2001:db8:7:{i:02x}{j:02x}::1" for i in range(5) for j in range(5)][:accounts.LIMIT_PER_IP + 2]
    codes = [_ask(client, f"v6-{n}@example.com", ip).status_code for n, ip in enumerate(ips)]
    assert codes == [202] * accounts.LIMIT_PER_IP + [429, 429]


def test_bulk_senders_cannot_spend_the_ceiling_kept_for_first_requests(client, sent, conn):
    _events(conn, "all", "all", accounts.LIMIT_GLOBAL_REPEAT)
    _events(conn, "ip", "203.0.113.50", 1)                            # this client has sent in the hour
    assert _ask(client, "bulk@example.com", "203.0.113.50").status_code == 429
    fresh = _ask(client, "person@example.com", "198.51.100.60")         # a first request is still served
    assert (fresh.status_code, fresh.text) == (202, '{"ok":true}')
    assert _ask(client, "person2@example.com", "198.51.100.60").status_code == 429   # its second is not
    _events(conn, "all", "all", accounts.LIMIT_GLOBAL - accounts.LIMIT_GLOBAL_REPEAT)
    assert _ask(client, "late@example.com", "198.51.100.61").status_code == 429      # the ceiling holds for everyone
    assert _count(conn, "all", "all") <= accounts.LIMIT_GLOBAL + 1


# ---------------------------------------------------------------- sign-in: no lockout by strangers

def test_a_stranger_slows_an_address_down_but_cannot_lock_its_owner_out(client, sent, conn):
    session, _ = sign_in(client, sent)
    for i in range(accounts.LOGIN_FREE_ADDR + 5):                       # from many clients
        assert login(client, password="wrong but long enough", ip=f"192.0.2.{i}").status_code in (401, 429)
    held = login(client, ip="198.51.100.9")                             # the owner, from its own client
    assert held.status_code == 429 and int(held.headers["retry-after"]) <= accounts.LOGIN_ADDR_DELAY_MAX
    # a signed-in session is never blocked by it: password change, key management, deletion
    assert client.post("/v1/account/me/password", headers={**H(session), "X-DG-Client-IP": "198.51.100.9"},
                       json={"currentPassword": PW, "newPassword": NEW_PW}).status_code == 200
    conn.execute("UPDATE app_auth_event SET at = at - interval '61 seconds' WHERE kind LIKE 'login%%'")
    conn.commit()
    assert login(client, password=NEW_PW, ip="198.51.100.9").status_code == 200      # slowed, never locked


def test_the_lockout_is_the_address_from_one_client(client, sent):
    sign_in(client, sent)
    for _ in range(accounts.LOGIN_FREE):
        login(client, password="wrong but long enough", ip="192.0.2.1")
    assert login(client, ip="192.0.2.1").status_code == 429             # that client waits
    assert login(client, ip="198.51.100.10").status_code == 200         # the owner elsewhere does not


def test_the_security_log_has_refusals_and_a_client_tag_never_the_address(client, sent, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="accounts")
    sign_in(client, sent)
    for _ in range(accounts.LOGIN_FREE + 1):
        login(client, password="wrong but long enough", ip="192.0.2.44")
    monkeypatch.setenv("DGATE_API_KEYS_OPEN", "1")
    config.reset_cache()
    apikeys._failed.clear()
    client.get("/v1/opportunities", headers=B(f"dgk_{secrets.token_hex(6)}_{secrets.token_urlsafe(32)}"))
    text = "\n".join(r.getMessage() for r in caplog.records)
    tag = accounts._client_tag("192.0.2.44")
    assert "event=sign_in_failed user=" in text and f"client={tag}" in text
    assert "event=sign_in_held" in text and "event=api_key_refused" in text
    assert "192.0.2.44" not in text and "203.0.113.7" not in text and "testclient" not in text


# ---------------------------------------------------------------- confirmation with the password

def test_a_registration_by_someone_else_cannot_be_confirmed_by_the_mailbox_owner(client, sent, conn):
    register(client, "victim@example.com", password="stranger's long password", ip="192.0.2.66")
    link = _token(sent)
    r = client.post("/v1/account/auth/verify", json={"token": link, "password": PW})
    assert (r.status_code, r.json()["error"]) == (403, "wrong_password")
    assert login(client, "victim@example.com", password="stranger's long password").json()["error"] == "not_verified"
    register(client, "victim@example.com", password=PW, ip="198.51.100.5")          # the owner registers: replaces it
    assert client.post("/v1/account/auth/verify", json={"token": link, "password": PW}).status_code == 400
    assert client.post("/v1/account/auth/verify", json={"token": _token(sent), "password": PW}).status_code == 200
    assert login(client, "victim@example.com", password="stranger's long password").status_code == 401
    assert login(client, "victim@example.com").status_code == 200


def test_a_wrong_password_does_not_use_the_link_up(client, sent):
    register(client)
    link = _token(sent)
    assert client.post("/v1/account/auth/verify", json={"token": link, "password": "not it at all"}).status_code == 403
    assert client.post("/v1/account/auth/verify", json={"token": link, "password": PW}).status_code == 200
    assert client.post("/v1/account/auth/verify", json={"token": link}).status_code == 422          # the password is asked


# ---------------------------------------------------------------- two-step sign-in, reset, keys

def test_turning_two_step_off_needs_a_code_and_turning_it_on_ends_the_other_sessions(client, sent, conn):
    here, _ = sign_in(client, sent)
    other, _ = sign_in(client, sent)
    _, codes = _enable_totp(client, here)
    assert client.get("/v1/account/me", headers=H(other)).status_code == 401           # signed out
    assert client.get("/v1/account/me", headers=H(here)).status_code == 200
    off = "/v1/account/me/totp/disable"
    assert client.post(off, headers=H(here), json={"password": PW}).status_code == 422        # the password alone
    r = client.post(off, headers=H(here), json={"password": PW, "code": "12345x"})
    assert (r.status_code, r.json()["error"]) == (403, "invalid_code")
    assert client.get("/v1/account/me", headers=H(here)).json()["security"]["totp"] is True
    assert client.post(off, headers=H(here), json={"password": PW, "code": codes[0]}).status_code == 200
    assert client.get("/v1/account/me", headers=H(here)).json()["security"]["totp"] is False


def test_a_password_reset_revokes_the_api_keys_and_the_export_holds_checkouts_and_key_events(client, sent, conn,
                                                                                             monkeypatch):
    monkeypatch.setenv("DGATE_API_KEYS_OPEN", "1")
    config.reset_cache()
    apikeys._minute.clear()
    apikeys._day.clear()
    apikeys._failed.clear()
    session, _ = licensed_sign_in(client, sent)
    key = make_key(client, session).json()["key"]
    assert client.get("/v1/opportunities", headers=B(key)).status_code == 200
    client.post("/v1/account/auth/reset/request", json={"email": "ann@example.com"})
    assert client.post("/v1/account/auth/reset/confirm",
                       json={"token": _token(sent, "/auth/reset"), "password": NEW_PW}).status_code == 200
    assert client.get("/v1/opportunities", headers=B(key)).status_code == 401
    assert client.get("/v1/account/me", headers=H(session)).status_code == 401           # every session ended
    session = login(client, password=NEW_PW).json()["session"]
    conn.execute("INSERT INTO billing_checkout (account_id, plan, period, product_id) "
                 "SELECT id, 'pro', 'monthly', 'prod_test' FROM app_user")
    conn.commit()
    out = client.get("/v1/account/export", headers=H(session)).json()
    assert [e["event"] for e in out["apiKeyEvents"]] == ["created", "revoked"]
    assert [(c["plan"], c["productId"]) for c in out["checkouts"]] == [("pro", "prod_test")]
    assert "key_hash" not in json.dumps(out)


# ---------------------------------------------------------------- saved searches: a page per request

def test_the_search_list_runs_one_page_of_searches(client, sent, conn, monkeypatch):
    session, _ = sign_in(client, sent)
    conn.execute("INSERT INTO app_saved_search (owner_id, name, kind, filters, cadence) "
                 "SELECT id, 'S' || g, 'tender', '{}', 'off' FROM app_user, generate_series(1, 60) AS g")
    conn.commit()
    runs = []
    real = accounts.run_search
    monkeypatch.setattr(accounts, "run_search", lambda *a, **k: runs.append(1) or real(*a, **k))
    first = client.get("/v1/account/searches", headers=H(session)).json()
    assert (len(first["items"]), first["total"], first["pageSize"]) == (accounts.SEARCH_PAGE, 60, accounts.SEARCH_PAGE)
    assert len(runs) <= accounts.SEARCH_PAGE
    second = client.get("/v1/account/searches?page=2", headers=H(session)).json()
    assert len(second["items"]) == 10 and not {s["id"] for s in first["items"]} & {s["id"] for s in second["items"]}


# ---------------------------------------------------------------- client profiles: the owner's are the owner's

def test_a_member_changes_only_the_client_profiles_it_made(client, sent):
    a, b = team(client, sent)
    acme = client.post("/v1/account/clients", headers=H(a), json={"name": "Acme Defence GmbH"}).json()
    assert client.patch(f"/v1/account/clients/{acme['id']}", headers=H(b), json={"note": "x"}).status_code == 403
    assert client.delete(f"/v1/account/clients/{acme['id']}", headers=H(b)).status_code == 403
    own = client.post("/v1/account/clients", headers=H(b), json={"name": "Bravo SL"}).json()
    assert client.patch(f"/v1/account/clients/{own['id']}", headers=H(b), json={"note": "mine"}).status_code == 200
    assert client.patch(f"/v1/account/clients/{own['id']}", headers=H(a), json={"note": "owner"}).status_code == 200
    names = [c["name"] for c in client.get("/v1/account/clients", headers=H(b)).json()["items"]]
    assert names == ["Acme Defence GmbH", "Bravo SL"]                  # both still seen by the member


# ---------------------------------------------------------------- API keys: refused before any lookup

@pytest.fixture()
def keys_on(client, monkeypatch):
    monkeypatch.setenv("DGATE_API_KEYS_OPEN", "1")
    monkeypatch.setenv("DGATE_RATE_LIMIT", "1")
    config.reset_cache()
    apikeys._minute.clear()
    apikeys._day.clear()
    apikeys._failed.clear()
    return client


def test_bad_keys_are_refused_by_address_before_any_lookup(keys_on, monkeypatch):
    looked = []
    real = apikeys.authenticate
    monkeypatch.setattr(apikeys, "authenticate", lambda raw: looked.append(1) or real(raw))
    monkeypatch.setattr(apikeys._failed, "clock", lambda: 1000.0)       # no refill while the loop runs
    got = [keys_on.get("/v1/opportunities", headers=B(f"dgk_{secrets.token_hex(6)}_{secrets.token_urlsafe(32)}"))
           for _ in range(300)]
    codes = [r.status_code for r in got]
    assert codes[:apikeys.FAILED_KEYS_PER_MINUTE] == [401] * apikeys.FAILED_KEYS_PER_MINUTE
    assert set(codes[apikeys.FAILED_KEYS_PER_MINUTE:]) == {429}
    assert len(looked) <= apikeys.FAILED_KEYS_PER_MINUTE + 1
    assert int(got[-1].headers["retry-after"]) >= 1


def test_a_key_over_its_rate_writes_no_usage_for_refused_requests(keys_on, sent, conn):
    session, _ = licensed_sign_in(keys_on, sent)
    key = make_key(keys_on, session).json()["key"]
    conn.execute("UPDATE api_key SET rate_per_minute = 2")
    conn.commit()
    codes = [keys_on.get("/v1/opportunities", headers=B(key)).status_code for _ in range(10)]
    assert codes == [200, 200] + [429] * 8
    assert conn.execute("SELECT requests FROM api_key_usage").fetchone()["requests"] == 2


def test_key_lookups_have_their_own_bound(keys_on, monkeypatch):
    bounds = []
    real = apikeys.db.bounded_connect
    monkeypatch.setattr(apikeys.db, "bounded_connect", lambda *a, **k: bounds.append((a[1], a[3] if len(a) > 3 else
                                                                                      k.get("name"))) or real(*a, **k))
    keys_on.get("/v1/opportunities", headers=B(f"dgk_{secrets.token_hex(6)}_{secrets.token_urlsafe(32)}"))
    assert bounds == [(apikeys.KEY_CONNECTIONS, "apikey")]


# ---------------------------------------------------------------- slow account routes: off the accounts pool

def test_parallel_reports_hold_no_accounts_connection_and_are_capped_per_account(client, sent, conn, monkeypatch):
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "1")
    monkeypatch.setenv("DGATE_APP_CONNECTIONS", "2")
    monkeypatch.setenv("DGATE_POOL_WAIT_MS", "500")
    config.reset_cache()
    monkeypatch.setattr(sell_report, "build", lambda conn, inp, **kw: time.sleep(1.5) or {"profile": {}})
    a, _ = sign_in(client, sent, email="ann@example.com")
    b, _ = sign_in(client, sent, email="bob@example.com", ip="203.0.113.8")
    body = {"country": "ES", "cpv": ["34330000"]}

    def report():
        return client.post("/v1/account/sell-report", headers=H(a), json=body).status_code

    with ThreadPoolExecutor(4) as pool:
        running = [pool.submit(report) for _ in range(4)]
        time.sleep(0.5)
        t0 = time.monotonic()
        me = client.get("/v1/account/me", headers=H(b))
        took = time.monotonic() - t0
        codes = sorted(f.result() for f in running)
    assert me.status_code == 200 and took < 1.0, (me.status_code, took)
    assert codes == [200] * accounts.MAX_RUNNING + [429] * (4 - accounts.MAX_RUNNING)
    assert conn.execute("SELECT count(*) AS n FROM sell_report_use").fetchone()["n"] == accounts.MAX_RUNNING


# ---------------------------------------------------------------- public caches

@pytest.fixture()
def cached(monkeypatch):
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()
    yield
    stats.reset_cache()


def test_a_call_s_partners_are_cached_under_its_id_whatever_the_slug(client, conn, cached, monkeypatch):
    from tests.integration.test_wp32 import call

    cid, _ = call(conn, "c-1", "EDF-2025-DA-SPACE-X")
    conn.commit()
    ran = []
    monkeypatch.setattr(partners, "partners_of", lambda *a, **k: ran.append(1) or {"partners": [], "total": 0})
    for suffix in ("a", "b", "x1", "x2"):
        assert client.get(f"/v1/funding/{cid}-{suffix}/partners").status_code == 200
    assert len(ran) == 1
    assert client.get("/v1/funding/not-a-call/partners").status_code == 404
    assert hardening.request_cost(f"/v1/funding/{cid}-x/partners", {}) >= 5


def test_contracts_ending_soon_is_cached_and_priced(client, conn, cached, monkeypatch):
    ran = []
    monkeypatch.setattr(expiring, "ending", lambda *a, **k: ran.append(1) or {"items": [], "total": 0})
    for _ in range(3):
        assert client.get("/v1/tenders/ending?within=12").status_code == 200
    assert len(ran) == 1
    assert hardening.request_cost("/v1/tenders/ending", {}) >= 5


# ---------------------------------------------------------------- roles

def test_the_worker_role_cannot_create_databases(conn):
    row = conn.execute("SELECT rolcreatedb FROM pg_roles WHERE rolname = 'dgate_worker'").fetchone()
    assert row is not None and row["rolcreatedb"] is False
