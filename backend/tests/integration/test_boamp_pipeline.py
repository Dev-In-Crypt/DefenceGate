"""The French daily run against a real Postgres.

The connector's shapes are covered by unit tests; what this checks is the path
through the database: every notice landed and indexed, only defence becoming an
opportunity, and the legal basis the source states surviving the trip.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from dgate import config, pipeline
from dgate.rawstore import build_store
from dgate.sources import boamp

pytestmark = pytest.mark.integration


def _record(idweb: str, *, perimetre: str, cpv: str = "45000000") -> dict:
    return {
        "idweb": idweb,
        "objet": f"Marche {idweb}",
        "nomacheteur": "Ministere des Armees",
        "dateparution": "2026-09-19",
        "datelimitereponse": "2026-10-15T12:00:00+00:00",
        "perimetre": perimetre,
        "nature": "APPEL_OFFRE",
        "donnees": json.dumps({"FNSimple": {"initial": {
            "natureMarche": {"codeCPV": {"objetPrincipal": {"classPrincipale": cpv}},
                             "description": "Description du marche"},
            "communication": {"adresseMailContact": "agent@example.fr"},
        }}}),
    }


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def test_everything_lands_and_only_the_defence_regime_becomes_an_opportunity(
        conn, fs_store, monkeypatch):
    records = [_record("26-1", perimetre="DIRECTIVE-81"),
               _record("26-2", perimetre="DIRECTIVE-24"),
               _record("26-3", perimetre="FNSimple")]
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(records))
    pipeline.run_boamp(days=2)

    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    rows = conn.execute(
        "SELECT native_id, legal_basis, sig_legal_basis FROM opportunity").fetchall()
    assert [(r["native_id"], r["legal_basis"], r["sig_legal_basis"]) for r in rows] == \
        [("26-1", "32009L0081", True)]


def test_the_landed_payload_carries_no_contact_address(conn, fs_store, monkeypatch):
    monkeypatch.setattr(boamp, "fetch_window",
                        lambda days_back=2: iter([_record("26-1", perimetre="DIRECTIVE-81")]))
    pipeline.run_boamp(days=2)
    key = conn.execute("SELECT storage_key FROM raw_ingest").fetchone()["storage_key"]
    landed = json.dumps(build_store().get(key), ensure_ascii=False)
    assert "agent@example.fr" not in landed


def test_a_run_that_collects_less_than_the_floor_is_partial_not_success(
        conn, fs_store, monkeypatch):
    """The floor exists to make a silently short day loud. France publishes
    seven days a week; 106 notices is a real Saturday and 3 is a broken run."""
    monkeypatch.setattr(boamp, "fetch_window",
                        lambda days_back=2: iter([_record("26-1", perimetre="DIRECTIVE-81")]))
    pipeline.run_boamp(days=2)
    row = conn.execute(
        "SELECT r.status, r.expected_min FROM ingest_run r JOIN source s ON s.id = r.source_id "
        "WHERE s.code = 'fr_boamp'").fetchone()
    assert row["status"] == "partial"
    assert row["expected_min"] >= 150


def test_reingesting_the_same_day_creates_no_second_version(conn, fs_store, monkeypatch):
    records = [_record("26-1", perimetre="DIRECTIVE-81")]
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(records))
    pipeline.run_boamp(days=2)
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(records))
    pipeline.run_boamp(days=2)
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1


def test_the_date_of_publication_is_read_from_the_record(conn, fs_store, monkeypatch):
    monkeypatch.setattr(boamp, "fetch_window",
                        lambda days_back=2: iter([_record("26-1", perimetre="DIRECTIVE-81")]))
    pipeline.run_boamp(days=2)
    row = conn.execute("SELECT published_at FROM opportunity").fetchone()
    assert row["published_at"] == date(2026, 9, 19)


# ------------------------------------------------- the historical load

def test_a_french_day_of_history_lands_as_one_bundle_and_is_marked_done(
        conn, fs_store, monkeypatch):
    """France publishes 1.7 million notices since March 2015, and the loader
    that walks them is the same one TED uses -- only the query and the mapper
    differ."""
    from datetime import date as _date

    from dgate import db

    days = {_date(2026, 9, 18): [_record("26-h1", perimetre="DIRECTIVE-81"),
                                 _record("26-h2", perimetre="DIRECTIVE-24")],
            _date(2026, 9, 19): [_record("26-h3", perimetre="CMP-2006-DEFENSE")]}
    monkeypatch.setattr(boamp, "search",
                        lambda params, **kw: iter(days.get(
                            _date.fromisoformat(params["where"][-11:-1]), [])))
    loaded = pipeline.run_history("fr_boamp", _date(2026, 9, 18), _date(2026, 9, 19))

    assert loaded == 2
    assert db.backfill_days_done(conn, "fr_boamp") == {_date(2026, 9, 18), _date(2026, 9, 19)}
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3
    keys = [r["storage_key"] for r in conn.execute(
        "SELECT storage_key FROM raw_ingest ORDER BY id").fetchall()]
    assert keys[0].startswith("fr_boamp/2026/09/18/bundle-0000") and "#0" in keys[0]
    assert conn.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 2
    assert conn.execute("SELECT count(*) n FROM ingest_run").fetchone()["n"] == 0


def test_a_source_without_a_historical_load_is_refused(conn, fs_store):
    """Refused, not attempted with a guessed query: PLACSP has no date filter
    at all, and pretending otherwise would record empty days as complete."""
    with pytest.raises(ValueError, match="no historical load"):
        pipeline.run_history("es_placsp", date(2026, 9, 1), date(2026, 9, 1))
