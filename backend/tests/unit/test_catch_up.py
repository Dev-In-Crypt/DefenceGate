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


def _run_catch_up(monkeypatch, ages: dict[str, float | None],
                  since_slot: float = 4.0) -> list[tuple[str, int]]:
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
    monkeypatch.setattr(worker, "hours_since_last_slot", lambda name: since_slot)
    worker.catch_up()
    return called


def test_a_fresh_source_is_left_alone(monkeypatch, fresh_settings):
    fresh_settings()
    assert _run_catch_up(monkeypatch, {"ted_daily": 3.0}) == []


def test_a_two_day_gap_is_covered_by_a_three_day_window(monkeypatch, fresh_settings):
    # Missed Tuesday and Wednesday, started Thursday: the window has to reach
    # back past both, not just past yesterday.
    fresh_settings(DGATE_INGEST_DAYS=2)
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


def test_start_up_waits_for_a_database_that_is_still_starting(monkeypatch):
    """After a reboot Docker starts every container at once, and Postgres takes
    a few seconds to accept queries. Catch-up has to wait for it rather than
    record three warnings and cover nothing."""
    attempts = {"n": 0}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql):
            return None

    def connect(dsn):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("the database system is starting up")
        return Conn()

    monkeypatch.setattr(worker.db, "connect", connect)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    assert worker.wait_for_database(timeout=60, interval=0) is True
    assert attempts["n"] == 3


def test_start_up_gives_up_on_a_database_that_never_comes(monkeypatch):
    def connect(dsn):
        raise RuntimeError("connection refused")

    clock = iter(range(0, 10_000, 5))
    monkeypatch.setattr(worker.db, "connect", connect)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker.time, "monotonic", lambda: next(clock))
    assert worker.wait_for_database(timeout=30, interval=0) is False


def test_start_up_seeds_the_buyer_list_before_classifying(monkeypatch):
    """The list lives only in the database. After a rebuild it was gone for five
    days and the buyer signal could not fire for any source."""
    from dgate import pipeline

    order = []
    monkeypatch.setattr(pipeline, "seed_buyers", lambda: order.append("seed"))
    monkeypatch.setattr(worker, "catch_up", lambda: order.append("catch-up") or [])
    monkeypatch.setattr(worker, "catch_up_backups", lambda: [])
    monkeypatch.setattr(worker, "wait_for_database", lambda *a, **k: True)
    monkeypatch.setattr(worker, "close_interrupted_runs", lambda: [])
    worker.job_catch_up()
    assert order == ["seed", "catch-up"]


def test_a_failed_seed_is_reported_not_swallowed(monkeypatch):
    from dgate import pipeline

    sent = []

    def boom():
        raise RuntimeError("relation organisation does not exist")

    monkeypatch.setattr(pipeline, "seed_buyers", boom)
    monkeypatch.setattr(worker, "notify", lambda text: sent.append(text))
    worker.ensure_buyer_list()
    assert sent and "not seeded" in sent[0]


def test_a_missed_slot_is_caught_up_even_under_a_day_old(monkeypatch, fresh_settings):
    """14 September 2026: PLACSP last succeeded 20 hours before the worker
    started, its 06:30 slot had passed with the machine off, and the old
    20-hour threshold let it wait another day."""
    fresh_settings(DGATE_INGEST_DAYS=2)
    assert _run_catch_up(monkeypatch, {"placsp_daily": 20.3}, since_slot=0.55) == [
        ("placsp_daily", 2)]


def test_a_job_that_ran_after_its_slot_is_left_alone(monkeypatch, fresh_settings):
    fresh_settings()
    assert _run_catch_up(monkeypatch, {"ted_daily": 0.5}, since_slot=0.8) == []


@pytest.mark.parametrize("now, expected", [
    ("2026-09-14T07:03:00+00:00", 0.55),     # after today's 06:30 slot
    ("2026-09-14T05:00:00+00:00", 22.5),     # before it: yesterday's slot counts
])
def test_the_last_slot_is_today_or_yesterday(monkeypatch, fresh_settings, now, expected):
    from datetime import datetime

    fresh_settings(DGATE_PLACSP_HOUR=6, DGATE_PLACSP_MINUTE=30)
    monkeypatch.setattr(worker, "_now", lambda: datetime.fromisoformat(now))
    assert worker.hours_since_last_slot("placsp_daily") == pytest.approx(expected, abs=0.01)


# ---------------------------------------------------------------- backups

def _backups(monkeypatch, fresh_settings, *, taken, verified, now):
    from datetime import datetime

    fresh_settings(DGATE_BACKUP_HOUR=2)
    monkeypatch.setattr(worker, "_now", lambda: datetime.fromisoformat(now))
    monkeypatch.setattr(worker, "last_backup_taken",
                        lambda: datetime.fromisoformat(taken) if taken else None)
    monkeypatch.setattr(worker, "last_backup_verified",
                        lambda: datetime.fromisoformat(verified) if verified else None)
    ran = []
    monkeypatch.setattr(worker, "job_backup",
                        lambda: ran.append("dump") or worker.JobResult("backup_nightly", "success", 0))
    monkeypatch.setattr(worker, "job_backup_verify",
                        lambda: ran.append("verify") or worker.JobResult("backup_verify", "success", 0))
    worker.catch_up_backups()
    return ran


def test_a_week_without_a_dump_is_caught_up_on_start(monkeypatch, fresh_settings):
    """8 to 15 September 2026: the 02:00 dump never ran on a laptop that is off at
    night, and the newest files were test dumps of an empty database."""
    ran = _backups(monkeypatch, fresh_settings, taken="2026-09-08T11:41:00+00:00",
                   verified="2026-09-14T09:00:00+00:00", now="2026-09-15T08:30:00+00:00")
    assert ran == ["dump"]


def test_no_dump_at_all_is_caught_up(monkeypatch, fresh_settings):
    ran = _backups(monkeypatch, fresh_settings, taken=None,
                   verified="2026-09-14T09:00:00+00:00", now="2026-09-15T08:30:00+00:00")
    assert ran == ["dump"]


def test_a_dump_taken_after_its_slot_is_left_alone(monkeypatch, fresh_settings):
    ran = _backups(monkeypatch, fresh_settings, taken="2026-09-15T02:01:00+00:00",
                   verified="2026-09-14T09:00:00+00:00", now="2026-09-15T08:30:00+00:00")
    assert ran == []


def test_a_restore_check_missed_on_sunday_night_runs_on_start(monkeypatch, fresh_settings):
    # Tuesday; the last Sunday 02:30 slot passed with no check since.
    ran = _backups(monkeypatch, fresh_settings, taken="2026-09-15T02:01:00+00:00",
                   verified="2026-09-10T09:00:00+00:00", now="2026-09-15T08:30:00+00:00")
    assert ran == ["verify"]


def test_a_restore_check_never_recorded_runs(monkeypatch, fresh_settings):
    ran = _backups(monkeypatch, fresh_settings, taken="2026-09-15T02:01:00+00:00",
                   verified=None, now="2026-09-15T08:30:00+00:00")
    assert ran == ["verify"]


@pytest.mark.parametrize("now, expected", [
    ("2026-09-15T08:30:00+00:00", 54.0),    # Tuesday: last Sunday 02:30 was 2 days 6 h ago
    ("2026-09-13T02:00:00+00:00", 167.5),   # Sunday before the slot: the previous Sunday
])
def test_the_weekly_slot_is_the_most_recent_sunday(monkeypatch, now, expected):
    from datetime import datetime

    monkeypatch.setattr(worker, "_now", lambda: datetime.fromisoformat(now))
    assert worker.hours_since_last_weekly_slot(6, 2, 30) == pytest.approx(expected, abs=0.01)
