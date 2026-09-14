"""An open call whose deadline has passed is not open.

On 14 September 2026, 12,539 of 13,412 notices served as open had a passed
deadline, or no deadline and a publication date over a year old.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from dgate.api import effective_status

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def test_a_passed_deadline_makes_an_open_call_expired():
    assert effective_status("open", datetime(2026, 9, 1, tzinfo=timezone.utc),
                            date(2026, 8, 1), NOW) == "expired"


def test_a_future_deadline_stays_open():
    assert effective_status("open", datetime(2026, 10, 1, tzinfo=timezone.utc),
                            date(2026, 9, 1), NOW) == "open"


def test_no_deadline_and_over_a_year_old_is_expired():
    assert effective_status("open", None, date(2024, 5, 1), NOW) == "expired"


def test_no_deadline_and_recent_stays_open():
    assert effective_status("open", None, date(2026, 6, 1), NOW) == "open"


def test_other_statuses_are_left_alone():
    past = datetime(2021, 1, 1, tzinfo=timezone.utc)
    assert effective_status("awarded", past, date(2021, 1, 1), NOW) == "awarded"
    assert effective_status("cancelled", past, date(2021, 1, 1), NOW) == "cancelled"
