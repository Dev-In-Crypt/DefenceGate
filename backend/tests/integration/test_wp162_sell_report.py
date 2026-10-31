"""WP-162 on a real Postgres: the "Who to sell to" report. Privacy (a form without consent is in no log and no table), the
mosaic rule and the sign-in rule for names, the quotas per tariff (and the cluster pool, and the WP-124 rule), mode A, the
sample, empty sections, and the Consultant's name and logo."""

# ruff: noqa: F811 - the fixtures `client` and `sent` come from test_accounts.py
from __future__ import annotations

import base64
import logging

import pytest

from dgate import config, sell_report
from dgate.readiness.seed import apply, load_file
from tests.integration.test_accounts import H, client, sent, sign_in  # noqa: F401
from tests.integration.test_billing_wp124 import _billing_env
from tests.integration.test_wp66_demand import award, notice, org
from tests.integration.test_wp155 import on_plan

pytestmark = pytest.mark.integration

MARK = "Zqxprivacy Werkzeugbau"          # a company name no fixture holds
NACE = "Q99.97"


@pytest.fixture()
def world(conn, monkeypatch):
    """Spain: a defence buyer with six procurements under vehicle parts; six small winners (one cell of six) and one
    winner alone in its cell (Portugal); a large prime (BAE Systems) alone in its cell."""
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "1")
    config.reset_cache()
    apply(conn, load_file())
    male = org(conn, "JAE Mando de Apoyo Logistico", "ES", is_defence_buyer=True)
    w = {"male": male}
    for i in range(6):
        opp = notice(conn, "ted", f"{100 + i}-2026", buyer=male, country="ES", cpv=("34330000",), procedure=f"P-{i}",
                     buyer_name="JAE Mando de Apoyo Logístico")
        w[f"t{i}"] = c = org(conn, f"Taller {i} SL", "ES")
        award(conn, opp, c, f"Taller {i} SL")
    lone = notice(conn, "ted", "200-2026", buyer=male, country="ES", cpv=("34330000",), procedure="P-pt")
    w["pt"] = c = org(conn, "Oficina Lusa Lda", "PT")
    award(conn, lone, c, "Oficina Lusa Lda", "PT")
    big = notice(conn, "ted", "300-2026", buyer=male, country="ES", cpv=("34330000",), procedure="P-bae")
    w["bae"] = c = org(conn, "BAE Systems plc", "GB")
    award(conn, big, c, "BAE Systems plc", "GB")
    conn.commit()
    return w


def form(**over) -> dict:
    body = {"name": MARK, "country": "ES", "cpv": ["34330000"], "nace": NACE, "size": "sme", "held": ["ISO9001"],
            "classified": "no", "exports": "outside_eu", "usComponents": "unsure"}
    return {**body, **over}


def everything_holding(conn, needle: str) -> list[str]:
    """Every table of the database whose rows, as text, hold `needle`."""
    tables = [r["t"] for r in conn.execute(
        "SELECT quote_ident(table_name) AS t FROM information_schema.tables WHERE table_schema = 'public' "
        "AND table_type = 'BASE TABLE'").fetchall()]
    return [t for t in tables if conn.execute(f"SELECT 1 FROM {t} x WHERE x::text ILIKE %s LIMIT 1",
                                              (f"%{needle}%",)).fetchone()]


# ---------------------------------------------------------------- privacy (constraint 1)
def test_without_consent_the_form_reaches_no_log_and_no_table(conn, client, sent, world, caplog, capfd):
    session, _ = sign_in(client, sent)
    caplog.set_level(logging.DEBUG)
    r = client.post("/v1/account/sell-report", headers=H(session), json=form())
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["profile"]["name"] == MARK and rep["profile"]["nace"] == NACE      # used for the answer...
    out, err = capfd.readouterr()
    logged = caplog.text + out + err
    assert MARK not in logged and NACE not in logged and "34330000" not in logged   # ...and in no log line
    assert everything_holding(conn, "Zqxprivacy") == [] and everything_holding(conn, NACE) == []
    assert conn.execute("SELECT count(*) AS n FROM sell_profile").fetchone()["n"] == 0
    use = conn.execute("SELECT * FROM sell_report_use").fetchall()
    assert len(use) == 1 and use[0]["org_id"] is None                   # only the count is kept
    # a refused body is not echoed back either
    bad = client.post("/v1/account/sell-report", headers=H(session), json={**form(), "cpv": [MARK]})
    assert bad.status_code == 422 and MARK not in bad.text


def test_with_consent_the_form_is_kept_shown_and_deleted(conn, client, sent, world):
    session, _ = sign_in(client, sent)
    assert client.post("/v1/account/sell-report", headers=H(session), json=form(consent=True)).status_code == 200
    assert everything_holding(conn, "Zqxprivacy") == ["sell_profile"]
    kept = client.get("/v1/account/sell-report/profile", headers=H(session)).json()["profile"]
    assert kept["name"] == MARK and "consent" not in kept
    assert client.get("/v1/account/export", headers=H(session)).json()["supplierProfile"]["nace"] == NACE
    assert client.delete("/v1/account/sell-report/profile", headers=H(session)).status_code == 204
    assert everything_holding(conn, "Zqxprivacy") == []
    assert client.get("/v1/account/sell-report/profile", headers=H(session)).status_code == 404


# ---------------------------------------------------------------- mosaic rule and names (constraint 2)
def test_names_follow_the_mosaic_rule_and_the_sign_in(conn, client, sent, world):
    session, _ = sign_in(client, sent)
    rep = client.post("/v1/account/sell-report", headers=H(session), json=form()).json()
    w = rep["market"]["winners"]
    named = {r["name"] for r in w["rows"]}
    assert {f"Taller {i} SL" for i in range(6)} <= named                # ES x 343: six companies
    assert "BAE Systems plc" in named and next(r for r in w["rows"] if r["name"] == "BAE Systems plc")["large"]
    assert "Oficina Lusa Lda" not in named                               # PT x 343: alone, counted only
    assert w["notNamed"] == [{"country": "PT", "companies": 1, "contracts": 1}]
    assert all(r["notice"]["sourceUrl"].startswith("https://") and r["href"].startswith("/suppliers/") for r in w["rows"])
    b = rep["market"]["buyers"][0]
    assert b["country"] == "ES" and b["procurements"] == 8 and b["rows"][0]["notice"]["sourceUrl"]
    # the public sample: no company named in section 3, never counted
    assert client.get("/v1/sell-report/sample").json()["market"]["winners"]["rows"] == []
    named_sample = client.get("/v1/account/sell-report/sample", headers=H(session)).json()
    assert named_sample["sample"] is True and named_sample["profile"]["name"].endswith("(fictitious)")
    assert conn.execute("SELECT count(*) AS n FROM sell_report_use").fetchone()["n"] == 1


# ---------------------------------------------------------------- quotas per tariff
def test_quotas_per_tariff_and_the_wp124_rule(conn, client, sent, world, monkeypatch):
    session, _ = sign_in(client, sent)

    def gen(**over):
        return client.post("/v1/account/sell-report", headers=H(session), json=form(**over))

    for _ in range(4):                                        # no plan on sale: counted, never refused
        assert gen().json()["quota"]["limit"] is None
    _billing_env(monkeypatch)
    conn.execute("DELETE FROM sell_report_use")
    conn.commit()
    assert (gen().status_code, gen().json()["error"]) == (402, "plan_required")          # Free
    on_plan(conn, "pro")
    assert [gen().json()["quota"]["left"] for _ in range(3)] == [2, 1, 0]
    refused = gen()
    assert refused.status_code == 402 and refused.json()["error"] == "report_quota" and "3 of 3" in refused.json()["message"]
    on_plan(conn, "team")
    assert gen().json()["quota"]["limit"] == 15
    on_plan(conn, "consultant")
    assert gen().json()["quota"]["limit"] is None
    # mode A: one company counts once a month
    on_plan(conn, "pro")
    conn.execute("DELETE FROM sell_report_use")
    conn.commit()
    slug = f"{world['t0']}-taller-0-sl"
    a = [client.post("/v1/account/sell-report", headers=H(session), json={"org": slug}).json() for _ in range(2)]
    assert [x["quota"]["used"] for x in a] == [1, 1] and a[0]["quota"]["counted"] and not a[1]["quota"]["counted"]
    assert a[0]["profile"]["mode"] == "A" and a[0]["profile"]["cpv"] == ["34330000"]
    # the company itself is not among "who wins": its own contracts are counted apart
    assert a[0]["market"]["winners"]["ownContracts"] == 1
    assert "Taller 0 SL" not in {r["name"] for r in a[0]["market"]["winners"]["rows"]}
    # switched off: nothing
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "0")
    config.reset_cache()
    assert gen().status_code == 404 and client.get("/v1/sell-report/sample").status_code == 404


def test_a_cluster_pool_replaces_the_monthly_number(conn, client, sent, world, monkeypatch):
    session, me = sign_in(client, sent)
    _billing_env(monkeypatch)
    conn.execute("INSERT INTO association (name, display_name, licensed_at, licensed_until, licence_reason, "
                 "sell_reports_per_year) VALUES ('cl', 'Cluster', now(), now() + interval '1 year', 'ref', 2)")
    conn.execute("INSERT INTO association_member (account_id, association_id) SELECT u.id, a.id FROM app_user u, association a")
    conn.commit()
    got = [client.post("/v1/account/sell-report", headers=H(session), json=form()) for _ in range(3)]
    assert [g.status_code for g in got] == [200, 200, 402]
    assert got[1].json()["quota"] == {"used": 2, "limit": 2, "left": 0, "per": "year", "counted": True}
    assert "this year" in got[2].json()["message"]


# ---------------------------------------------------------------- empty sections, white-label
def test_a_report_with_nothing_found_has_every_section_empty_and_honest(conn, client, sent, world):
    session, _ = sign_in(client, sent)
    rep = client.post("/v1/account/sell-report", headers=H(session),
                      json=form(cpv=["03111000"], country="PL", held=[])).json()
    m = rep["market"]
    assert m["available"] and m["total"]["procurements"] == 0 and m["buyers"] == [] and m["winners"]["rows"] == []
    assert rep["open"]["tenders"]["rows"] == [] and rep["ending"] is None
    assert rep["steps"][0]["key"] == "codes" and rep["sources"]["disclaimer"] == sell_report.DISCLAIMER


def test_the_consultants_name_and_logo_go_on_the_cover(conn, client, sent, world, monkeypatch):
    session, _ = sign_in(client, sent)
    _billing_env(monkeypatch)
    on_plan(conn, "team")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    logo = {"type": "image/png", "data": base64.b64encode(png).decode()}
    assert client.put("/v1/account/sell-report/logo", headers=H(session), json=logo).status_code == 402
    on_plan(conn, "consultant")
    svg = {"type": "image/png", "data": base64.b64encode(b"<svg onload=alert(1)>").decode()}
    assert client.put("/v1/account/sell-report/logo", headers=H(session), json=svg).status_code == 422
    assert client.put("/v1/account/sell-report/logo", headers=H(session), json=logo).status_code == 204
    client.patch("/v1/account/me", headers=H(session), json={"reportName": "Acme Advisory"})
    rep = client.post("/v1/account/sell-report", headers=H(session), json=form()).json()
    assert rep["brand"]["name"] == "Acme Advisory" and rep["brand"]["logo"].startswith("data:image/png;base64,")
    on_plan(conn, "pro")
    assert client.post("/v1/account/sell-report", headers=H(session), json=form()).json()["brand"] is None
