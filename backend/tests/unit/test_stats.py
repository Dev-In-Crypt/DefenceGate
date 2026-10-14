"""The pure parts of dgate/stats.py: the month list and the hour of cache."""

from __future__ import annotations

import threading
import time
from datetime import date

from dgate import stats


def test_month_starts_end_with_the_current_month_and_cross_the_year():
    got = stats.month_starts(date(2026, 2, 17), 4)
    assert got == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


def test_36_months_from_october_2026_start_in_november_2023():
    got = stats.month_starts(date(2026, 10, 13), 36)
    assert len(got) == 36 and got[0] == date(2023, 11, 1) and got[-1] == date(2026, 10, 1)


def test_a_value_is_computed_once_per_hour(monkeypatch):
    stats.reset_cache()
    clock = [1000.0]
    monkeypatch.setattr(stats.time, "monotonic", lambda: clock[0])
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}

    assert stats.cached("k", compute) == {"n": 1}
    clock[0] += stats.CACHE_SECONDS - 1
    assert stats.cached("k", compute) == {"n": 1}
    clock[0] += 2
    assert stats.cached("k", compute) == {"n": 2}
    stats.reset_cache()


def test_nothing_is_not_cached(monkeypatch):
    stats.reset_cache()
    calls = []
    assert stats.cached("missing", lambda: calls.append(1)) is None
    assert stats.cached("missing", lambda: calls.append(1)) is None
    assert len(calls) == 2 and "missing" not in stats._cache


def test_the_cache_is_bounded_and_drops_the_oldest(monkeypatch):
    stats.reset_cache()
    monkeypatch.setattr(stats, "MAX_CACHED", 3)
    clock = [0.0]
    monkeypatch.setattr(stats.time, "monotonic", lambda: clock[0])
    for key in "abcd":
        clock[0] += 1
        stats.cached(key, lambda key=key: key)
    assert sorted(stats._cache) == ["b", "c", "d"]
    stats.reset_cache()


def test_a_computation_that_raises_is_not_cached_and_does_not_disturb_the_rest():
    stats.reset_cache()
    assert stats.cached("done", lambda: 1) == 1

    def boom():
        raise RuntimeError("out of budget")

    try:
        stats.cached("failed", boom)
    except RuntimeError:
        pass
    assert "failed" not in stats._cache and stats.cached("done", lambda: 2) == 1
    assert stats.cached("failed", lambda: 3) == 3
    stats.reset_cache()


def test_one_slow_key_does_not_hold_up_another(monkeypatch):
    """Audit M1: one lock round every computation made a buyer profile (seconds) hold up the
    list pages' own timestamp read. Different keys run side by side; one key runs once."""
    stats.reset_cache()
    slow_started, release = threading.Event(), threading.Event()
    runs = {"slow": 0}

    def slow():
        runs["slow"] += 1
        slow_started.set()
        release.wait(5)
        return "slow-value"

    results: list[str] = []
    threads = [threading.Thread(target=lambda: results.append(stats.cached("slow", slow)))
               for _ in range(3)]
    for t in threads:
        t.start()
    assert slow_started.wait(2)
    started = time.monotonic()
    assert stats.cached("fast", lambda: "fast-value") == "fast-value"
    assert time.monotonic() - started < 1, "a fast key waited for a slow one"
    release.set()
    for t in threads:
        t.join(5)
    assert results == ["slow-value"] * 3 and runs["slow"] == 1, "one computation, shared"
    stats.reset_cache()


def test_followers_of_a_failing_computation_get_its_error_and_nothing_is_kept():
    stats.reset_cache()
    started, release = threading.Event(), threading.Event()

    def failing():
        started.set()
        release.wait(5)
        raise ValueError("no")

    errors: list[str] = []

    def ask():
        try:
            stats.cached("k", failing)
        except ValueError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=ask) for _ in range(3)]
    for t in threads:
        t.start()
    assert started.wait(2)
    release.set()
    for t in threads:
        t.join(5)
    assert errors == ["no"] * 3
    assert stats.cached("k", lambda: "recovered") == "recovered"
    stats.reset_cache()
