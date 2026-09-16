"""The Polish backfill has to finish on its own.

A hand-started run lives in a process that any container restart kills. On
13 September 2026 that happened three times in one morning -- a reboot, a DNS
outage, and the WSL virtual machine under Docker restarting -- and each time the
run sat stopped until somebody noticed. The worker now owns it.
"""

from __future__ import annotations

import pytest

from dgate import config, pipeline, worker


@pytest.fixture
def env(monkeypatch, tmp_path):
    def apply(**values):
        monkeypatch.setenv("DGATE_ATLAS_DIR", str(tmp_path))
        for key, value in values.items():
            monkeypatch.setenv(key, str(value))
        config.reset_cache()
        return config.settings()

    yield apply
    config.reset_cache()


def test_years_parse_from_the_environment(env):
    assert env(DGATE_ATLAS_BACKFILL_YEARS="2024, 2025").atlas_backfill_years == [2024, 2025]


def test_no_years_configured_means_no_backfill(env, monkeypatch):
    monkeypatch.delenv("DGATE_TED_HISTORY_FROM", raising=False)
    env(DGATE_ATLAS_BACKFILL_YEARS="")
    assert worker.pending_backfill_years() == []
    assert worker.start_backfill_thread() == []


def test_a_year_with_its_marker_is_finished(env):
    env(DGATE_ATLAS_BACKFILL_YEARS="2024,2025")
    pipeline.atlas_done_marker(2024).write_text("completed", encoding="utf-8")
    assert worker.pending_backfill_years() == [2025]


def test_a_failed_attempt_is_retried_and_the_year_still_finishes(env, monkeypatch):
    env(DGATE_ATLAS_BACKFILL_YEARS="2024")
    calls = []

    def flaky(year, **kw):
        calls.append(year)
        if len(calls) < 3:
            raise ConnectionError("Could not connect to the endpoint URL")

    monkeypatch.setattr(pipeline, "run_atlas_backfill", flaky)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker, "run_job",
                        lambda name, fn, **kw: fn() or worker.JobResult(name, "success", 0))
    worker.job_atlas_backfill(attempts=6, pause=0)
    assert calls == [2024, 2024, 2024]


def test_it_gives_up_after_the_last_attempt(env, monkeypatch):
    env(DGATE_ATLAS_BACKFILL_YEARS="2024")

    def always_fails(year, **kw):
        raise ConnectionError("down")

    monkeypatch.setattr(pipeline, "run_atlas_backfill", always_fails)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    monkeypatch.setattr(worker, "run_job", lambda name, fn, **kw: fn())
    with pytest.raises(ConnectionError):
        worker.job_atlas_backfill(attempts=3, pause=0)


def test_the_backfill_uses_its_own_wider_writer_pool(env, monkeypatch):
    env(DGATE_ATLAS_BACKFILL_YEARS="2024", DGATE_ATLAS_WRITE_WORKERS=64)
    seen = {}
    monkeypatch.setattr(pipeline, "run_atlas_backfill",
                        lambda year, **kw: seen.update(kw))
    monkeypatch.setattr(worker, "run_job", lambda name, fn, **kw: fn())
    worker.job_atlas_backfill(attempts=1, pause=0)
    assert seen["workers"] == 64


# --------------------------------------------- the TED history load

def test_the_history_is_off_until_a_start_date_is_given(env, monkeypatch):
    """Seven million notices over several days is a decision, not something a
    container inherits by starting."""
    monkeypatch.delenv("DGATE_TED_HISTORY_FROM", raising=False)
    env()
    assert worker.ted_history_window() is None


def test_the_history_ends_yesterday_unless_told_otherwise(env, monkeypatch):
    """Today is the daily job's business; the history stops where it begins."""
    from datetime import date, timedelta

    monkeypatch.delenv("DGATE_TED_HISTORY_TO", raising=False)
    env(DGATE_TED_HISTORY_FROM="2017-01-01")
    start, end = worker.ted_history_window()
    assert start == date(2017, 1, 1)
    assert end == date.today() - timedelta(days=1)


def test_a_window_that_ends_before_it_starts_is_no_window(env):
    env(DGATE_TED_HISTORY_FROM="2020-01-01", DGATE_TED_HISTORY_TO="2019-01-01")
    assert worker.ted_history_window() is None


def test_the_history_runs_beside_the_catch_up_not_before_it(env, monkeypatch):
    """A decade of history must not hold up three missed days of collection."""
    env(DGATE_ATLAS_BACKFILL_YEARS="", DGATE_TED_HISTORY_FROM="2017-01-01")
    started: list[str] = []

    class _Thread:
        def __init__(self, target=None, name=None, daemon=None):
            self.name = name

        def start(self):
            started.append(self.name)

    monkeypatch.setattr(worker.threading, "Thread", _Thread)
    threads = worker.start_backfill_thread()
    assert started == ["ted-history"]
    assert len(threads) == 1
