"""A store outage during a replay is waited out, never recorded as bad data.

On 13 September 2026 the network dropped 7,800 keys into a reclassification and
the run carried on through 147,000 more, marking every one failed without
reading any of them.
"""

from __future__ import annotations

import pytest

from dgate import reprocess


class FlakyStore:
    def __init__(self, outages: int, bad_keys: set[str] | None = None) -> None:
        self.outages = outages
        self.bad_keys = bad_keys or set()
        self.rounds = 0

    def get(self, key):
        if self.rounds < self.outages:
            raise ConnectionError('Could not connect to the endpoint URL')
        if key in self.bad_keys:
            raise ValueError("corrupt object")
        return {"key": key}


def read(store, keys, attempts=5):
    def next_round(*_):
        store.rounds += 1

    # Each pause stands for the time in which the outage clears.
    original = reprocess._read_all

    def counted(s, ks, w):
        out = original(s, ks, w)
        if all(isinstance(p, Exception) for p in out):
            next_round()
        return out

    reprocess._read_all = counted
    try:
        return reprocess._read_batch(store, keys, workers=1, attempts=attempts, pause=0)
    finally:
        reprocess._read_all = original


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import time

    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_a_batch_is_retried_until_the_store_comes_back():
    payloads = read(FlakyStore(outages=2), ["a", "b", "c"])
    assert payloads == [{"key": "a"}, {"key": "b"}, {"key": "c"}]


def test_a_store_that_never_comes_back_stops_the_run():
    with pytest.raises(reprocess.StoreUnavailable):
        read(FlakyStore(outages=100), ["a", "b"], attempts=3)


def test_one_bad_object_among_good_ones_is_not_an_outage():
    """The rule that one unreadable object must not stop a replay still holds."""
    store = FlakyStore(outages=0, bad_keys={"b"})
    payloads = read(store, ["a", "b", "c"])
    assert payloads[0] == {"key": "a"} and payloads[2] == {"key": "c"}
    assert isinstance(payloads[1], ValueError)
    assert store.rounds == 0
