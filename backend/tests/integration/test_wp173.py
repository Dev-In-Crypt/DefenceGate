"""WP-173 (QA 24 Nov 2026, funding): the next cut-off of a multiple cut-off call, a rolling call past its last cut-off, the cut-offs
and stages served, and titles that tell the EIC editions apart."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, db
from dgate.normalise import Call, from_eu_call
from dgate.sources import eu_portal as portal

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
DAY_MS = 86_400_000


def _ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _put(conn, native_id: str, *, days: float, title: str | None = None, topic: str | None = None,
         conditions: dict | None = None) -> int:
    call = Call(programme_code="HORIZON", native_id=native_id, title=title or f"Call {native_id}",
                topic_code=topic or f"HORIZON-{native_id}", status="open", regime="defence",
                deadline_at=NOW + timedelta(days=days), deadline_precision="date", conditions_raw=conditions)
    call_id, _, _ = db.upsert_call(conn, call, f"hash-{native_id}", db.source_id(conn, "eu_portal"))
    conn.commit()
    return call_id


def test_the_next_cut_off_comes_from_the_stored_topic_page_when_the_calendar_states_no_model(conn):
    """C-1: support for SEAPs, served "last cut-off 12 Nov, no next published" while the portal listed four more."""
    past, nxt, later = date.today() - timedelta(days=12), date.today() + timedelta(days=84), date.today() + timedelta(days=300)
    record = {"type": 1, "ccm2Id": 51000001, "identifier": "EDF-EDIP-P-2026-2027-FNLC-SA-SEAP", "title": "Support for SEAPs",
              "frameworkProgramme": [{"abbreviation": "EDF"}], "status": {"abbreviation": "Open"},
              "actions": [{"deadlineDates": [_ms(past)]}]}
    call = from_eu_call(record)
    assert call.deadline_at.date() == past                       # the calendar alone: its one date
    assert portal.with_stored_cut_offs(conn, call, record).deadline_at.date() == past    # nothing stored yet: unchanged
    db.upsert_call(conn, call, "h-seap", db.source_id(conn, "eu_portal"))
    conn.execute("""UPDATE call SET conditions_raw = %s::jsonb WHERE native_id = '51000001'""",
                  ('{"deadline_model": "multiple cut-off", "budget_line": {"deadlineDates": [%d, %d, %d]}}'
                   % (_ms(past), _ms(nxt), _ms(later)),))
    conn.commit()
    again = portal.with_stored_cut_offs(conn, from_eu_call(record), record)
    assert again.deadline_at.date() == nxt and again.deadline_precision == "date"
    db.upsert_call(conn, again, "h-seap", db.source_id(conn, "eu_portal"))      # same payload: the corrected deadline still lands
    conn.commit()
    assert conn.execute("SELECT deadline_at FROM call WHERE native_id = '51000001'").fetchone()["deadline_at"].date() == nxt


def test_a_rolling_call_is_held_open_a_week_past_its_cut_off_not_for_ever(client, conn):
    """A-7, F33: EIC Accelerator 2026 (4 Nov) and EIC STEP Scale Up 2026 (8 Oct) were Open on 24 Nov with no cut-off to come."""
    recent = _put(conn, "recent", days=-4, conditions={"deadline_model": "continuous"})
    stale = _put(conn, "stale", days=-20, conditions={"deadline_model": "continuous"})
    assert client.get(f"/v1/funding/{recent}").json()["status"] == "open"
    assert client.get(f"/v1/funding/{stale}").json()["status"] == "closed"
    ids = [c["id"] for c in client.get("/v1/funding", params={"status": "open"}).json()["items"]]
    assert str(recent) in ids and str(stale) not in ids


def test_the_stages_and_cut_offs_and_the_edition_are_served(client, conn):
    """C-9: EIC Pathfinder two-stage showed one deadline and its bare code as the title; C-1: the cut-offs."""
    s1, s2 = date(2027, 2, 25), date(2027, 9, 16)
    two = _put(conn, "PF", days=90, title="HORIZON-EIC-2027-PATHFINDEROPEN-two-stage", topic="HORIZON-EIC-2027-PATHFINDEROPEN-two-stage",
               conditions={"deadline_model": "two-stage", "budget_line": {"deadlineDates": [_ms(s2), _ms(s1)]}})
    body = client.get(f"/v1/funding/{two}").json()
    assert body["cutOffs"] == ["2027-02-25", "2027-09-16"] and body["deadlineModel"] == "two-stage"
    assert body["title"] == "EIC Pathfinder Open 2027 (two-stage)"
    assert body["slug"].startswith(f"{two}-horizon-eic-2027")          # the stored title keeps the link
    one = _put(conn, "ONE", days=30, conditions={"deadline_model": "single-stage", "budget_line": {"deadlineDates": [_ms(s1)]}})
    body = client.get(f"/v1/funding/{one}").json()
    assert body["cutOffs"] == [] and body["deadlineModel"] is None
