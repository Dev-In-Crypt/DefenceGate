"""WP-143 against a real Postgres: the digest weeks a suppression entry dropped are stored again by the hourly gap run, which
writes nothing (and no job_run row) when nothing is missing; a frequent search word's first page is kept with the warm lists."""

from __future__ import annotations

import pytest

from dgate import tenders, worker
from dgate import weekly_digest as W
from dgate.ops import suppress, warm_lists

pytestmark = pytest.mark.integration


def _digest_runs(conn) -> int:
    return conn.execute("SELECT count(*) AS n FROM job_run WHERE job = 'digest'").fetchone()["n"]


def test_missing_digest_weeks_are_stored_again_within_the_hour(conn, monkeypatch):
    monkeypatch.setenv("DGATE_JOB_RUNS", "1")
    weeks = W.all_weeks(W.datetime.now(W.timezone.utc))
    assert W.missing_weeks(conn) == weeks                         # nothing stored yet
    first = worker.job_digest_gaps()
    assert first.status == "success"
    assert len(W.missing_weeks(conn)) == max(0, len(weeks) - 8)   # eight a run, newest first
    if len(weeks) > 8:
        worker.job_digest_gaps()
    assert W.missing_weeks(conn) == []
    runs = _digest_runs(conn)
    quiet = worker.job_digest_gaps()
    assert quiet.detail == "nothing missing" and _digest_runs(conn) == runs     # no build and no job_run row
    # 26 October 2026: an organisation entry in `suppression` dropped every stored issue
    suppress.drop_derived(conn)
    conn.commit()
    assert W.missing_weeks(conn) == weeks
    worker.job_digest_gaps()
    assert len(W.missing_weeks(conn)) == max(0, len(weeks) - 8)


def test_the_first_page_of_a_frequent_search_word_is_kept_with_the_warm_lists():
    todo = warm_lists.views([])
    for q in tenders.search_set_words():
        for status in ("closed", "all"):
            assert any(n == "tenders" and kw.get("q") == q and kw["status"] == status and kw["page"] == 1 for n, _, kw in todo), (q, status)
            assert any(n == "tender-scope-counts" and kw.get("q") == q and kw["status"] == status for n, _, kw in todo), (q, status)
    assert not any(kw.get("q") and kw.get("status") == "open" for _, _, kw in todo)         # open lists stay live
