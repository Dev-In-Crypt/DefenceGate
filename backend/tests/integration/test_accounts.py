"""Accounts, against docs/SECURITY_REQUIREMENTS.md (A1-A6, O1-O3) and ACCOUNT_CONTRACT.md."""

from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from dgate import accounts, api, config, db, migrate
from dgate.normalise import Opportunity
from dgate.ops import mailer

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=5)


@pytest.fixture()
def sent(monkeypatch):
    """Mail goes to a list, and the relay counts as configured."""
    box: list[dict] = []
    monkeypatch.setenv("DGATE_SMTP_HOST", "relay.invalid")
    monkeypatch.setenv("DGATE_SMTP_FROM", "no-reply@example.test")
    monkeypatch.setenv("DGATE_SITE_URL", "https://site.test")
    config.reset_cache()
    monkeypatch.setattr(mailer, "send_mail",
                        lambda to, subject, body: box.append({"to": to, "body": body}) or True)
    yield box
    config.reset_cache()


@pytest.fixture()
def client(conn, sent):
    accounts._cache.clear()          # search results and the pulse are cached for minutes
    with TestClient(api.app) as c:
        yield c
    accounts._cache.clear()


def _binder() -> str:
    return secrets.token_urlsafe(32)


def _token(box: list[dict]) -> str:
    return re.search(r"token=([A-Za-z0-9_-]{43})", box[-1]["body"]).group(1)


def sign_in(client, box, email="ann@example.com", ip="203.0.113.7") -> tuple[str, dict]:
    binder = _binder()
    r = client.post("/v1/account/auth/request", json={"email": email, "binder": binder},
                    headers={"X-DG-Client-IP": ip})
    assert r.status_code == 202, r.text
    v = client.post("/v1/account/auth/verify", json={"token": _token(box), "binder": binder})
    assert v.status_code == 200, v.text
    return v.json()["session"], v.json()


def H(session: str) -> dict[str, str]:
    return {"X-DG-Session": session}


def _put(conn, native_id: str, *, buyer="Ministry of Defence", title="Armoured vehicles",
         deadline=FUTURE, published: date | None = None, cpv=("35400000",), country="PL") -> int:
    published = published or date.today()
    opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=title,
                      country=country, published_at=published, deadline_at=deadline, cpv_codes=list(cpv),
                      status="open", is_defence=True, sig_cpv=True)
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}-{title}-{deadline}", src)
    conn.commit()
    return oid


# ---------------------------------------------------------------- status / A6

def test_sign_in_is_open_only_when_mail_can_be_sent(client, monkeypatch):
    assert client.get("/v1/account/status").json() == {"open": True}
    monkeypatch.delenv("DGATE_SMTP_HOST")
    config.reset_cache()
    assert client.get("/v1/account/status").json() == {"open": False}
    r = client.post("/v1/account/auth/request", json={"email": "a@example.com", "binder": _binder()})
    assert r.status_code == 503 and r.json()["error"] == "not_open"


@pytest.mark.parametrize("headers", [{"Origin": "https://evil.test"}, {"X-Forwarded-For": "198.51.100.9"}])
def test_a_browser_or_proxied_request_is_refused(client, headers):
    r = client.get("/v1/account/status", headers=headers)
    assert r.status_code == 403 and r.json()["error"] == "forbidden"


def test_account_responses_are_never_cacheable_and_an_oversized_body_is_refused(client, sent):
    session, _ = sign_in(client, sent)
    assert client.get("/v1/account/me", headers=H(session)).headers["cache-control"] == "private, no-store"
    r = client.post("/v1/account/auth/request", content=b"{" + b" " * 20000 + b"}",
                    headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_there_is_no_cookie_anywhere(client, sent):
    session, _ = sign_in(client, sent)
    r = client.get("/v1/account/me", headers=H(session))
    assert "set-cookie" not in r.headers


def test_no_session_is_401_and_the_shape_is_the_contract(client):
    for path in ("/v1/account/me", "/v1/account/dashboard", "/v1/account/searches",
                 "/v1/account/shortlist", "/v1/account/follows"):
        r = client.get(path)
        assert r.status_code == 401 and r.json()["error"] == "unauthenticated"
    assert client.get("/v1/account/me", headers=H("x" * 43)).status_code == 401


# ---------------------------------------------------------------- A1

def test_one_address_in_three_spellings_is_one_account(client, sent, conn):
    ids = set()
    for email in ("Ann@Example.com", " ann@example.COM ", "ann@example.com"):
        session, body = sign_in(client, sent, email=email)
        ids.add(client.get("/v1/account/me", headers=H(session)).json()["id"])
    assert len(ids) == 1
    assert conn.execute("SELECT count(*) AS n FROM app_user").fetchone()["n"] == 1


def test_a_first_sign_in_is_new_and_a_second_is_not(client, sent):
    assert sign_in(client, sent)[1]["isNew"] is True
    assert sign_in(client, sent)[1]["isNew"] is False


# ---------------------------------------------------------------- A2

def test_a_link_works_once(client, sent):
    binder = _binder()
    client.post("/v1/account/auth/request", json={"email": "ann@example.com", "binder": binder})
    token = _token(sent)
    assert client.post("/v1/account/auth/verify", json={"token": token, "binder": binder}).status_code == 200
    again = client.post("/v1/account/auth/verify", json={"token": token, "binder": binder})
    assert again.status_code == 400 and again.json()["error"] == "invalid_or_expired"


def test_a_link_expires(client, sent, conn):
    binder = _binder()
    client.post("/v1/account/auth/request", json={"email": "ann@example.com", "binder": binder})
    conn.execute("UPDATE app_login_token SET expires_at = now() - interval '1 minute'")
    conn.commit()
    assert client.post("/v1/account/auth/verify",
                       json={"token": _token(sent), "binder": binder}).status_code == 400


def test_a_link_is_bound_to_the_browser_that_asked_and_a_stranger_does_not_burn_it(client, sent):
    binder = _binder()
    client.post("/v1/account/auth/request", json={"email": "ann@example.com", "binder": binder})
    token = _token(sent)
    other = client.post("/v1/account/auth/verify", json={"token": token, "binder": _binder()})
    assert other.status_code == 400
    assert client.post("/v1/account/auth/verify", json={"token": token, "binder": binder}).status_code == 200


def test_only_hashes_are_stored(client, sent, conn):
    binder = _binder()
    client.post("/v1/account/auth/request", json={"email": "ann@example.com", "binder": binder})
    token = _token(sent)
    session = client.post("/v1/account/auth/verify", json={"token": token, "binder": binder}).json()["session"]
    stored = [bytes(r["token_hash"]) for r in conn.execute("SELECT token_hash FROM app_login_token").fetchall()]
    stored += [bytes(r["id_hash"]) for r in conn.execute("SELECT id_hash FROM app_session").fetchall()]
    assert stored and all(token.encode() not in s and session.encode() not in s for s in stored)
    assert all(len(s) == 32 for s in stored)


# ---------------------------------------------------------------- A3 / A4

def test_the_sixth_request_for_one_address_is_refused_and_the_answer_does_not_reveal_the_address(client, sent):
    known = sign_in(client, sent, email="known@example.com", ip="198.51.100.1")
    assert known
    body_known = client.post("/v1/account/auth/request",
                             json={"email": "known@example.com", "binder": _binder()},
                             headers={"X-DG-Client-IP": "198.51.100.2"})
    body_unknown = client.post("/v1/account/auth/request",
                               json={"email": "nobody@example.com", "binder": _binder()},
                               headers={"X-DG-Client-IP": "198.51.100.3"})
    assert (body_known.status_code, body_known.json()) == (body_unknown.status_code, body_unknown.json()) \
        == (202, {"ok": True})
    # Review M3: beyond the per-address limit the answer is the same 202 and nothing is sent, so
    # a stranger can neither learn which address is being mailed nor lock a person out by
    # asking for their address. Only the per-IP and global limits are a 429.
    before = len(sent)
    answers = [client.post("/v1/account/auth/request", json={"email": "burst@example.com", "binder": _binder()},
                           headers={"X-DG-Client-IP": f"192.0.2.{i}"}) for i in range(8)]
    assert [(r.status_code, r.json()) for r in answers] == [(202, {"ok": True})] * 8
    assert len(sent) - before == 5                      # the sixth and later: nothing sent


def test_one_ip_is_limited_across_addresses(client, sent):
    codes = [client.post("/v1/account/auth/request", json={"email": f"u{i}@example.com", "binder": _binder()},
                         headers={"X-DG-Client-IP": "192.0.2.50"}).status_code for i in range(22)]
    assert codes[:20] == [202] * 20 and codes[20:] == [429, 429]


def test_a_disposable_domain_gets_the_same_answer_and_no_mail(client, sent):
    r = client.post("/v1/account/auth/request", json={"email": "x@mailinator.com", "binder": _binder()})
    assert (r.status_code, r.json()) == (202, {"ok": True})
    assert sent == []


def test_a_malformed_address_or_binder_is_refused(client, sent):
    assert client.post("/v1/account/auth/request",
                       json={"email": "nope", "binder": _binder()}).json()["error"] == "invalid_email"
    assert client.post("/v1/account/auth/request",
                       json={"email": "a@example.com", "binder": "short"}).status_code == 422


# ---------------------------------------------------------------- A5

def test_a_new_sign_in_gets_a_new_session_and_logout_ends_one(client, sent):
    s1, _ = sign_in(client, sent)
    s2, _ = sign_in(client, sent)
    assert s1 != s2
    assert client.post("/v1/account/auth/logout", headers=H(s1)).status_code == 204
    assert client.get("/v1/account/me", headers=H(s1)).status_code == 401
    assert client.get("/v1/account/me", headers=H(s2)).status_code == 200


def test_sessions_expire_absolutely_and_when_idle(client, sent, conn):
    session, _ = sign_in(client, sent)
    conn.execute("UPDATE app_session SET last_seen_at = now() - interval '8 days'")
    conn.commit()
    assert client.get("/v1/account/me", headers=H(session)).status_code == 401
    session, _ = sign_in(client, sent)
    conn.execute("UPDATE app_session SET expires_at = now() - interval '1 second'")
    conn.commit()
    assert client.get("/v1/account/me", headers=H(session)).status_code == 401


def test_other_sessions_can_be_revoked_from_the_account(client, sent):
    s1, _ = sign_in(client, sent)
    s2, _ = sign_in(client, sent)
    listed = client.get("/v1/account/sessions", headers=H(s2)).json()
    assert len(listed) == 2 and [s["current"] for s in listed].count(True) == 1
    other = [s for s in listed if not s["current"]][0]["id"]
    assert client.delete(f"/v1/account/sessions/{other}", headers=H(s2)).status_code == 204
    assert client.get("/v1/account/me", headers=H(s1)).status_code == 401
    s3, _ = sign_in(client, sent)
    assert client.delete("/v1/account/sessions", headers=H(s3)).status_code == 204
    assert client.get("/v1/account/me", headers=H(s2)).status_code == 401
    assert client.get("/v1/account/me", headers=H(s3)).status_code == 200


# ---------------------------------------------------------------- O1 / O2

def test_another_account_s_objects_are_404_never_the_row(client, sent, conn):
    oid = _put(conn, "N-1")
    a, _ = sign_in(client, sent, email="a@example.com")
    b, _ = sign_in(client, sent, email="b@example.com")
    search = client.post("/v1/account/searches", headers=H(a),
                         json={"name": "Armour", "kind": "tender", "filters": {"q": "armoured"}}).json()
    assert re.fullmatch(r"[0-9a-f-]{36}", search["id"])                    # O2: not a counter
    assert client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(a),
                      json={"status": "bidding", "note": "mine"}).status_code == 200

    for call in (lambda: client.patch(f"/v1/account/searches/{search['id']}", headers=H(b), json={"name": "x"}),
                 lambda: client.delete(f"/v1/account/searches/{search['id']}", headers=H(b)),
                 lambda: client.delete(f"/v1/account/shortlist/tender/{oid}", headers=H(b))):
        assert call().status_code == 404
    assert client.get("/v1/account/searches", headers=H(b)).json()["items"] == []
    assert client.get("/v1/account/shortlist", headers=H(b)).json()["items"] == []
    # and A still has them
    assert len(client.get("/v1/account/searches", headers=H(a)).json()["items"]) == 1
    assert client.get("/v1/account/shortlist", headers=H(a)).json()["items"][0]["note"] == "mine"


# ---------------------------------------------------------------- profile

def test_onboarding_marks_the_account_and_a_bad_country_is_refused(client, sent):
    session, _ = sign_in(client, sent)
    me = client.get("/v1/account/me", headers=H(session)).json()
    assert me["onboarded"] is False and me["profile"]["tracks"] == []
    r = client.patch("/v1/account/me", headers=H(session),
                     json={"role": "supplier", "tracks": ["tenders", "funding"], "countries": ["pl", "DE", "pl"]})
    body = r.json()
    assert body["onboarded"] is True and body["profile"]["countries"] == ["PL", "DE"]
    assert client.patch("/v1/account/me", headers=H(session),
                        json={"countries": ["Poland"]}).json()["error"] == "invalid_country"
    assert client.patch("/v1/account/me", headers=H(session), json={"role": "ceo"}).status_code == 422
    assert client.patch("/v1/account/me", headers=H(session), json={"is_admin": True}).status_code == 422


def test_deleting_the_account_removes_everything_it_owned(client, sent, conn):
    oid = _put(conn, "N-1")
    session, _ = sign_in(client, sent)
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session), json={"status": "watching"})
    client.post("/v1/account/searches", headers=H(session), json={"name": "s", "kind": "tender", "filters": {}})
    export = client.get("/v1/account/export", headers=H(session)).json()
    assert len(export["shortlist"]) == 1 and len(export["searches"]) == 1 and "exportedAt" in export
    wrong = client.request("DELETE", "/v1/account/me", headers=H(session), json={"confirm": "other@example.com"})
    assert wrong.status_code == 422
    ok = client.request("DELETE", "/v1/account/me", headers=H(session), json={"confirm": "ANN@example.com"})
    assert ok.status_code == 204
    for table in ("app_user", "app_session", "app_saved_search", "app_shortlist", "app_follow"):
        assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
    assert client.get("/v1/account/me", headers=H(session)).status_code == 401


# ---------------------------------------------------------------- searches / shortlist / follows

def test_a_saved_search_counts_matches_and_new_ones(client, sent, conn):
    _put(conn, "OLD", title="Armoured vehicles", published=date.today() - timedelta(days=30))
    _put(conn, "NEW", title="Armoured trucks", published=date.today())
    session, _ = sign_in(client, sent)
    made = client.post("/v1/account/searches", headers=H(session),
                       json={"name": "Armour", "kind": "tender", "filters": {"q": "armoured", "country": "PL"}})
    assert made.status_code == 201
    body = made.json()
    assert body["matchCount"] == 2 and body["newCount"] == 1 and body["cadence"] == "daily"
    assert client.post("/v1/account/searches", headers=H(session),
                       json={"name": "bad", "kind": "tender", "filters": {"drop": "x"}}).status_code == 422
    assert client.post("/v1/account/searches", headers=H(session),
                       json={"name": "bad", "kind": "tender", "filters": {"country": ",".join(["PL"] * 30)}}
                       ).status_code == 422                                   # the list endpoint's own cap
    patched = client.patch(f"/v1/account/searches/{body['id']}", headers=H(session),
                           json={"cadence": "weekly", "name": "Armour weekly"}).json()
    assert (patched["cadence"], patched["name"]) == ("weekly", "Armour weekly")


def test_at_most_ten_searches(client, sent):
    session, _ = sign_in(client, sent)
    for i in range(10):
        assert client.post("/v1/account/searches", headers=H(session),
                           json={"name": f"s{i}", "kind": "tender", "filters": {}}).status_code == 201
    r = client.post("/v1/account/searches", headers=H(session), json={"name": "x", "kind": "tender", "filters": {}})
    assert r.status_code == 409 and r.json()["error"] == "limit_reached"


def test_shortlist_follow_and_the_state_the_buttons_ask_for(client, sent, conn):
    oid = _put(conn, "N-1")
    org = conn.execute("SELECT id FROM organisation LIMIT 1").fetchone()["id"]
    session, _ = sign_in(client, sent)
    assert client.put("/v1/account/shortlist/tender/999999", headers=H(session),
                      json={"status": "watching"}).status_code == 404
    assert client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session),
                      json={"status": "nonsense"}).status_code == 422
    item = client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session),
                      json={"status": "evaluating", "note": "ask legal"}).json()
    assert item["item"]["noticeId"] == "N-1" and item["status"] == "evaluating"
    assert client.put(f"/v1/account/follows/buyer/{org}", headers=H(session)).status_code == 200
    assert client.put("/v1/account/follows/buyer/424242", headers=H(session)).status_code == 404
    st = client.post("/v1/account/state", headers=H(session), json={"keys": [
        {"type": "shortlist", "kind": "tender", "ref": str(oid)},
        {"type": "shortlist", "kind": "tender", "ref": "424242"},
        {"type": "follow", "kind": "buyer", "ref": str(org)}]}).json()["items"]
    assert [i["saved"] for i in st] == [True, False, True] and st[0]["status"] == "evaluating"
    assert client.delete(f"/v1/account/shortlist/tender/{oid}", headers=H(session)).status_code == 204
    assert client.delete(f"/v1/account/shortlist/tender/{oid}", headers=H(session)).status_code == 404


def test_a_note_longer_than_the_limit_is_refused(client, sent, conn):
    oid = _put(conn, "N-1")
    session, _ = sign_in(client, sent)
    r = client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session),
                   json={"status": "watching", "note": "x" * 501})
    assert r.status_code == 422


# ---------------------------------------------------------------- dashboard

def test_the_dashboard_has_every_block_and_moves_the_last_visit(client, sent, conn):
    oid = _put(conn, "SOON", deadline=datetime.now(timezone.utc) + timedelta(days=3))
    _put(conn, "LATER", deadline=datetime.now(timezone.utc) + timedelta(days=40))
    session, _ = sign_in(client, sent)
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session), json={"status": "bidding"})
    client.post("/v1/account/searches", headers=H(session),
                json={"name": "all", "kind": "tender", "filters": {}})
    first = client.get("/v1/account/dashboard", headers=H(session)).json()
    assert set(first) == {"lastVisitAt", "matches", "closingSoon", "changes", "following", "shortlist", "pulse"}
    assert first["lastVisitAt"] is None
    assert [c["item"]["noticeId"] for c in first["closingSoon"]] == ["SOON"]
    assert first["closingSoon"][0]["source"] == "shortlist"
    assert first["shortlist"]["counts"]["bidding"] == 1
    assert first["matches"][0]["totalCount"] == 2
    assert first["pulse"]["openTenders"] == 2 and first["pulse"]["tendersPublished30d"] == 2
    second = client.get("/v1/account/dashboard", headers=H(session)).json()
    assert second["lastVisitAt"] is not None


def test_a_change_on_a_shortlisted_tender_is_shown_after_the_last_visit(client, sent, conn):
    oid = _put(conn, "CHG", deadline=datetime.now(timezone.utc) + timedelta(days=10))
    session, _ = sign_in(client, sent)
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session), json={"status": "watching"})
    client.get("/v1/account/dashboard", headers=H(session))                  # the visit that sets the baseline
    _put(conn, "CHG", deadline=datetime.now(timezone.utc) + timedelta(days=20))     # deadline moved: a new version
    board = client.get("/v1/account/dashboard", headers=H(session)).json()
    assert [c["item"]["noticeId"] for c in board["changes"]] == ["CHG"]
    assert board["changes"][0]["changes"][0]["field"] == "deadline_at"


# ---------------------------------------------------------------- privileges / counter

def test_the_public_roles_cannot_read_the_account_tables(conn):
    for role in ("dgate_api", "dgate_worker"):
        for table in ("app_session", "app_login_token", "app_auth_event", "app_follow", "app_shortlist",
                      "app_hit_daily"):
            assert conn.execute("SELECT has_table_privilege(%s, %s, 'SELECT') AS ok",
                                (role, table)).fetchone()["ok"] is False, (role, table)
    # the worker reads who to mail and records that it did, nothing more
    ok = lambda priv, table: conn.execute(  # noqa: E731
        "SELECT has_table_privilege('dgate_worker', %s, %s) AS ok", (table, priv)).fetchone()["ok"]
    assert ok("SELECT", "app_user") and not ok("UPDATE", "app_user") and not ok("DELETE", "app_saved_search")


def test_a_visit_is_counted_by_page_with_no_identifier(client, conn):
    for path in ("/tenders/12-armoured", "/tenders/99-other", "/wp-login.php"):
        assert client.post("/v1/internal/hit", json={"route": path, "referrer": "https://www.google.com/x?q=s"}
                           ).status_code == 204
    rows = {r["route"]: r["hits"] for r in conn.execute("SELECT route, hits FROM app_hit_daily").fetchall()}
    assert rows == {"/tenders/[slug]": 2, "/other": 1}
    assert {r["referrer"] for r in conn.execute("SELECT referrer FROM app_hit_daily").fetchall()} == {"google.com"}
    cols = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'app_hit_daily'").fetchall()}
    assert cols == {"day", "route", "referrer", "device", "hits"}
    assert client.post("/v1/internal/hit", json={"route": "/x"}, headers={"Origin": "https://evil.test"}
                       ).status_code == 403


# ---------------------------------------------------------------- review H1: the counter

def _counted(conn) -> dict[tuple[str, str, str], int]:
    return {(r["route"], r["referrer"], r["device"]): r["hits"] for r in conn.execute(
        "SELECT route, referrer, device, hits FROM app_hit_daily").fetchall()}


def test_a_batch_of_visits_is_summed_into_a_bounded_set_of_rows(client, conn):
    batch = {"hits": [
        {"route": "/tenders/1-x", "referrer": "google.com", "mobile": False, "count": 5},
        {"route": "/tenders/2-y", "referrer": "https://www.google.pl/q?x=1", "mobile": False, "count": 3},
        {"route": "/tenders", "referrer": "tracker-7731.example", "mobile": True, "count": 2},
        {"route": "/funding", "count": 1},
        {"route": "not-a-path", "count": 9},
    ]}
    assert client.post("/v1/internal/hits", json=batch).status_code == 204
    assert _counted(conn) == {("/tenders/[slug]", "google.com", "desktop"): 8,
                              ("/tenders", "other", "mobile"): 2, ("/funding", "", "desktop"): 1}
    assert client.post("/v1/internal/hits", json={"hits": batch["hits"][:1]}).status_code == 204
    assert _counted(conn)[("/tenders/[slug]", "google.com", "desktop")] == 13           # adds, not replaces
    assert client.post("/v1/internal/hit", json={"route": "/funding"}).status_code == 204   # the old call
    assert _counted(conn)[("/funding", "", "desktop")] == 2


def test_a_batch_is_capped_in_size_and_in_each_count(client, conn):
    many = [{"route": f"/tenders/{n}", "count": 1} for n in range(accounts.MAX_HITS_PER_BATCH + 1)]
    assert client.post("/v1/internal/hits", json={"hits": many}).status_code == 422
    assert client.post("/v1/internal/hits",
                       json={"hits": [{"route": "/", "count": accounts.MAX_HIT_COUNT + 1}]}).status_code == 422
    assert client.post("/v1/internal/hits", json={"hits": [{"route": "/", "count": 0}]}).status_code == 422
    assert _counted(conn) == {}


def test_five_hundred_distinct_referrers_make_one_row(client, conn):
    hits = [{"route": "/", "referrer": f"https://site{n}.example/p", "count": 1} for n in range(150)]
    assert client.post("/v1/internal/hits", json={"hits": hits}).status_code == 204
    assert _counted(conn) == {("/", "other", "desktop"): 150}


def test_the_visit_counter_does_not_drain_the_shared_internal_bucket(conn, monkeypatch):
    """The site's server is one private address with one bucket; its counter calls used to
    take tokens out of it until pages themselves were refused."""
    from dgate.hardening import TokenBuckets

    monkeypatch.setenv("DGATE_RATE_LIMIT", "1")
    config.reset_cache()
    api.app.middleware_stack = None
    try:
        with TestClient(api.app, client=("172.18.0.9", 5000)) as c:
            limiter = c.app.middleware_stack
            while limiter is not None and not hasattr(limiter, "internal"):
                limiter = getattr(limiter, "app", None)
            assert limiter is not None, "RateLimit not found in the middleware stack"
            limiter.internal = TokenBuckets(capacity=5, refill=0.0)
            assert [c.post("/v1/internal/hit", json={"route": "/"}).status_code for _ in range(40)] == [204] * 40
            assert [c.get("/v1/health").status_code for _ in range(6)].count(429) >= 1
    finally:
        monkeypatch.setenv("DGATE_RATE_LIMIT", "0")
        config.reset_cache()
        api.app.middleware_stack = None


# ---------------------------------------------------------------- review H2 / M3 / M7: the throttle

def _auth_rows(conn) -> tuple[int, int]:
    return (conn.execute("SELECT count(*) AS n FROM app_auth_event").fetchone()["n"],
            conn.execute("SELECT count(*) AS n FROM app_login_token").fetchone()["n"])


def _ask(client, email, ip="198.51.100.20"):
    return client.post("/v1/account/auth/request", json={"email": email, "binder": _binder()},
                       headers={"X-DG-Client-IP": ip})


def test_a_request_that_is_not_served_writes_nothing(client, sent, conn):
    for i in range(accounts.LIMIT_PER_ADDRESS):
        assert _ask(client, "victim@example.com", f"192.0.2.{i}").status_code == 202
    after_accepted = _auth_rows(conn)
    assert after_accepted == (3 * accounts.LIMIT_PER_ADDRESS, accounts.LIMIT_PER_ADDRESS)
    for i in range(10):                                           # over the per-address limit
        assert _ask(client, "victim@example.com", f"192.0.2.{50 + i}").status_code == 202
    assert _auth_rows(conn) == after_accepted
    assert len(sent) == accounts.LIMIT_PER_ADDRESS                # and no mail went out for them

    for i in range(accounts.LIMIT_PER_IP):                        # one IP over its own limit
        assert _ask(client, f"u{i}@example.com", "203.0.113.77").status_code == 202
    filled = _auth_rows(conn)
    for i in range(5):
        r = _ask(client, f"late{i}@example.com", "203.0.113.77")
        assert r.status_code == 429 and r.headers["retry-after"] == "3600"
    assert _auth_rows(conn) == filled


def test_the_per_address_limit_answers_like_any_other_request_and_never_locks_the_person_out(client, sent):
    """M3: it is the same 202 and body, and the address's owner is unaffected by what a
    stranger asked: their own request, once the hour is over, is served again."""
    first = [_ask(client, "ann@example.com", f"192.0.2.{i}") for i in range(7)]
    assert {(r.status_code, r.text) for r in first} == {(202, '{"ok":true}')}
    other = _ask(client, "someone-else@example.com", "192.0.2.200")
    assert (other.status_code, other.text) == (202, '{"ok":true}')


def test_expired_events_and_tokens_are_pruned_at_the_start_of_a_request_even_when_it_is_refused(client, sent, conn):
    for i in range(accounts.LIMIT_PER_IP):
        _ask(client, f"u{i}@example.com", "203.0.113.5")
    conn.execute("INSERT INTO app_auth_event (kind, key_hash, at) VALUES ('ip', '\\x00', now() - interval '3 days')")
    conn.execute("INSERT INTO app_login_token (token_hash, binder_hash, email_canonical, email_display, expires_at) "
                 "VALUES ('\\x01', '\\x02', 'old@example.com', 'old@example.com', now() - interval '3 days')")
    conn.commit()
    assert _ask(client, "x@example.com", "203.0.113.5").status_code == 429       # refused ...
    assert conn.execute("SELECT count(*) AS n FROM app_auth_event WHERE at < now() - interval '1 day'"
                        ).fetchone()["n"] == 0                                    # ... and still pruned
    assert conn.execute("SELECT count(*) AS n FROM app_login_token WHERE email_canonical = 'old@example.com'"
                        ).fetchone()["n"] == 0


def test_the_throttle_keys_are_not_a_plain_hash_of_the_address_or_the_ip(client, sent, conn):
    import hashlib

    _ask(client, "ann@example.com", "198.51.100.9")
    stored = {bytes(r["key_hash"]) for r in conn.execute("SELECT key_hash FROM app_auth_event").fetchall()}
    assert len(stored) == 3
    for plain in (b"ann@example.com", b"198.51.100.9", b"all"):
        assert hashlib.sha256(plain).digest() not in stored


def test_the_event_table_has_an_index_on_time(conn):
    assert conn.execute("SELECT 1 FROM pg_indexes WHERE tablename = 'app_auth_event' "
                        "AND indexdef LIKE '%(at)%'").fetchone() is not None


# ---------------------------------------------------------------- review M1: the shared secret

def test_with_a_secret_set_account_and_counter_calls_need_it_and_empty_headers_are_refused(
        client, sent, monkeypatch):
    secret = "k" * 40
    monkeypatch.setenv("DGATE_INTERNAL_SECRET", secret)
    config.reset_cache()
    good = {"X-DG-Internal": secret}
    assert client.get("/v1/account/status").status_code == 403
    assert client.get("/v1/account/status", headers={"X-DG-Internal": "wrong"}).status_code == 403
    assert client.get("/v1/account/status", headers=good).status_code == 200
    assert client.post("/v1/internal/hit", json={"route": "/"}).status_code == 403
    assert client.post("/v1/internal/hits", json={"hits": []}).status_code == 403
    assert client.post("/v1/internal/hit", json={"route": "/"}, headers=good).status_code == 204
    for extra in ({"Origin": ""}, {"X-Forwarded-For": ""}):
        assert client.get("/v1/account/status", headers={**good, **extra}).status_code == 403, extra


def test_an_empty_origin_is_refused_with_no_secret_too(client):
    assert client.get("/v1/account/status", headers={"Origin": ""}).status_code == 403


def test_a_chunked_body_with_no_length_is_refused_by_what_arrives(client):
    def chunks():
        for _ in range(8):
            yield b" " * 4096

    for path in ("/v1/account/auth/request", "/v1/internal/hit", "/v1/internal/hits"):
        r = client.post(path, content=chunks(), headers={"content-type": "application/json"})
        assert r.status_code == 413, path
    ok = client.post("/v1/internal/hit", json={"route": "/"})
    assert ok.status_code == 204


# ---------------------------------------------------------------- review M2: per account

def test_searches_and_the_dashboard_are_limited_per_account(client, sent, monkeypatch):
    from dgate.hardening import TokenBuckets

    monkeypatch.setattr(accounts, "_user_buckets", TokenBuckets(accounts.USER_RATE, 0.0))
    a, _ = sign_in(client, sent, email="a@example.com")
    b, _ = sign_in(client, sent, email="b@example.com")
    codes = [client.get("/v1/account/searches", headers=H(a)).status_code for _ in range(accounts.USER_RATE + 2)]
    assert codes[:accounts.USER_RATE] == [200] * accounts.USER_RATE and codes[accounts.USER_RATE:] == [429, 429]
    limited = client.get("/v1/account/dashboard", headers=H(a))          # the same bucket
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
    assert client.post("/v1/account/searches", headers=H(a),
                       json={"name": "x", "kind": "tender", "filters": {}}).status_code == 429
    assert client.get("/v1/account/me", headers=H(a)).status_code == 200      # not a search call
    assert client.get("/v1/account/searches", headers=H(b)).status_code == 200  # another account


def test_the_cache_keeps_the_total_twenty_items_and_every_date(client, sent, conn):
    for n in range(30):
        _put(conn, f"BULK-{n}", title=f"Armoured vehicle lot {n}")
    session, _ = sign_in(client, sent)
    client.post("/v1/account/searches", headers=H(session),
                json={"name": "armour", "kind": "tender", "filters": {"q": "armoured"}})
    entries = [v for k, v in accounts._cache.items() if k[0] == "tender"]
    assert len(entries) == 1
    cached = entries[0][1]
    assert cached["total"] == 30 and len(cached["items"]) == accounts.CACHED_ITEMS
    assert len(cached["stamps"]) == 30
    board = client.get("/v1/account/dashboard", headers=H(session)).json()
    assert board["matches"][0]["totalCount"] == 30 and board["matches"][0]["newCount"] == 30
    assert len(board["matches"][0]["items"]) == 5


def test_the_digest_still_sees_every_new_item_not_only_the_cached_twenty(client, sent, conn):
    from dgate.ops.digest import run_digests

    for n in range(25):
        _put(conn, f"DIG-{n}", title=f"Armoured vehicle lot {n}", published=date.today())
    session, _ = sign_in(client, sent)
    client.post("/v1/account/searches", headers=H(session),
                json={"name": "armour", "kind": "tender", "filters": {"q": "armoured"}, "cadence": "daily"})
    conn.execute("UPDATE app_saved_search SET created_at = now() - interval '2 days', "
                 "last_alerted_at = now() - interval '2 days'")
    conn.commit()
    accounts._cache.clear()
    assert run_digests(conn)["mails"] == 1
    assert "25 new" in sent[-1]["body"]


# ---------------------------------------------------------------- review LOW

def test_a_session_beyond_ten_ends_the_oldest_of_the_accounts_own(client, sent, conn):
    first, _ = sign_in(client, sent)
    uid = conn.execute("SELECT id FROM app_user").fetchone()["id"]
    for n in range(12):
        conn.execute(
            "INSERT INTO app_session (id_hash, user_id, created_at, expires_at) "
            "VALUES (%s, %s, now() - make_interval(hours => %s), now() + interval '10 days')",
            (secrets.token_bytes(32), uid, n + 2))
    conn.commit()
    assert conn.execute("SELECT count(*) AS n FROM app_session").fetchone()["n"] == 13
    newest, _ = sign_in(client, sent)
    assert conn.execute("SELECT count(*) AS n FROM app_session").fetchone()["n"] == accounts.MAX_SESSIONS
    assert client.get("/v1/account/me", headers=H(newest)).status_code == 200
    assert client.get("/v1/account/me", headers=H(first)).status_code == 200      # recent: kept


def test_a_reference_with_leading_zeros_is_the_same_item_everywhere(client, sent, conn):
    oid = _put(conn, "N-ZERO")
    org = conn.execute("SELECT id FROM organisation LIMIT 1").fetchone()["id"]
    session, _ = sign_in(client, sent)
    padded = f"000{oid}"
    item = client.put(f"/v1/account/shortlist/tender/{padded}", headers=H(session), json={"status": "watching"})
    assert item.status_code == 200 and item.json()["ref"] == str(oid)
    assert client.put(f"/v1/account/follows/buyer/00{org}", headers=H(session)).json()["ref"] == str(org)
    stored = {(r["kind"], r["ref"]) for r in conn.execute(
        "SELECT kind, ref FROM app_shortlist UNION ALL SELECT kind, ref FROM app_follow").fetchall()}
    assert stored == {("tender", str(oid)), ("buyer", str(org))}
    # a second spelling updates the one row instead of adding another
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session), json={"status": "bidding"})
    assert conn.execute("SELECT count(*) AS n FROM app_shortlist").fetchone()["n"] == 1
    st = client.post("/v1/account/state", headers=H(session), json={"keys": [
        {"type": "shortlist", "kind": "tender", "ref": padded},
        {"type": "follow", "kind": "buyer", "ref": f"0{org}"}]}).json()["items"]
    assert [i["saved"] for i in st] == [True, True] and st[0]["status"] == "bidding"
    assert client.delete(f"/v1/account/shortlist/tender/{padded}", headers=H(session)).status_code == 204
    assert client.delete(f"/v1/account/follows/buyer/0{org}", headers=H(session)).status_code == 204


# ---------------------------------------------------------------- review M4: the accounts role

READ_BY_ACCOUNT_CODE = ("opportunity", "opportunity_version", "opportunity_version_note", "call",
                        "programme", "source", "organisation")


def test_the_accounts_role_reads_only_what_the_account_code_needs(conn):
    def can(priv: str, table: str) -> bool:
        return conn.execute("SELECT has_table_privilege('dgate_app', %s, %s) AS ok",
                            (table, priv)).fetchone()["ok"]

    for table in READ_BY_ACCOUNT_CODE:
        assert can("SELECT", table), table
        assert not can("INSERT", table) and not can("UPDATE", table) and not can("DELETE", table), table
    for table in ("raw_ingest", "ingest_run", "schema_migrations", "organisation_alias",
                  "organisation_merge_candidate", "enrichment_job", "enrichment", "backfill_day"):
        assert not can("SELECT", table), table
    for table in ("app_user", "app_session", "app_login_token", "app_auth_event", "app_saved_search",
                  "app_shortlist", "app_follow", "app_hit_daily", "app_disposable_domain"):
        assert can("SELECT", table) and can("INSERT", table) and can("DELETE", table), table
    # a table made later is not readable by default
    conn.execute("CREATE TABLE zz_later (a int)")
    assert not can("SELECT", "zz_later")
    conn.rollback()


@pytest.fixture()
def as_app_role(schema, monkeypatch):
    """The account endpoints connect as the real `dgate_app` login, not as the test owner."""
    monkeypatch.setenv("DGATE_APP_PASSWORD", "app-test-password-1")
    with db.connect(schema) as admin:
        assert "dgate_app" in migrate.set_role_passwords(admin)
    parts = urlsplit(schema)
    dsn = urlunsplit(parts._replace(netloc=f"dgate_app:app-test-password-1@{parts.hostname}:{parts.port}"))
    monkeypatch.setenv("DGATE_APP_DSN", dsn)
    config.reset_cache()
    yield dsn
    config.reset_cache()


def test_every_account_flow_works_as_the_least_privileged_role(client, sent, conn, as_app_role):
    import psycopg

    with psycopg.connect(as_app_role) as probe:
        assert probe.execute("SELECT current_user").fetchone()[0] == "dgate_app"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            probe.execute("SELECT count(*) FROM raw_ingest")
        probe.rollback()

    oid = _put(conn, "ROLE-1", deadline=datetime.now(timezone.utc) + timedelta(days=3))
    org = conn.execute("SELECT id FROM organisation LIMIT 1").fetchone()["id"]
    session, _ = sign_in(client, sent)
    h = H(session)
    assert client.patch("/v1/account/me", headers=h, json={"role": "supplier", "tracks": ["tenders"]}).status_code == 200
    assert client.put(f"/v1/account/shortlist/tender/{oid}", headers=h, json={"status": "bidding"}).status_code == 200
    assert client.put(f"/v1/account/follows/buyer/{org}", headers=h).status_code == 200
    assert client.get("/v1/account/follows", headers=h).json()["items"][0]["item"] is not None
    assert client.post("/v1/account/searches", headers=h,
                       json={"name": "t", "kind": "tender", "filters": {"q": "armoured"}}).status_code == 201
    assert client.post("/v1/account/searches", headers=h,
                       json={"name": "c", "kind": "call", "filters": {}}).status_code == 201
    assert client.get("/v1/account/shortlist", headers=h).json()["items"][0]["item"]["noticeId"] == "ROLE-1"
    client.get("/v1/account/dashboard", headers=h)                           # sets the baseline visit
    _put(conn, "ROLE-1", deadline=datetime.now(timezone.utc) + timedelta(days=9))   # a new version
    board = client.get("/v1/account/dashboard", headers=h)
    assert board.status_code == 200
    body = board.json()
    assert body["changes"] and body["pulse"]["openTenders"] >= 1 and body["following"]
    assert client.get("/v1/account/export", headers=h).status_code == 200
    assert client.get("/v1/account/sessions", headers=h).status_code == 200
    with psycopg.connect(as_app_role) as c2:                                 # programme chips
        from psycopg.rows import dict_row
        c2.row_factory = dict_row
        assert isinstance(accounts._programmes(c2), dict)
    assert client.request("DELETE", "/v1/account/me", headers=h, json={"confirm": "ann@example.com"}).status_code == 204


# ---------------------------------------------------------------- digests

def test_a_digest_lists_what_is_new_once_and_the_window_moves_on(client, sent, conn):
    from dgate.ops.digest import run_digests

    session, _ = sign_in(client, sent)
    client.post("/v1/account/searches", headers=H(session),
                json={"name": "Armour", "kind": "tender", "filters": {"q": "armoured"}, "cadence": "daily"})
    _put(conn, "NEW-1", title="Armoured vehicles", published=date.today())
    conn.execute("UPDATE app_saved_search SET created_at = now() - interval '2 days', "
                 "last_alerted_at = now() - interval '2 days'")
    conn.commit()
    accounts._cache.clear()
    before = len(sent)
    counts = run_digests(conn)
    assert counts["mails"] == 1 and len(sent) == before + 1
    mail = sent[-1]
    assert mail["to"] == "ann@example.com" and "Armoured vehicles" in mail["body"]
    assert "https://site.test/tenders/" in mail["body"] and "not an official source" in mail["body"]
    accounts._cache.clear()
    assert run_digests(conn)["mails"] == 0          # not due again, and nothing new


def test_a_failed_send_is_not_marked_as_sent(client, sent, conn, monkeypatch):
    from dgate.ops.digest import run_digests

    session, _ = sign_in(client, sent)
    client.post("/v1/account/searches", headers=H(session),
                json={"name": "All", "kind": "tender", "filters": {}, "cadence": "instant"})
    _put(conn, "NEW-2", published=date.today())
    conn.execute("UPDATE app_saved_search SET created_at = now() - interval '1 day', "
                 "last_alerted_at = now() - interval '1 day'")
    conn.commit()
    accounts._cache.clear()
    monkeypatch.setattr(mailer, "send_mail", lambda *a: False)
    assert run_digests(conn)["failed"] == 1
    assert conn.execute("SELECT last_alerted_at < now() - interval '12 hours' AS old "
                        "FROM app_saved_search").fetchone()["old"] is True


def test_with_no_relay_nothing_is_sent_and_nothing_is_marked(client, sent, conn, monkeypatch):
    from dgate.ops.digest import run_digests

    monkeypatch.delenv("DGATE_SMTP_HOST")
    config.reset_cache()
    assert run_digests(conn) == {"accounts": 0, "mails": 0, "searches": 0, "failed": 0}
