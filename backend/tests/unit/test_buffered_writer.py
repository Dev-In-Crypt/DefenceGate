"""Concurrent raw writes, and the one ordering they must not break.

Raw payloads go to object storage one small HTTPS round trip at a time. At
530 ms each -- measured against R2 from this deployment -- a daily PLACSP run
cannot finish inside a day, so the writes overlap. What must survive that is
the rule the whole durability story rests on: a committed `raw_ingest` row
always has its object in the store.
"""

from __future__ import annotations

import threading

import pytest

from dgate.rawstore import BufferedWriter, FileRawStore


class SlowStore(FileRawStore):
    """A store that blocks until released, so ordering can be observed."""

    def __init__(self, root, gate: threading.Event) -> None:
        super().__init__(root)
        self.gate = gate
        self.written: list[str] = []
        self._lock = threading.Lock()

    def put(self, key, payload, content_type="application/json"):
        self.gate.wait(timeout=5)
        result = super().put(key, payload, content_type)
        with self._lock:
            self.written.append(key)
        return result


def test_put_returns_before_the_write_lands(tmp_path):
    gate = threading.Event()
    store = SlowStore(tmp_path, gate)
    with BufferedWriter(store, workers=4) as writer:
        writer.put("a/1.json", {"n": 1})
        assert store.written == [], "put() must not block on the round trip"
        gate.set()
        writer.drain()
    assert store.written == ["a/1.json"]


def test_drain_waits_for_every_queued_write(tmp_path):
    gate = threading.Event()
    gate.set()
    store = SlowStore(tmp_path, gate)
    with BufferedWriter(store, workers=8) as writer:
        for i in range(50):
            writer.put(f"a/{i}.json", {"n": i})
        assert writer.drain() == 50
        assert sorted(store.written) == sorted(f"a/{i}.json" for i in range(50))


def test_drain_reraises_a_failed_write(tmp_path):
    class BrokenStore(FileRawStore):
        def put(self, key, payload, content_type="application/json"):
            raise OSError("bucket unreachable")

    with pytest.raises(OSError, match="bucket unreachable"):
        with BufferedWriter(BrokenStore(tmp_path), workers=4) as writer:
            writer.put("a/1.json", {"n": 1})
            writer.drain()


def test_a_failure_is_not_hidden_by_a_later_success(tmp_path):
    """One bad write must fail the drain even when the rest are fine.

    Otherwise the run commits `raw_ingest` rows for a payload that is not in
    the store, which is the exact divergence draining exists to prevent.
    """
    class FlakyStore(FileRawStore):
        def put(self, key, payload, content_type="application/json"):
            if key.endswith("7.json"):
                raise OSError("write rejected")
            return super().put(key, payload, content_type)

    with pytest.raises(OSError, match="write rejected"):
        with BufferedWriter(FlakyStore(tmp_path), workers=8) as writer:
            for i in range(20):
                writer.put(f"a/{i}.json", {"n": i})
            writer.drain()


def test_payload_is_captured_at_submit_not_at_write(tmp_path):
    """The caller reuses and mutates payload dicts; the store must not see that."""
    gate = threading.Event()
    store = SlowStore(tmp_path, gate)
    payload = {"value": "original"}
    with BufferedWriter(store, workers=2) as writer:
        writer.put("a/1.json", payload)
        payload["value"] = "mutated after submit"
        gate.set()
        writer.drain()
    assert store.get("a/1.json") == {"value": "original"}


def test_a_single_worker_writes_straight_through(tmp_path):
    """workers=1 keeps the old synchronous behaviour, for a store that needs it."""
    gate = threading.Event()
    gate.set()
    store = SlowStore(tmp_path, gate)
    writer = BufferedWriter(store, workers=1)
    writer.put("a/1.json", {"n": 1})
    assert store.written == ["a/1.json"], "no queueing when there is one worker"
    writer.close()


def test_the_first_write_into_a_new_directory_is_accepted(tmp_path):
    """A key whose parent does not exist yet must still be accepted.

    On Windows `Path.resolve()` returns the extended-length `\\?\C:\...` form
    for a path that does not exist and the plain form for one that does, so a
    containment check that resolved both rejected every key under a directory
    not yet created. Every date directory is new exactly once, which made this
    the first write of each day.
    """
    store = FileRawStore(tmp_path / "store")
    key = store.put("ted/2026/09/10/notice-1.json", {"n": 1})
    assert store.get(key) == {"n": 1}


def test_a_key_that_climbs_out_of_the_root_is_still_refused(tmp_path):
    store = FileRawStore(tmp_path / "store")
    with pytest.raises(ValueError, match="escapes the store root"):
        store.put("../../escaped.json", {"n": 1})


def test_concurrent_writes_into_one_new_directory_all_land(tmp_path):
    store = FileRawStore(tmp_path / "store")
    with BufferedWriter(store, workers=8) as writer:
        for i in range(60):
            writer.put(f"ted/2026/09/10/n{i}.json", {"n": i})
        writer.drain()
    assert sorted(store.get(f"ted/2026/09/10/n{i}.json")["n"] for i in range(60)) == list(range(60))
