"""WP-120 without a database: an expired aggregate is answered at once while one background read renews it, and a list
request with no counting time left starts no count."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from dgate import stats, tenders


def test_an_expired_value_is_answered_while_one_background_read_renews_it(monkeypatch):
    stats.reset_cache()
    renewed = threading.Event()
    calls: list[str] = []

    @contextmanager
    def fake_connection():
        yield "background"

    monkeypatch.setattr(stats, "_connection", fake_connection)

    def compute(c):
        calls.append(c)
        if c == "background":
            renewed.set()
        return f"value from {c}"

    key = ("wp120-test",)
    assert stats.cached_stale(key, compute, "request", 60, 600) == "value from request"      # nothing kept: computed now
    stats._cache[key] = (time.monotonic() - 1, "old")                                         # expired a second ago
    assert stats.cached_stale(key, compute, "request", 60, 600) == "old"                      # answered at once
    assert renewed.wait(5)
    for _ in range(50):
        if key not in stats._refreshing:
            break
        time.sleep(0.01)
    assert stats.cached_stale(key, compute, "request", 60, 600) == "value from background"
    stats._cache[key] = (time.monotonic() - 700, "too old")                                   # past the stale window
    assert stats.cached_stale(key, compute, "request", 60, 600) == "value from request"
    assert calls == ["request", "background", "request"]
    stats.reset_cache()


def test_a_failed_renewal_keeps_the_old_value(monkeypatch):
    stats.reset_cache()
    done = threading.Event()

    @contextmanager
    def fake_connection():
        try:
            yield "background"
        finally:
            done.set()

    monkeypatch.setattr(stats, "_connection", fake_connection)

    def compute(c):
        raise RuntimeError("down")

    key = ("wp120-fail",)
    stats._cache[key] = (time.monotonic() - 1, "old")
    assert stats.cached_stale(key, compute, None, 60, 600) == "old"
    assert done.wait(5)
    for _ in range(50):
        if key not in stats._refreshing:
            break
        time.sleep(0.01)
    assert stats._cache[key][1] == "old" and key not in stats._refreshing
    stats.reset_cache()


def test_no_count_is_started_without_counting_time_left():
    with tenders.count_budget(tenders.COUNT_MIN_MS - 1):
        # no connection is touched: the count is "not in time" at once
        assert tenders._count_up_to(None, "TRUE", [], [], 10, 1000) is None
    assert tenders._COUNT_LEFT.get() is None                                                  # outside a request: no budget
