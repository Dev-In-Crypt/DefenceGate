"""WP-155: the owner's plan split (28 Oct 2026) as billing holds it, without a database: which plan has which feature, how
many reports and saved searches, nothing withheld while no plan is on sale, the report month, the name on reports."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dgate import accounts, billing, competition, config, signals
from dgate.accounts import AccountError

PLANS = ("free", "pro", "team", "consultant", "founding")
# The owner's table: feature -> plans that have it (Founding customer is Pro).
TABLE = {
    "saved_searches": {"pro", "team", "consultant", "founding"},
    "email_alerts": {"pro", "team", "consultant", "founding"},
    "company_report": {"pro", "team", "consultant", "founding"},
    "competitors_full": {"pro", "team", "consultant", "founding"},
    "signals_full": {"pro", "team", "consultant", "founding"},
    "signals_csv": {"team", "consultant"},
    "consortium_gaps": {"team", "consultant"},
    "branded_reports": {"consultant"},
}


def user(plan: str | None) -> dict:
    return {"sub_plan": plan, "sub_status": "active" if plan else None, "sub_period_end": None}


@pytest.fixture()
def on_sale(monkeypatch):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: True)


@pytest.fixture()
def reports(monkeypatch):
    monkeypatch.setenv("DGATE_COMPANY_REPORT_OPEN", "1")
    config.reset_cache()
    yield
    config.reset_cache()


def test_each_feature_is_the_plans_the_owner_gave_it():
    assert {f: {p for p in PLANS if billing.allows(p, f)} for f in billing.FEATURES} == TABLE
    # the data API is no plan's: a licence (dgate/ops/api_licence.py)
    assert "api_keys" not in billing.FEATURES


def test_founding_is_pro_everywhere():
    assert all(billing.allows("founding", f) == billing.allows("pro", f) for f in billing.FEATURES)
    assert billing.REPORTS_PER_MONTH["founding"] == billing.REPORTS_PER_MONTH["pro"]
    assert billing.SAVED_SEARCHES["founding"] == billing.SAVED_SEARCHES["pro"]


def test_reports_and_searches_a_plan_allows(on_sale):
    assert [billing.report_limit(user(p)) for p in PLANS] == [0, 3, 15, None, 3]
    assert [billing.search_limit(user(p)) for p in PLANS] == [0, 10, 50, billing.SEARCH_CEILING, 10]
    assert accounts.MAX_SEARCHES == billing.SEARCH_CEILING       # the export lists every search a plan may hold


def test_with_plans_on_sale_each_gate_follows_the_table(on_sale, reports):
    for plan in PLANS:
        u = user(plan)
        assert sorted(billing.features(u)) == sorted(f for f, plans in TABLE.items() if plan in plans)
        for f in billing.FEATURES:
            if plan in TABLE[f]:
                billing.require(u, f)
            else:
                with pytest.raises(AccountError) as e:
                    billing.require(u, f)
                assert (e.value.status, e.value.code) == (402, "plan_required")


def test_while_no_plan_is_on_sale_nobody_is_refused_a_paid_feature(monkeypatch, reports):
    monkeypatch.setattr(billing, "plans_on_sale", lambda: False)
    free = user(None)
    assert set(billing.features(free)) == set(billing.FEATURES)
    assert billing.report_limit(free) is None                      # no report counted against anyone
    assert billing.search_limit(free) == billing.SEARCHES_UNSOLD == 10   # what every account had (WP-123)
    monkeypatch.setenv("DGATE_SIGNALS_FULL_OPEN", "true")
    config.reset_cache()
    assert signals.may_see_full(free)


def test_reports_and_the_name_on_them_need_the_reports_switch(monkeypatch):
    monkeypatch.delenv("DGATE_COMPANY_REPORT_OPEN", raising=False)
    config.reset_cache()
    assert not billing.may(user("consultant"), "company_report")
    assert not billing.may(user("consultant"), "branded_reports")


def test_the_report_month_is_the_utc_calendar_month():
    assert competition.month_bounds(datetime(2026, 10, 28, 23, 59, tzinfo=timezone.utc)) == (date(2026, 10, 1),
                                                                                               date(2026, 11, 1))
    assert competition.month_bounds(datetime(2026, 12, 31, tzinfo=timezone.utc)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_the_name_on_reports_is_plain_text_on_one_line():
    assert accounts.clean_report_name("  Acme \n Advisory\tLtd ") == "Acme Advisory Ltd"
    assert accounts.clean_report_name("A‮B\x00C") == "A B C"          # no direction or control characters
    assert accounts.clean_report_name(" ​ ") is None
    assert accounts.clean_report_name("x" * 100) == "x" * 80
    # markup stays text: the site prints it escaped
    assert accounts.clean_report_name("<b>Acme</b>") == "<b>Acme</b>"


def test_the_public_competitor_list_is_shorter_than_the_full_one():
    assert competition.FREE_COMPETITORS == 5 < competition.COMPETITORS


def test_a_small_company_is_under_ten_procurements_and_csv_is_a_large_page():
    assert signals.SMALL_BELOW == 10
    assert signals.FREE_ROWS == 10 and signals.PAGE_MAX < signals.MAX_PAGE_SIZE


def test_the_mosaic_rule_covers_the_procurement_tabs_not_the_funding_tab():
    assert signals.MOSAIC_KINDS == ("growing", "markets") and "funding" in signals.KINDS
