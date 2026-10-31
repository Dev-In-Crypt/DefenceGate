"""WP-160 on a real Postgres: contracts ending soon. Each end basis pinned (stated, computed, estimated only when asked for,
no end from a duration alone or from a typo), one row per contract, the period on the notice's page and on the data API,
the coverage note from the data, the gate in both states (first 10 rows free, the whole list Pro, the CSV Team, the buyer
page's block free), and the saved search of kind `ending` with its alert (built dark: only with accounts open; the mail
written by the mailer's catcher)."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import email
from datetime import date, timedelta
from email import policy

import pytest

from dgate import accounts, config, db, expiring
from dgate.normalise import Opportunity
from dgate.ops import mailer
from dgate.ops.mailer import send_mail as REAL_SEND
from tests.integration.test_accounts import H, client, sent, sign_in  # noqa: F401
from tests.integration.test_billing_wp124 import _billing_env
from tests.integration.test_wp152 import company, win
from tests.integration.test_wp155 import on_plan

pytestmark = pytest.mark.integration

TODAY = date.today()
BUND = "Bundesamt fuer Ausruestung"


def contract(conn, nid: str, *, source="ted", buyer=BUND, country="DE", status="awarded", published=None,
             procedure=None, ted_ref=None, **period) -> int:
    opp = Opportunity(source_code=source, native_id=nid, buyer_name_raw=buyer, title_original=f"Contract {nid}",
                      title_en=f"Contract {nid}", country=country, published_at=published or TODAY - timedelta(days=30),
                      cpv_codes=["35410000"], status=status, is_defence=True, sig_legal_basis=True, sig_cpv=True,
                      sig_cpv_military=True, procedure_identifier=procedure, ted_ref=ted_ref,
                      source_url=f"https://notice.example/{nid}", **period)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{nid}", src)
    conn.commit()
    return oid


def ending(client, **q) -> dict:
    r = client.get("/v1/tenders/ending", params=q)
    assert r.status_code == 200, r.text
    return r.json()


def ids(answer: dict) -> list[int]:
    return [int(i["id"]) for i in answer["items"]]


def bases(conn) -> dict[str, int]:
    return {
        "stated": contract(conn, "stated", contract_end=TODAY + timedelta(days=60), contract_renewal=True,
                           contract_renewals_max=2),
        "computed": contract(conn, "computed", contract_start=TODAY - timedelta(days=200), contract_duration=12,
                             contract_duration_unit="MONTH"),
        # an award notice with a duration and no start: its publication date + the duration, an estimate
        "estimated": contract(conn, "estimated", published=TODAY - timedelta(days=30), contract_duration=3,
                              contract_duration_unit="MONTH"),
        # a call for competition with a duration and no start: no end at all
        "duration_only": contract(conn, "duration-only", status="open", contract_duration=3, contract_duration_unit="MONTH"),
        "later": contract(conn, "later", contract_end=TODAY + timedelta(days=500)),
        # a duration of five thousand years is a typo: nothing is computed from it
        "typo": contract(conn, "typo", contract_start=TODAY - timedelta(days=10), contract_duration=5000,
                         contract_duration_unit="YEAR"),
    }


def test_each_basis_and_estimates_only_when_asked_for(client, conn):
    b = bases(conn)
    default = ending(client)
    assert ids(default) == [b["stated"], b["computed"]] and default["total"] == 2 and default["estimated"] is False
    period = {int(i["id"]): i["contractPeriod"] for i in default["items"]}
    assert period[b["stated"]] == {"start": None, "end": (TODAY + timedelta(days=60)).isoformat(), "endBasis": "stated",
                                   "estimatedFrom": None, "duration": None, "durationUnit": None, "renewal": True,
                                   "renewalsMax": 2}
    computed = expiring.add_months(TODAY - timedelta(days=200), 12)
    assert (period[b["computed"]]["end"], period[b["computed"]]["endBasis"]) == (computed.isoformat(), "computed")
    with_estimates = ending(client, estimated="true")
    assert set(ids(with_estimates)) == {b["stated"], b["computed"], b["estimated"]}
    est = next(i for i in with_estimates["items"] if int(i["id"]) == b["estimated"])["contractPeriod"]
    assert (est["endBasis"], est["estimatedFrom"], est["end"]) == (
        "estimated", "award_published", expiring.add_months(TODAY - timedelta(days=30), 3).isoformat())
    assert ids(ending(client, within=3)) == [b["stated"]]
    assert client.get("/v1/tenders/ending", params={"within": 5}).status_code == 422
    assert client.get("/v1/tenders/ending", params={"estimated": "yes"}).status_code == 422
    assert client.get("/v1/tenders/ending", params={"q": "x"}).status_code == 422          # known parameters only

    # the notice's own page and the data API say the same, whatever the basis
    page = client.get(f"/v1/tenders/{b['duration_only']}").json()["contractPeriod"]
    assert (page["end"], page["endBasis"], page["duration"], page["durationUnit"]) == (None, None, 3, "MONTH")
    assert client.get(f"/v1/tenders/{b['typo']}").json()["contractPeriod"]["end"] is None
    assert client.get(f"/v1/tenders/{b['estimated']}").json()["contractPeriod"]["endBasis"] == "estimated"
    api = client.get(f"/v1/opportunities/{b['computed']}").json()["contract_period"]
    assert (api["end"], api["end_basis"], api["renewals_max"]) == (computed.isoformat(), "computed", None)
    listed = client.get("/v1/opportunities", params={"status": "awarded"}).json()     # the list items carry it too
    assert sorted((i["contract_period"]["end_basis"] or "none") for i in listed) == [
        "computed", "estimated", "none", "stated", "stated"]                         # typo: no end; later: stated
    # the coverage note: from the data, dated apart from estimated
    assert default["coverage"] == [{"country": "DE", "dated": 3, "estimated": 1}]


def test_one_row_per_contract(client, conn):
    call = contract(conn, "call", status="closed", procedure="proc-1", contract_end=TODAY + timedelta(days=40))
    award = contract(conn, "award", procedure="proc-1", contract_end=TODAY + timedelta(days=40))
    ted = contract(conn, "100-2026", contract_end=TODAY + timedelta(days=50))
    national = contract(conn, "boamp-1", source="fr_boamp", ted_ref="100-2026", contract_end=TODAY + timedelta(days=50))
    alone = contract(conn, "boamp-2", source="fr_boamp", ted_ref="999-2026", contract_end=TODAY + timedelta(days=55))
    contract(conn, "cancelled", status="cancelled", contract_end=TODAY + timedelta(days=45))
    got = ids(ending(client))
    assert got == [award, ted, alone] and call not in got and national not in got


def test_the_winner_where_known(client, conn):
    oid = contract(conn, "won", contract_end=TODAY + timedelta(days=30))
    acme = company(conn, "Acme Defence GmbH", "DE", "100000001")
    win(conn, oid, acme, "Acme Defence GmbH")
    item = ending(client)["items"][0]
    assert [w["name"] for w in item["awardedTo"]] == ["Acme Defence GmbH"]


def test_first_ten_free_the_list_pro_the_csv_team_the_buyer_block_free(client, sent, conn, monkeypatch):
    made = [contract(conn, f"c-{i:02d}", contract_end=TODAY + timedelta(days=10 + i)) for i in range(22)]
    public = ending(client)
    assert (len(public["items"]), public["total"], public["freeRows"], public["public"]) == (10, 22, 10, True)
    assert ids(public) == made[:10]
    buyer = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (made[0],)).fetchone()["buyer_org_id"]
    block = ending(client, buyer=buyer)
    assert len(block["items"]) == expiring.BUYER_ROWS and block["total"] == 22      # free in full, no sign-in

    url = "/v1/account/contracts/ending"
    assert client.get(url).status_code == 401
    session, _ = sign_in(client, sent)
    full = client.get(url, headers=H(session))                     # no plan on sale: nobody refused (WP-124)
    assert full.status_code == 200 and len(full.json()["items"]) == 22 and full.json()["csv"] is True
    assert full.headers["cache-control"] == "private, no-store"
    assert client.get(url, params={"pageSize": 2000}, headers=H(session)).status_code == 200
    page2 = client.get(url, params={"page": 3, "pageSize": 10}, headers=H(session)).json()
    assert ids(page2) == made[20:] and page2["total"] == 22
    assert client.get(url, params={"page": 4, "pageSize": 10}, headers=H(session)).json()["total"] == 22

    _billing_env(monkeypatch)                                      # plans on sale
    r = client.get(url, headers=H(session))
    assert (r.status_code, r.json()["error"]) == (402, "plan_required")
    assert "Pro" in r.json()["message"]
    for plan in ("pro", "founding"):
        on_plan(conn, plan)
        ok = client.get(url, headers=H(session))
        assert ok.status_code == 200 and len(ok.json()["items"]) == 22 and ok.json()["csv"] is False, plan
        csv = client.get(url, params={"pageSize": 2000}, headers=H(session))
        assert (csv.status_code, csv.json()["error"]) == (402, "plan_required") and "Team" in csv.json()["message"]
    for plan in ("team", "consultant"):
        on_plan(conn, plan)
        assert client.get(url, params={"pageSize": 2000}, headers=H(session)).json()["csv"] is True, plan
    assert len(ending(client)["items"]) == 10 and len(ending(client, buyer=buyer)["items"]) == 20   # public: the same


def _ending_search(client, session, **filters):
    return client.post("/v1/account/searches", headers=H(session),
                       json={"name": "Ending in Germany", "kind": "ending", "filters": {"country": "DE", **filters},
                             "cadence": "daily"})


def test_a_search_of_contracts_ending_soon_is_pro(client, sent, conn, monkeypatch):
    contract(conn, "s-1", contract_end=TODAY + timedelta(days=20))
    session, _ = sign_in(client, sent)
    r = _ending_search(client, session, within="6")
    assert r.status_code == 201, r.text
    assert (r.json()["kind"], r.json()["matchCount"], r.json()["paused"]) == ("ending", 1, False)
    assert _ending_search(client, session, within="5").status_code == 422
    assert _ending_search(client, session, q="radar").status_code == 422
    _billing_env(monkeypatch)
    on_plan(conn, None)
    assert _ending_search(client, session).status_code == 402
    accounts._cache.clear()
    listed = client.get("/v1/account/searches", headers=H(session)).json()["items"]
    assert listed[0]["paused"] is True
    on_plan(conn, "pro")
    assert _ending_search(client, session).status_code == 201
    accounts._cache.clear()
    dash = client.get("/v1/account/dashboard", headers=H(session)).json()
    assert {m["search"]["kind"] for m in dash["matches"]} == {"ending"}


@pytest.fixture()
def accounts_open(monkeypatch):
    monkeypatch.setenv("DGATE_ACCOUNTS_OPEN", "1")
    config.reset_cache()


def _due(conn):
    conn.execute("UPDATE app_saved_search SET created_at = now() - interval '2 days', "
                 "last_alerted_at = now() - interval '2 days'")
    conn.commit()
    accounts._cache.clear()


def test_the_alert_reports_contracts_that_enter_the_window_once(client, sent, conn, accounts_open):
    from dgate.ops.digest import run_digests

    session, _ = sign_in(client, sent)
    assert _ending_search(client, session, within="12").status_code == 201
    stated = contract(conn, "a-1", contract_end=TODAY + timedelta(days=90), contract_renewal=True, contract_renewals_max=1)
    contract(conn, "a-2", contract_start=TODAY - timedelta(days=200), contract_duration=12, contract_duration_unit="MONTH")
    contract(conn, "a-3", published=TODAY - timedelta(days=30), contract_duration=3, contract_duration_unit="MONTH")
    contract(conn, "a-4", country="FR", contract_end=TODAY + timedelta(days=90))
    _due(conn)
    before = len(sent)
    assert run_digests(conn)["mails"] == 1 and len(sent) == before + 1
    body = sent[-1]["body"]
    assert "Ending in Germany: 2 contracts newly ending within 12 months" in body
    assert "(stated end date); renewal options: up to 1 renewal" in body and "(computed from start + duration)" in body
    assert "Contract a-3" not in body and "Contract a-4" not in body          # an estimate not asked for; another country
    assert f"https://site.test/tenders/{stated}-" in body and "not an official source" in body
    accounts._cache.clear()
    assert run_digests(conn)["mails"] == 0                         # not due again, and nothing new


def test_no_alert_while_accounts_are_closed_or_without_the_plan(client, sent, conn, monkeypatch):
    from dgate.ops.digest import run_digests

    session, _ = sign_in(client, sent)
    _ending_search(client, session)
    contract(conn, "b-1", contract_end=TODAY + timedelta(days=30))
    _due(conn)
    before = len(sent)
    assert run_digests(conn)["mails"] == 0 and len(sent) == before                 # accounts closed: dark
    moved = conn.execute("SELECT last_alerted_at > now() - interval '1 minute' AS m FROM app_saved_search").fetchone()
    assert moved["m"]                                              # the window moved on: no backlog later
    monkeypatch.setenv("DGATE_ACCOUNTS_OPEN", "1")
    _billing_env(monkeypatch)
    on_plan(conn, None)
    _due(conn)
    assert run_digests(conn)["mails"] == 0 and len(sent) == before                 # free plan once plans are on sale
    on_plan(conn, "pro")
    contract(conn, "b-2", contract_end=TODAY + timedelta(days=31))
    _due(conn)
    assert run_digests(conn)["mails"] == 1


def test_the_alert_mail_as_the_catcher_writes_it(client, sent, conn, accounts_open, monkeypatch, tmp_path):
    from dgate.ops.digest import run_digests

    session, _ = sign_in(client, sent)
    _ending_search(client, session, within="3")
    contract(conn, "m-1", contract_end=TODAY + timedelta(days=45))
    _due(conn)
    monkeypatch.setattr(mailer, "send_mail", REAL_SEND)
    monkeypatch.setenv("DGATE_MAIL_CATCHER_DIR", str(tmp_path))
    config.reset_cache()
    mailer.reset_check()
    assert run_digests(conn)["mails"] == 1
    [eml] = list(tmp_path.glob("*.eml"))
    msg = email.message_from_bytes(eml.read_bytes(), policy=policy.default)
    assert msg["To"] == "ann@example.com" and msg["Subject"] == "DefenceGate: 1 new for your saved searches"
    text = msg.get_body(("plain",)).get_content()
    html = msg.get_body(("html",)).get_content()
    line = f"ends {(TODAY + timedelta(days=45)).isoformat()} (stated end date)"
    assert "1 contract newly ending within 3 months" in text and line in text and line in html
