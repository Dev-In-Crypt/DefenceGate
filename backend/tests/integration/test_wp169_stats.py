"""WP-169: the visit counter's detail (exact path, referrer host, country) behind DGATE_STATS_DETAIL, its growth caps, and the
owner's stats command."""

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
    return {(r["route"], r["path"], r["referrer"], r["device"], r["country"]): r["hits"] for r in conn.execute(
        "SELECT route, path, referrer, device, country, hits FROM app_hit_daily").fetchall()}


@pytest.fixture()
def detail(monkeypatch):
    monkeypatch.setenv("DGATE_STATS_DETAIL", "1")
    config.reset_cache()
    yield
    config.reset_cache()


def test_with_the_switch_off_the_detail_is_dropped(client, conn):
    assert client.post("/v1/internal/hits", json=BATCH).status_code == 204
    assert _rows(conn) == {
        ("/tenders/[slug]", "", "other", "desktop", ""): 5,
        ("/suppliers/[slug]", "", "", "mobile", ""): 2,          # our own site is no referrer, as before
        ("/app", "", "", "desktop", ""): 3,
        ("/other", "", "google.com", "desktop", ""): 1,
    }


def test_with_the_switch_on_the_path_host_and_country_are_kept(client, conn, detail):
    assert client.post("/v1/internal/hits", json=BATCH).status_code == 204
    assert _rows(conn) == {
        ("/tenders/[slug]", "/tenders/12-armoured", "news.example.org", "desktop", "DE"): 5,   # never the referrer's path
        ("/suppliers/[slug]", "/suppliers/406963-indra/competitors", "internal", "mobile", "ES"): 2,
        ("/app", "", "", "desktop", "FR"): 3,                     # the account area: its page only, never its path
        ("/other", "", "www.google.com", "desktop", ""): 1,      # an unknown page, and a country that is not one
    }
    assert client.post("/v1/internal/hit", json={"route": "/funding?q=secret", "country": "PL"}).status_code == 204
    assert ("/funding", "/funding", "", "desktop", "PL") in _rows(conn)      # never the query


def test_past_the_daily_row_ceiling_a_view_is_counted_without_detail(client, conn, detail, monkeypatch):
    monkeypatch.setattr(accounts, "HIT_ROWS_PER_DAY", 3)
    hits = [{"route": f"/tenders/{n}-x", "referrer": f"h{n}.example", "count": 1, "country": "DE"} for n in range(5)]
    assert client.post("/v1/internal/hits", json={"hits": hits}).status_code == 204     # under the ceiling: all detailed
    assert len(_rows(conn)) == 5
    more = [{"route": f"/tenders/{n}-y", "referrer": f"k{n}.example", "count": 1, "country": "FR"} for n in range(50)]
    assert client.post("/v1/internal/hits", json={"hits": more}).status_code == 204
    rows = _rows(conn)
    assert len(rows) == 6 and rows[("/tenders/[slug]", "", "other", "desktop", "")] == 50
    assert sum(rows.values()) == 55


def _put(conn, day: date, rows: list[tuple[str, str, str, str, int]]) -> None:
    for route, path, ref, country, n in rows:
        conn.execute("INSERT INTO app_hit_daily (day, route, path, referrer, device, country, hits) "
                     "VALUES (%s, %s, %s, %s, 'desktop', %s, %s)", (day, route, path, ref, country, n))
    conn.commit()


def test_old_days_fold_rare_paths_and_hosts_and_keep_the_totals(conn):
    today = conn.execute("SELECT (now() AT TIME ZONE 'UTC')::date AS d").fetchone()["d"]
    old, recent = today - timedelta(days=35), today - timedelta(days=5)
    rows = [
        ("/tenders/[slug]", "/tenders/1-popular", "www.google.com", "DE", 40),
        ("/tenders/[slug]", "/tenders/2-rare", "www.google.com", "DE", 1),
        ("/tenders/[slug]", "/tenders/3-rare", "blog.example", "DE", 1),
        ("/tenders/[slug]", "/tenders/1-popular", "blog.example", "FR", 1),
        ("/tenders/[slug]", "", "other", "DE", 7),                  # an existing folded row is added to
        ("/funding", "/funding", "internal", "", 1),                # `internal` is never folded
    ]
    _put(conn, old, rows)
    _put(conn, recent, rows)
    total = conn.execute("SELECT sum(hits) AS n FROM app_hit_daily").fetchone()["n"]

    accounts.fold_old_hits(conn)
    conn.commit()
    got = {(r["path"], r["referrer"], r["country"]): r["hits"] for r in conn.execute(
        "SELECT path, referrer, country, hits FROM app_hit_daily WHERE day = %s", (old,)).fetchall()}
    assert got == {
        ("/tenders/1-popular", "www.google.com", "DE"): 40,
        ("", "www.google.com", "DE"): 1,                           # a rare path: its page key
        ("/tenders/1-popular", "other", "FR"): 1,                  # a rare host (2 views that day): `other`
        ("", "other", "DE"): 7 + 1,                                # both rare: added to the existing row
        ("", "internal", ""): 1,                                   # the rare /funding path folded; `internal` is never folded
    }
    recent_rows = conn.execute("SELECT count(*) AS n FROM app_hit_daily WHERE day = %s", (recent,)).fetchone()["n"]
    assert recent_rows == len(rows)                                # within 30 days nothing is folded
    assert conn.execute("SELECT sum(hits) AS n FROM app_hit_daily").fetchone()["n"] == total
    before = conn.execute("SELECT day, route, path, referrer, device, country, hits FROM app_hit_daily ORDER BY 1,2,3,4,5,6").fetchall()
    accounts.fold_old_hits(conn)                                   # again: nothing changes
    conn.commit()
    assert conn.execute("SELECT day, route, path, referrer, device, country, hits FROM app_hit_daily ORDER BY 1,2,3,4,5,6").fetchall() == before


def test_the_stats_command_prints_paths_hosts_countries_devices_and_days(conn):
    today = conn.execute("SELECT (now() AT TIME ZONE 'UTC')::date AS d").fetchone()["d"]
    _put(conn, today, [("/tenders/[slug]", "/tenders/1-popular", "www.google.com", "DE", 12),
                       ("/", "", "", "", 3)])
    _put(conn, today - timedelta(days=20), [("/funding", "/funding", "news.example.org", "FR", 5)])
    _put(conn, today - timedelta(days=40), [("/pricing", "/pricing", "old.example", "IT", 99)])   # outside 30 days
    text = stats.report(conn, days=30, top=10)
    assert "Page views: last 7 days 15, last 30 days 20" in text
    for line in ("/tenders/1-popular", "www.google.com", "(direct)", "news.example.org", "DE", "FR", "(not kept)",
                 "desktop", str(today)):
        assert line in text, line
    assert "/pricing" not in text and "old.example" not in text
