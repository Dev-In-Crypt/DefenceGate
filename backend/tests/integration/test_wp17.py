"""WP-17: the PLACSP archive replay of 16 October 2026 lost its connection ("the connection
is lost") on the 2023 and 2024 annual archives. Cause: the first entry is asked for after
the source id was read, and the generator downloads and parses the whole archive (30-40
minutes) before it yields it, so the connection sat idle in a transaction for longer than
the worker role's `idle_in_transaction_session_timeout` of 30 minutes.

The tests give the session a timeout of 1.5 s and a slow iterator instead of an archive.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from dgate import config, db, pipeline
from dgate.sources import placsp

pytestmark = pytest.mark.integration

XML = (Path(__file__).resolve().parents[1] / "fixtures" / "placsp_live_entries.atom"
       ).read_text(encoding="utf-8")
NATIVE = "2026/ETSAE0921/00001111E"
UTC = timezone.utc
AFTERNOON = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


def _entry(n: int = 0):
    opps, _ = placsp.parse_feed(XML.encode("utf-8"))
    opp = next(o for o in opps if o.native_id == NATIVE)
    return dataclasses.replace(opp, native_id=f"{NATIVE}-{n}") if n else opp


@pytest.fixture()
def short_timeout(conn, monkeypatch, tmp_path):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    dsn = make_conninfo(conn.info.dsn, password=conn.info.password,
                        options="-c idle_in_transaction_session_timeout=1500")
    monkeypatch.setenv("DGATE_DSN", dsn)
    config.reset_cache()
    yield
    config.reset_cache()


def test_a_slow_first_entry_does_not_hold_a_transaction(conn, short_timeout):
    def slow():
        time.sleep(2.5)         # the download and parse of an annual archive
        yield _entry()

    fetched, _, _ = pipeline._ingest_placsp(slow(), "es_placsp-2023-replay", replay=True)
    assert fetched == 1
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 1


def test_a_lost_connection_restarts_the_unit_after_the_finished_entries(
        conn, short_timeout, monkeypatch):
    total, calls = 450, []

    def fake(url, dataset=placsp.MAIN, *, since=None, **kw):
        calls.append(url)

        def gen():
            for n in range(total):
                if len(calls) == 1 and n == 440:
                    raise psycopg.OperationalError("the connection is lost")
                yield _entry(n)
        return gen()

    upserts = []
    real = db.upsert_opportunity
    monkeypatch.setattr(db, "upsert_opportunity",
                        lambda *a, **k: upserts.append(a[1].native_id) or real(*a, **k))
    monkeypatch.setattr(placsp, "fetch_archive", fake)
    slept = []

    result = pipeline.run_placsp_replay((2023, 1), (2023, 1), [placsp.MAIN], pause=0,
                                        sleep=slept.append, now=AFTERNOON)

    assert result["done"] == ["es_placsp-2023"] and not result["failed"]
    assert len(calls) == 2 and 30.0 in slept
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == total
    # first attempt: 440 entries processed, 399 committed; second: from entry 400 on
    assert len(upserts) == 440 + (total - 399)
    # a finished unit starts again from its first entry
    assert db.backfill_progress(conn, "es_placsp-replay-progress", datetime(2023, 1, 1).date()) == 0
