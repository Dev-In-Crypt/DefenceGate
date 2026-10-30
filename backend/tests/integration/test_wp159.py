"""WP-159 against a real Postgres: a stated contract period is written on the serving row without a version, a version
that does not state it keeps it, the raw-store backfill (report by default, --yes to write, idempotent), the corrected
source licences, and a key reading TenderNed by default."""

# ruff: noqa: F811 - the fixtures `client`, `sent` and `on` come from the WP-153 tests
from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from dgate import config, db
from dgate.normalise import Opportunity, from_de_bkms, strip_personal_data
from dgate.ops import contract_periods
from dgate.rawstore import build_store, storage_key
from dgate.sources.ted import content_hash
from tests.integration.test_api_keys_wp153 import B, _put, client, make_key, on, sent, sign_in  # noqa: F401
from tests.unit.test_wp159 import _bkms

pytestmark = pytest.mark.integration

PERIOD = ('<cac:PlannedPeriod><cbc:EndDate>2030-12-31+01:00</cbc:EndDate>'
          '<cbc:DurationMeasure unitCode="MONTH">48</cbc:DurationMeasure></cac:PlannedPeriod>')


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield
    config.reset_cache()


def _ted(**kw) -> Opportunity:
    return Opportunity(**{"source_code": "ted", "native_id": "1-2026", "buyer_name_raw": "Ministry of Defence",
                          "title_original": "T", "country": "DE", "published_at": date(2026, 10, 1),
                          "status": "awarded", "is_defence": True, **kw})


def _row(conn, oid: int) -> dict:
    return conn.execute(f"SELECT current_version, {', '.join(db.CONTRACT_PERIOD_COLUMNS)} FROM opportunity WHERE id = %s",
                        (oid,)).fetchone()


def test_a_stated_period_writes_no_version_and_a_later_version_keeps_it(conn):
    src = db.source_id(conn, "ted")
    oid, action = db.upsert_opportunity(conn, _ted(), "h1", src)
    assert action == "new"
    # the same notice fetched again with the period fields: the raw hash moved, nothing versioned did
    stated = _ted(contract_end=date(2030, 4, 30), contract_duration=48, contract_duration_unit="MONTH",
                  contract_renewal=True, contract_renewals_max=2)
    assert db.upsert_opportunity(conn, stated, "h2", src) == (oid, "unchanged")
    row = _row(conn, oid)
    assert row["current_version"] == 1
    assert (row["contract_end"], row["contract_duration"], row["contract_duration_unit"], row["contract_renewal"],
            row["contract_renewals_max"]) == (date(2030, 4, 30), 48, "MONTH", True, 2)
    # a real change read from a payload without the period: a version, and the period stays
    _, action = db.upsert_opportunity(conn, _ted(title_original="T2"), "h3", src)
    assert action == "changed"
    row = _row(conn, oid)
    assert row["current_version"] == 2 and row["contract_end"] == date(2030, 4, 30)
    count = conn.execute("SELECT count(*) AS n FROM opportunity_version WHERE opportunity_id = %s", (oid,)).fetchone()
    assert count["n"] == 2


def test_the_backfill_fills_germany_from_the_raw_store_once(conn, fs_store):
    raw = strip_personal_data(_bkms(PERIOD))
    full = from_de_bkms(raw)
    assert full.contract_duration == 48
    before = replace(full, **{c: None for c in db.CONTRACT_PERIOD_COLUMNS}, is_defence=True)   # read before WP-159
    digest = content_hash(raw)
    src = db.source_id(conn, "de_bkms")
    key = build_store().put(storage_key("de_bkms", full.native_id, content_hash=digest), raw)
    db.record_raw(conn, src, full.native_id, digest, key)
    oid, _ = db.upsert_opportunity(conn, before, digest, src)
    conn.commit()

    report = contract_periods.backfill(conn, "de_bkms", write=False)
    conn.rollback()
    assert (report["notices"], report["stated"], report["filled"]) == (1, 1, 1)
    assert _row(conn, oid)["contract_duration"] is None, "a report writes nothing"

    assert contract_periods.backfill(conn, "de_bkms", write=True)["filled"] == 1
    row = _row(conn, oid)
    assert (row["current_version"], row["contract_end"], row["contract_duration"]) == (1, date(2030, 12, 31), 48)
    assert contract_periods.backfill(conn, "de_bkms", write=True)["unchanged"] == 1
    cov = {r["source"]: r for r in contract_periods.coverage(conn)}
    assert (cov["de_bkms"]["with_period"], cov["de_bkms"]["with_end"], cov["de_bkms"]["with_duration"]) == (1, 1, 1)


def test_the_source_licences_read_cc0(conn):
    rows = {r["code"]: r["licence"] for r in conn.execute(
        "SELECT code, licence FROM source WHERE code IN ('se_vinnova', 'de_bkms')").fetchall()}
    assert rows["se_vinnova"].startswith("CC0") and rows["de_bkms"].startswith("CC0")
    # switching Germany on stays the owner's: the migration names neither `active` nor `commercial_ok` (other tests of
    # this session flip `active`, so the row's value proves nothing here)
    sql = (Path(__file__).resolve().parents[2] / "migrations" / "0151_wp159_contract_periods.sql").read_text("utf-8")
    assert "active" not in sql.replace("inactive", "") and "commercial_ok =" not in sql


def test_a_key_reads_tenderned_by_default_and_not_spain(on, sent, conn, monkeypatch):
    monkeypatch.delenv("DGATE_API_KEY_SOURCES", raising=False)
    config.reset_cache()
    nl = _put(conn, "nl_tenderned", "NL-1")
    ted = _put(conn, "ted", "100-2026")
    _put(conn, "es_placsp", "ES-1")
    session, _ = sign_in(on, sent)
    key = make_key(on, session).json()["key"]
    r = on.get("/v1/opportunities?collapse=false", headers=B(key))
    assert r.status_code == 200, r.text
    assert {o["id"] for o in r.json()} == {nl, ted}
    assert on.get("/v1/opportunities?source=es_placsp", headers=B(key)).json()["error"] == "source_not_licensed"
