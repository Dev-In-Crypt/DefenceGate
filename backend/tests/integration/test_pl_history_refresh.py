"""Polish bulletin: the history load, the re-read of open notices, Atlas pass two.

Against a real Postgres. The board is a fake that serves notices in pages of ten
and can answer 503 on a page, which is what happened on 6 October 2026 (page 301
of that day).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from dgate import config, db, pipeline
from dgate.rawstore import build_store
from dgate.sources import ezamowienia as ez

pytestmark = pytest.mark.integration

RECENT = date.today() - timedelta(days=3)


def notice(n: int, *, defence: bool = True, notice_type: str = "ContractNotice",
           day: date = RECENT, deadline: datetime | None = None, version: int = 1,
           **extra) -> dict:
    return {
        "bzpNumber": f"2026/BZP {n:08d}",
        "noticeNumber": f"2026/BZP {n:08d}/{version:02d}",
        "noticeType": notice_type,
        "objectId": f"obj-{n}",
        "orderObject": f"Dostawa {n}",
        "orderType": "Delivery",
        "cpvCode": "35300000-7 (Bron, amunicja)" if defence else "45000000-7 (Roboty)",
        "organizationName": "Jednostka Wojskowa Nr 1",
        "organizationCountry": "PL",
        "publicationDate": f"{day.isoformat()}T08:00:00Z",
        "submittingOffersDate": (deadline.strftime("%Y-%m-%dT%H:%M:%SZ") if deadline else None),
        "tenderType": "1.1.1",
        "userId": "0a8758fd-0000-0000-0000-000000000000",
        **extra,
    }


def soon(days: int = 20) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("DGATE_ATLAS_DIR", str(tmp_path / "atlas"))
    (tmp_path / "atlas").mkdir()
    config.reset_cache()
    monkeypatch.setattr("time.sleep", lambda s: None)
    yield tmp_path / "raw"
    config.reset_cache()


# ----------------------------------------------------------- history load

class Board:
    """The bulletin as the history sees it: a day's notices, ten to a page."""

    def __init__(self, by_day: dict[date, list[dict]]):
        self.by_day = by_day
        self.fail: tuple[date, int] | None = None
        self.asked: list[tuple[date, int]] = []

    def get(self, url, params=None, timeout=None):
        day = date.fromisoformat(params["publicationDateFrom"][:10])
        page = params["PageNumber"]
        self.asked.append((day, page))
        if self.fail == (day, page):
            return httpx.Response(503, request=httpx.Request("GET", url))
        records = self.by_day.get(day, [])
        start = (page - 1) * ez.PAGE_SIZE

        class Ok:
            def raise_for_status(self):
                return None

            def json(self):
                return records[start:start + ez.PAGE_SIZE]

        return Ok()

    def close(self):
        return None


JAN5, JAN6 = date(2026, 1, 5), date(2026, 1, 6)


def _two_days() -> dict[date, list[dict]]:
    return {JAN5: [notice(i, defence=i % 5 == 0, day=JAN5) for i in range(1, 26)],
            JAN6: [notice(i, defence=i % 5 == 0, day=JAN6) for i in range(101, 126)]}


def test_a_day_that_returned_503_mid_way_is_not_marked_and_is_done_again(conn, store, monkeypatch):
    """The 6-7 October failure: page 301 of a day answered 503 and the day was
    left behind. A marker that runs ahead of the data would make it a hole."""
    board = Board(_two_days())
    board.fail = (JAN6, 2)
    monkeypatch.setattr(ez, "new_client", lambda **kw: board)

    with pytest.raises(httpx.HTTPStatusError):
        pipeline.run_history("pl_ezam", JAN5, JAN6)

    assert db.backfill_days_done(conn, "pl_ezam") == {JAN5}
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 25
    assert not (store / "pl_ezam" / "2026" / "01" / "06").exists(), \
        "a half-walked day must leave no bundle behind"

    board.fail = None
    board.asked.clear()
    assert pipeline.run_history("pl_ezam", JAN5, JAN6) == 1

    assert {d for d, _ in board.asked} == {JAN6}, "only the unfinished day is asked for"
    assert (JAN6, 1) in board.asked, "and it is done again from its first page"
    assert db.backfill_days_done(conn, "pl_ezam") == {JAN5, JAN6}
    row = conn.execute("SELECT notices FROM backfill_day WHERE source_code='pl_ezam' "
                       "AND day = %s", (JAN6,)).fetchone()
    assert row["notices"] == 25
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 50


def test_the_history_lands_everything_and_archives_only_defence(conn, store, monkeypatch):
    board = Board(_two_days())
    monkeypatch.setattr(ez, "new_client", lambda **kw: board)
    pipeline.run_history("pl_ezam", JAN5, JAN6)

    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 50
    # i % 5 == 0 on each day: 5 and 5.
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 10
    keys = [r["storage_key"] for r in conn.execute("SELECT storage_key FROM raw_ingest")]
    assert all("#" in k for k in keys), "one bundle per day, addressed by line"
    landed = build_store().get(keys[0])
    assert "userId" not in landed, "the person who filed the notice is stripped before landing"


def test_the_history_writes_no_run_that_could_pass_for_a_daily_one(conn, store, monkeypatch):
    monkeypatch.setattr(ez, "new_client", lambda **kw: Board(_two_days()))
    pipeline.run_history("pl_ezam", JAN5, JAN5)
    assert conn.execute("SELECT count(*) n FROM ingest_run").fetchone()["n"] == 0


# ------------------------------------------------------ re-read of open notices

class _NoClient:
    def close(self):
        return None


@pytest.fixture
def reread(monkeypatch, store):
    """Window and by-number reads replaced; records what was asked by number."""
    state = {"window": [], "live": {}, "asked": [], "fail": None, "unread": []}

    def fake_window(days_back=2, failed=None, **kw):
        if failed is not None:
            failed.extend(state["unread"])
        yield from state["window"]

    def fake_fetch(number, client=None):
        state["asked"].append(number)
        if state["fail"]:
            raise state["fail"]
        return state["live"].get(number)

    monkeypatch.setattr(ez, "fetch_window", fake_window)
    monkeypatch.setattr(ez, "fetch_notice", fake_fetch)
    monkeypatch.setattr(pipeline, "new_client", lambda **kw: _NoClient())
    return state


def _land(conn, reread, *notices):
    """Ingest the window, then make what it read two days old: a notice read a
    moment ago is, rightly, not asked for again."""
    reread["window"] = list(notices)
    pipeline.run_ezamowienia(days=2, refresh_limit=0)
    reread["window"] = []
    conn.execute("UPDATE raw_ingest SET fetched_at = now() - interval '2 days'")
    conn.commit()


def _last_run(conn):
    return conn.execute("SELECT * FROM ingest_run ORDER BY id DESC LIMIT 1").fetchone()


def test_a_deadline_moved_in_place_is_picked_up_by_the_re_read(conn, reread):
    """Notice 139666: the source said 29 September, the archive 28th, and no
    publication-day window could ever see it, because a change made in place
    keeps the notice number and the publication date."""
    before = notice(1, deadline=soon(20))
    _land(conn, reread, before)
    reread["live"][before["noticeNumber"]] = notice(1, deadline=soon(21))

    pipeline.run_ezamowienia(days=None, refresh_limit=10)

    assert reread["asked"] == ["2026/BZP 00000001/01"]
    row = conn.execute("SELECT current_version, deadline_at FROM opportunity").fetchone()
    assert row["current_version"] == 2
    changed = conn.execute("SELECT changed_fields FROM opportunity_version "
                           "WHERE version = 2").fetchone()["changed_fields"]
    assert changed == ["deadline_at"]
    run = _last_run(conn)
    assert (run["status"], run["records_fetched"], run["expected_min"]) == ("success", 0, None)


def test_only_open_notices_are_asked_for(conn, reread):
    _land(conn, reread,
          notice(1, deadline=soon(20)),                                   # open
          notice(2, notice_type="ContractPerformingNotice"),             # awarded
          notice(3, deadline=soon(-10)),                                  # deadline passed
          notice(4, notice_type="TenderPlanNotice", orderObject=None))   # forthcoming, no deadline

    pipeline.run_ezamowienia(days=None, refresh_limit=10)
    assert reread["asked"] == ["2026/BZP 00000001/01"]


def test_the_notice_number_is_rebuilt_from_the_identifier_and_the_revision(conn, reread):
    ted = notice(7, deadline=soon(20), noticeType=None, noticeTypeTed="eforms-16",
                 bzpNumber="2026/S 172-612773", noticeNumber="2026/S 172-612773",
                 pdfUrl="https://ted.europa.eu/pl/notice/612773-2026/pdf")
    _land(conn, reread, notice(1, deadline=soon(20), version=3), ted)

    pipeline.run_ezamowienia(days=None, refresh_limit=10)
    assert sorted(reread["asked"]) == ["2026/BZP 00000001/03", "2026/S 172-612773"]


def test_the_least_recently_read_goes_first_and_the_limit_holds(conn, reread):
    landed = [notice(i, deadline=soon(20)) for i in (1, 2, 3)]
    _land(conn, reread, *landed)
    reread["live"] = {n["noticeNumber"]: n for n in landed}
    # 2 read five days ago, 1 three days ago, 3 an hour ago.
    for n, ago in ((2, "5 days"), (1, "3 days"), (3, "1 hour")):
        conn.execute("UPDATE raw_ingest SET fetched_at = now() - %s::interval "
                     "WHERE native_id = %s", (ago, f"2026/BZP {n:08d}"))
    conn.commit()

    pipeline.run_ezamowienia(days=None, refresh_limit=1)
    assert reread["asked"] == ["2026/BZP 00000002/01"]

    reread["asked"].clear()
    pipeline.run_ezamowienia(days=None, refresh_limit=10)
    # 2 was read a moment ago and 3 an hour ago: only 1 is old enough.
    assert reread["asked"] == ["2026/BZP 00000001/01"]


def test_a_re_read_counts_as_a_read(conn, reread):
    """No new column: the newest raw_ingest row of an identifier is its last read,
    so a notice asked for tonight is not asked for again tomorrow morning."""
    _land(conn, reread, notice(1, deadline=soon(20)))
    conn.execute("UPDATE raw_ingest SET fetched_at = now() - interval '4 days'")
    conn.commit()
    reread["live"]["2026/BZP 00000001/01"] = notice(1, deadline=soon(20))

    pipeline.run_ezamowienia(days=None, refresh_limit=10)
    pipeline.run_ezamowienia(days=None, refresh_limit=10)
    assert reread["asked"] == ["2026/BZP 00000001/01"]


def test_three_failures_in_a_row_stop_the_re_read_and_say_so(conn, reread):
    _land(conn, reread, *[notice(i, deadline=soon(20)) for i in range(1, 7)])
    conn.execute("UPDATE raw_ingest SET fetched_at = now() - interval '4 days'")
    conn.commit()
    reread["fail"] = httpx.ConnectError("down")

    pipeline.run_ezamowienia(days=None, refresh_limit=10)

    assert len(reread["asked"]) == 3
    run = _last_run(conn)
    assert run["status"] == "partial"
    assert "re-read" in run["error_message"]


def test_a_notice_the_board_no_longer_has_does_not_fail_the_run(conn, reread):
    _land(conn, reread, notice(1, deadline=soon(20)))
    conn.execute("UPDATE raw_ingest SET fetched_at = now() - interval '4 days'")
    conn.commit()
    pipeline.run_ezamowienia(days=None, refresh_limit=10)
    assert _last_run(conn)["status"] == "success"
    assert conn.execute("SELECT current_version FROM opportunity").fetchone()[
        "current_version"] == 1


def test_a_day_the_window_could_not_finish_makes_the_run_partial_and_names_it(conn, reread):
    reread["window"] = [notice(1, deadline=soon(20))]
    reread["unread"] = [date(2026, 10, 6)]
    pipeline.run_ezamowienia(days=2, refresh_limit=0)

    run = _last_run(conn)
    assert run["status"] == "partial"
    assert "2026-10-06" in run["error_message"]
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 1, \
        "the days that could be read were still ingested"


# ------------------------------------------------------------ Atlas pass two

def _atlas_file(path, tender_type):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from dgate.sources import atlas_pl

    rows = 3
    table = {c: [None] * rows for c in atlas_pl.COLUMNS}
    table["id"] = [f"2024/BZP {i:08d}" for i in range(rows)]
    table["title"] = ["Dostawa"] * rows
    table["buyer"] = ["Gmina Testowa"] * rows
    table["cpv_code"] = ["35300000", "45000000", "45000000"]
    table["date"] = ["2024-01-02"] * rows
    table["notice_type"] = ["ContractNotice"] * rows
    table["tender_type"] = [tender_type] * rows
    pq.write_table(pa.table({k: pa.array(v, type=pa.string()) for k, v in table.items()}), path)


def test_refresh_known_lands_the_new_columns_for_opportunities_only(conn, store, tmp_path):
    path = tmp_path / "tenders_2024.parquet"
    _atlas_file(path, tender_type=None)
    pipeline.run_atlas_backfill(2024, path=path, workers=2)
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 1

    _atlas_file(path, tender_type="1.1.1")
    pipeline.run_atlas_backfill(2024, path=path, workers=2, refresh_known=True)

    # one more raw row, for the one row that is an opportunity
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 4
    newest = conn.execute("SELECT storage_key FROM raw_ingest ORDER BY id DESC "
                          "LIMIT 1").fetchone()["storage_key"]
    assert build_store().get(newest)["tender_type"] == "1.1.1"
    # nothing was written to the archive: a replay does that, and marks it
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1
    assert conn.execute("SELECT procedure_type FROM opportunity").fetchone()[
        "procedure_type"] is None
