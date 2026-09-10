"""Ingestion must commit as it goes, in a feed that is mostly not defence.

Every feed we ingest is overwhelmingly non-defence, so the branch that skips a
non-defence notice is the common path, not the exception. A checkpoint placed
after that skip is therefore a checkpoint that never runs: the whole ingest
becomes one transaction, nothing is logged, and a failure at the end discards
every `raw_ingest` row while the payloads already written to object storage
stay where they are. That divergence -- a store the index no longer describes --
is the one thing the raw store is meant to rule out.
"""

from __future__ import annotations

import inspect

import pytest

from dgate import pipeline


class FakeConn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def test_checkpoint_commits_on_the_interval():
    conn = FakeConn()
    for fetched in range(1, 401):
        pipeline._checkpoint(conn, "src", fetched, 0, 0, every=100)
    assert conn.commits == 4


def test_checkpoint_does_nothing_before_the_first_interval():
    conn = FakeConn()
    pipeline._checkpoint(conn, "src", 0, 0, 0, every=100)
    pipeline._checkpoint(conn, "src", 99, 0, 0, every=100)
    assert conn.commits == 0


@pytest.mark.parametrize("func", ["run_ted", "run_ezamowienia", "_ingest_placsp"])
def test_the_checkpoint_runs_before_anything_can_skip_the_record(func):
    """The checkpoint must sit above every `continue` in the ingest loop.

    Read as source rather than exercised, because reproducing it behaviourally
    needs a live feed; the ordering is the whole property, and it is what was
    wrong.
    """
    body = inspect.getsource(getattr(pipeline, func))
    lines = [ln.strip() for ln in body.splitlines()]
    checkpoint = next(i for i, ln in enumerate(lines) if ln.startswith("_checkpoint("))
    skips = [i for i, ln in enumerate(lines) if ln == "continue"]
    assert skips, f"{func} has no skip; this test is guarding nothing"
    assert checkpoint < min(skips), (
        f"{func} checkpoints after a `continue`, so it will not run on a "
        "feed that is mostly non-defence"
    )


@pytest.mark.parametrize("func", ["run_ted", "run_ezamowienia", "_ingest_placsp"])
def test_no_ingest_loop_commits_by_hand(func):
    """One place decides when to commit, so the three loops cannot drift apart."""
    body = inspect.getsource(getattr(pipeline, func))
    assert "conn.commit()" not in body
