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


def test_a_buyer_withheld_as_a_person_is_said_so_and_one_removed_on_request_keeps_its_words(conn):
    from datetime import datetime, timezone

    from fastapi.testclient import TestClient

    from dgate import api, stats
    from dgate.ops import person_rows
    from dgate.suppress import PERSON_NAME, WITHHELD_NAME
    from tests.integration.test_wp138 import put

    person = put(conn, "495013-2020", buyer="John Example", country="GB", cpv="35320000")
    asked = put(conn, "495015-2020", buyer="Asked Removal Ltd", country="GB", cpv="35320000")
    org_of = lambda oid: conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (oid,)).fetchone()["buyer_org_id"]  # noqa: E731
    person_org, asked_org = org_of(person), org_of(asked)
    person_rows.mark(conn, [person_org], write=True)
    suppress.add(conn, kind="organisation", source=None, native_id=None, organisation=asked_org, reason="request",
                 requested_at=datetime.now(timezone.utc), decided_by="owner")
    conn.commit()
    stats.reset_cache()
    with TestClient(api.app) as c:
        got = c.get(f"/v1/tenders/{person}").json()
        assert got["buyerName"] == PERSON_NAME and got["buyerId"] is None and "John Example" not in str(got)
        listed = {t["id"]: t["buyerName"] for t in c.get("/v1/tenders", params={"status": "all", "scope": "all"}).json()["items"]}
        assert listed[str(person)] == PERSON_NAME and listed[str(asked)] == WITHHELD_NAME
        page = c.get(f"/v1/buyers/{person_org}")
        assert page.status_code == 410 and page.json()["detail"] == PERSON_NAME
        removed = c.get(f"/v1/buyers/{asked_org}")
        assert removed.status_code == 410 and removed.json()["detail"] == "removed on request"
        assert "on request" not in str(c.get(f"/v1/opportunities/{person}").json())


def test_the_first_page_of_a_frequent_search_word_is_kept_with_the_warm_lists():
    todo = warm_lists.views([])
    for q in tenders.search_set_words():
        for status in ("closed", "all"):
            assert any(n == "tenders" and kw.get("q") == q and kw["status"] == status and kw["page"] == 1 for n, _, kw in todo), (q, status)
            assert any(n == "tender-scope-counts" and kw.get("q") == q and kw["status"] == status for n, _, kw in todo), (q, status)
    assert not any(kw.get("q") and kw.get("status") == "open" for _, _, kw in todo)         # open lists stay live
