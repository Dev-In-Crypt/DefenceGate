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


def test_a_day_is_one_object_in_the_store(conn, store, monkeypatch):
    """Writes are what object storage bills for. Four point eight million
    notices written one at a time cost about $22; a day written whole is one
    write instead of three thousand."""
    _days_served(monkeypatch, {date(2019, 6, 3): [_notice(f"{i:03d}-2019", defence=False)
                                                  for i in range(25)]})
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3))

    objects = sorted(p.name for p in (store / "ted" / "2019" / "06" / "03").iterdir())
    assert objects == ["bundle-0000.jsonl.gz"]


def test_each_record_keeps_its_own_address_inside_the_bundle(conn, store, monkeypatch):
    """Replay reads one payload at a time, so a bundled record still has to be
    addressable on its own -- the key carries the line."""
    from dgate.rawstore import build_store

    _days_served(monkeypatch, {date(2019, 6, 3): [_notice("001-2019", defence=True),
                                                  _notice("002-2019", defence=True)]})
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3))

    keys = [r["storage_key"] for r in conn.execute(
        "SELECT storage_key FROM raw_ingest ORDER BY id").fetchall()]
    assert keys == ["ted/2019/06/03/bundle-0000.jsonl.gz#0",
                    "ted/2019/06/03/bundle-0000.jsonl.gz#1"]
    payloads = [build_store().get(key) for key in keys]
    assert [p["notice-identifier"] for p in payloads] == [["001-2019"], ["002-2019"]]


def test_a_landed_payload_carries_no_personal_data(conn, store, monkeypatch):
    """The bundle is written from the cleaned payloads, not the raw ones: the
    strip has to happen before the store, not after it."""
    from dgate.rawstore import build_store

    notice = _notice("001-2019", defence=True)
    notice["buyer-email"] = ["someone@example.eu"]
    notice["buyer-person"] = ["A Person"]
    _days_served(monkeypatch, {date(2019, 6, 3): [notice]})
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3))

    key = conn.execute("SELECT storage_key FROM raw_ingest").fetchone()["storage_key"]
    landed = build_store().get(key)
    assert "buyer-email" not in landed and "buyer-person" not in landed


def test_a_day_larger_than_one_bundle_is_written_in_parts(conn, store, monkeypatch):
    _days_served(monkeypatch, {date(2019, 6, 3): [_notice(f"{i:05d}-2019", defence=False)
                                                  for i in range(7)]})
    monkeypatch.setattr(pipeline, "BUNDLE_CHUNK", 3)
    pipeline.run_ted_history(date(2019, 6, 3), date(2019, 6, 3))

    objects = sorted(p.name for p in (store / "ted" / "2019" / "06" / "03").iterdir())
    assert objects == ["bundle-0000.jsonl.gz", "bundle-0001.jsonl.gz",
                       "bundle-0002.jsonl.gz"]
    rows = conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"]
    assert rows == 7


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
