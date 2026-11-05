"""The fixes of November 2026 that need no database: the report's mode A codes, request prices, the delays, the buckets."""

from __future__ import annotations

from dgate import accounts, hardening, sell_report


def test_mode_a_reads_the_company_s_own_codes_and_country_whatever_the_request_says(monkeypatch):
    monkeypatch.setattr("dgate.tenders.cpv_titles", lambda codes: {})
    org = {"name": "Taller Uno SL", "slug": "7-taller-uno-sl", "href": None, "country": "ES", "awards": 3, "projects": [],
           "wonCodes": [{"code": "34330000", "contracts": 3}]}
    p = sell_report._profile(sell_report.ReportIn(org="7", cpv=["72000000", "50000000"], country="DE"), org)
    assert (p["mode"], p["cpv"], p["country"], p["cpvFrom"]) == ("A", ["34330000"], "ES", "awards")
    b = sell_report._profile(sell_report.ReportIn(cpv=["72000000"], country="DE"), None)
    assert (b["mode"], b["cpv"], b["country"], b["cpvFrom"]) == ("B", ["72000000"], "DE", "request")


def test_a_call_s_partners_and_contracts_ending_are_priced_as_heavy_lists():
    assert hardening.request_cost("/v1/funding/118-anything/partners", {}) >= 5
    assert hardening.request_cost("/v1/organisations/5-x/partners", {}) >= 5
    assert hardening.request_cost("/v1/tenders/ending", {}) >= 5


def test_the_per_address_delay_is_capped_and_the_lockout_is_not():
    free = accounts.LOGIN_FREE_ADDR
    assert accounts.login_wait(free - 1, 0, free, accounts.LOGIN_ADDR_DELAY_MAX) == 0
    assert accounts.login_wait(free + 50, 0, free, accounts.LOGIN_ADDR_DELAY_MAX) == accounts.LOGIN_ADDR_DELAY_MAX
    assert accounts.login_wait(accounts.LOGIN_FREE + 20, 0, accounts.LOGIN_FREE) == 3600
    assert accounts.LIMIT_GLOBAL == 120 and accounts.LIMIT_GLOBAL_REPEAT < accounts.LIMIT_GLOBAL


def test_peek_takes_nothing():
    now = [0.0]
    b = hardening.TokenBuckets(2, 1, clock=lambda: now[0])
    assert b.peek("k", 1) == (True, 0.0) and b.take("k", 2)[0]
    ok, wait = b.peek("k", 1)
    assert not ok and wait == 1.0
    now[0] = 1.0
    assert b.peek("k", 1)[0] and b.peek("k", 1)[0]          # a peek does not spend the token it sees
    b.clear()
    assert b.peek("k", 2)[0]


def test_the_key_lookup_bound_fits_in_the_accounts_role_limit():
    import re
    from pathlib import Path

    from dgate import apikeys, config

    sql = (Path(__file__).resolve().parents[2] / "migrations" / "0027_accounts.sql").read_text(encoding="utf-8")
    limit = int(re.search(r"ALTER ROLE dgate_app CONNECTION LIMIT (\d+)", sql).group(1))
    assert config.Settings().app_connections + apikeys.KEY_CONNECTIONS <= limit


def test_the_client_tag_is_not_the_address():
    tag = accounts._client_tag("192.0.2.44")
    assert tag != "192.0.2.44" and len(tag) == 12 and tag == accounts._client_tag("192.0.2.44")
    assert tag != accounts._client_tag("192.0.2.45")
