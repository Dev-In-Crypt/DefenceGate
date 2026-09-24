"""The grant run against a real Postgres.

What the unit tests cannot check is the part that costs money and the part that
makes a change visible: a payload is landed once however many nights the portal
republishes it, and a deadline that moves updates the call and says which field
moved.
"""

from __future__ import annotations

import pytest

from dgate import config, db, pipeline
from dgate.sources import eu_portal as portal

pytestmark = pytest.mark.integration


def _topic(ccm2id: int, code: str, *, programme: str = "EDF",
           deadline: str = "1790640000000", status: str = "Open") -> dict:
    return {
        "type": 1,
        "ccm2Id": ccm2id,
        "identifier": code,
        "callIdentifier": code.rsplit("-", 2)[0],
        "title": f"Topic {code}",
        "frameworkProgramme": [{"abbreviation": programme}],
        "programmeDivision": [],
        "status": {"abbreviation": status},
        "tags": [],
        "actions": [{"types": [{"typeOfAction": f"{programme}-RA"}],
                     "deadlineDates": [deadline]}],
    }


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _serve(monkeypatch, records: list[dict]) -> None:
    monkeypatch.setattr(portal, "fetch_snapshot",
                        lambda client=None: {"fundingData": {"GrantTenderObj": records}})


def test_calls_land_and_are_served_with_their_programme(conn, fs_store, monkeypatch):
    _serve(monkeypatch, [
        _topic(1, "EDF-2026-RA-SENS-MSDT"),
        _topic(2, "HORIZON-CL3-2026-01-DRS-01", programme="HORIZON"),
        _topic(3, "AGRIP-MULTI-2026-IM", programme="AGRIP2027"),   # out of scope
    ])
    pipeline.run_eu_portal()

    rows = conn.execute(
        """SELECT p.code, c.topic_code, c.regime, c.status, c.deadline_at, c.content_hash
             FROM call c JOIN programme p ON p.id = c.programme_id
            ORDER BY c.topic_code""").fetchall()
    assert [(r["code"], r["regime"]) for r in rows] == [
        ("EDF", "defence"), ("HORIZON", "dual_use")]
    assert all(r["status"] == "open" and r["deadline_at"] is not None for r in rows)
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 2


def test_a_second_night_lands_no_payload_and_writes_no_version(conn, fs_store, monkeypatch):
    """The portal republishes the same document nightly. Landing it again would
    pay for 150 writes a night for nothing, so the run lands only payloads whose
    hash is new -- and `last_seen_at` still moves, because that is how a call
    that stopped being published becomes visible."""
    _serve(monkeypatch, [_topic(1, "EDF-2026-RA-SENS-MSDT")])
    pipeline.run_eu_portal()
    first = conn.execute("SELECT id, last_seen_at, first_seen_at FROM call").fetchone()

    pipeline.run_eu_portal()
    again = conn.execute("SELECT id, last_seen_at, first_seen_at FROM call").fetchone()

    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 1
    assert again["id"] == first["id"]
    assert again["first_seen_at"] == first["first_seen_at"]
    assert again["last_seen_at"] >= first["last_seen_at"]
    runs = conn.execute(
        """SELECT records_fetched, records_new, records_changed, status
             FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.code = 'eu_portal' ORDER BY r.id""").fetchall()
    assert [r["records_new"] for r in runs] == [1, 0]
    assert [r["records_changed"] for r in runs] == [0, 0]


def test_a_deadline_that_moves_is_recorded_as_a_change(conn, fs_store, monkeypatch):
    _serve(monkeypatch, [_topic(1, "EDF-2026-RA-SENS-MSDT")])
    pipeline.run_eu_portal()
    before = conn.execute("SELECT deadline_at FROM call").fetchone()["deadline_at"]

    # The same topic, four days later. This is the change the product exists to
    # notice, and it is the reason a call is hashed rather than merely upserted.
    _serve(monkeypatch, [_topic(1, "EDF-2026-RA-SENS-MSDT", deadline="1790985600000")])
    pipeline.run_eu_portal()

    after = conn.execute("SELECT deadline_at, content_hash FROM call").fetchone()
    assert after["deadline_at"] > before
    assert conn.execute("SELECT count(*) n FROM call").fetchone()["n"] == 1
    # Both payloads are in the archive: the state before the extension is still
    # readable, which is what makes "the deadline moved" provable later.
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 2
    run = conn.execute(
        """SELECT records_changed FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.code = 'eu_portal' ORDER BY r.id DESC LIMIT 1""").fetchone()
    assert run["records_changed"] == 1


def test_an_unseeded_programme_is_created_rather_than_refusing_the_call(conn):
    """A programme that appears mid-year -- EDIP's first calls will -- must not
    stop the night's run. The row it gets has no regulation, which is visible in
    the table and is the signal that it needs a look."""
    created = db.programme_id(conn, "EUDIS")
    row = conn.execute("SELECT code, name, legal_basis FROM programme WHERE id = %s",
                       (created,)).fetchone()
    assert (row["code"], row["name"], row["legal_basis"]) == ("EUDIS", "EUDIS", None)
    assert db.programme_id(conn, "EUDIS") == created      # and not a second row


def test_a_defence_seal_on_a_civil_programme_reaches_the_database(conn, fs_store,
                                                                  monkeypatch):
    topic = _topic(9, "DIGITAL-2026-CYBER-01", programme="DIGITAL")
    topic["tags"] = ["STEP-Defence"]
    _serve(monkeypatch, [topic])
    pipeline.run_eu_portal()
    row = conn.execute("SELECT regime FROM call").fetchone()
    assert row["regime"] == "defence"
