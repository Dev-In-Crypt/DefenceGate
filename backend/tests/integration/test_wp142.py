"""WP-142 against a real Postgres: the stored match sets of the frequent search words (migration 0142). The worker reads them,
a list request uses the set and re-tests only the search rows written since, so it lists what the live condition lists (a
notice written after the set and one whose title changed included), its total and its rows agree, an old set is ignored, a
set of a search no longer listed is deleted, and the trigger stamps a row only when a searched column changes."""

from __future__ import annotations

import pytest

from dgate import tenders
from dgate.ops import warm_lists
from tests.integration.test_warm_lists import _put
from tests.integration.test_wp95 import client, env  # noqa: F401 - fixtures

pytestmark = pytest.mark.integration


def get(c, path: str, **params) -> dict:
    r = c.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _titled(conn, native_id: str, title: str, status: str = "closed") -> int:
    oid = _put(conn, native_id, status=status)
    conn.execute("UPDATE opportunity SET title_original = %s WHERE id = %s", (title, oid))
    conn.commit()
    return oid


def _ids(page: dict) -> list[str]:
    return sorted(i["id"] for i in page["items"])


def test_a_stored_set_lists_what_the_live_search_lists_with_the_notices_written_since(client, conn, monkeypatch):  # noqa: F811
    a = [_titled(conn, f"W-142-A{i}", "Armoured vehicles and ammunition", s) for i, s in enumerate(("open", "closed", "awarded"))]
    _titled(conn, "W-142-B", "Armoured vehicles")                                   # not a match
    got = warm_lists.run(conn, write=True)
    # WP-143: a word that matches nothing is not stored (counted in search_sets_empty)
    assert got["failed"] == 0 and got["search_sets"] == len(tenders.search_set_words())
    assert got["search_sets_written"] >= 1 and got["search_sets_written"] + got["search_sets_empty"] == got["search_sets"]
    row = conn.execute("SELECT ids FROM search_match_set WHERE q = 'ammunition'").fetchone()
    assert sorted(row["ids"]) == sorted(a)
    # after the set: a new match, and a match whose title no longer matches
    new = _titled(conn, "W-142-C", "Small arms ammunition")
    conn.execute("UPDATE opportunity SET title_original = 'Armoured vehicles' WHERE id = %s", (a[1],))
    conn.commit()
    asked = []
    real = tenders.search_ids
    monkeypatch.setattr(tenders, "search_ids", lambda *x: asked.append(real(*x)) or asked[-1])
    stored = {s: get(client, "/v1/tenders", q="ammunition", status=s) for s in ("all", "closed", "open")}
    assert asked and all(x == sorted([a[0], a[2], new]) for x in asked)             # the set, re-tested where written since
    conn.execute("DELETE FROM search_match_set")
    conn.commit()
    asked.clear()
    live = {s: get(client, "/v1/tenders", q="ammunition", status=s) for s in ("all", "closed", "open")}
    assert asked and all(x is None for x in asked)                                 # no set: the per-row test, as before
    for s in live:
        assert _ids(stored[s]) == _ids(live[s]) and stored[s]["total"] == live[s]["total"], s
    assert stored["all"]["total"] == len(stored["all"]["items"]) == 3              # the list and its count agree
    counts = get(client, "/v1/tenders/scope-counts", q="ammunition", status="all")
    assert counts["relevant"] == 3


def test_an_old_set_is_not_used_and_a_set_no_longer_listed_is_deleted(client, conn, monkeypatch):  # noqa: F811
    _titled(conn, "W-142-D", "Ammunition")
    tenders.refresh_search_sets(conn, write=True)
    conn.execute("UPDATE search_match_set SET ids = '{}', computed_at = now() - interval '25 hours'")
    conn.commit()
    assert get(client, "/v1/tenders", q="ammunition", status="all")["total"] == 1   # the empty old set was not read
    conn.execute("INSERT INTO search_match_set (key, q, ids, snapshot_xmin) VALUES ('gone', 'gone', '{}', '1')")
    conn.commit()
    assert tenders.refresh_search_sets(conn, write=True)["search_sets_removed"] == 1
    assert conn.execute("SELECT count(*) AS n FROM search_match_set WHERE key = 'gone'").fetchone()["n"] == 0
    report = tenders.refresh_search_sets(conn, write=False)
    assert report["search_sets_written"] == 0 and report["search_sets"] > 0


def test_the_trigger_stamps_a_search_row_only_when_a_searched_column_changes(conn):
    oid = _titled(conn, "W-142-E", "Fuel")
    xid = lambda: conn.execute("SELECT changed_xid::text::bigint AS x FROM opportunity_search WHERE id = %s", (oid,)).fetchone()["x"]  # noqa: E731
    first = xid()
    assert first is not None
    conn.execute("UPDATE opportunity SET status = 'awarded' WHERE id = %s", (oid,))
    conn.commit()
    assert xid() == first                                                          # not a searched column: no new stamp
    conn.execute("UPDATE opportunity SET title_original = 'Diesel fuel' WHERE id = %s", (oid,))
    conn.commit()
    assert xid() > first


def test_past_the_retest_limit_the_set_is_not_used(conn, monkeypatch):
    _titled(conn, "W-142-F", "Ammunition")
    tenders.refresh_search_sets(conn, write=True)
    built = tenders.search_match("ammunition")
    assert tenders.stored_matches(conn, *built) is not None
    _titled(conn, "W-142-G", "Ammunition boxes")                                   # written since the set
    assert len(tenders.stored_matches(conn, *built)) == 2
    monkeypatch.setattr(tenders, "SEARCH_SET_RETEST_MAX", 0)
    assert tenders.stored_matches(conn, *built) is None                            # the live query instead
