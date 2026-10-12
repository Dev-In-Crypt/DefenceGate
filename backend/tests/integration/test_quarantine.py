"""One poisoned record must not fail its whole source, and must not hide.

The review of 12 October 2026 found that any exception on one notice rolled the run
back and, because the notice stays inside the fetch window, did it again every night.
These tests run the French daily run (the shape is the same in every connector) with
records that break in different places.
"""

from __future__ import annotations

import json

import psycopg
import pytest

from dgate import config, db, pipeline
from dgate.normalise import from_boamp as real_from_boamp
from dgate.sources import boamp

pytestmark = pytest.mark.integration


def _record(idweb: str) -> dict:
    return {
        "idweb": idweb,
        "objet": f"Marche {idweb}",
        "nomacheteur": "Ministere des Armees",
        "dateparution": "2026-09-19",
        "datelimitereponse": "2026-10-15T12:00:00+00:00",
        "perimetre": "DIRECTIVE-81",
        "nature": "APPEL_OFFRE",
        "donnees": json.dumps({"FNSimple": {"initial": {
            "natureMarche": {"codeCPV": {"objetPrincipal": {"classPrincipale": "35000000"}},
                             "description": "Description du marche"}}}}),
    }


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


def _run(monkeypatch, records):
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(records))
    pipeline.run_boamp(days=2)


def _last_run(conn):
    return conn.execute(
        "SELECT r.status, r.error_message FROM ingest_run r JOIN source s ON s.id = r.source_id "
        "WHERE s.code = 'fr_boamp' ORDER BY r.id DESC LIMIT 1").fetchone()


def _native_ids(conn, table):
    return sorted(r["native_id"] for r in conn.execute(f"SELECT native_id FROM {table}"))


def test_a_record_that_breaks_normalisation_is_set_aside_and_the_rest_are_kept(
        conn, fs_store, monkeypatch):
    def broken_on_two(clean):
        if clean["idweb"] == "26-2":
            raise KeyError("a field the source dropped")
        return real_from_boamp(clean)

    monkeypatch.setattr(pipeline, "from_boamp", broken_on_two)
    _run(monkeypatch, [_record("26-1"), _record("26-2"), _record("26-3")])

    assert _native_ids(conn, "opportunity") == ["26-1", "26-3"]
    run = _last_run(conn)
    assert run["status"] == "partial"
    assert "1 records quarantined" in run["error_message"]
    assert "26-2 (KeyError)" in run["error_message"]


def test_a_record_whose_write_fails_leaves_no_half_written_row_behind(
        conn, fs_store, monkeypatch):
    """Its raw_ingest row was written before the upsert raised. The savepoint takes it
    back, so the index never lists a record that has no archive row."""
    real = db.upsert_opportunity

    def refuse_two(c, opp, h, src_id):
        if opp.native_id == "26-2":
            raise psycopg.DataError("value too long for type")
        return real(c, opp, h, src_id)

    monkeypatch.setattr(db, "upsert_opportunity", refuse_two)
    _run(monkeypatch, [_record("26-1"), _record("26-2"), _record("26-3")])

    assert _native_ids(conn, "opportunity") == ["26-1", "26-3"]
    assert _native_ids(conn, "raw_ingest") == ["26-1", "26-3"]
    assert "26-2 (DataError)" in _last_run(conn)["error_message"]


def test_the_quarantined_record_is_tried_again_the_next_night(conn, fs_store, monkeypatch):
    monkeypatch.setattr(pipeline, "from_boamp",
                        lambda clean: (_ for _ in ()).throw(TypeError("shape")))
    _run(monkeypatch, [_record("26-1")])
    assert _native_ids(conn, "opportunity") == []

    monkeypatch.setattr(pipeline, "from_boamp", real_from_boamp)
    _run(monkeypatch, [_record("26-1")])
    assert _native_ids(conn, "opportunity") == ["26-1"]


def test_many_poisoned_records_are_a_changed_source_and_fail_the_run(
        conn, fs_store, monkeypatch):
    monkeypatch.setattr(pipeline, "from_boamp",
                        lambda clean: (_ for _ in ()).throw(AttributeError("new shape")))
    records = [_record(f"26-{n}") for n in range(pipeline.MAX_QUARANTINED + 5)]
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(records))
    with pytest.raises(RuntimeError, match="more than 50 records"):
        pipeline.run_boamp(days=2)
    assert _last_run(conn)["status"] == "failed"
    assert _native_ids(conn, "opportunity") == []


def test_a_database_failure_is_not_a_poisoned_record(conn, fs_store, monkeypatch):
    def down(clean):
        raise psycopg.OperationalError("server closed the connection")

    monkeypatch.setattr(pipeline, "from_boamp", down)
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter([_record("26-1")]))
    with pytest.raises(psycopg.OperationalError):
        pipeline.run_boamp(days=2)
    assert _last_run(conn)["status"] == "failed"
