"""WP-160 without a database: the one end-date rule and its index, where an end comes from (each basis pinned), the alert's
words, when a contract enters a window, and the filters of a saved search of contracts ending soon."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from dgate import accounts, billing, expiring
from dgate.accounts import AccountError
from dgate.ops import digest

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0152_wp160_contracts_ending.sql"


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def test_the_index_is_the_rule():
    sql = _flat(MIGRATION.read_text("utf-8"))
    rule = _flat(expiring.end_sql(""))
    # the indexed expression and the partial predicate are the list's own expression, written without the alias
    assert f"ON opportunity (({rule}))" in sql and f"AND {rule} IS NOT NULL;" in sql
    assert _flat(expiring.END_SQL) == _flat(expiring.end_sql("o."))


def test_the_rule_reads_stated_then_start_plus_duration_then_an_award_s_date():
    plain = expiring.end_sql(estimated=False)
    assert plain.startswith("COALESCE(o.contract_end, (o.contract_start + ")
    assert "published_at" not in plain and "o.published_at" in expiring.END_SQL
    assert "WHEN o.status = 'awarded' THEN o.published_at" in expiring.END_SQL
    for unit, limit in expiring.END_LIMITS.items():         # a duration over a century is a typo: no end
        assert f"o.contract_duration_unit = '{unit}' AND o.contract_duration <= {limit}" in plain
    basis = expiring.basis_sql()
    assert basis.index("'stated'") < basis.index("'computed'") < basis.index("'estimated'")


def _row(**kw):
    base = {c: None for c in ("contract_start", "contract_end", "contract_duration", "contract_duration_unit",
                              "contract_renewal", "contract_renewals_max", "period_end", "end_basis")}
    return {**base, **kw}


@pytest.mark.parametrize(("row", "basis", "text"), [
    (_row(contract_end=date(2027, 3, 31), period_end=date(2027, 3, 31), end_basis="stated"),
     "stated", "ends 2027-03-31 (stated end date)"),
    (_row(contract_start=date(2026, 4, 1), contract_duration=12, contract_duration_unit="MONTH",
          period_end=date(2027, 4, 1), end_basis="computed"),
     "computed", "ends 2027-04-01 (computed from start + duration)"),
    (_row(contract_duration=6, contract_duration_unit="MONTH", period_end=date(2027, 1, 15), end_basis="estimated"),
     "estimated", "ends 2027-01-15 (estimated: award notice publication date + duration)"),
    (_row(contract_duration=6, contract_duration_unit="MONTH"), None, "duration only, no start: no end date"),
    (_row(contract_renewal=True), None, "no end date stated; renewal possible"),
])
def test_each_basis_is_said(row, basis, text):
    p = expiring.period(row)
    assert p["endBasis"] == basis
    assert p["estimatedFrom"] == ("award_published" if basis == "estimated" else None)
    assert expiring.period_text(p) == text


def test_a_renewal_is_said_apart_and_never_added():
    p = expiring.period(_row(contract_end=date(2027, 3, 31), period_end=date(2027, 3, 31), end_basis="stated",
                             contract_renewal=True, contract_renewals_max=2))
    assert p["end"] == date(2027, 3, 31)
    assert expiring.period_text(p) == "ends 2027-03-31 (stated end date); renewal options: up to 2 renewals"
    assert expiring.period(_row()) is None and expiring.period_text(None) == "no contract period stated"


def test_months_and_the_day_a_contract_enters_a_window():
    assert expiring.add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert expiring.add_months(date(2026, 10, 31), 12) == date(2027, 10, 31)
    assert expiring.add_months(date(2027, 1, 31), -3) == date(2026, 10, 31)
    seen = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
    # seen long before: it enters when its end comes within the window
    assert expiring.entered_at(date(2027, 10, 31), 12, seen) == datetime(2026, 10, 31, tzinfo=timezone.utc)
    # first seen with its end already inside: it enters when we saw it
    assert expiring.entered_at(date(2027, 1, 31), 12, seen) == seen


def test_an_ending_search_keeps_its_own_filters_only():
    assert accounts.clean_filters("ending", {"country": "DE", "within": "6", "estimated": "true", "buyer": 12}) == {
        "country": "DE", "within": "6", "estimated": "true", "buyer": "12"}
    for bad in ({"within": "5"}, {"q": "radar"}, {"estimated": "yes"}, {"buyer": "x"}):
        with pytest.raises(AccountError):
            accounts.clean_filters("ending", bad)


def test_the_gate_is_pro_and_the_csv_team(monkeypatch):
    assert billing.FEATURES["expiring_contracts"] == billing.PRO
    assert billing.FEATURES["expiring_contracts_csv"] == billing.TEAM
    free = {"sub_plan": None, "sub_status": None, "sub_period_end": None}
    assert accounts.search_kind_allowed(free, "ending")          # no plan on sale: nobody is refused (WP-124)
    monkeypatch.setattr(billing, "plans_on_sale", lambda: True)
    assert not accounts.search_kind_allowed(free, "ending") and accounts.search_kind_allowed(free, "tender")
    pro = {"sub_plan": "pro", "sub_status": "active", "sub_period_end": None}
    assert accounts.search_kind_allowed(pro, "ending") and not billing.may(pro, "expiring_contracts_csv")


def test_the_alert_line_says_where_the_end_comes_from():
    item = {"title": "Vehicle maintenance", "buyerName": "Bundeswehr", "country": "DE", "slug": "7-vehicle-maintenance",
            "awardedTo": [{"name": "Acme GmbH"}],
            "contractPeriod": expiring.period(_row(contract_end=date(2027, 3, 31), period_end=date(2027, 3, 31),
                                                   end_basis="stated", contract_renewal=True))}
    assert digest._line("ending", item, "https://site.test") == (
        "- Vehicle maintenance\n  Bundeswehr, DE | ends 2027-03-31 (stated end date); renewal possible\n"
        "  awarded to Acme GmbH\n  https://site.test/tenders/7-vehicle-maintenance")
