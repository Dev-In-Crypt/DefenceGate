"""ISO weeks of the weekly digest (WP-31)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dgate import weekly_digest as W


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_a_week_runs_monday_to_monday_in_utc():
    start, end = W.week_bounds("2026-W41")
    assert (start, end) == (utc(2026, 10, 5), utc(2026, 10, 12))


@pytest.mark.parametrize("bad", ["2026-W54", "2026-W00", "26-W41", "2026W41", "", "2026-W4", "2026-w41"])
def test_a_string_that_is_not_a_week_is_refused(bad):
    with pytest.raises(ValueError):
        W.week_bounds(bad)


def test_the_year_boundary_follows_iso():
    assert W.week_id(utc(2026, 12, 31).date()) == "2026-W53"
    assert W.week_id(utc(2027, 1, 1).date()) == "2026-W53"
    assert W.week_id(utc(2027, 1, 4).date()) == "2027-W01"


def test_the_latest_issue_is_the_last_week_that_has_ended():
    assert W.last_complete_week(utc(2026, 10, 17, 12)) == "2026-W41"      # a Saturday: W42 is running
    assert W.last_complete_week(utc(2026, 10, 19, 0, 5)) == "2026-W42"    # Monday just after midnight
    assert W.last_complete_week(utc(2026, 10, 18, 23, 59)) == "2026-W41"  # Sunday evening


def test_the_issues_run_from_the_archive_start_to_the_latest_week_newest_first():
    weeks = W.all_weeks(utc(2026, 10, 17, 12))
    assert weeks[0] == "2026-W41" and weeks[-1] == "2026-W37" and len(weeks) == 5
    assert W.all_weeks(utc(2026, 9, 10)) == [], "no week of the archive has ended yet"
