"""The start-up catch-up.

A cron entry cannot recover a slot that passed while the process was stopped.
These tests pin the arithmetic that decides how far back to reach, because
getting it wrong is silent: too narrow and the gap stays a hole in the archive,
too wide and a start-up loop hammers a public portal.
"""

from __future__ import annotations

import pytest

from dgate import config, worker


@pytest.fixture
def fresh_settings(monkeypatch):
    def apply(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        config.reset_cache()
        return config.settings()

    yield apply
    config.reset_cache()


def _run_catch_up(monkeypatch, ages: dict[str, float | None]) -> list[tuple[str, int]]:
    """Run catch_up() with the database and the jobs replaced by fakes."""
    called: list[tuple[str, int]] = []

    def fake_job(name):
        def job(days: int | None = None) -> worker.JobResult:
            called.append((name, days or 0))
            return worker.JobResult(name, "success", 0.0)
        return job

    monkeypatch.setattr(worker, "daily_jobs", lambda: {
        name: (fake_job(name), (name,)) for name in ages
    })
    monkeypatch.setattr(worker, "hours_since_last_success", lambda codes: ages[codes[0]])
    worker.catch_up()
    return called


def test_a_fresh_source_is_left_alone(monkeypatch, fresh_settings):
    fresh_settings(DGATE_CATCH_UP_AFTER_HOURS=20)
    assert _run_catch_up(monkeypatch, {"ted_daily": 3.0}) == []


def test_a_two_day_gap_is_covered_by_a_three_day_window(monkeypatch, fresh_settings):
    # Missed Tuesday and Wednesday, started Thursday: the window has to reach
    # back past both, not just past yesterday.
    fresh_settings(DGATE_CATCH_UP_AFTER_HOURS=20, DGATE_INGEST_DAYS=2)
    assert _run_catch_up(monkeypatch, {"ted_daily": 50.0}) == [("ted_daily", 3)]


def test_a_source_that_never_succeeded_is_treated_as_a_gap(monkeypatch, fresh_settings):
    fresh_settings(DGATE_INGEST_DAYS=2)
    assert _run_catch_up(monkeypatch, {"ted_daily": None}) == [("ted_daily", 2)]


def test_a_long_outage_stops_at_the_cap(monkeypatch, fresh_settings):
    # Two months off. Pulling sixty days of every source at start-up is a
    # decision for a person; the cap keeps the shortfall visible instead.
    fresh_settings(DGATE_CATCH_UP_MAX_DAYS=7)
    assert _run_catch_up(monkeypatch, {"ted_daily": 24 * 60}) == [("ted_daily", 7)]


def test_catch_up_can_be_switched_off(monkeypatch, fresh_settings):
    fresh_settings(DGATE_CATCH_UP=0)
    assert _run_catch_up(monkeypatch, {"ted_daily": None}) == []


def test_an_unreachable_database_does_not_block_start_up(monkeypatch, fresh_settings):
    fresh_settings()
    monkeypatch.setattr(worker, "daily_jobs", lambda: {"ted_daily": (None, ("ted",))})

    def boom(codes):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(worker, "hours_since_last_success", boom)
    assert worker.catch_up() == []


def test_placsp_widens_by_pages_not_days(monkeypatch, fresh_settings):
    # PLACSP has no date parameter: its feed is a chain walked backwards, so
    # covering a wider gap means walking further, and the walk is capped.
    cfg = fresh_settings(DGATE_PLACSP_PAGES=20, DGATE_PLACSP_MAX_PAGES=120)
    seen: list[int] = []
    monkeypatch.setattr(worker, "run_placsp_live", lambda max_pages: seen.append(max_pages))
    monkeypatch.setattr(worker, "run_job", lambda name, fn, **kw: fn() or
                        worker.JobResult(name, "success", 0.0))
    worker.job_placsp(days=3)
    worker.job_placsp(days=30)
    assert seen == [60, cfg.placsp_max_pages]
