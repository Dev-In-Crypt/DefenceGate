"""WP-155 on a real Postgres: the owner's plan split. Each gate in both states: while no plan is on sale nobody is refused a
paid feature (WP-124), and once the plans are on sale each follows the table (docs/verification/features/wp155-selfcheck.md).
The mosaic rule (full competitor lists and small companies' signal rows only after sign-in), the report count per calendar
month, the sample report, the name on reports and the data API licence."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import pytest

from dgate import apikeys, competition, config, money, signals
from dgate.ops import api_licence
from tests.integration.test_accounts import PW, H, client, sent, sign_in  # noqa: F401
from tests.integration.test_billing_wp124 import _billing_env
from tests.integration.test_wp152 import company, notice, win
from tests.integration.test_wp154_signals import notice as signal_notice
from tests.integration.test_wp154_signals import org as signal_org
from tests.integration.test_wp154_signals import win as signal_win

pytestmark = pytest.mark.integration


def on_plan(conn, plan: str | None) -> None:
    """Every account on `plan` (None: no subscription)."""
    conn.execute("DELETE FROM billing_subscription")
    if plan:
        conn.execute("""INSERT INTO billing_subscription (account_id, plan, period, status, last_event_id, last_event_at)
                        SELECT id, %s, 'yearly', 'active', 'evt_test', now() FROM app_user""", (plan,))
    conn.commit()


@pytest.fixture()
def reports(monkeypatch):
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "1")
    config.reset_cache()


def rivals(conn, n: int = 8) -> dict[str, int]:
    """A company and `n` rivals winning contracts of the same buyer under the same CPV class; three other companies."""
    acme = company(conn, "Acme Defence GmbH", "DE", "100000000")
    bund = "Bundesamt fuer Ausruestung"
    win(conn, notice(conn, "a-1", bund, "DE", "35410000"), acme, "Acme Defence GmbH")
    out = {"acme": acme}
    for i in range(n):
        r = company(conn, f"Rival {i} AG", "DE", f"2000000{i:02d}")
        for j in range(i + 1):                                    # Rival 7 overlaps most, Rival 0 least
            win(conn, notice(conn, f"r-{i}-{j}", bund, "DE", "35410000"), r, f"Rival {i} AG")
        out[f"rival{i}"] = r
    for i in range(3):
        out[f"other{i}"] = c = company(conn, f"Other {i} SA", "FR", f"30000000{i}")
        win(conn, notice(conn, f"o-{i}", "DGA", "FR", "35300000"), c, f"Other {i} SA")
    money.store(conn)
    conn.commit()
    return out


# ---------------------------------------------------------------- competitors (mosaic rule)

def test_the_public_answer_names_five_competitors_and_a_signed_in_account_the_rest(conn, client, sent, monkeypatch):
    ids = rivals(conn)
    public = client.get(f"/v1/suppliers/{ids['acme']}/competition").json()
    assert public["competitorCount"] == 8 and len(public["competitors"]) == competition.FREE_COMPETITORS
    assert public["full"] is False
    assert public["competitors"][0]["slug"].startswith(f"{ids['rival7']}-")
    url = f"/v1/account/suppliers/{ids['acme']}/competition"
    assert client.get(url).status_code == 401
    session, _ = sign_in(client, sent)
    full = client.get(url, headers=H(session))                     # no plan on sale: nobody refused
    assert full.status_code == 200 and len(full.json()["competitors"]) == 8 and full.json()["full"] is True
    assert full.headers["cache-control"] == "private, no-store"
    assert [c["slug"] for c in full.json()["competitors"][:5]] == [c["slug"] for c in public["competitors"]]

    _billing_env(monkeypatch)                                      # plans on sale
    refused = client.get(url, headers=H(session))
    assert (refused.status_code, refused.json()["error"]) == (402, "plan_required")
    for plan in ("pro", "founding", "team", "consultant"):
        on_plan(conn, plan)
        assert len(client.get(url, headers=H(session)).json()["competitors"]) == 8, plan


# ---------------------------------------------------------------- company reports

def test_reports_are_counted_once_per_company_and_month_against_the_plan(conn, client, sent, monkeypatch, reports):
    ids = rivals(conn)
    session, _ = sign_in(client, sent)

    def open_(key: str):
        return client.post(f"/v1/account/suppliers/{ids[key]}/report", headers=H(session))

    # no plan on sale: counted, never refused
    for k in ("rival0", "rival1", "rival2", "rival3", "rival4"):
        r = open_(k)
        assert r.status_code == 200 and r.json()["limit"] is None and r.json()["left"] is None
    _billing_env(monkeypatch)
    conn.execute("DELETE FROM company_report_open")
    conn.commit()
    assert (open_("acme").status_code, open_("acme").json()["error"]) == (402, "plan_required")   # free
    on_plan(conn, "pro")
    got = [open_(k).json() for k in ("rival0", "rival1", "rival1", "rival2")]
    assert [(g["used"], g["left"], g["counted"]) for g in got] == [(1, 2, True), (2, 1, True), (2, 1, False), (3, 0, True)]
    first, resets = competition.month_bounds()
    assert got[0]["resetsAt"] == resets.isoformat()
    refused = open_("rival3")
    assert refused.status_code == 402 and refused.json()["error"] == "report_quota"
    assert "3 of 3" in refused.json()["message"] and resets.isoformat() in refused.json()["message"]
    assert open_("rival2").status_code == 200                       # one already opened this month: open again
    # last month's openings do not count
    conn.execute("UPDATE company_report_open SET month = %s::date - interval '1 month'", (first,))
    conn.commit()
    assert open_("rival3").json()["used"] == 1
    on_plan(conn, "team")
    assert open_("rival4").json()["limit"] == 15
    on_plan(conn, "consultant")
    assert open_("rival5").json()["limit"] is None


def test_the_sample_report_is_open_to_everyone_and_never_counted(conn, client, sent, monkeypatch, reports):
    ids = rivals(conn)
    monkeypatch.setenv("DGATE_SAMPLE_REPORT_SLUG", f"{ids['acme']}-acme-defence-gmbh")
    config.reset_cache()
    public = client.get(f"/v1/suppliers/{ids['acme']}/competition").json()
    assert public["isSample"] is True and public["sampleReport"] == f"{ids['acme']}-acme-defence-gmbh"
    assert client.get(f"/v1/suppliers/{ids['rival0']}/competition").json()["isSample"] is False
    session, _ = sign_in(client, sent)
    _billing_env(monkeypatch)                                       # plans on sale, this account has none
    r = client.post(f"/v1/account/suppliers/{ids['acme']}/report", headers=H(session))
    assert r.status_code == 200 and r.json()["sample"] is True and r.json()["counted"] is False
    assert conn.execute("SELECT count(*) AS n FROM company_report_open").fetchone()["n"] == 0
    # reports switched off: no sample either
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "0")
    config.reset_cache()
    assert client.get(f"/v1/suppliers/{ids['acme']}/competition").json()["reportOpen"] is False
    assert client.post(f"/v1/account/suppliers/{ids['acme']}/report", headers=H(session)).status_code == 404


def test_the_name_on_reports_is_the_consultants_and_plain_text(conn, client, sent, monkeypatch, reports):
    ids = rivals(conn, 1)
    session, _ = sign_in(client, sent)
    _billing_env(monkeypatch)
    on_plan(conn, "team")
    r = client.patch("/v1/account/me", headers=H(session), json={"reportName": "Acme Advisory"})
    assert (r.status_code, r.json()["error"]) == (402, "plan_required")
    on_plan(conn, "consultant")
    assert client.patch("/v1/account/me", headers=H(session), json={"reportName": "x" * 81}).status_code == 422
    me = client.patch("/v1/account/me", headers=H(session), json={"reportName": " <b>Acme</b>\n Advisory "}).json()
    assert me["profile"]["reportName"] == "<b>Acme</b> Advisory"
    assert "branded_reports" in me["features"] and me["limits"] == {"savedSearches": 200, "reportsPerMonth": None}
    report = client.post(f"/v1/account/suppliers/{ids['rival0']}/report", headers=H(session)).json()
    assert report["reportName"] == "<b>Acme</b> Advisory"
    on_plan(conn, "team")                                           # a plan without it: kept, not printed
    assert client.post(f"/v1/account/suppliers/{ids['rival0']}/report", headers=H(session)).json()["reportName"] is None
    on_plan(conn, "consultant")
    assert client.patch("/v1/account/me", headers=H(session), json={"reportName": ""}).json()["profile"]["reportName"] is None
    export = client.get("/v1/account/export", headers=H(session)).json()
    assert export["companyReports"][0]["organisationId"] == ids["rival0"] and "apiLicensedAt" in export


# ---------------------------------------------------------------- company signals (mosaic rule, CSV)

def test_small_companies_rows_need_a_sign_in_and_the_csv_is_team_and_up(conn, client, sent, monkeypatch):
    small = []
    for i in range(3):                                              # 3 procurements, 3 against 0: small, ranked first
        o = signal_org(conn, f"Small {i} AS", "NO")
        small.append(o)
        for d in (5, 6, 7):
            signal_win(conn, signal_notice(conn, f"s{i}-{d}", days_ago=d, country="NO", buyer="FMA"), o, "NO")
    big = signal_org(conn, "Big Defence AB", "SE")                  # 10 procurements, 6 against 4: not small, ranked last
    for d in (10, 11, 12, 13, 14, 15, 400, 401, 402, 403):
        signal_win(conn, signal_notice(conn, f"b-{d}", days_ago=d, country="SE", buyer="FMV"), big, "SE")
    conn.commit()
    public = client.get("/v1/signals/growing").json()
    assert public["total"] == 4 and [i["company"]["id"] for i in public["items"]] == [str(big)]
    assert public["public"] is True and public["smallBelow"] == signals.SMALL_BELOW
    session, _ = sign_in(client, sent)
    first = client.get("/v1/account/signals/growing/first", headers=H(session)).json()
    assert len(first["items"]) == 4 and first["public"] is False and first["total"] == 4
    assert {i["company"]["id"] for i in first["items"][:3]} == {str(o) for o in small}

    monkeypatch.setenv("DGATE_SIGNALS_FULL_OPEN", "true")
    config.reset_cache()
    csv = f"/v1/account/signals/growing?pageSize={signals.MAX_PAGE_SIZE}"
    assert client.get(csv, headers=H(session)).status_code == 200    # no plan on sale: nobody refused
    _billing_env(monkeypatch)
    for plan, page, export in ((None, 402, 402), ("pro", 200, 402), ("founding", 200, 402), ("team", 200, 200),
                               ("consultant", 200, 200)):
        on_plan(conn, plan)
        assert client.get("/v1/account/signals/growing", headers=H(session)).status_code == page, plan
        assert client.get(csv, headers=H(session)).status_code == export, plan
    assert client.get("/v1/account/signals/growing/first", headers=H(session)).status_code == 200   # free too
    on_plan(conn, "pro")
    assert client.get("/v1/account/signals/growing", headers=H(session)).json()["csv"] is False


# ---------------------------------------------------------------- saved searches

def test_saved_searches_follow_the_plan_and_those_over_it_pause(conn, client, sent, monkeypatch):
    session, _ = sign_in(client, sent)
    _billing_env(monkeypatch)
    on_plan(conn, "team")
    for i in range(12):
        assert client.post("/v1/account/searches", headers=H(session),
                           json={"name": f"s{i}", "kind": "tender", "filters": {}}).status_code == 201
    listed = client.get("/v1/account/searches", headers=H(session)).json()
    assert listed["limit"] == 50 and not any(s["paused"] for s in listed["items"])
    on_plan(conn, "pro")                                            # 12 kept, the oldest 10 run
    listed = client.get("/v1/account/searches", headers=H(session)).json()
    assert [s["name"] for s in listed["items"] if s["paused"]] == ["s11", "s10"]
    r = client.post("/v1/account/searches", headers=H(session), json={"name": "x", "kind": "tender", "filters": {}})
    assert (r.status_code, r.json()["error"]) == (409, "limit_reached")
    on_plan(conn, None)
    r = client.post("/v1/account/searches", headers=H(session), json={"name": "x", "kind": "tender", "filters": {}})
    assert (r.status_code, r.json()["error"]) == (402, "plan_required")


def test_the_status_says_whether_plans_are_on_sale(client, monkeypatch):
    assert client.get("/v1/account/status").json()["plansOnSale"] is False
    _billing_env(monkeypatch)
    assert client.get("/v1/account/status").json()["plansOnSale"] is True


# ---------------------------------------------------------------- the data API licence

def test_keys_need_a_licence_that_only_the_operator_grants(conn, client, sent, monkeypatch, capsys):
    monkeypatch.setenv("DGATE_API_KEYS_OPEN", "1")
    config.reset_cache()
    apikeys._minute.clear()
    apikeys._day.clear()
    session, _ = sign_in(client, sent)
    body = {"name": "script", "scopes": ["tenders"], "password": PW}
    assert "api_keys" not in client.get("/v1/account/me", headers=H(session)).json()["features"]
    r = client.post("/v1/account/keys", json=body, headers=H(session))
    assert (r.status_code, r.json()["error"]) == (403, "no_licence")
    for plan in ("pro", "team", "consultant"):                      # no plan grants it
        _billing_env(monkeypatch)
        on_plan(conn, plan)
        assert client.post("/v1/account/keys", json=body, headers=H(session)).status_code == 403, plan
    assert api_licence.main(["--email", "ann@example.com"]) == 0     # report only
    assert "dry run" in capsys.readouterr().out
    assert conn.execute("SELECT api_licensed_at FROM app_user").fetchone()["api_licensed_at"] is None
    assert api_licence.main(["--email", "ann@example.com", "--yes"]) == 0
    assert "licence granted" in capsys.readouterr().out
    key = client.post("/v1/account/keys", json=body, headers=H(session)).json()["key"]
    auth = {"Authorization": f"Bearer {key}"}
    assert client.get("/v1/opportunities", headers=auth).status_code == 200
    assert api_licence.main(["--email", "ann@example.com", "--revoke", "--yes"]) == 0
    assert client.get("/v1/opportunities", headers=auth).status_code == 401  # withdrawn: the key is refused at once
    assert api_licence.main(["--email", "nobody@example.com"]) == 1
