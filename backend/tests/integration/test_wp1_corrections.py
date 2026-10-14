"""The correction paths of work package WP-1, against a real Postgres: BOAMP deadline and
lots, TED placeholder amounts, PLACSP stored records and Atlas payloads landed but never
applied. Every correction is a new version annotated `remapped`, nothing is erased, and a
second run writes nothing.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from dgate import config, db
from dgate.normalise import (
    Opportunity,
    from_atlas_pl,
    from_boamp,
    from_ted,
    strip_personal_data,
)
from dgate.ops import remap_source, repair_ted
from dgate.rawstore import build_store, storage_key
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BOAMP = json.loads((FIXTURES / "boamp_eforms_deadlines.json").read_text(encoding="utf-8"))


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
    conn.execute("DELETE FROM ted_repair_marker")
    conn.commit()


def land(conn, source: str, native_id: str, payload: dict) -> str:
    digest = content_hash(payload)
    key = build_store().put(storage_key(source, native_id, content_hash=digest), payload)
    db.record_raw(conn, db.source_id(conn, source), native_id, digest, key)
    return digest


def versions(conn, opp_id: int) -> list[dict]:
    return conn.execute(
        """SELECT v.version, v.changed_fields, v.raw_hash, v.payload,
                  array_remove(array_agg(n.kind), NULL) AS kinds
             FROM opportunity_version v
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s GROUP BY v.id ORDER BY v.version""",
        (opp_id,)).fetchall()


def row(conn, opp_id: int) -> dict:
    return conn.execute("SELECT * FROM opportunity WHERE id = %s", (opp_id,)).fetchone()


# ------------------------------------------------------------------ BOAMP

def test_boamp_deadline_and_lots_reach_the_stored_row_as_a_remapped_version(conn, fs_store):
    record = strip_personal_data(BOAMP["thirteen_lots"])       # 26-90291
    digest = land(conn, "fr_boamp", record["idweb"], record)
    src = db.source_id(conn, "fr_boamp")
    stored = replace(from_boamp(record), deadline_at=None, lot_count=None, is_defence=True,
                     sig_legal_basis=True)
    assert stored.status == "open"
    oid, action = db.upsert_opportunity(conn, stored, digest, src)
    assert action == "new"
    conn.commit()

    dry = remap_source.run("fr_boamp", write=False, epoch=3)
    assert dry.versions == 1 and row(conn, oid)["deadline_at"] is None

    first = remap_source.run("fr_boamp", write=True, epoch=3)
    assert (first.examined, first.versions, first.failed) == (1, 1, 0)
    got = versions(conn, oid)
    assert [v["version"] for v in got] == [1, 2]
    assert got[1]["changed_fields"] == ["deadline_at"] and got[1]["kinds"] == ["remapped"]
    served = row(conn, oid)
    assert served["deadline_at"] == datetime(2026, 10, 2, 15, 30, tzinfo=timezone.utc)
    assert served["lot_count"] == 13
    assert served["is_defence"] is True, "the correction never reclassifies"

    assert remap_source.run("fr_boamp", write=True, epoch=3).examined == 0
    assert len(versions(conn, oid)) == 2


def test_boamp_lots_alone_are_written_without_a_version(conn, fs_store):
    record = strip_personal_data(BOAMP["single_lot_negotiated"])
    digest = land(conn, "fr_boamp", record["idweb"], record)
    stored = replace(from_boamp(record), lot_count=None, is_defence=True, sig_legal_basis=True)
    oid, _ = db.upsert_opportunity(conn, stored, digest, db.source_id(conn, "fr_boamp"))
    conn.commit()
    result = remap_source.run("fr_boamp", write=True, epoch=3)
    assert (result.versions, result.direct) == (0, 1)
    assert row(conn, oid)["lot_count"] == 1
    assert len(versions(conn, oid)) == 1


# -------------------------------------------------------------------- TED

def ted_notice(**fields) -> dict:
    return {"publication-number": "1-2026", "notice-title": "t", "buyer-name": "b",
            "notice-type": "cn-standard", "buyer-country": "POL",
            "publication-date": "2026-07-01+02:00", "official-language": "POL", **fields}


def test_a_stored_placeholder_amount_is_cleared_by_a_remapped_version(conn, fs_store):
    raw = ted_notice(**{"estimated-value-proc": "0.01", "estimated-value-cur-proc": "EUR"})
    digest = land(conn, "ted", "1-2026", raw)
    # as the old mapper stored it: the placeholder served as money
    old = replace(from_ted(raw), value_amount=0.01, value_currency="EUR", value_kind="estimated",
                  is_defence=True, sig_legal_basis=True)
    oid, _ = db.upsert_opportunity(conn, old, digest, db.source_id(conn, "ted"))
    conn.commit()
    assert float(row(conn, oid)["value_amount"]) == 0.01

    result = repair_ted.run("raw", write=True, epoch=3)
    assert (result.versions, result.failed) == (1, 0)
    got = versions(conn, oid)
    assert got[1]["kinds"] == ["remapped"]
    assert set(got[1]["changed_fields"]) >= {"value_amount", "value_currency"}
    served = row(conn, oid)
    assert served["value_amount"] is None and served["value_currency"] is None
    assert served["value_kind"] == "not_stated"
    # the archive keeps what TED stated
    assert got[0]["payload"]["value_amount"] == 0.01
    assert repair_ted.run("raw", write=True, epoch=3).examined == 0


# ----------------------------------------------------------------- PLACSP

def test_a_placsp_record_is_brought_up_from_its_own_stored_payload(conn, fs_store):
    stored = Opportunity(
        source_code="es_placsp", native_id="2026/ETSAE0905/1", buyer_name_raw="b",
        title_original="t", country="ES", status="awarded", status_native="RES",
        procedure_type="9", published_at=date(2026, 8, 4),
        deadline_at=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
        source_updated_at=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
        is_defence=True, sig_legal_basis=True)
    payload = db.opportunity_payload(stored)
    digest = land(conn, "es_placsp", stored.native_id, payload)
    oid, _ = db.upsert_opportunity(conn, stored, digest, db.source_id(conn, "es_placsp"))
    conn.commit()

    result = remap_source.run("es_placsp", write=True)
    assert (result.versions, result.failed) == (1, 0)
    got = versions(conn, oid)
    assert got[1]["kinds"] == ["remapped"]
    assert set(got[1]["changed_fields"]) == {"procedure_type", "published_at"}
    served = row(conn, oid)
    assert served["procedure_type"] == "Abierto simplificado"
    assert served["published_at"] is None
    assert got[0]["payload"]["published_at"] == "2026-08-04"      # the archive keeps it
    assert remap_source.run("es_placsp", write=True).examined == 0


def test_a_re_read_that_only_learns_the_lot_count_writes_it_without_a_version(conn):
    src = db.source_id(conn, "es_placsp")
    first = Opportunity(source_code="es_placsp", native_id="X-9", buyer_name_raw="b",
                        title_original="t", country="ES", status="open", status_native="PUB",
                        published_at=date(2026, 9, 1), is_defence=True, sig_legal_basis=True,
                        source_updated_at=datetime(2026, 9, 2, tzinfo=timezone.utc))
    oid, _ = db.upsert_opportunity(conn, first, "h1", src)
    again = replace(first, lot_count=3)
    same, action = db.upsert_opportunity(conn, again, "h2", src)
    conn.commit()
    assert (same, action) == (oid, "unchanged")
    assert row(conn, oid)["lot_count"] == 3
    assert len(versions(conn, oid)) == 1


# ------------------------------------------------------------------ Atlas

ATLAS_OLD = {
    "id": "2024/BZP 00605709", "source": "bzp", "notice_type": "TenderResultNotice",
    "title": "Dostawa srodkow czystosci", "buyer": "Lotnicza Akademia Wojskowa",
    "cpv_code": "39800000-0", "date": "2024-11-20", "estimated_value": None, "currency": "PLN",
    "organization_country": "PL", "submitting_offers_date": "2024-12-02 09:30:00",
}


def test_a_payload_landed_by_the_refresh_is_applied_with_latest_raw(conn, fs_store):
    """`atlas-pl --refresh-known` lands `tender_type` and `procedure_result` and writes no
    version. The current version's own payload lacks them, so a remap of it changes
    nothing (the 12 October runs wrote 0 changes); `--latest-raw` reads the new one."""
    old = strip_personal_data(ATLAS_OLD)
    src = db.source_id(conn, "pl_atlas")
    d_old = land(conn, "pl_atlas", old["id"], old)
    stored = replace(from_atlas_pl(old), is_defence=True, sig_cpv=True)
    assert stored.status == "awarded"
    oid, _ = db.upsert_opportunity(conn, stored, d_old, src)
    refreshed = {**old, "tender_type": "1.1.1",
                 "procedure_result": "uniewaznienie;nieRozstrzygnieto;nieRozstrzygnieto"}
    d_new = land(conn, "pl_atlas", old["id"], refreshed)
    conn.commit()

    assert remap_source.run("pl_atlas", write=False, epoch=3).versions == 0, \
        "the payload of the current version cannot say what the refresh landed"

    result = remap_source.run("pl_atlas", write=True, epoch=3, latest_raw=True)
    assert (result.versions, result.failed) == (1, 0)
    got = versions(conn, oid)
    assert got[1]["kinds"] == ["remapped"] and got[1]["raw_hash"] == d_new
    assert {"status", "procedure_type"} <= set(got[1]["changed_fields"])
    served = row(conn, oid)
    assert served["status"] == "cancelled"        # was `closed` until DC6 (14 October 2026)
    assert served["procedure_type"] == "Basic procedure (art. 275 pt 1)"
    assert remap_source.run("pl_atlas", write=True, epoch=3, latest_raw=True).examined == 0


# --------------------------------------------------------------- TenderNed

def test_a_european_notice_gets_its_ted_number_when_it_is_read_again(conn, fs_store, monkeypatch):
    """443697 was read on the day it was published, before TED numbered it, and never again
    (fields:D18): its twin 701268-2026 was served as a second tender."""
    from datetime import timedelta

    from dgate import pipeline
    from dgate.sources import tenderned
    from tests.integration.test_tenderned_pipeline import DIRECTIVE, _record

    published = (date.today() - timedelta(days=5)).isoformat()
    record = {**_record("443697", form=DIRECTIVE), "publicatieDatum": published}
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter([record]))
    pipeline.run_tenderned(days=2, reread=True)
    first = conn.execute("SELECT id, ted_ref, legal_basis FROM opportunity").fetchone()
    assert first["ted_ref"] is None and first["legal_basis"] is not None

    stated = {**record["detail"], "pbNummerTed": "701268-2026"}
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter([]))
    monkeypatch.setattr(tenderned, "fetch_detail", lambda pid, client=None: stated)
    pipeline.run_tenderned(days=2, reread=True)

    row_ = row(conn, first["id"])
    assert row_["ted_ref"] == "701268-2026"
    assert len(versions(conn, first["id"])) == 1, "a link is not an amendment"

    # linked now: tonight it is not asked for again
    calls: list[str] = []
    monkeypatch.setattr(tenderned, "fetch_detail",
                        lambda pid, client=None: calls.append(pid) or stated)
    pipeline.run_tenderned(days=2, reread=True)
    assert calls == []


def test_a_notice_outside_the_window_or_without_a_directive_is_not_read_again(
        conn, fs_store, monkeypatch):
    from datetime import timedelta

    from dgate import pipeline
    from dgate.sources import tenderned
    from tests.integration.test_tenderned_pipeline import DIRECTIVE, _record

    old = {**_record("1", form=DIRECTIVE),
           "publicatieDatum": (date.today() - timedelta(days=40)).isoformat()}
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter([old]))
    pipeline.run_tenderned(days=2, reread=True)
    calls: list[str] = []
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter([]))
    monkeypatch.setattr(tenderned, "fetch_detail",
                        lambda pid, client=None: calls.append(pid) or {})
    pipeline.run_tenderned(days=2, reread=True)
    assert calls == []


# ------------------------------------------------------ Polish update notices

def test_an_update_notice_is_linked_to_the_notice_whose_mo_identifier_it_names(conn, fs_store):
    """fields:D15. The board names the parent only by `moIdentifier`; no column holds it."""
    from dgate.normalise import from_ezamowienia
    from dgate.ops import link_ezam_updates

    def board(number: str, kind: str, mo: str, base: str | None = None) -> dict:
        return {"bzpNumber": f"2026/BZP {number}", "noticeNumber": f"2026/BZP {number}/01",
                "noticeType": kind, "moIdentifier": mo, "baseNoticeMOIdentifier": base,
                "objectId": f"obj-{number}", "orderObject": "Dostawa", "cpvCode": "35000000-4",
                "organizationName": "Jednostka Wojskowa", "publicationDate": "2026-09-01T10:00:00Z",
                "tenderType": "1.1.1"}

    src = db.source_id(conn, "pl_ezam")
    ids = {}
    for payload in (board("00000001", "ContractNotice", "mo-parent"),
                    board("00000002", "NoticeUpdateNotice", "mo-update", "mo-parent"),
                    board("00000003", "NoticeUpdateNotice", "mo-orphan", "mo-not-stored")):
        digest = land(conn, "pl_ezam", payload["bzpNumber"], payload)
        opp = replace(from_ezamowienia(payload), is_defence=True, sig_cpv=True)
        ids[payload["bzpNumber"]], _ = db.upsert_opportunity(conn, opp, digest, src)
    conn.commit()

    dry = link_ezam_updates.run(write=False)
    assert (dry.naming_a_parent, dry.linked, dry.parent_not_stored) == (2, 1, 1)
    assert row(conn, ids["2026/BZP 00000002"])["related_native_id"] is None

    link_ezam_updates.run(write=True)
    assert row(conn, ids["2026/BZP 00000002"])["related_native_id"] == "2026/BZP 00000001"
    assert row(conn, ids["2026/BZP 00000003"])["related_native_id"] is None
    assert row(conn, ids["2026/BZP 00000001"])["related_native_id"] is None
    assert len(versions(conn, ids["2026/BZP 00000002"])) == 1, "a link is not an amendment"
    assert link_ezam_updates.run(write=True).linked == 0
