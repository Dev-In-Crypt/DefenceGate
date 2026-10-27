"""WP-153: keys of the data API, against docs/SECURITY_REQUIREMENTS.md K1-K3, O1-O2, and the licence filter
(a key reads only the sources of DGATE_API_KEY_SOURCES, TED by default)."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import hashlib
import logging
from datetime import date

import pytest

from dgate import apikeys, config, db
from dgate.normalise import Opportunity
from tests.integration.test_accounts import FUTURE, PW, H, client, sent, sign_in  # noqa: F401

pytestmark = pytest.mark.integration

KEYS = "/v1/account/keys"


@pytest.fixture()
def on(client, monkeypatch):
    monkeypatch.setenv("DGATE_API_KEYS_OPEN", "1")
    config.reset_cache()
    apikeys._minute.clear()
    apikeys._day.clear()
    return client


def _put(conn, source: str, native_id: str, *, ted_ref: str | None = None, title="Armoured vehicles") -> int:
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw="Ministry of Defence",
                      title_original=title, country="ES", published_at=date.today(), deadline_at=FUTURE,
                      cpv_codes=["35400000"], status="open", is_defence=True, sig_cpv=True, ted_ref=ted_ref)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, "Ministry of Defence", "ES", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    conn.commit()
    return oid


def make_key(client, session, scopes=("tenders", "archive"), name="My script", password=PW):
    return client.post(KEYS, json={"name": name, "scopes": list(scopes), "password": password}, headers=H(session))


def B(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


# ---------------------------------------------------------------- closed by default

def test_keys_are_closed_by_default(client, sent):
    session, _ = sign_in(client, sent)
    r = make_key(client, session)
    assert (r.status_code, r.json()["error"]) == (403, "api_keys_closed")
    assert client.get(KEYS, headers=H(session)).json()["open"] is False
    assert "api_keys" not in client.get("/v1/account/me", headers=H(session)).json()["features"]
    r = client.get("/v1/opportunities", headers=B("dgk_" + "0" * 12 + "_" + "a" * 43))
    assert (r.status_code, r.json()["error"]) == (401, "api_keys_closed")


# ---------------------------------------------------------------- K1, K2: issued once, stored hashed, fresh sign-in

def test_a_key_is_shown_once_and_only_its_hash_is_stored(on, sent, conn):
    session, _ = sign_in(on, sent)
    assert "api_keys" in on.get("/v1/account/me", headers=H(session)).json()["features"]
    r = make_key(on, session)
    assert r.status_code == 201, r.text
    key = r.json()["key"]
    assert apikeys._KEY.match(key) and r.json()["prefix"] in key
    listed = on.get(KEYS, headers=H(session)).json()
    assert key not in str(listed) and listed["keys"][0]["name"] == "My script"
    assert listed["events"][0]["event"] == "created"
    row = conn.execute("SELECT * FROM api_key").fetchone()
    assert bytes(row["key_hash"]) == hashlib.sha256(key.encode()).digest()
    assert key not in str(dict(row)) and (row["expires_at"] - row["created_at"]).days == 365
    assert len(apikeys._KEY.match(key).group(2)) == 43       # 256 bits, URL-safe base64 (it may hold "_" itself)


def test_creating_or_revoking_a_key_needs_the_password(on, sent):
    session, _ = sign_in(on, sent)
    r = make_key(on, session, password="not the password")
    assert (r.status_code, r.json()["error"]) == (403, "wrong_password")
    kid = make_key(on, session).json()["id"]
    r = on.post(f"{KEYS}/{kid}/revoke", json={"password": "wrong again"}, headers=H(session))
    assert r.status_code == 403
    assert on.post(f"{KEYS}/{kid}/revoke", json={"password": PW}, headers=H(session)).status_code == 200


def test_at_most_five_active_keys(on, sent):
    session, _ = sign_in(on, sent)
    for i in range(apikeys.MAX_KEYS):
        assert make_key(on, session, name=f"k{i}").status_code == 201
    r = make_key(on, session, name="one too many")
    assert (r.status_code, r.json()["error"]) == (409, "too_many_keys")


# ---------------------------------------------------------------- O1: another account's key

def test_another_accounts_key_is_a_404_and_never_listed(on, sent):
    ann, _ = sign_in(on, sent, "ann@example.com")
    bob, _ = sign_in(on, sent, "bob@example.com", ip="203.0.113.8")
    kid = make_key(on, ann).json()["id"]
    assert on.get(KEYS, headers=H(bob)).json()["keys"] == []
    r = on.post(f"{KEYS}/{kid}/revoke", json={"password": PW}, headers=H(bob))
    assert (r.status_code, r.json()["error"]) == (404, "not_found")
    assert on.get(KEYS, headers=H(ann)).json()["keys"][0]["revokedAt"] is None


# ---------------------------------------------------------------- reading with a key: licence filter and scopes

def test_a_key_reads_only_the_licensed_sources(on, sent, conn):
    ted = _put(conn, "ted", "100-2026")
    es = _put(conn, "es_placsp", "ES-1", ted_ref="100-2026")
    session, _ = sign_in(on, sent)
    key = make_key(on, session).json()["key"]

    anonymous = on.get("/v1/opportunities?collapse=false").json()
    assert {o["id"] for o in anonymous} == {ted, es}
    r = on.get("/v1/opportunities?collapse=false", headers=B(key))
    assert r.status_code == 200, r.text
    assert [o["id"] for o in r.json()] == [ted]
    assert r.json()[0]["same_notice"] == []              # the Spanish twin is another source's record
    assert r.headers["cache-control"] == "private, no-store"

    r = on.get("/v1/opportunities?source=es_placsp", headers=B(key))
    assert (r.status_code, r.json()["error"]) == (403, "source_not_licensed")
    assert on.get(f"/v1/opportunities/{es}", headers=B(key)).status_code == 404
    assert on.get(f"/v1/opportunities/{es}/versions", headers=B(key)).status_code == 404
    assert on.get(f"/v1/opportunities/{ted}", headers=B(key)).json()["source"] == "ted"
    assert on.get(f"/v1/opportunities/{ted}/versions", headers=B(key)).json()["version_count"] == 1
    # the anonymous answers are unchanged
    assert on.get(f"/v1/opportunities/{es}").status_code == 200


def test_the_licence_list_is_a_setting(on, sent, conn, monkeypatch):
    _put(conn, "ted", "100-2026")
    es = _put(conn, "es_placsp", "ES-1")
    session, _ = sign_in(on, sent)
    key = make_key(on, session).json()["key"]
    monkeypatch.setenv("DGATE_API_KEY_SOURCES", "ted,es_placsp")
    config.reset_cache()
    assert len(on.get("/v1/opportunities", headers=B(key)).json()) == 2
    assert [o["id"] for o in on.get("/v1/opportunities?source=es_placsp", headers=B(key)).json()] == [es]


def test_a_key_reads_its_scopes_and_its_routes_only(on, sent, conn):
    ted = _put(conn, "ted", "100-2026")
    session, _ = sign_in(on, sent)
    key = make_key(on, session, scopes=("tenders",)).json()["key"]
    assert on.get(f"/v1/opportunities/{ted}", headers=B(key)).status_code == 200
    r = on.get(f"/v1/opportunities/{ted}/versions", headers=B(key))
    assert (r.status_code, r.json()["error"]) == (403, "out_of_scope")
    for path in ("/v1/tenders", "/v1/suppliers", "/v1/buyers", "/v1/health"):
        assert on.get(path, headers=B(key)).json()["error"] == "not_available", path
    r = on.post("/v1/readiness/assess", json={}, headers=B(key))
    assert (r.status_code, r.json()["error"]) == (403, "not_available")


def test_an_unknown_revoked_or_expired_key_is_refused(on, sent, conn):
    session, _ = sign_in(on, sent)
    made = make_key(on, session).json()
    key = made["key"]
    assert on.get("/v1/opportunities", headers=B(key)).status_code == 200
    for bad in (key[:-1] + ("A" if key[-1] != "A" else "B"), "dgk_short", "", key.upper()):
        r = on.get("/v1/opportunities", headers=B(bad))
        assert (r.status_code, r.json()["error"]) == (401, "invalid_key"), bad
    assert on.get("/v1/opportunities", headers={"Authorization": f"Basic {key}"}).status_code == 401

    conn.execute("UPDATE api_key SET expires_at = now() - interval '1 second'")
    conn.commit()
    assert on.get("/v1/opportunities", headers=B(key)).status_code == 401
    conn.execute("UPDATE api_key SET expires_at = now() + interval '1 day'")
    conn.commit()
    assert on.post(f"{KEYS}/{made['id']}/revoke", json={"password": PW}, headers=H(session)).status_code == 200
    assert on.get("/v1/opportunities", headers=B(key)).status_code == 401
    events = [e["event"] for e in on.get(KEYS, headers=H(session)).json()["events"]]
    assert events == ["revoked", "created"]


# ---------------------------------------------------------------- K3: the key's own limits

def test_a_key_over_its_rate_gets_429_with_retry_after(on, sent, conn, monkeypatch):
    monkeypatch.setenv("DGATE_RATE_LIMIT", "1")              # the address limiter on: the key is not charged there
    config.reset_cache()
    session, _ = sign_in(on, sent)
    made = make_key(on, session).json()
    conn.execute("UPDATE api_key SET rate_per_minute = 2")
    conn.commit()
    assert [on.get("/v1/opportunities", headers=B(made["key"])).status_code for _ in range(3)] == [200, 200, 429]
    r = on.get("/v1/opportunities", headers=B(made["key"]))
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert on.get("/v1/opportunities").status_code == 200   # the address itself is not spent


def test_usage_and_last_use_are_recorded(on, sent, conn):
    session, _ = sign_in(on, sent)
    key = make_key(on, session).json()["key"]
    for _ in range(3):
        on.get("/v1/opportunities", headers=B(key))
    listed = on.get(KEYS, headers=H(session)).json()["keys"][0]
    assert listed["requestsToday"] == 3 and listed["lastUsedAt"] is not None


# ---------------------------------------------------------------- the account: export, deletion, the security log

def test_export_lists_the_keys_without_their_hash_and_deletion_removes_them(on, sent, conn):
    session, _ = sign_in(on, sent)
    key = make_key(on, session).json()["key"]
    on.get("/v1/opportunities", headers=B(key))
    exported = on.get("/v1/account/export", headers=H(session)).json()["apiKeys"]
    assert exported[0]["name"] == "My script" and sum(exported[0]["requestsByDay"].values()) == 1
    assert "key" not in exported[0] and "hash" not in str(exported).lower()
    r = on.request("DELETE", "/v1/account/me", json={"confirm": "ann@example.com", "password": PW}, headers=H(session))
    assert r.status_code == 204, r.text
    for table in ("api_key", "api_key_usage", "api_key_event"):
        assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0, table


def test_the_security_log_names_the_key_prefix_never_the_key(on, sent, caplog):
    session, _ = sign_in(on, sent)
    with caplog.at_level(logging.INFO, logger="accounts"):
        made = make_key(on, session).json()
    assert f"key={made['prefix']}" in caplog.text and made["key"] not in caplog.text
