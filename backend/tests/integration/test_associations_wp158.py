"""WP-158: the cluster licence (ops.association), the plan it gives through billing.plan_in_force in both states of the
plans, the member's digest choice (O1 scoping, 404 for others), the stop link, and the co-branded weekly digest job."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from dgate import associations, billing, config, weekly_digest
from dgate.ops import association as ops
from dgate.ops import mailer
from tests.integration.test_accounts import PW, H, client, sent, sign_in  # noqa: F401

pytestmark = pytest.mark.integration

ME = "/v1/account/me"
MINE = "/v1/account/association"
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
WEEK = weekly_digest.last_complete_week(NOW)
LICENCE = ("--until", "2099-12-31", "--reason", "Agreement 2026-07")


def run(*argv: str) -> int:
    return ops.main(list(argv))


@pytest.fixture()
def cluster(client, sent, conn):
    """An association with an admin (ann) and a member (bob); carl is an account of no association."""
    ann, _ = sign_in(client, sent, "ann@example.com")
    bob, _ = sign_in(client, sent, "bob@example.com")
    carl, _ = sign_in(client, sent, "carl@example.com")
    assert run("--create", "cluster-x", "--display-name", "Cluster X", *LICENCE, "--yes") == 0
    assert run("--association", "cluster-x", "--add-member", "ann@example.com", "--admin", "--yes") == 0
    assert run("--association", "cluster-x", "--add-member", "bob@example.com", "--yes") == 0
    return {"ann": ann, "bob": bob, "carl": carl}


@pytest.fixture()
def on_sale(monkeypatch):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: True)


def plan(client, session) -> tuple[str, list[str]]:
    me = client.get(ME, headers=H(session)).json()
    return me["plan"]["current"], me["features"]


# ---------------------------------------------------------------- the operator module

def test_the_module_reports_by_default_and_writes_only_with_yes(client, sent, conn, capsys):
    sign_in(client, sent, "ann@example.com")
    assert run("--create", "cluster-x", "--display-name", "Cluster X", *LICENCE) == 0
    assert conn.execute("SELECT count(*) AS n FROM association").fetchone()["n"] == 0
    assert run("--create", "Bad Name!", "--display-name", "X", *LICENCE, "--yes") == 2
    # D3: a grant by hand is dated, reasoned and expiring
    assert run("--create", "cluster-x", "--display-name", "Cluster X", "--yes") == 2
    assert run("--create", "cluster-x", "--display-name", "Cluster X", "--until", "2020-01-01", "--reason", "x", "--yes") == 2
    assert run("--create", "cluster-x", "--display-name", "Cluster" + chr(0x202E) + " X\n", *LICENCE, "--yes") == 0
    row = conn.execute("SELECT * FROM association").fetchone()
    assert row["display_name"] == "Cluster X" and row["licensed_at"] is not None and row["seat_cap"] == 50
    assert row["licence_reason"] == "Agreement 2026-07" and row["licensed_until"] == datetime(2100, 1, 1, tzinfo=timezone.utc)
    assert run("--association", "cluster-x", "--add-member", "ann@example.com") == 0       # dry run
    assert conn.execute("SELECT count(*) AS n FROM association_member").fetchone()["n"] == 0
    assert run("--association", "cluster-x", "--add-member", "nobody@example.com", "--yes") == 1
    out = capsys.readouterr().out
    assert "dry run" in out and "ann@example.com" not in out                               # ids, never addresses


def test_the_seat_cap_holds_and_an_account_is_in_one_association(cluster, client, sent, conn):
    conn.execute("UPDATE association SET seat_cap = 2")
    conn.commit()
    assert run("--association", "cluster-x", "--add-member", "carl@example.com", "--yes") == 1    # 2 of 2 taken
    assert run("--create", "cluster-y", "--display-name", "Cluster Y", *LICENCE, "--yes") == 0
    assert run("--association", "cluster-y", "--add-member", "bob@example.com", "--yes") == 1    # already in cluster-x
    assert conn.execute("SELECT count(*) AS n FROM association_member").fetchone()["n"] == 2


# ---------------------------------------------------------------- the plan, in both states

def test_on_sale_the_member_has_pro_the_admin_team_and_others_free(cluster, client, on_sale):
    # merge of WP-156 into this: the eligibility pack is Pro's, so a member has it (the list on 5370fac missed it)
    assert plan(client, cluster["bob"]) == ("pro", ["saved_searches", "email_alerts", "competitors_full", "signals_full",
                                                    "eligibility_export", "association"])
    p, f = plan(client, cluster["ann"])
    assert p == "team" and {"signals_csv", "consortium_gaps", "association"} <= set(f) and "branded_reports" not in f
    assert plan(client, cluster["carl"]) == ("free", [])
    body = {"name": "s", "kind": "tender", "filters": {}}
    assert client.post("/v1/account/searches", json=body, headers=H(cluster["bob"])).status_code == 201
    assert client.post("/v1/account/searches", json=body, headers=H(cluster["carl"])).status_code == 402


def test_withdrawing_the_licence_or_the_member_ends_the_plan(cluster, client, on_sale):
    assert run("--association", "cluster-x", "--revoke", "bob@example.com", "--yes") == 0
    assert plan(client, cluster["bob"]) == ("free", [])
    assert run("--association", "cluster-x", "--revoke", "--yes") == 0                      # the licence
    assert plan(client, cluster["ann"]) == ("free", [])
    assert client.get(MINE, headers=H(cluster["ann"])).status_code == 404
    assert run("--association", "cluster-x", "--license", "--yes") == 2                     # no end date, no reason
    assert run("--association", "cluster-x", "--license", *LICENCE, "--yes") == 0
    assert plan(client, cluster["ann"])[0] == "team"


def test_the_licence_ends_by_itself_on_its_last_day(cluster, client, conn, on_sale):
    conn.execute("UPDATE association SET licensed_at = now() - interval '2 days', licensed_until = now() - interval '1 second'")
    conn.commit()
    assert plan(client, cluster["bob"]) == ("free", [])
    assert client.get(MINE, headers=H(cluster["bob"])).status_code == 404


def test_while_no_plan_is_on_sale_the_member_is_refused_nothing_either(cluster, client):
    assert not billing.plans_on_sale()
    p, f = plan(client, cluster["bob"])
    assert p == "pro" and "association" in f and "signals_csv" in f                     # WP-124: nothing withheld
    assert "association" not in plan(client, cluster["carl"])[1]


# ---------------------------------------------------------------- the member's page and choice

def test_the_association_is_the_member_s_own_and_seats_are_counted_for_the_admin(cluster, client):
    r = client.get(MINE, headers=H(cluster["bob"]))
    assert r.status_code == 200 and r.json()["name"] == "Cluster X" and r.json()["role"] == "member"
    assert "seats" not in r.json() and "ann" not in r.text
    admin = client.get(MINE, headers=H(cluster["ann"])).json()
    assert admin["role"] == "admin" and admin["seats"] == {"used": 2, "cap": 50} and "bob" not in str(admin)
    r = client.get(MINE, headers=H(cluster["carl"]))
    assert (r.status_code, r.json()["error"]) == (404, "not_found")
    r = client.put(f"{MINE}/digest", json={"on": True}, headers=H(cluster["carl"]))
    assert r.status_code == 404
    assert client.get(MINE).status_code == 401


def test_the_digest_choice_is_validated_and_stored(cluster, client, conn):
    r = client.put(f"{MINE}/digest", json={"on": True, "country": "es", "cpv": ["35400000-1", "3541", "3541"]},
                   headers=H(cluster["bob"]))
    assert r.status_code == 200, r.text
    assert r.json()["digest"] == {"on": True, "country": "ES", "cpv": ["35400000", "3541"], "lastWeek": None}
    r = client.put(f"{MINE}/digest", json={"on": True, "cpv": ["not a code"]}, headers=H(cluster["bob"]))
    assert (r.status_code, r.json()["error"]) == (422, "invalid_cpv")
    assert client.put(f"{MINE}/digest", json={"on": True, "country": "Spain"}, headers=H(cluster["bob"])).status_code == 422
    export = client.get("/v1/account/export", headers=H(cluster["bob"])).json()["association"]
    assert export["association"] == "Cluster X" and export["digest"]["on"] is True
    assert conn.execute("SELECT unsubscribe_token FROM association_member LIMIT 1").fetchone()["unsubscribe_token"] \
        not in str(export)


def test_the_stop_link_switches_off_that_member_only(cluster, client, conn):
    for who in ("ann", "bob"):
        client.put(f"{MINE}/digest", json={"on": True}, headers=H(cluster[who]))
    token = conn.execute("SELECT m.unsubscribe_token FROM association_member m JOIN app_user u ON u.id = m.account_id "
                         "WHERE u.email_canonical = 'bob@example.com'").fetchone()["unsubscribe_token"]
    assert re.fullmatch(r"[0-9a-f]{64}", token)
    r = client.post(f"{MINE}/unsubscribe", json={"token": "0" * 64})
    assert r.json() == {"done": True}                                    # the same answer for a token of nobody
    assert client.post(f"{MINE}/unsubscribe", json={"token": "x"}).status_code == 422
    assert client.post(f"{MINE}/unsubscribe", json={"token": token}).json() == {"done": True}
    assert client.get(MINE, headers=H(cluster["bob"])).json()["digest"]["on"] is False
    assert client.get(MINE, headers=H(cluster["ann"])).json()["digest"]["on"] is True


def test_deleting_an_account_removes_its_membership_and_the_admin_mark(cluster, client, conn):
    r = client.request("DELETE", ME, headers=H(cluster["ann"]), json={"confirm": "ann@example.com", "password": PW})
    assert r.status_code == 204
    assert conn.execute("SELECT count(*) AS n FROM association_member").fetchone()["n"] == 1
    assert conn.execute("SELECT admin_id FROM association").fetchone()["admin_id"] is None


# ---------------------------------------------------------------- the co-branded digest job

class Box(list):
    fake = None


@pytest.fixture()
def outbox(monkeypatch):
    box = Box()

    def fake(to, subject, body, sender_name=None, headers=None):
        box.append({"to": to, "subject": subject, "body": body, "sender": sender_name, "headers": headers})
        return fake.ok

    fake.ok = True
    monkeypatch.setattr(mailer, "send_mail", fake)
    box.fake = fake
    return box


@pytest.fixture()
def accounts_open(monkeypatch):
    monkeypatch.setenv("DGATE_ACCOUNTS_OPEN", "1")
    config.reset_cache()
    yield
    config.reset_cache()


def _opt_in(client, cluster, conn, *who):
    for w in who:
        assert client.put(f"{MINE}/digest", json={"on": True, "country": "ES"}, headers=H(cluster[w])).status_code == 200
    weekly_digest.refresh_week(conn, WEEK, now=NOW)


def test_the_digest_is_sent_only_while_accounts_are_open(cluster, client, conn, outbox):
    _opt_in(client, cluster, conn, "bob")
    assert associations.run_digests(conn, now=NOW)["mails"] == 0 and outbox == []


def test_the_digest_goes_once_a_week_to_members_who_opted_in_under_the_association_s_name(
        cluster, client, conn, outbox, accounts_open):
    _opt_in(client, cluster, conn, "bob")
    assert associations.run_digests(conn, now=NOW)["mails"] == 1
    (mail,) = outbox
    assert mail["to"] == "bob@example.com" and mail["sender"] == "Cluster X via DefenceGate"
    assert mail["subject"] == f"Cluster X: weekly defence digest, {WEEK}" and mail["body"].startswith("Cluster X: ")
    token = re.search(r"/unsubscribe\?token=([0-9a-f]{64})", mail["body"]).group(1)
    assert mail["headers"]["List-Unsubscribe"] == f"<https://site.test/unsubscribe?token={token}>"
    assert f"https://site.test/digest/{WEEK}?country=ES" in mail["body"]
    assert associations.run_digests(conn, now=NOW)["mails"] == 0                    # once a week
    assert client.post(f"{MINE}/unsubscribe", json={"token": token}).status_code == 200
    conn.execute("UPDATE association_member SET digest_last_week = NULL")
    conn.commit()
    assert associations.run_digests(conn, now=NOW)["mails"] == 0                    # stopped by the link


def test_no_digest_without_a_licence_or_before_the_issue_is_stored_and_a_failed_send_is_retried(
        cluster, client, conn, outbox, accounts_open):
    for w in ("ann", "bob"):
        client.put(f"{MINE}/digest", json={"on": True}, headers=H(cluster[w]))
    assert associations.run_digests(conn, now=NOW) == {"mails": 0, "failed": 0, "issues": 0, "waiting": 1}
    weekly_digest.refresh_week(conn, WEEK, now=NOW)
    outbox.fake.ok = False
    assert associations.run_digests(conn, now=NOW)["failed"] == 2
    outbox.fake.ok = True
    assert associations.run_digests(conn, now=NOW)["mails"] == 2                    # not marked, so tried again
    conn.execute("UPDATE association_member SET digest_last_week = NULL")
    conn.commit()
    assert run("--association", "cluster-x", "--revoke", "--yes") == 0
    assert associations.run_digests(conn, now=NOW)["mails"] == 0
    assert "carl@example.com" not in {m["to"] for m in outbox}
