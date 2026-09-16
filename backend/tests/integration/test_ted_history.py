"""The historical load, against a real Postgres.

Seven million notices over days of running means the question is not whether it
works, but what happens when it stops halfway: on a restart, a network outage,
a full disk. These tests pin that.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import config, db, pipeline
from dgate.sources import ted

pytestmark = pytest.mark.integration


def _notice(number: str, *, defence: bool) -> dict:
    return {
        "notice-identifier": [number],
        "publication-number": [number],
        "notice-title": {"eng": "Supply contract"},
        "buyer-name": {"eng": ["Something Authority"]},
        "buyer-country": ["DEU"],
        "official-language": ["eng"],
        "dispatch-date": ["2019-06-03+02:00"],
        "classification-cpv": ["35700000" if defence else "45210000"],
        "legal-basis": ["32009L0081" if defence else "32014L0024"],
    }


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _days_served(monkeypatch, by_day: dict[date, list[dict]], fail_on: date | None = None):
    asked: list[str] = []

    def fake_search(query, *a, **kw):
        asked.append(query)
        day = date.fromisoformat(
            f"{query[len('publication-date>='):][:4]}-"
            f"{query[len('publication-date>='):][4:6]}-"
            f"{query[len('publication-date>='):][6:8]}")
        if day == fail_on:
            raise ConnectionError("the network went away mid-day")
        yield from by_day.get(day, [])

    monkeypatch.setattr(ted, "search", fake_search)
    return asked


def test_every_notice_is_landed_and_only_defence_becomes_an_opportunity(conn, store, monkeypatch):
    """The point of the history: land all of it, decide later. A signal learned
    next year must be a reclassification, not a refetch of a decade."""
    _days_served(monkeypatch, {
        date(2019, 6, 3): [_notice("001-2019", defence=True),
                           _notice("002-2019", defence=False)],
        date(2019, 6, 4): [_notice("003-2019", defence=False)],
    })
    loaded = pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 4))

    assert loaded == 2
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 1
    assert conn.execute("SELECT count(*) n FROM ingest_run").fetchone()["n"] == 0


def test_a_finished_day_is_recorded_with_what_it_held(conn, store, monkeypatch):
    _days_served(monkeypatch, {date(2019, 6, 3): [_notice("001-2019", defence=False)] * 1})
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3))
    row = conn.execute("SELECT day, notices FROM backfill_day WHERE source_code='ted'").fetchone()
    assert (row["day"], row["notices"]) == (date(2019, 6, 3), 1)


def test_an_interrupted_day_is_not_marked_and_is_asked_for_again(conn, store, monkeypatch):
    """A marker that runs ahead of the data turns an interruption into a
    permanent hole -- the one failure a resumable load must not have."""
    by_day = {date(2019, 6, 3): [_notice("001-2019", defence=True)],
              date(2019, 6, 4): [_notice("002-2019", defence=True)]}
    _days_served(monkeypatch, by_day, fail_on=date(2019, 6, 4))
    with pytest.raises(ConnectionError):
        pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 4))
    assert db.backfill_days_done(conn, "ted") == {date(2019, 6, 3)}

    asked = _days_served(monkeypatch, by_day)
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 4))
    assert asked == [ted.day_query(date(2019, 6, 4))]
    assert db.backfill_days_done(conn, "ted") == {date(2019, 6, 3), date(2019, 6, 4)}


def test_reloading_a_day_writes_no_second_version(conn, store, monkeypatch):
    """Unchanged content is not a change, so a day loaded twice by hand costs
    requests and nothing else."""
    by_day = {date(2019, 6, 3): [_notice("001-2019", defence=True)]}
    _days_served(monkeypatch, by_day)
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3))
    _days_served(monkeypatch, by_day)
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3), resume=False)
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1


def test_the_history_never_claims_a_daily_run_happened(conn, store, monkeypatch):
    """Catch-up decides freshness from the last successful run. A run that
    collected June 2019 says nothing about today, so the history writes none."""
    _days_served(monkeypatch, {date(2019, 6, 3): [_notice("001-2019", defence=True)]})
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3))
    assert conn.execute("SELECT count(*) n FROM ingest_run").fetchone()["n"] == 0
