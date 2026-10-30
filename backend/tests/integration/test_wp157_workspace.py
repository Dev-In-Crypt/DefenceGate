"""WP-157 on a real Postgres: the team workspace and the client profiles (docs/verification/features/wp157-selfcheck.md).

Each gate in both states (no plan on sale: nobody refused, WP-124; plans on sale: the owner's split), the invitation built to
docs/SECURITY_REQUIREMENTS.md (one-time, hashed, expiring, bound to the invited address, no oracle, rate-limited), O1 across
workspaces (404, never the row), the shared rows, the owner's plan for members, leaving and removal."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import re

import pytest

from dgate import accounts, billing, workspace
from tests.integration.test_accounts import H, _put, client, sent, sign_in  # noqa: F401
from tests.integration.test_billing_wp124 import _billing_env

pytestmark = pytest.mark.integration

ANN, BOB, CAROL = "ann@example.com", "bob@example.com", "carol@example.com"


def on_plan(conn, email: str, plan: str | None) -> None:
    conn.execute("DELETE FROM billing_subscription WHERE account_id = (SELECT id FROM app_user WHERE email_canonical = %s)",
                 (email,))
    if plan:
        conn.execute("""INSERT INTO billing_subscription (account_id, plan, period, status, last_event_id, last_event_at)
                        SELECT id, %s, 'yearly', 'active', 'evt_test', now() FROM app_user WHERE email_canonical = %s""",
                     (plan, email))
    conn.commit()


def invite_token(sent: list[dict], to: str) -> str:
    mail = [m for m in sent if m["to"] == to and "/app/team/join" in m["body"]][-1]
    assert mail["subject"] == workspace.INVITE_MAIL[0]
    return re.search(r"/app/team/join\?token=([A-Za-z0-9_-]{43})", mail["body"]).group(1)


def team(client, sent, owner=ANN, member=BOB) -> tuple[str, str]:
    """`owner` makes a workspace and `member` joins it; their sessions."""
    a, _ = sign_in(client, sent, email=owner)
    b, _ = sign_in(client, sent, email=member, ip="203.0.113.8")
    assert client.post("/v1/account/workspace", headers=H(a)).status_code == 201
    assert client.post("/v1/account/workspace/invites", headers=H(a), json={"email": member}).status_code == 201
    r = client.post("/v1/account/workspace/join", headers=H(b), json={"token": invite_token(sent, member)})
    assert r.status_code == 200, r.text
    return a, b


# ---------------------------------------------------------------- sharing

def test_members_see_the_workspace_s_shortlist_follows_and_searches(client, sent, conn):
    oid = _put(conn, "N-1")
    org = conn.execute("SELECT id FROM organisation LIMIT 1").fetchone()["id"]
    a, _ = sign_in(client, sent, email=ANN)
    # rows made before the workspace join it with their author
    assert client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(a), json={"status": "evaluating",
                                                                                 "note": "ask legal"}).status_code == 200
    search = client.post("/v1/account/searches", headers=H(a), json={"name": "Armour", "kind": "tender",
                                                                    "filters": {"q": "armoured"}}).json()
    a, b = team(client, sent)
    assert client.put(f"/v1/account/follows/buyer/{org}", headers=H(b)).status_code == 200

    seen = client.get("/v1/account/shortlist", headers=H(b)).json()["items"]
    assert [(s["ref"], s["status"], s["note"]) for s in seen] == [(str(oid), "evaluating", "ask legal")]
    assert [f["ref"] for f in client.get("/v1/account/follows", headers=H(a)).json()["items"]] == [str(org)]
    listed = client.get("/v1/account/searches", headers=H(b)).json()["items"]
    assert [(s["id"], s["mine"]) for s in listed] == [(search["id"], False)]
    assert client.get("/v1/account/searches", headers=H(a)).json()["items"][0]["mine"] is True
    # a teammate changes the one shared entry (no second row); a teammate's search is changed by its author only
    assert client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(b), json={"status": "bidding",
                                                                                 "note": "we bid"}).status_code == 200
    assert conn.execute("SELECT count(*) AS n FROM app_shortlist").fetchone()["n"] == 1
    assert client.get("/v1/account/shortlist", headers=H(a)).json()["items"][0]["status"] == "bidding"
    assert client.patch(f"/v1/account/searches/{search['id']}", headers=H(b), json={"name": "x"}).status_code == 404
    assert client.delete(f"/v1/account/searches/{search['id']}", headers=H(b)).status_code == 404
    state = client.post("/v1/account/state", headers=H(b), json={"keys": [{"type": "shortlist", "kind": "tender",
                                                                           "ref": str(oid)}]}).json()["items"][0]
    assert state == {"type": "shortlist", "kind": "tender", "ref": str(oid), "saved": True, "status": "bidding"}
    dash = client.get("/v1/account/dashboard", headers=H(b)).json()
    assert dash["shortlist"]["counts"]["bidding"] == 1 and [f["ref"] for f in dash["following"]] == [str(org)]
    # following what a teammate follows adds nothing
    assert client.put(f"/v1/account/follows/buyer/{org}", headers=H(a)).status_code == 200
    assert conn.execute("SELECT count(*) AS n FROM app_follow").fetchone()["n"] == 1


def test_an_account_outside_the_workspace_sees_none_of_it(client, sent, conn):
    oid = _put(conn, "N-1")
    a, b = team(client, sent)
    c, _ = sign_in(client, sent, email=CAROL, ip="203.0.113.9")
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(a), json={"status": "bidding"})
    assert client.get("/v1/account/shortlist", headers=H(c)).json()["items"] == []
    assert client.delete(f"/v1/account/shortlist/tender/{oid}", headers=H(c)).status_code == 404
    ws = client.get("/v1/account/workspace", headers=H(c)).json()
    assert ws["workspace"] is None
    member = client.get("/v1/account/workspace", headers=H(a)).json()["workspace"]["members"][1]["id"]
    assert client.delete(f"/v1/account/workspace/members/{member}", headers=H(c)).status_code == 403   # owns nothing
    # Carol's own workspace cannot reach Ann's member or invitation
    assert client.post("/v1/account/workspace", headers=H(c)).status_code == 201
    assert client.delete(f"/v1/account/workspace/members/{member}", headers=H(c)).status_code == 404
    inv = client.post("/v1/account/workspace/invites", headers=H(a), json={"email": "dan@example.com"}).json()
    assert re.fullmatch(r"[0-9a-f-]{36}", inv["id"])                                   # O2
    assert client.delete(f"/v1/account/workspace/invites/{inv['id']}", headers=H(c)).status_code == 404
    # and a member is not the owner
    assert client.post("/v1/account/workspace/invites", headers=H(b), json={"email": "eve@example.com"}).status_code == 403


# ---------------------------------------------------------------- the invitation

def test_an_invitation_is_hashed_works_once_for_the_invited_address_only_and_expires(client, sent, conn):
    a, _ = sign_in(client, sent, email=ANN)
    c, _ = sign_in(client, sent, email=CAROL, ip="203.0.113.9")
    client.post("/v1/account/workspace", headers=H(a))
    r = client.post("/v1/account/workspace/invites", headers=H(a), json={"email": "Bob@Example.com"})
    assert r.status_code == 201 and "token" not in r.text
    token = invite_token(sent, "Bob@example.com")
    stored = conn.execute("SELECT token_hash, email_canonical, expires_at - created_at AS ttl FROM workspace_invite").fetchone()
    assert stored["token_hash"] == accounts._hash(token) and token.encode() not in bytes(stored["token_hash"])
    assert stored["email_canonical"] == BOB and stored["ttl"] == workspace.INVITE_TTL
    # a forwarded link is no use to another account, and is not spent by it
    wrong = client.post("/v1/account/workspace/join", headers=H(c), json={"token": token})
    assert (wrong.status_code, wrong.json()["error"]) == (403, "wrong_account")
    b, _ = sign_in(client, sent, email=BOB, ip="203.0.113.8")
    assert client.post("/v1/account/workspace/join", headers=H(b), json={"token": token}).status_code == 200
    again = client.post("/v1/account/workspace/join", headers=H(b), json={"token": token})
    assert (again.status_code, again.json()["error"]) == (400, "invalid_or_expired")
    # expired
    client.post("/v1/account/workspace/invites", headers=H(a), json={"email": "dan@example.com"})
    conn.execute("UPDATE workspace_invite SET expires_at = now() - interval '1 minute' WHERE email_canonical = 'dan@example.com'")
    conn.commit()
    d, _ = sign_in(client, sent, email="dan@example.com", ip="203.0.113.10")
    assert client.post("/v1/account/workspace/join", headers=H(d),
                       json={"token": invite_token(sent, "dan@example.com")}).status_code == 400


def test_invitations_are_limited_by_seats_and_by_time(client, sent, conn):
    a, _ = sign_in(client, sent, email=ANN)
    client.post("/v1/account/workspace", headers=H(a))
    for i in range(billing.SEATS["team"] - 1):                      # the owner holds one place
        assert client.post("/v1/account/workspace/invites", headers=H(a), json={"email": f"m{i}@example.com"}).status_code == 201
    full = client.post("/v1/account/workspace/invites", headers=H(a), json={"email": "one-more@example.com"})
    assert (full.status_code, full.json()["error"]) == (409, "seats_full")
    # one mail an hour to one address
    again = client.post("/v1/account/workspace/invites", headers=H(a), json={"email": "m0@example.com"})
    assert again.status_code == 429 and again.headers["retry-after"] == "3600"
    conn.execute("UPDATE workspace_invite SET created_at = now() - interval '2 hours'")
    conn.commit()
    assert client.post("/v1/account/workspace/invites", headers=H(a), json={"email": "m0@example.com"}).status_code == 201
    assert conn.execute("SELECT count(*) AS n FROM workspace_invite").fetchone()["n"] == billing.SEATS["team"] - 1
    own = client.post("/v1/account/workspace/invites", headers=H(a), json={"email": ANN})
    assert own.status_code == 422


def test_no_invitation_while_accounts_are_closed(client, sent, monkeypatch):
    a, _ = sign_in(client, sent, email=ANN)
    client.post("/v1/account/workspace", headers=H(a))
    monkeypatch.setattr(accounts, "accounts_problem", lambda: "DGATE_ACCOUNTS_OPEN")
    r = client.post("/v1/account/workspace/invites", headers=H(a), json={"email": BOB})
    assert (r.status_code, r.json()["error"]) == (503, "not_open")


# ---------------------------------------------------------------- the plan

def test_members_have_the_owner_s_plan_once_plans_are_on_sale(client, sent, conn, monkeypatch):
    oid = _put(conn, "N-1")
    a, _ = sign_in(client, sent, email=ANN)
    b, _ = sign_in(client, sent, email=BOB, ip="203.0.113.8")
    _billing_env(monkeypatch)
    for plan in (None, "pro", "founding"):                         # Free and Pro have no workspace
        on_plan(conn, ANN, plan)
        r = client.post("/v1/account/workspace", headers=H(a))
        assert (r.status_code, r.json()["error"]) == (402, "plan_required"), plan
    on_plan(conn, ANN, "team")
    assert client.post("/v1/account/workspace", headers=H(a)).status_code == 201
    client.post("/v1/account/workspace/invites", headers=H(a), json={"email": BOB})
    assert client.post("/v1/account/workspace/join", headers=H(b), json={"token": invite_token(sent, BOB)}).status_code == 200
    me = client.get("/v1/account/me", headers=H(b)).json()
    assert me["plan"]["current"] == "team" and "signals_csv" in me["features"] and "client_profiles" not in me["features"]
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(a), json={"status": "bidding"})
    assert len(client.get("/v1/account/shortlist", headers=H(b)).json()["items"]) == 1
    # a member with a higher plan of its own keeps it
    on_plan(conn, BOB, "consultant")
    assert client.get("/v1/account/me", headers=H(b)).json()["plan"]["current"] == "consultant"
    on_plan(conn, BOB, None)
    # the owner moves to Pro: the members' plan and the sharing stop, the rows stay
    on_plan(conn, ANN, "pro")
    assert client.get("/v1/account/me", headers=H(b)).json()["plan"]["current"] == "free"
    assert client.get("/v1/account/shortlist", headers=H(b)).json()["items"] == []
    assert client.get("/v1/account/workspace", headers=H(a)).json()["workspace"]["active"] is False
    assert len(client.get("/v1/account/shortlist", headers=H(a)).json()["items"]) == 1
    refused = client.post("/v1/account/workspace/invites", headers=H(a), json={"email": CAROL})
    assert (refused.status_code, refused.json()["error"]) == (402, "plan_required")
    # an invitation sent while the plan had the workspace is refused while it has not
    on_plan(conn, ANN, "team")
    client.post("/v1/account/workspace/invites", headers=H(a), json={"email": CAROL})
    on_plan(conn, ANN, "pro")
    c, _ = sign_in(client, sent, email=CAROL, ip="203.0.113.9")
    r = client.post("/v1/account/workspace/join", headers=H(c), json={"token": invite_token(sent, CAROL)})
    assert (r.status_code, r.json()["error"]) == (402, "plan_required")


def test_the_alert_digest_reads_the_owner_s_plan(client, sent, conn, monkeypatch):
    from dgate.ops import digest

    a, b = team(client, sent)
    _billing_env(monkeypatch)
    on_plan(conn, ANN, "team")
    client.post("/v1/account/searches", headers=H(b), json={"name": "Armour", "kind": "tender", "filters": {"q": "x"}})
    conn.execute("UPDATE app_saved_search SET created_at = now() - interval '2 days'")
    conn.commit()
    due = conn.execute(digest.DUE_SQL).fetchall()
    assert len(due) == 1 and billing.plan_of(due[0]) == "team" and billing.may(due[0], "email_alerts")


# ---------------------------------------------------------------- leaving

def test_a_member_leaves_or_is_removed_with_its_rows_and_the_owner_dissolves(client, sent, conn):
    oid = _put(conn, "N-1")
    a, b = team(client, sent)
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(b), json={"status": "watching", "note": "Bob's"})
    assert len(client.get("/v1/account/shortlist", headers=H(a)).json()["items"]) == 1
    assert client.post("/v1/account/workspace/leave", headers=H(a)).json()["error"] == "owner_cannot_leave"
    assert client.post("/v1/account/workspace/leave", headers=H(b)).status_code == 204
    assert client.get("/v1/account/shortlist", headers=H(a)).json()["items"] == []
    assert client.get("/v1/account/shortlist", headers=H(b)).json()["items"][0]["note"] == "Bob's"
    assert client.get("/v1/account/workspace", headers=H(b)).json()["workspace"] is None
    # invited again and removed by the owner
    conn.execute("DELETE FROM workspace_invite")
    conn.commit()
    client.post("/v1/account/workspace/invites", headers=H(a), json={"email": BOB})
    client.post("/v1/account/workspace/join", headers=H(b), json={"token": invite_token(sent, BOB)})
    ws = client.get("/v1/account/workspace", headers=H(a)).json()["workspace"]
    assert [m["role"] for m in ws["members"]] == ["owner", "member"] and ws["seats"] == billing.SEATS["team"]
    owner_id = ws["members"][0]["id"]
    assert client.delete(f"/v1/account/workspace/members/{owner_id}", headers=H(a)).status_code == 404
    assert client.delete(f"/v1/account/workspace/members/{ws['members'][1]['id']}", headers=H(a)).status_code == 204
    assert client.get("/v1/account/shortlist", headers=H(a)).json()["items"] == []
    # the owner ends it: its own rows stay, without the workspace
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(a), json={"status": "bidding"})
    assert client.delete("/v1/account/workspace", headers=H(a)).status_code == 204
    assert conn.execute("SELECT count(*) AS n FROM app_shortlist WHERE workspace_id IS NOT NULL").fetchone()["n"] == 0
    assert len(client.get("/v1/account/shortlist", headers=H(a)).json()["items"]) == 1
    assert conn.execute("SELECT count(*) AS n FROM workspace_member").fetchone()["n"] == 0


def test_the_export_holds_the_membership_and_the_owner_s_invitations_and_clients(client, sent):
    a, b = team(client, sent)
    client.post("/v1/account/clients", headers=H(a), json={"name": "Acme Defence GmbH", "country": "DE"})
    out = client.get("/v1/account/export", headers=H(a)).json()["workspace"]
    assert out["role"] == "owner" and out["invitations"][0]["email"] == BOB and out["clients"][0]["name"] == "Acme Defence GmbH"
    assert client.get("/v1/account/export", headers=H(b)).json()["workspace"]["role"] == "member"
    assert "invitations" not in client.get("/v1/account/export", headers=H(b)).json()["workspace"]


# ---------------------------------------------------------------- client profiles

def test_client_profiles_hold_commercial_data_and_label_searches_and_shortlist(client, sent, conn):
    oid = _put(conn, "N-1")
    a, _ = sign_in(client, sent, email=ANN)
    r = client.post("/v1/account/clients", headers=H(a), json={"name": "  Acme ‮ Defence  ", "country": "de",
                                                               "cpvCodes": ["35400000", "35"], "note": "sells vehicles"})
    assert r.status_code == 201, r.text
    acme = r.json()
    assert (acme["name"], acme["country"], acme["cpvCodes"]) == ("Acme Defence", "DE", ["35400000", "35"])
    assert client.get("/v1/account/workspace", headers=H(a)).json()["workspace"]["role"] == "owner"   # made with it
    for bad in ({"name": "x", "country": "Germany"}, {"name": "x", "cpvCodes": ["35-x"]}, {"name": " "},
                {"name": "x", "email": "a@b.c"}):
        assert client.post("/v1/account/clients", headers=H(a), json=bad).status_code == 422, bad
    s = client.post("/v1/account/searches", headers=H(a), json={"name": "Acme", "kind": "tender",
                                                                "filters": {"q": "armoured"}, "clientId": acme["id"]})
    assert s.json()["clientId"] == acme["id"]
    other = client.post("/v1/account/searches", headers=H(a), json={"name": "Mine", "kind": "tender", "filters": {}}).json()
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(a), json={"status": "watching", "clientId": acme["id"]})
    only = client.get(f"/v1/account/searches?client={acme['id']}", headers=H(a)).json()["items"]
    assert [x["id"] for x in only] == [s.json()["id"]]
    assert client.get(f"/v1/account/shortlist?client={acme['id']}", headers=H(a)).json()["items"][0]["clientId"] == acme["id"]
    # a status change keeps the client; null takes it off
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(a), json={"status": "bidding"})
    assert client.get("/v1/account/shortlist", headers=H(a)).json()["items"][0]["clientId"] == acme["id"]
    assert client.patch(f"/v1/account/searches/{other['id']}", headers=H(a), json={"clientId": acme["id"]}).json()["clientId"] == acme["id"]
    assert client.patch(f"/v1/account/searches/{other['id']}", headers=H(a), json={"clientId": None}).json()["clientId"] is None
    patched = client.patch(f"/v1/account/clients/{acme['id']}", headers=H(a), json={"note": "and drones"}).json()
    assert patched["note"] == "and drones" and patched["name"] == "Acme Defence"
    # another workspace's client is a 404 everywhere
    c, _ = sign_in(client, sent, email=CAROL, ip="203.0.113.9")
    for call in (lambda: client.get(f"/v1/account/searches?client={acme['id']}", headers=H(c)),
                 lambda: client.patch(f"/v1/account/clients/{acme['id']}", headers=H(c), json={"note": "x"}),
                 lambda: client.delete(f"/v1/account/clients/{acme['id']}", headers=H(c)),
                 lambda: client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(c),
                                    json={"status": "watching", "clientId": acme["id"]}),
                 lambda: client.get("/v1/account/shortlist?client=not-a-uuid", headers=H(a))):
        assert call().status_code == 404
    assert client.get("/v1/account/clients", headers=H(c)).json()["items"] == []
    # removed: the rows stay, without a client
    assert client.delete(f"/v1/account/clients/{acme['id']}", headers=H(a)).status_code == 204
    assert client.get("/v1/account/shortlist", headers=H(a)).json()["items"][0]["clientId"] is None
    assert len(client.get("/v1/account/searches", headers=H(a)).json()["items"]) == 2


def test_client_profiles_are_consultant_s_and_capped(client, sent, conn, monkeypatch):
    a, _ = sign_in(client, sent, email=ANN)
    # no plan on sale: nobody refused, the Consultant number
    assert client.get("/v1/account/clients", headers=H(a)).json()["limit"] == billing.CLIENTS["consultant"]
    _billing_env(monkeypatch)
    for plan in (None, "pro", "team"):
        on_plan(conn, ANN, plan)
        r = client.post("/v1/account/clients", headers=H(a), json={"name": "Acme"})
        assert (r.status_code, r.json()["error"]) == (402, "plan_required"), plan
    on_plan(conn, ANN, "consultant")
    for i in range(billing.CLIENTS["consultant"]):
        assert client.post("/v1/account/clients", headers=H(a), json={"name": f"Client {i}"}).status_code == 201
    over = client.post("/v1/account/clients", headers=H(a), json={"name": "One more"})
    assert (over.status_code, over.json()["error"]) == (409, "limit_reached")
    assert client.get("/v1/account/workspace", headers=H(a)).json()["workspace"]["seats"] == billing.SEATS["consultant"]
    # back to Team: the profiles stay listed, none can be attached
    on_plan(conn, ANN, "team")
    listed = client.get("/v1/account/clients", headers=H(a)).json()
    assert len(listed["items"]) == billing.CLIENTS["consultant"] and listed["allowed"] is False
    r = client.post("/v1/account/searches", headers=H(a), json={"name": "x", "kind": "tender", "filters": {},
                                                                "clientId": listed["items"][0]["id"]})
    assert r.status_code == 402


def test_a_company_report_carries_the_client_s_name(client, sent, conn, monkeypatch):
    from dgate import config
    from tests.integration.test_wp155 import rivals

    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "1")
    config.reset_cache()
    ids = rivals(conn, 1)
    a, _ = sign_in(client, sent, email=ANN)
    acme = client.post("/v1/account/clients", headers=H(a), json={"name": "Client One SL"}).json()
    url = f"/v1/account/suppliers/{ids['rival0']}/report"
    assert client.post(url, headers=H(a)).json()["clientName"] is None
    assert client.post(f"{url}?client={acme['id']}", headers=H(a)).json()["clientName"] == "Client One SL"
    c, _ = sign_in(client, sent, email=CAROL, ip="203.0.113.9")
    assert client.post(f"{url}?client={acme['id']}", headers=H(c)).status_code == 404
