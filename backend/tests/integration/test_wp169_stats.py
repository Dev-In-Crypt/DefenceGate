"""WP-169: the visit counter's detail (exact path, referrer host; the country as its own daily total) behind
DGATE_STATS_DETAIL, its growth caps, and the owner's stats command."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from dgate import accounts, config
from dgate.ops import stats
from tests.integration import test_accounts

pytestmark = pytest.mark.integration
client, sent = test_accounts.client, test_accounts.sent      # the accounts tests' fixtures

BATCH = {"hits": [
    {"route": "/tenders/12-armoured", "referrer": "https://news.example.org/a?b=c", "count": 4, "country": "DE"},
    {"route": "/tenders/12-armoured/", "referrer": "news.example.org", "count": 1, "country": "DE"},
    {"route": "/suppliers/406963-indra/competitors", "referrer": "internal", "mobile": True, "count": 2, "country": "ES"},
    {"route": "/app/searches/9f1c", "referrer": "", "count": 3, "country": "FR"},
    {"route": "/wp-login.php", "referrer": "https://www.google.com/", "count": 1, "country": "<script>"},
]}


def _rows(conn) -> dict[tuple, int]:
    return {(r["route"], r["path"], r["referrer"], r["device"]): r["hits"] for r in conn.execute(
        "SELECT route, path, referrer, device, hits FROM app_hit_daily").fetchall()}


def _countries(conn) -> dict[str, int]:
    return {r["country"]: r["hits"] for r in conn.execute("SELECT country, hits FROM app_hit_country_daily").fetchall()}


@pytest.fixture()
def detail(monkeypatch):
    monkeypatch.setenv("DGATE_STATS_DETAIL", "1")
    config.reset_cache()
    yield
    config.reset_cache()


def test_with_the_switch_off_the_detail_is_dropped(client, conn):
    assert client.post("/v1/internal/hits", json=BATCH).status_code == 204
    assert _rows(conn) == {
        ("/tenders/[slug]", "", "other", "desktop"): 5,
        ("/suppliers/[slug]", "", "", "mobile"): 2,          # our own site is no referrer, as before
        ("/app", "", "", "desktop"): 3,
        ("/other", "", "google.com", "desktop"): 1,
    }
    assert _countries(conn) == {}


def test_with_the_switch_on_the_path_and_host_are_kept_and_the_country_apart(client, conn, detail):
    assert client.post("/v1/internal/hits", json=BATCH).status_code == 204
    assert _rows(conn) == {
        ("/tenders/[slug]", "/tenders/12-armoured", "news.example.org", "desktop"): 5,   # never the referrer's path
        ("/suppliers/[slug]", "/suppliers/406963-indra/competitors", "internal", "mobile"): 2,
        ("/app", "", "", "desktop"): 3,                       # the account area: its page only, never its path
        ("/other", "", "www.google.com", "desktop"): 1,      # an unknown page
    }
    # the country is a daily total of its own, never in a row with a page, a referrer or a device
    assert _countries(conn) == {"DE": 5, "ES": 2, "FR": 3}   # `<script>` is no country
    cols = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'app_hit_country_daily'").fetchall()}
    assert cols == {"day", "country", "hits"}
    assert client.post("/v1/internal/hit", json={"route": "/funding?q=secret", "country": "PL"}).status_code == 204
    assert ("/funding", "/funding", "", "desktop") in _rows(conn)       # never the query
    assert _countries(conn)["PL"] == 1


def test_the_country_table_has_the_counters_grants(conn):
    def ok(role: str, priv: str) -> bool:
        return conn.execute("SELECT has_table_privilege(%s, 'app_hit_country_daily', %s) AS ok",
                            (role, priv)).fetchone()["ok"]
    assert not ok("dgate_api", "SELECT")
    assert ok("dgate_worker", "SELECT") and not ok("dgate_worker", "INSERT") and not ok("dgate_worker", "DELETE")
    assert ok("dgate_app", "INSERT") and ok("dgate_app", "UPDATE")


def test_past_the_daily_row_ceiling_a_view_is_counted_without_detail(client, conn, detail, monkeypatch):
    monkeypatch.setattr(accounts, "HIT_ROWS_PER_DAY", 3)
    hits = [{"route": f"/tenders/{n}-x", "referrer": f"h{n}.example", "count": 1, "country": "DE"} for n in range(5)]
    assert client.post("/v1/internal/hits", json={"hits": hits}).status_code == 204     # under the ceiling: all detailed
    assert len(_rows(conn)) == 5
    more = [{"route": f"/tenders/{n}-y", "referrer": f"k{n}.example", "count": 1, "country": "FR"} for n in range(50)]
    assert client.post("/v1/internal/hits", json={"hits": more}).status_code == 204
    rows = _rows(conn)
    assert len(rows) == 6 and rows[("/tenders/[slug]", "", "other", "desktop")] == 50
    assert sum(rows.values()) == 55
    assert _countries(conn) == {"DE": 5, "FR": 50}            # bounded by itself (one row per code): still counted


def _put(conn, day: date, rows: list[tuple[str, str, str, int]]) -> None:
    for route, path, ref, n in rows:
        conn.execute("INSERT INTO app_hit_daily (day, route, path, referrer, device, hits) "
                     "VALUES (%s, %s, %s, %s, 'desktop', %s)", (day, route, path, ref, n))
    conn.commit()


def test_old_days_fold_rare_paths_and_hosts_and_keep_the_totals(conn):
    today = conn.execute("SELECT (now() AT TIME ZONE 'UTC')::date AS d").fetchone()["d"]
    old, recent = today - timedelta(days=35), today - timedelta(days=5)
    rows = [
        ("/tenders/[slug]", "/tenders/1-popular", "www.google.com", 40),
        ("/tenders/[slug]", "/tenders/2-rare", "www.google.com", 1),
        ("/tenders/[slug]", "/tenders/3-rare", "blog.example", 1),
        ("/tenders/[slug]", "/tenders/1-popular", "blog.example", 1),
        ("/tenders/[slug]", "", "other", 7),                  # an existing folded row is added to
        ("/funding", "/funding", "internal", 1),              # `internal` is never folded
    ]
    _put(conn, old, rows)
    _put(conn, recent, rows)
    total = conn.execute("SELECT sum(hits) AS n FROM app_hit_daily").fetchone()["n"]

    accounts.fold_old_hits(conn)
    conn.commit()
    got = {(r["route"], r["path"], r["referrer"]): r["hits"] for r in conn.execute(
        "SELECT route, path, referrer, hits FROM app_hit_daily WHERE day = %s", (old,)).fetchall()}
    assert got == {
        ("/tenders/[slug]", "/tenders/1-popular", "www.google.com"): 40,
        ("/tenders/[slug]", "", "www.google.com"): 1,            # a rare path: its page key
        ("/tenders/[slug]", "/tenders/1-popular", "other"): 1,   # a rare host (2 views that day): `other`
        ("/tenders/[slug]", "", "other"): 7 + 1,                 # both rare: added to the existing row
        ("/funding", "", "internal"): 1,                         # the rare /funding path folded; `internal` never is
    }
    recent_rows = conn.execute("SELECT count(*) AS n FROM app_hit_daily WHERE day = %s", (recent,)).fetchone()["n"]
    assert recent_rows == len(rows)                              # within 30 days nothing is folded
    assert conn.execute("SELECT sum(hits) AS n FROM app_hit_daily").fetchone()["n"] == total
    q = "SELECT day, route, path, referrer, device, hits FROM app_hit_daily ORDER BY 1, 2, 3, 4, 5"
    before = conn.execute(q).fetchall()
    accounts.fold_old_hits(conn)                                 # again: nothing changes
    conn.commit()
    assert conn.execute(q).fetchall() == before


def test_the_stats_command_prints_paths_hosts_countries_devices_and_days(conn):
    today = conn.execute("SELECT (now() AT TIME ZONE 'UTC')::date AS d").fetchone()["d"]
    _put(conn, today, [("/tenders/[slug]", "/tenders/1-popular", "www.google.com", 12), ("/", "", "", 3)])
    _put(conn, today - timedelta(days=20), [("/funding", "/funding", "news.example.org", 5)])
    _put(conn, today - timedelta(days=40), [("/pricing", "/pricing", "old.example", 99)])   # outside 30 days
    for day, cc, n in ((today, "DE", 12), (today - timedelta(days=20), "FR", 5), (today - timedelta(days=40), "IT", 99)):
        conn.execute("INSERT INTO app_hit_country_daily (day, country, hits) VALUES (%s, %s, %s)", (day, cc, n))
    conn.commit()
    text = stats.report(conn, days=30, top=10)
    assert "Page views: last 7 days 15, last 30 days 20" in text
    for line in ("/tenders/1-popular", "www.google.com", "(direct)", "news.example.org", "Countries", "DE", "FR",
                 "desktop", str(today)):
        assert line in text, line
    assert "/pricing" not in text and "old.example" not in text and " IT " not in text
