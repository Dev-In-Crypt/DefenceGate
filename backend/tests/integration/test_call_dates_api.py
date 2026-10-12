"""Calls: a date is a date, a continuous call stays open, and a corrected reading of an
unchanged payload reaches the row without waiting for the source to edit the call.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline
from dgate.normalise import Call
from dgate.sources import eu_portal as portal

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _put(conn, native_id: str, *, days: float | None = 20, status: str = "open",
         precision: str | None = None, published: date | None = None,
         conditions: dict | None = None, programme: str = "HORIZON") -> int:
    call = Call(
        programme_code=programme, native_id=native_id, title=f"Call {native_id}",
        topic_code=f"{programme}-{native_id}", status=status, regime="defence",
        deadline_at=(NOW + timedelta(days=days)) if days is not None else None,
        deadline_precision=precision, published_at=published, conditions_raw=conditions)
    call_id, _, _ = db.upsert_call(conn, call, f"hash-{native_id}", db.source_id(conn, "eu_portal"))
    conn.commit()
    return call_id


def _call(client, call_id):
    return client.get(f"/v1/funding/{call_id}").json()


def _open_ids(client, **params):
    body = client.get("/v1/funding", params={"status": "open", **params}).json()
    return [c["topicId"].rsplit("-", 1)[1] for c in body["items"]]


# -------------------------------------------------------------- date only

def test_a_date_only_deadline_is_flagged_and_a_timed_one_is_not(client, conn):
    day = _put(conn, "day", precision="date")
    timed = _put(conn, "timed", precision=None)
    assert _call(client, day)["deadlineIsDate"] is True
    assert _call(client, timed)["deadlineIsDate"] is False


def test_a_deadline_stored_at_midnight_utc_before_the_flag_existed_reads_as_a_date(client, conn):
    legacy = _put(conn, "legacy", days=None)
    conn.execute("UPDATE call SET deadline_at = %s WHERE id = %s",
                 (datetime(2027, 3, 2, tzinfo=UTC), legacy))
    conn.commit()
    assert _call(client, legacy)["deadlineIsDate"] is True


def test_a_call_with_no_deadline_is_not_a_date(client, conn):
    none = _put(conn, "none", days=None)
    body = _call(client, none)
    assert (body["deadline"], body["deadlineIsDate"]) == (None, False)


def test_the_publication_date_is_served(client, conn):
    dated = _put(conn, "dated", published=date(2026, 2, 11))
    undated = _put(conn, "undated")
    assert _call(client, dated)["publishedAt"].startswith("2026-02-11")
    assert _call(client, undated)["publishedAt"] is None


# ------------------------------------------------------------- continuous

def test_a_continuous_call_the_source_still_calls_open_is_not_served_closed(client, conn):
    """HORIZON-EIC-2026-STEP, 8 October 2026: cut-off passed, the portal still Open."""
    rolling = _put(conn, "rolling", days=-4, conditions={"deadline_model": "continuous"})
    single = _put(conn, "single", days=-4, conditions={"deadline_model": "single-stage"})
    unknown = _put(conn, "unknown", days=-4)
    assert _call(client, rolling)["status"] == "open"
    assert _call(client, single)["status"] == "closed"
    assert _call(client, unknown)["status"] == "closed"
    assert _open_ids(client) == ["rolling"]


def test_a_continuous_call_closes_when_the_source_says_so(client, conn):
    rolling = _put(conn, "rolling", days=-4, conditions={"deadline_model": "continuous"})
    _put(conn, "rolling", days=-4, status="closed", conditions={"deadline_model": "continuous"})
    assert _call(client, rolling)["status"] == "closed"


def test_a_call_with_several_cut_offs_stays_open_between_them(client, conn):
    several = _put(conn, "several", days=-2, conditions={"deadline_model": "multiple cut-off"})
    assert _call(client, several)["status"] == "open"


def test_a_held_open_call_sorts_after_the_ones_with_a_deadline_to_come(client, conn):
    _put(conn, "rolling", days=-4, conditions={"deadline_model": "continuous"})
    _put(conn, "soon", days=5)
    _put(conn, "later", days=40)
    assert _open_ids(client) == ["soon", "later", "rolling"]


def test_closing_soon_does_not_include_a_call_whose_cut_off_has_passed(client, conn):
    _put(conn, "rolling", days=-4, conditions={"deadline_model": "continuous"})
    _put(conn, "soon", days=5)
    body = client.get("/v1/funding", params={"status": "closing-soon"}).json()
    assert [c["topicId"].rsplit("-", 1)[1] for c in body["items"]] == ["soon"]


# ---------------------------------------------------------------- anomalies

def test_the_call_anomalies_are_named(client, conn):
    before = _put(conn, "before", days=10, published=date.today() + timedelta(days=30))
    far = _put(conn, "far", days=365 * 5)
    fine = _put(conn, "fine", days=30, published=date.today() - timedelta(days=3))
    assert _call(client, before)["anomalies"] == ["deadline-before-publication"]
    assert _call(client, far)["anomalies"] == ["deadline-more-than-3y"]
    assert _call(client, fine)["anomalies"] == []


# -------------------------------------------------- a corrected reading

def test_an_unchanged_payload_applies_a_deadline_read_better_than_before(conn):
    """The portal's deadline was stored as 00:00Z, the start of its last day. The mapping
    now stores the end of that day; the payload (and its hash) did not change, so the
    correction has to be applied from the unchanged branch."""
    src = db.source_id(conn, "eu_portal")
    midnight = datetime(2026, 12, 1, tzinfo=UTC)
    old = Call(programme_code="HORIZON", native_id="9", title="T", status="open",
               regime="dual_use", deadline_at=midnight)
    call_id, action, _ = db.upsert_call(conn, old, "same-hash", src)
    assert action == "new"

    better = Call(programme_code="HORIZON", native_id="9", title="T", status="open",
                  regime="dual_use", deadline_at=datetime(2026, 12, 1, 22, 59, 59, tzinfo=UTC),
                  deadline_precision="date", published_at=date(2026, 2, 11))
    assert db.upsert_call(conn, better, "same-hash", src) == (call_id, "changed", ["deadline_at"])
    row = conn.execute("SELECT deadline_at, deadline_precision, published_at FROM call "
                       "WHERE id = %s", (call_id,)).fetchone()
    assert row["deadline_at"] == datetime(2026, 12, 1, 22, 59, 59, tzinfo=UTC)
    assert (row["deadline_precision"], row["published_at"]) == ("date", date(2026, 2, 11))

    # and the next night is quiet
    assert db.upsert_call(conn, better, "same-hash", src) == (call_id, "unchanged", [])


def test_an_unchanged_payload_with_no_deadline_never_erases_the_stored_one(conn):
    src = db.source_id(conn, "eu_portal")
    call = Call(programme_code="HORIZON", native_id="9", title="T", status="open",
                regime="dual_use", deadline_at=NOW + timedelta(days=9), deadline_precision="date")
    call_id, _, _ = db.upsert_call(conn, call, "h", src)
    blank = Call(programme_code="HORIZON", native_id="9", title="T", status="open",
                 regime="dual_use")
    assert db.upsert_call(conn, blank, "h", src)[1] == "unchanged"
    row = conn.execute("SELECT deadline_at, deadline_precision FROM call WHERE id = %s",
                       (call_id,)).fetchone()
    assert row["deadline_at"] is not None and row["deadline_precision"] == "date"


# ------------------------------------------------------- military mobility

@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def test_the_cef_military_mobility_call_is_collected_under_a_seeded_programme(
        conn, fs_store, monkeypatch):
    milmob = {
        "type": 1, "ccm2Id": 51468068, "identifier": "CEF-T-2026-MILMOB-WORKS",
        "callIdentifier": "CEF-T-2026-MILMOB", "title": "Adaptation of the TEN-T to "
        "civilian-defence dual use - studies, works or mixed",
        "frameworkProgramme": {"abbreviation": "CEF2027"},
        "programmeDivision": [{"abbreviation": "CEF-2.1.3", "description": "Military Mobility"}],
        "status": {"abbreviation": "Open"}, "tags": ["CEF", "MILMOB", "military mobility"],
        "publicationDateLong": 1781740800000,
        "actions": [{"deadlineDates": [str(int((NOW + timedelta(days=20)).replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000))]}],
    }
    civil = {**milmob, "ccm2Id": 51468099, "identifier": "CEF-T-2026-GREEN-WORKS",
             "tags": ["CEF"], "programmeDivision": [{"abbreviation": "CEF-2.1.1"}]}
    monkeypatch.setattr(portal, "fetch_snapshot",
                        lambda client=None: {"fundingData": {"GrantTenderObj": [milmob, civil]}})
    pipeline.run_eu_portal()

    rows = conn.execute(
        """SELECT p.code, p.name, c.topic_code, c.regime, c.published_at, c.deadline_precision
             FROM call c JOIN programme p ON p.id = c.programme_id""").fetchall()
    assert [(r["code"], r["topic_code"], r["regime"]) for r in rows] == [
        ("CEF2027", "CEF-T-2026-MILMOB-WORKS", "dual_use")]
    assert rows[0]["name"] == "Connecting Europe Facility (CEF)"      # seeded, not inserted
    assert rows[0]["published_at"] == date(2026, 6, 18)
    assert rows[0]["deadline_precision"] == "date"
