"""A notice with no deadline is not open when its procedure is over (SUPERSEDED_SQL says so)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from dgate.api import effective_status

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def test_a_superseded_notice_with_no_deadline_is_expired_though_recent():
    assert effective_status("open", None, date(2026, 9, 1), NOW, superseded=True) == "expired"


def test_a_deadline_of_its_own_is_not_judged_by_the_flag():
    assert effective_status("open", datetime(2026, 11, 1, tzinfo=timezone.utc),
                            date(2026, 9, 1), NOW, superseded=True) == "open"


def test_the_flag_changes_no_other_status():
    assert effective_status("awarded", None, date(2026, 9, 1), NOW, superseded=True) == "awarded"
