"""WP-20 (UX walk-throughs of 16 October 2026): history loads are not news, and search folds
accents and punctuation both ways.

  - a version written inside `db.historical_load` carries a `history` note; /v1/changes, the
    amendment flag and the amendment share leave it out, the tender page lists it as historic
  - `dgate.ops.tag_history` annotates the versions written before, on evidence (a marker of a
    history/replay run near the observation AND a source date weeks earlier)
  - a notice counts as new only if it was published in the window (two days of slack)
  - tender and buyer search: "Ausrüstung" = "Ausrustung", "off-road" = "off road", each word
    must begin a word
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, stats
from dgate.ops import tag_history

from .test_changes import LATER, TODAY, age, amend, feed, opp, store

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _kinds(conn, oid: int) -> dict[int, list[str]]:
    rows = conn.execute(
        """SELECT v.version, n.kind FROM opportunity_version v
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s ORDER BY v.version""", (oid,)).fetchall()
    out: dict[int, list[str]] = {}
    for r in rows:
        out.setdefault(r["version"], [])
        if r["kind"]:
            out[r["version"]].append(r["kind"])
    return out


# ---------------------------------------------------------------- the tag at write time

def test_a_version_written_by_a_history_load_is_tagged_and_is_not_a_change(client, conn):
    first = opp("H-1")
    oid = store(conn, first)
    age(conn, oid, 20)
    with db.historical_load("history"):
        amend(conn, first, "b", deadline_at=LATER)
    assert _kinds(conn, oid) == {1: [], 2: ["history"]}
    assert feed(client)["total"] == 0


def test_the_same_amendment_outside_a_load_is_still_listed(client, conn):
    first = opp("H-2")
    oid = store(conn, first)
    age(conn, oid, 20)
    amend(conn, first, "b", deadline_at=LATER)
    assert _kinds(conn, oid)[2] == []
    assert feed(client)["counts"]["amended"] == 1


def test_a_notice_first_written_by_a_load_is_tagged_too(conn):
    with db.historical_load("replay"):
        oid = store(conn, opp("H-3"))
    assert _kinds(conn, oid) == {1: ["history"]}


def test_the_tender_page_lists_a_historic_version_but_does_not_call_the_notice_amended(client, conn):
    first = opp("H-4")
    oid = store(conn, first)
    with db.historical_load("history"):
        amend(conn, first, "b", deadline_at=LATER)
    versions = client.get(f"/v1/tenders/{oid}/versions").json()
    assert [v["historic"] for v in versions] == [True, False]      # newest first
    assert versions[0]["changes"][0]["field"] == "deadline_at"
    assert client.get(f"/v1/tenders/{oid}").json()["amended"] is False


def test_a_history_version_is_not_in_the_amendment_share(conn):
    first = opp("H-5")
    store(conn, first)
    other = opp("H-6")
    store(conn, other)
    with db.historical_load("history"):
        amend(conn, first, "b", deadline_at=LATER)
    amend(conn, other, "b", deadline_at=LATER)
    share = stats.amendment_share(conn, "o.is_defence", [])
    assert share["notices"] == 2 and share["amended"] == 1


# ------------------------------------------------------- new = published in the window

def test_a_notice_published_before_the_window_is_not_new_even_if_collected_in_it(client, conn):
    store(conn, opp("OLD-ISH", published=TODAY - timedelta(days=18)))      # 4 days before it
    assert feed(client)["total"] == 0


def test_a_notice_published_a_day_before_the_window_is_new(client, conn):
    store(conn, opp("EDGE", published=TODAY - timedelta(days=15)))
    assert feed(client)["counts"]["new"] == 1


# ------------------------------------------------------- tagging what exists already

def test_the_tool_tags_a_version_a_history_run_wrote_before_the_tag_existed(conn, dsn):
    old = opp("T-OLD", published=TODAY - timedelta(days=400))        # a change dated long ago
    oid_old = store(conn, old)
    amend(conn, old, "b", deadline_at=LATER)
    live = opp("T-LIVE", published=TODAY)                            # a change dated this week
    oid_live = store(conn, live)
    amend(conn, live, "b", deadline_at=LATER)
    unmarked = opp("T-NOMARK", published=TODAY - timedelta(days=400), source="fr_boamp",
                   country="FR")
    oid_nomark = store(conn, unmarked)
    amend(conn, unmarked, "b", deadline_at=LATER)
    db.mark_backfill_day(conn, "ted", TODAY - timedelta(days=1), 5)
    conn.commit()

    assert tag_history.run(write=False, dsn=dsn).get("ted") == 1
    assert _kinds(conn, oid_old)[2] == []                            # a report writes nothing
    tag_history.run(write=True, dsn=dsn)
    assert _kinds(conn, oid_old)[2] == ["history"]
    assert _kinds(conn, oid_live)[2] == []                           # dated this week: live
    assert _kinds(conn, oid_nomark)[2] == []                         # old, no run explains it
    assert tag_history.run(write=True, dsn=dsn).get("ted") is None   # a second run: nothing


# ---------------------------------------------------------------------------- search

def _notice_ids(client, **params):
    r = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params})
    assert r.status_code == 200, r.text
    return sorted(t["noticeId"] for t in r.json()["items"])


def test_tender_search_folds_accents_and_punctuation_both_ways(client, conn):
    store(conn, opp("S-1", title="Ausrüstung für Off-Road Fahrzeuge"))
    store(conn, opp("S-2", title="Ausrustung of the Rust Belt Depot"))
    store(conn, opp("S-3", title="Łódź kitchen equipment"))
    for q in ("Ausrüstung", "Ausrustung", "AUSRÜSTUNG "):
        assert _notice_ids(client, q=q) == ["S-1", "S-2"], q
    assert _notice_ids(client, q="off road") == ["S-1"]
    assert _notice_ids(client, q="Off-Road") == ["S-1"]
    assert _notice_ids(client, q="fahrzeuge off-road") == ["S-1"]
    assert _notice_ids(client, q="lodz") == ["S-3"]
    assert _notice_ids(client, q="Łódź") == ["S-3"]
    # a word must begin a word: "rust" is not inside "Ausrustung", it is a word of S-2
    assert _notice_ids(client, q="rust") == ["S-2"]
    # the notice number is still matched as typed
    assert _notice_ids(client, q="S-1") == ["S-1"]
    # LIKE's own characters are text
    assert _notice_ids(client, q="100%") == []
    assert _notice_ids(client, q="_") == _notice_ids(client)


def test_buyer_search_folds_accents_both_ways(client, conn):
    o = opp("B-1")
    o.buyer_name_raw = "Bundesamt für Ausrüstung, Informationstechnik und Nutzung der Bundeswehr"
    o.country = "DE"
    store(conn, o)
    for q in ("Ausrüstung", "Ausrustung", "ausrüstung bundeswehr", "informationstechnik-und"):
        got = client.get("/v1/buyers", params={"q": q}).json()
        assert got["total"] == 1, q
    assert client.get("/v1/buyers", params={"q": "rustung"}).json()["total"] == 0


# ------------------------------------------------------------------------------ market

def test_the_market_can_be_asked_for_a_calendar_year_and_a_country(client, conn):
    from datetime import date
    store(conn, opp("Y-1", country="PL", published=date(2025, 3, 10)))
    store(conn, opp("Y-2", country="PL", published=date(2025, 11, 2)))
    store(conn, opp("Y-3", country="DE", published=date(2025, 6, 1)))
    store(conn, opp("Y-4", country="PL", published=date(2024, 6, 1)))
    got = client.get("/v1/stats/market", params={"year": 2025}).json()
    assert got["year"] == 2025 and got["country"] is None
    assert got["windowFrom"] == "2025-01-01" and got["windowTo"] == "2025-12-31"
    assert len(got["months"]) == 12 and got["months"][2]["count"] == 1
    assert {c["country"]: c["count"] for c in got["countries"]["items"]} == {"PL": 2, "DE": 1}
    assert "in 2025" in got["basis"]["countries"]
    pl = client.get("/v1/stats/market", params={"year": 2025, "country": "pl"}).json()
    assert pl["country"] == "PL" and pl["countries"]["total"] == 2
    assert sum(m["count"] for m in pl["months"]) == 2
    # the default is unchanged: the rolling window, 36 months, no year
    default = client.get("/v1/stats/market").json()
    assert default["year"] is None and len(default["months"]) == 36
    assert client.get("/v1/stats/market", params={"year": 2999}).status_code == 422
    assert client.get("/v1/stats/market", params={"country": "POL"}).status_code == 422
