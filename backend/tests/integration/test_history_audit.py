"""Proving the history is complete, not assuming it.

A day that comes back short looks exactly like a quiet day. The audit's whole
value is catching that, so these tests are mostly about the short day.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import db
from dgate.ops import history_audit as audit

pytestmark = pytest.mark.integration


def _load(conn, days: dict[str, int]) -> None:
    for day, notices in days.items():
        db.mark_backfill_day(conn, "ted", date.fromisoformat(day), notices)


def _reported(totals: dict[str, int | None], monkeypatch):
    seen = []

    def fake(first, last, client=None):
        seen.append((first, last))
        return totals.get(f"{first:%Y-%m}")

    monkeypatch.setattr(audit, "reported_total", fake)
    return seen


def test_a_month_that_matches_the_source_is_complete(conn, monkeypatch):
    _load(conn, {"2019-06-03": 1000, "2019-06-04": 500})
    _reported({"2019-06": 1500}, monkeypatch)
    months = list(audit.audit(conn))
    assert [m.complete for m in months] == [True]
    assert months[0].missing == 0


def test_a_month_short_of_the_source_names_what_is_missing(conn, monkeypatch):
    """The failure this exists for: a day cut short by a bad page, recorded as
    a small day, indistinguishable from a quiet one until counted this way."""
    _load(conn, {"2019-06-03": 1000, "2019-06-04": 40})
    _reported({"2019-06": 1500}, monkeypatch)
    month = next(iter(audit.audit(conn)))
    assert not month.complete
    assert month.missing == 460
    assert "MISSING 460" in str(month)


def test_a_month_the_source_cannot_count_is_not_called_a_mismatch(conn, monkeypatch):
    """Older windows answer with no total at all. Unknown is not disagreement."""
    _load(conn, {"2016-06-03": 10})
    _reported({"2016-06": None}, monkeypatch)
    assert next(iter(audit.audit(conn))).complete


def test_the_audit_asks_the_source_once_per_month_over_the_whole_month(conn, monkeypatch):
    """One request per month, whatever the month holds: the count is free, the
    walk is not."""
    _load(conn, {"2019-06-03": 5, "2019-06-28": 5, "2019-07-01": 5})
    seen = _reported({"2019-06": 10, "2019-07": 5}, monkeypatch)
    list(audit.audit(conn))
    assert seen == [(date(2019, 6, 1), date(2019, 6, 30)),
                    (date(2019, 7, 1), date(2019, 7, 31))]


def test_forgetting_a_month_makes_the_loader_ask_for_its_days_again(conn, monkeypatch):
    _load(conn, {"2019-06-03": 1000, "2019-06-04": 40, "2019-07-01": 10})
    _reported({"2019-06": 1500, "2019-07": 10}, monkeypatch)
    months = list(audit.audit(conn))
    removed = audit.forget(conn, [m for m in months if not m.complete])
    assert removed == 2
    assert db.backfill_days_done(conn, "ted") == {date(2019, 7, 1)}


def test_a_range_limits_what_is_checked(conn, monkeypatch):
    _load(conn, {"2019-06-03": 5, "2019-07-01": 5, "2019-08-01": 5})
    _reported({"2019-06": 5, "2019-07": 5, "2019-08": 5}, monkeypatch)
    months = list(audit.audit(conn, date(2019, 7, 1), date(2019, 7, 31)))
    assert [f"{m.first:%Y-%m}" for m in months] == ["2019-07"]
