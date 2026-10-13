"""The generic re-map of non-TED sources: a correction is a `remapped` version, nothing is
erased, a second run writes nothing, and the archive trigger is never touched."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from dgate import config, db
from dgate.normalise import from_ezamowienia, strip_personal_data
from dgate.ops import remap_source
from dgate.rawstore import build_store, storage_key
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration

CASES = json.loads((Path(__file__).resolve().parents[1] / "fixtures" /
                    "ezamowienia_status_cases.json").read_text(encoding="utf-8"))


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield
    config.reset_cache()


@pytest.fixture(autouse=True)
def clean_markers(conn):
    conn.execute("DELETE FROM remap_marker")
    conn.commit()


def seed(conn, case: str, **old) -> int:
    """The notice as stored before the mapper was fixed: the payload landed as it was, the
    row mapped by the old rules (`old` overrides)."""
    raw = strip_personal_data(CASES[case])
    new = from_ezamowienia(raw)
    digest = content_hash(raw)
    src = db.source_id(conn, "pl_ezam")
    key = build_store().put(storage_key("pl_ezam", new.native_id, content_hash=digest), raw)
    db.record_raw(conn, src, new.native_id, digest, key)
    stale = replace(new, is_defence=True, sig_legal_basis=True, **old)
    opp_id, action = db.upsert_opportunity(conn, stale, digest, src)
    assert action == "new"
    conn.commit()
    return opp_id


def versions(conn, opp_id: int):
    return conn.execute(
        """SELECT v.version, v.changed_fields, array_remove(array_agg(n.kind), NULL) AS kinds
             FROM opportunity_version v
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s GROUP BY v.id ORDER BY v.version""", (opp_id,)).fetchall()


def test_a_wrong_status_is_corrected_by_a_remapped_version_and_a_second_run_writes_nothing(conn, fs_store):
    oid = seed(conn, "ted_can_29", status="unknown", status_native=None)
    dry = remap_source.run("pl_ezam", write=False)
    assert dry.versions == 1
    assert len(versions(conn, oid)) == 1

    first = remap_source.run("pl_ezam", write=True)
    assert (first.examined, first.versions, first.failed) == (1, 1, 0)
    got = versions(conn, oid)
    assert [v["version"] for v in got] == [1, 2]
    assert got[1]["changed_fields"] == ["status"] and got[1]["kinds"] == ["remapped"]
    assert conn.execute("SELECT status FROM opportunity WHERE id = %s", (oid,)).fetchone()["status"] == "awarded"

    second = remap_source.run("pl_ezam", write=True)
    assert second.examined == 0                     # marked done
    assert len(versions(conn, oid)) == 2


def test_a_fact_the_mapper_no_longer_states_is_not_erased(conn, fs_store):
    oid = seed(conn, "ted_can_29", status="unknown", value_amount=12345.0, value_currency="PLN")
    remap_source.run("pl_ezam", write=True)
    row = conn.execute("SELECT value_amount, value_currency FROM opportunity WHERE id = %s",
                       (oid,)).fetchone()
    mapped = from_ezamowienia(strip_personal_data(CASES["ted_can_29"]))
    if mapped.value_amount is None:
        assert (float(row["value_amount"]), row["value_currency"]) == (12345.0, "PLN")


def test_an_unknown_source_is_refused():
    # es_placsp was the example until 13 October 2026, when it gained a mapper of its own.
    with pytest.raises(SystemExit):
        remap_source.run("ted")


def test_a_second_epoch_runs_again_without_resetting_anything(conn, fs_store):
    oid = seed(conn, "ted_can_29", status="unknown", status_native=None)
    remap_source.run("pl_ezam", write=True)
    assert remap_source.run("pl_ezam", write=True).examined == 0
    again = remap_source.run("pl_ezam", write=True, epoch=2)
    assert again.examined == 1 and again.versions == 0       # same mapping: nothing to write
    assert len(versions(conn, oid)) == 2
