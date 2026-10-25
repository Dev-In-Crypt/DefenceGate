"""WP-139 (verification round 8, system) against a real Postgres:

  - a list's "latest run of its sources" is a run that brought data (the home page's rule since WP-131)
  - the buyer profile finds the buyer's notices once and counts every figure over them, with the same figures
  - the TED award reader is short on a day TED brought result notices and it read none; the second run of a day is not
  - the EU portal's topic-page run records a floor, and is partial when most of the pages it asked could not be read
  - a job a restart cut short is run again by the start-up catch-up, a weekly one too, and the restart says so
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from dgate import awards, config, db, pipeline, stats, worker
from dgate.sources import eu_portal as portal
from tests.integration.test_changes import client, opp, store  # noqa: F401 - fixtures
from tests.integration.test_topic_details import (  # noqa: F401 - fixtures
    _calendar,
    _calendar_topic,
    _details,
    fs_store,
    no_pause,
)
from tests.integration.test_wp95 import FakeTed

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    config.reset_cache()
    yield
    stats.reset_cache()
    config.reset_cache()


def _run(conn, code: str, finished: datetime, fetched: int, status: str = "success") -> None:
    run_id = db.start_run(conn, code, expected_min=None)
    db.finish_run(conn, run_id, fetched=fetched, new=0, changed=0, status="success")
    conn.execute("UPDATE ingest_run SET status = %s, finished_at = %s, started_at = %s WHERE id = %s",
                 (status, finished, finished - timedelta(minutes=5), run_id))
    conn.commit()


# ------------------------------------------------------------------ 1. the lists' "latest run"

def test_a_run_that_read_nothing_is_not_the_lists_latest_run(client, conn):  # noqa: F811
    """25 Oct 2026: "Latest run of its sources: 17:39 (e-Zamówienia)", a refused source's run of 0 records, while the home page
    said 06:57 (TED). The list names the newest run that brought data, as the home page does."""
    base = datetime(2026, 10, 25, 6, 57, tzinfo=timezone.utc)
    _run(conn, "ted", base, 65)
    _run(conn, "pl_ezam", base + timedelta(hours=10, minutes=42), 0, status="partial")
    meta = client.get("/v1/tenders").json()["meta"]
    assert datetime.fromisoformat(meta["updatedAt"]) == base
    assert meta["updatedBy"] == conn.execute("SELECT name FROM source WHERE code = 'ted'").fetchone()["name"]


# ------------------------------------------------------------------ 2. the buyer profile

class _Counting:
    """The connection, counting the statements that read the buyer's family (the costly scope)."""

    def __init__(self, conn):
        self.conn, self.scoped = conn, 0

    def execute(self, sql, *args, **kw):
        self.scoped += "dgate_family_ids" in str(sql)
        return self.conn.execute(sql, *args, **kw)


def test_the_buyer_profile_reads_the_buyers_notices_once_with_the_same_figures(client, conn):  # noqa: F811
    """3 RBLog's profile took 6.9 s cold (25 Oct 2026): a dozen statements each found the buyer's notices with the collapse
    rules. Shaped like WP-135's buyer 7310 (10 bulletin, 4 TED, 3 mirror notices, 2 copies of TED: 12 notices)."""
    for i in range(4):
        store(conn, replace(opp(f"80000{i}-2025", country="PL"), buyer_name_raw="Ministry PL"))
    for i in range(10):
        store(conn, replace(opp(f"2025/BZP 0000010{i}", source="pl_ezam", country="PL",
                                ted_ref=f"80000{i}-2025" if i < 2 else None), buyer_name_raw="Ministry PL"))
    for i in range(3):
        store(conn, replace(opp(f"2025/BZP 0000010{i + 5}", source="pl_atlas", country="PL"), buyer_name_raw="Ministry PL"))
    listed = client.get("/v1/tenders", params={"status": "all", "pageSize": 100}).json()
    buyer = int(listed["items"][0]["buyerId"])
    spy = _Counting(conn)
    profile = stats.buyer_profile(spy, buyer)
    assert spy.scoped == 1
    assert profile["tenderCount"] == listed["total"] == 12
    assert sum(s["count"] for s in profile["sources"]) == 12
    assert sum(y["count"] for y in profile["perYear"]) + profile["perYearEarlier"] + profile["perYearUndated"] == 12
    assert profile["cpvGroups"] == [{"group": "354", "count": 12}]
    assert profile["openNow"] == 12 and profile["amendments"]["observedFrom"] is not None
    assert stats.buyer_profile(conn, 999_999_999) is None


# ------------------------------------------------------------------ 3. the TED award reader's floor

def _result_notice(conn, native: str) -> None:
    conn.execute(
        """INSERT INTO opportunity (source_id, native_id, buyer_name_raw, country, title_original, published_at, cpv_codes,
                                    is_defence, sig_legal_basis, sig_cpv, sig_cpv_military, buyer_class, notice_subtype,
                                    status, status_native)
           VALUES ((SELECT id FROM source WHERE code = 'ted'), %s, 'Ministerio de Defensa', 'ES', 'Trajes', current_date - 3,
                   '{35510000}', true, true, true, true, 'defence', '29', 'awarded', 'can-standard')""", (native,))
    conn.commit()


def _award_runs(conn) -> list[tuple[str, int, int]]:
    return [(r["status"], r["records_fetched"], r["expected_min"]) for r in conn.execute(
        """SELECT r.status, r.records_fetched, r.expected_min FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.code = 'ted_awards' ORDER BY r.id""").fetchall()]


def test_a_day_on_which_the_award_reader_read_nothing_is_short_and_its_second_run_is_not(conn, fs_store, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DGATE_FLOOR_TED_AWARDS", "2")
    config.reset_cache()
    ted = FakeTed({})
    awards.run_awards(client=ted.client(), pause=0, sleep=lambda s: None)
    assert _award_runs(conn) == [("partial", 0, 2)]             # was: expected_min 0 and "success" (run 488 of 25 Oct)
    conn.execute("DELETE FROM ingest_run WHERE source_id = (SELECT id FROM source WHERE code = 'ted_awards')")
    conn.commit()
    for n in ("1-2026", "2-2026", "3-2026"):
        _result_notice(conn, n)
    ted = FakeTed({n: {"publication-number": n} for n in ("1-2026", "2-2026", "3-2026")})
    awards.run_awards(client=ted.client(), pause=0, sleep=lambda s: None)
    awards.run_awards(client=ted.client(), pause=0, sleep=lambda s: None)      # nothing left: the day's floor is met
    assert _award_runs(conn) == [("success", 3, 3), ("success", 0, 0)]


# ------------------------------------------------------------------ 4. the topic-page run's floor

def test_the_topic_page_run_records_a_floor_and_is_partial_when_most_pages_fail(conn, fs_store, monkeypatch):  # noqa: F811
    codes = [f"EDF-2026-RA-T{i}" for i in range(4)]
    _calendar(monkeypatch, [_calendar_topic(i + 1, c) for i, c in enumerate(codes)])
    pipeline.run_eu_portal()

    def flaky(identifier, client=None):  # noqa: F811 - the reader's own keyword
        if identifier != codes[0]:
            raise RuntimeError("503")
        return _details(identifier)

    monkeypatch.setattr(portal, "fetch_topic_details", flaky)
    pipeline.run_topic_details()
    run = conn.execute(
        """SELECT r.status, r.records_fetched, r.expected_min FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.code = 'eu_portal' ORDER BY r.id DESC LIMIT 1""").fetchone()
    assert (run["status"], run["records_fetched"], run["expected_min"]) == ("partial", 1, 2)


# ------------------------------------------------------------------ 5. a job a restart cut short

def test_a_weekly_job_a_restart_cut_short_is_run_again_and_the_restart_says_so(conn, monkeypatch):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    monkeypatch.setenv("DGATE_JOB_RUNS", "1")
    config.reset_cache()
    said: list[str] = []
    monkeypatch.setattr(worker, "notify", lambda text, *a, **k: said.append(text) or True)
    ran: list[str] = []
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(lambda: ran.append("requalify_weekly"), CronTrigger(day_of_week="sun", hour=12, minute=0),
                  id="requalify_weekly")
    sched.add_job(lambda: ran.append("digest"), CronTrigger(hour=11, minute=0), id="digest_daily")
    conn.execute("INSERT INTO job_run (job, started_at, owner) VALUES ('requalify_weekly', '2026-10-25 12:00+00', %s)",
                 (db.RUN_KIND,))
    conn.execute("INSERT INTO job_run (job, started_at, status) VALUES ('digest', '2026-10-25 11:00+00', 'success')")
    conn.commit()
    worker.close_interrupted_runs()                     # the deploy of 13:24 recreated the worker
    assert conn.execute("SELECT status FROM job_run WHERE job = 'requalify_weekly'").fetchone()["status"] == "interrupted"
    assert any("requalify_weekly (started 2026-10-25 12:00 UTC)" in s for s in said)
    worker.catch_up_jobs(sched, datetime(2026, 10, 25, 13, 30, tzinfo=timezone.utc))
    assert ran == ["requalify_weekly"]                  # was: none, the next slot 1 Nov
