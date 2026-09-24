"""The topic-details pass against a real Postgres.

Three properties decide whether this step is safe to run every night: it reads
only the pages that need reading, it lands a payload only when the payload
changed, and one unreadable page does not cost the others.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline
from dgate.sources import eu_portal as portal

pytestmark = pytest.mark.integration


def _calendar_topic(ccm2id: int, code: str, *, status: str = "Open") -> dict:
    return {
        "type": 1,
        "ccm2Id": ccm2id,
        "identifier": code,
        "callIdentifier": "EDF-2026-RA",
        "title": f"Topic {code}",
        "frameworkProgramme": [{"abbreviation": "EDF"}],
        "programmeDivision": [],
        "status": {"abbreviation": status},
        "tags": [],
        "actions": [{"types": [{"typeOfAction": "EDF-RA"}],
                     "deadlineDates": ["1790640000000"]}],
    }


def _details(code: str, *, budget: str = "30000000", states: bool = False) -> dict:
    conditions = ("<p>Other Eligible Conditions: at least 3 organisations from at least "
                  "2 different EU Member States.</p>") if states else \
        "<p>Eligible Countries described in section 6 of the call document.</p>"
    return {
        "identifier": code,
        "topicMGAs": [{"abbreviation": "EDF-AG"}],
        "tags": ["STEP-Defence"],
        "sme": False,
        "links": [],
        "conditions": conditions,
        "budgetOverviewJSONItem": {"budgetTopicActionMap": {"1": [
            {"action": f"{code} - EDF-RA", "budgetYearMap": {"2026": budget},
             "expectedGrants": 2, "minContribution": 0, "maxContribution": 15000000,
             "deadlineModel": "single-stage"},
        ]}},
    }


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(portal, "DETAIL_PAUSE", 0.0)


def _calendar(monkeypatch, records: list[dict]) -> None:
    monkeypatch.setattr(portal, "fetch_snapshot",
                        lambda client=None: {"fundingData": {"GrantTenderObj": records}})


def test_the_details_reach_the_call_that_needed_them(conn, fs_store, monkeypatch):
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-RA-SENS-MSDT")])
    pipeline.run_eu_portal()
    monkeypatch.setattr(portal, "fetch_topic_details",
                        lambda ident, client=None: _details(ident, states=True))
    pipeline.run_topic_details()

    row = conn.execute(
        """SELECT budget, budget_scope, min_consortium_size, min_member_states,
                  eligibility_text, conditions_raw, details_hash, details_seen_at
             FROM call""").fetchone()
    assert float(row["budget"]) == 30_000_000.0
    assert row["budget_scope"] == "topic"
    assert (row["min_consortium_size"], row["min_member_states"]) == (3, 2)
    assert "at least 3 organisations" in row["eligibility_text"]
    assert row["conditions_raw"]["expected_grants"] == 2
    assert row["conditions_raw"]["max_contribution"] == 15_000_000
    assert row["details_hash"] and row["details_seen_at"]
    # The calendar payload and the topic page are two documents, both archived.
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 2


def test_a_page_that_has_not_changed_is_not_landed_again(conn, fs_store, monkeypatch):
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-RA-SENS-MSDT")])
    pipeline.run_eu_portal()
    monkeypatch.setattr(portal, "fetch_topic_details",
                        lambda ident, client=None: _details(ident))
    pipeline.run_topic_details()
    first = conn.execute("SELECT details_seen_at FROM call").fetchone()["details_seen_at"]

    # Zero days, so the refresh window cannot be the reason it is skipped.
    pipeline.run_topic_details(refresh_after_days=0)
    again = conn.execute("SELECT details_seen_at FROM call").fetchone()["details_seen_at"]

    assert again >= first
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 2


def test_a_corrected_budget_is_applied_and_archived(conn, fs_store, monkeypatch):
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-RA-SENS-MSDT")])
    pipeline.run_eu_portal()
    monkeypatch.setattr(portal, "fetch_topic_details",
                        lambda ident, client=None: _details(ident, budget="30000000"))
    pipeline.run_topic_details()

    monkeypatch.setattr(portal, "fetch_topic_details",
                        lambda ident, client=None: _details(ident, budget="45000000"))
    pipeline.run_topic_details(refresh_after_days=0)

    assert float(conn.execute("SELECT budget FROM call").fetchone()["budget"]) == 45_000_000.0
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3


def test_a_read_page_is_not_read_again_while_it_is_fresh(conn, fs_store, monkeypatch):
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-RA-SENS-MSDT")])
    pipeline.run_eu_portal()
    src_id = db.source_id(conn, "eu_portal")
    assert len(db.calls_needing_details(conn, src_id)) == 1

    monkeypatch.setattr(portal, "fetch_topic_details",
                        lambda ident, client=None: _details(ident))
    pipeline.run_topic_details()
    conn.commit()
    assert db.calls_needing_details(conn, src_id) == []


def test_a_closed_call_is_read_once_and_then_left_alone(conn, fs_store, monkeypatch):
    """A closed call cannot change any more. Re-reading every night would be 150
    requests a day to learn nothing."""
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-RA-OLD", status="Closed")])
    pipeline.run_eu_portal()
    monkeypatch.setattr(portal, "fetch_topic_details",
                        lambda ident, client=None: _details(ident))
    pipeline.run_topic_details()
    conn.commit()
    src_id = db.source_id(conn, "eu_portal")
    assert db.calls_needing_details(conn, src_id, refresh_after_days=0) == []


def test_one_unreadable_page_does_not_cost_the_others(conn, fs_store, monkeypatch):
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-RA-ONE"),
                            _calendar_topic(2, "EDF-2026-RA-TWO")])
    pipeline.run_eu_portal()

    def flaky(identifier, client=None):
        if identifier == "EDF-2026-RA-ONE":
            raise RuntimeError("404 withdrawn")
        return _details(identifier)

    monkeypatch.setattr(portal, "fetch_topic_details", flaky)
    pipeline.run_topic_details()

    rows = conn.execute(
        "SELECT topic_code, budget FROM call ORDER BY topic_code").fetchall()
    assert [(r["topic_code"], r["budget"] is None) for r in rows] == [
        ("EDF-2026-RA-ONE", True), ("EDF-2026-RA-TWO", False)]
    run = conn.execute(
        """SELECT records_fetched, status, error_message FROM ingest_run r
             JOIN source s ON s.id = r.source_id
            WHERE s.code = 'eu_portal' ORDER BY r.id DESC LIMIT 1""").fetchone()
    assert run["records_fetched"] == 1
    assert "1 topic pages unreadable" in (run["error_message"] or "")


def test_a_pot_shared_by_sibling_topics_is_labelled_all_the_way_to_the_api(
        conn, fs_store, monkeypatch):
    """The path that matters most for EDF: eleven topics, one figure. If the
    label is lost anywhere between the portal and the response, a supplier reads
    a call's pot as its own topic's budget."""
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-DA-AIR-SPS"),
                            _calendar_topic(2, "EDF-2026-DA-GROUND-MRL")])
    pipeline.run_eu_portal()

    def shared(identifier, client=None):
        return {
            "identifier": identifier,
            "conditions": "<p>described in section 6 of the call document.</p>",
            "budgetOverviewJSONItem": {"budgetTopicActionMap": {"113484": [
                {"action": "EDF-2026-DA-AIR-SPS - EDF-DA",
                 "budgetYearMap": {"2026": "422000000"}},
                {"action": "EDF-2026-DA-GROUND-MRL - EDF-DA",
                 "budgetYearMap": {"2026": "422000000"}},
            ]}},
        }

    monkeypatch.setattr(portal, "fetch_topic_details", shared)
    pipeline.run_topic_details()
    conn.commit()

    with TestClient(api.app) as client:
        for call in client.get("/v1/calls").json():
            assert call["budget"] == 422_000_000.0
            assert call["budget_scope"] == "call"
        one = client.get("/v1/calls/%s" % conn.execute(
            "SELECT id FROM call ORDER BY id LIMIT 1").fetchone()["id"]).json()
        assert one["conditions"]["topics_sharing_budget"] == 2


def test_the_conditions_are_served_on_the_single_call(conn, fs_store, monkeypatch):
    _calendar(monkeypatch, [_calendar_topic(1, "EDF-2026-RA-SENS-MSDT")])
    pipeline.run_eu_portal()
    monkeypatch.setattr(portal, "fetch_topic_details",
                        lambda ident, client=None: _details(ident, states=True))
    pipeline.run_topic_details()
    conn.commit()
    call_id = conn.execute("SELECT id FROM call").fetchone()["id"]

    with TestClient(api.app) as client:
        listed = client.get("/v1/calls").json()[0]
        assert listed["budget"] == 30_000_000.0
        assert listed["budget_scope"] == "topic"
        assert (listed["min_consortium_size"], listed["min_member_states"]) == (3, 2)
        assert "eligibility_text" not in listed      # the long text is not in the list

        one = client.get(f"/v1/calls/{call_id}").json()
        assert "at least 3 organisations" in one["eligibility_text"]
        assert one["conditions"]["expected_grants"] == 2
        assert one["details_seen_at"] is not None
        assert client.get("/v1/calls/999999").status_code == 404
