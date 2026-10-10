"""The Dutch daily run against a real Postgres.

The connector's shapes are covered by unit tests; what this checks is the path
through the database: every publication landed and indexed, only the defence
directive becoming an opportunity, the CPV codes from the detail page surviving
the trip, and a publication that lost its detail page making the run partial.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from dgate import config, db, pipeline
from dgate.rawstore import build_store
from dgate.sources import tenderned

pytestmark = pytest.mark.integration

DIRECTIVE = "Aankondiging van een opdracht - defensierichtlijn, standaardregeling"
GENERAL = "Aankondiging van een opdracht - algemene richtlijn, standaardregeling"


def _record(pid: str, *, form: str = DIRECTIVE, code: str = "EF18", detail: bool = True,
            cpv: str = "90500000") -> dict:
    record = {
        "publicatieId": pid,
        "publicatieDatum": "2026-10-09",
        "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
        "aanbestedingNaam": f"Opdracht {pid}",
        "opdrachtgeverNaam": "Gemeente Voorbeeld",
        "sluitingsDatum": "2026-11-19T17:00:00",
        "publicatiecode": {"code": code, "omschrijving": form},
        "opdrachtBeschrijving": "Levering. Contact: inkoop@voorbeeld.nl",
    }
    if detail:
        record["detail"] = {"publicatieId": int(pid), "cpvCodes": [
            {"isHoofdOpdracht": True, "code": f"{cpv}-1", "omschrijving": "Omschrijving"}]}
    else:
        record["detailError"] = "HTTPStatusError: 404"
    return record


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _feed(monkeypatch, records):
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter(records))


def test_everything_lands_and_only_the_defence_directive_becomes_an_opportunity(
        conn, fs_store, monkeypatch):
    _feed(monkeypatch, [_record("1"), _record("2", form=GENERAL, code="EF16"),
                        _record("3", form=GENERAL, code="EF16")])
    pipeline.run_tenderned(days=2)

    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    rows = conn.execute(
        "SELECT native_id, country, legal_basis, sig_legal_basis, cpv_codes FROM opportunity"
    ).fetchall()
    assert [(r["native_id"], r["country"], r["legal_basis"], r["sig_legal_basis"])
            for r in rows] == [("1", "NL", "32009L0081", True)]
    assert rows[0]["cpv_codes"] == ["90500000"]


def test_a_military_cpv_code_from_the_detail_page_is_enough_under_the_general_directive(
        conn, fs_store, monkeypatch):
    """The list says "general directive", the detail page says CPV 35700000
    (military electronic systems). Only the detail page can say so, which is why
    it is read for every publication and not only the ones already flagged."""
    _feed(monkeypatch, [_record("5", form=GENERAL, code="EF16", cpv="35700000")])
    pipeline.run_tenderned(days=2)
    row = conn.execute(
        "SELECT legal_basis, sig_legal_basis, sig_cpv FROM opportunity").fetchone()
    assert (row["legal_basis"], row["sig_legal_basis"], row["sig_cpv"]) == (None, False, True)


def test_the_landed_payload_carries_no_contact_address(conn, fs_store, monkeypatch):
    _feed(monkeypatch, [_record("1")])
    pipeline.run_tenderned(days=2)
    key = conn.execute("SELECT storage_key FROM raw_ingest").fetchone()["storage_key"]
    landed = json.dumps(build_store().get(key), ensure_ascii=False)
    assert "inkoop@voorbeeld.nl" not in landed


def test_a_publication_without_its_detail_page_makes_the_run_partial(
        conn, fs_store, monkeypatch):
    """Landed, classified from the list alone, and said to be thinner than the
    rest. A green tick would hide the missing CPV codes."""
    _feed(monkeypatch, [_record("1"), _record("2", detail=False)])
    pipeline.run_tenderned(days=2)
    run = conn.execute(
        "SELECT r.status, r.error_message FROM ingest_run r JOIN source s ON s.id = r.source_id "
        "WHERE s.code = 'nl_tenderned'").fetchone()
    assert run["status"] == "partial"
    assert "1 publications without their detail page" in run["error_message"]
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 2


def test_reingesting_the_same_day_creates_no_second_version(conn, fs_store, monkeypatch):
    records = [_record("1")]
    _feed(monkeypatch, records)
    pipeline.run_tenderned(days=2)
    _feed(monkeypatch, records)
    pipeline.run_tenderned(days=2)
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1


def test_the_date_and_the_url_come_from_the_record(conn, fs_store, monkeypatch):
    _feed(monkeypatch, [_record("1")])
    pipeline.run_tenderned(days=2)
    row = conn.execute("SELECT published_at, source_url FROM opportunity").fetchone()
    assert row["published_at"] == date(2026, 10, 9)
    assert row["source_url"].endswith("/aankondigingen/overzicht/1")


# ------------------------------------------------- the historical load

def test_a_dutch_day_of_history_lands_as_one_bundle_and_is_marked_done(
        conn, fs_store, monkeypatch):
    days = {date(2026, 1, 5): [_record("10"), _record("11", form=GENERAL, code="EF16")],
            date(2026, 1, 6): [_record("12")]}
    monkeypatch.setattr(tenderned, "fetch_day", lambda day, **kw: iter(days.get(day, [])))
    loaded = pipeline.run_history("nl_tenderned", date(2026, 1, 5), date(2026, 1, 6))

    assert loaded == 2
    assert db.backfill_days_done(conn, "nl_tenderned") == {date(2026, 1, 5), date(2026, 1, 6)}
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    keys = [r["storage_key"] for r in conn.execute(
        "SELECT storage_key FROM raw_ingest ORDER BY id").fetchall()]
    assert keys[0].startswith("nl_tenderned/2026/01/05/bundle-0000") and "#0" in keys[0]
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 2
