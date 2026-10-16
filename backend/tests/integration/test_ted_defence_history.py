"""`ted-defence-history`: the same steps as the daily run, over a server-side selection."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from dgate import config, pipeline
from dgate.sources import ted

pytestmark = pytest.mark.integration

PAGE = json.loads((Path(__file__).parent.parent / "fixtures"
                   / "ted_defence_history_page.json").read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _window(query: str) -> tuple[date, date]:
    a, b = re.search(r"publication-date>=(\d{8}) AND publication-date<=(\d{8})", query).groups()
    return (date(int(a[:4]), int(a[4:6]), int(a[6:])), date(int(b[:4]), int(b[4:6]), int(b[6:])))


def _serve(monkeypatch, *, counts=None, notices=None, short=False):
    asked: list[tuple[date, date]] = []

    def count(query, **kw):
        return counts(_window(query)) if counts else len(PAGE["notices"])

    def search(query, *a, **kw):
        asked.append(_window(query))
        yield from (notices(asked[-1]) if notices else PAGE["notices"][:2 if short else 3])

    monkeypatch.setattr(ted, "count", count)
    monkeypatch.setattr(ted, "search", search)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    return asked


def test_a_month_is_landed_and_only_what_qualifies_is_kept(conn, store, monkeypatch):
    asked = _serve(monkeypatch)
    assert pipeline.run_ted_defence_history(date(2021, 3, 1), date(2021, 3, 31)) == 1

    assert asked == [(date(2021, 3, 1), date(2021, 3, 31))]
    keys = [r["storage_key"] for r in conn.execute(
        "SELECT storage_key FROM raw_ingest ORDER BY id").fetchall()]
    assert keys == [f"ted-defence/2021/03/01/bundle-0000.jsonl.gz#{i}" for i in range(3)]
    kept = sorted(r["native_id"] for r in conn.execute(
        "SELECT native_id FROM opportunity WHERE is_defence").fetchall())
    # the directive notice and the added military CPV qualify; a civil purchase does not
    assert kept == ["103679-2021", "105063-2021"]
    assert conn.execute("SELECT count(*) n FROM backfill_day WHERE source_code = 'ted-defence:M'"
                        ).fetchone()["n"] == 1


def test_a_marked_window_is_not_asked_again_and_a_known_notice_gets_no_version(
        conn, store, monkeypatch):
    asked = _serve(monkeypatch)
    pipeline.run_ted_defence_history(date(2021, 3, 1), date(2021, 3, 31))
    pipeline.run_ted_defence_history(date(2021, 3, 1), date(2021, 3, 31))
    assert len(asked) == 1

    pipeline.run_ted_defence_history(date(2021, 3, 1), date(2021, 3, 31), resume=False)
    assert len(asked) == 2
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 2


def test_a_month_above_the_paging_cap_is_walked_in_weeks(conn, store, monkeypatch):
    month = (date(2021, 3, 1), date(2021, 3, 31))
    asked = _serve(monkeypatch, counts=lambda w: 20_000 if w == month else 1,
                   notices=lambda w: PAGE["notices"][:1])
    pipeline.run_ted_defence_history(*month)

    assert asked[0] == (date(2021, 3, 1), date(2021, 3, 7))
    assert asked[-1] == (date(2021, 3, 29), date(2021, 3, 31))
    assert len(asked) == 5
    assert conn.execute("SELECT count(*) n FROM backfill_day WHERE source_code = 'ted-defence:W'"
                        ).fetchone()["n"] == 5
    assert conn.execute("SELECT count(*) n FROM backfill_day WHERE source_code = 'ted-defence:M'"
                        ).fetchone()["n"] == 0


def test_a_short_read_leaves_the_window_unmarked(conn, store, monkeypatch):
    _serve(monkeypatch, short=True)          # the API states 3, the stream ends at 2
    with pytest.raises(RuntimeError, match="not marking it done"):
        pipeline.run_ted_defence_history(date(2021, 3, 1), date(2021, 3, 31))
    assert conn.execute("SELECT count(*) n FROM backfill_day").fetchone()["n"] == 0
    # what was read is kept (idempotent); the window is asked for again on the next run


def test_the_dry_run_counts_windows_notices_and_requests(conn, monkeypatch, capsys):
    _serve(monkeypatch, counts=lambda w: 250)
    plan = pipeline.plan_ted_defence_history(conn, date(2021, 1, 1), date(2021, 2, 28))
    assert [(p["start"], p["notices"], p["requests"]) for p in plan] == [
        (date(2021, 1, 1), 250, 4), (date(2021, 2, 1), 250, 4)]
    pipeline.print_defence_plan(plan)
    assert "total  500 notices, 8 requests" in capsys.readouterr().out
