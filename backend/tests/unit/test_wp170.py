"""WP-170: a list count is kept for the next page (`tenders._count_up_to`), by its conditions, its cap and the newest notice; a
count that got less than its own time box, because the request had spent its budget on other counts, is not kept (in another
request it may finish)."""

from __future__ import annotations

import pytest

from dgate import config, stats, tenders


class Conn:
    """Answers the newest notice's id (part of a kept count's key)."""
    newest = 1

    def execute(self, *_):
        return self

    def fetchone(self):
        return {"m": self.newest}


@pytest.fixture
def cache_on(monkeypatch):
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "60")
    config.reset_cache()
    stats.reset_cache()
    yield
    monkeypatch.setenv("DGATE_LIST_CACHE_SECONDS", "0")
    config.reset_cache()
    stats.reset_cache()


def _live(monkeypatch, answer):
    calls = []
    monkeypatch.setattr(tenders, "_count_live", lambda *a: calls.append(a) or answer)
    return calls


def test_a_count_is_kept_by_its_conditions_its_cap_and_the_newest_notice(cache_on, monkeypatch):
    calls, c = _live(monkeypatch, 7), Conn()
    args = (c, "a AND b", ["a"], [1], tenders.SMALL_CAP, 100)
    assert tenders._count_up_to(*args) == tenders._count_up_to(*args) == 7 and len(calls) == 1
    tenders._count_up_to(c, "a AND b", ["a"], [2], tenders.SMALL_CAP, 100)          # other parameters
    tenders._count_up_to(c, "a AND b", ["a"], [1], tenders.TOTAL_CAP, 100)          # another cap
    tenders._count_up_to(c, "a AND b", ["a", "b"], [1], tenders.SMALL_CAP, 100)     # same text, other collapse rules
    assert len(calls) == 4
    c.newest = 2                                                                     # a notice was added: counted again
    tenders._count_up_to(*args)
    assert len(calls) == 5


def test_a_count_that_ran_out_of_its_own_box_is_kept_one_cut_short_by_the_request_is_not(cache_on, monkeypatch):
    calls, c = _live(monkeypatch, None), Conn()
    with tenders.count_budget(50):                     # less left than the count's own box of 100 ms
        assert tenders._count_up_to(c, "c", ["c"], [], 200, 100) is None
    assert tenders._count_up_to(c, "c", ["c"], [], 200, 100) is None   # tried again, with its whole box
    assert len(calls) == 2
    assert tenders._count_up_to(c, "c", ["c"], [], 200, 100) is None   # kept: "at least" on the next page too
    assert len(calls) == 2


def test_nothing_is_kept_with_the_list_cache_off(monkeypatch):
    calls = _live(monkeypatch, 3)
    for _ in range(2):
        tenders._count_up_to(Conn(), "d", ["d"], [], 200, 100)
    assert len(calls) == 2
