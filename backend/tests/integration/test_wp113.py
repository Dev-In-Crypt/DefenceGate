"""WP-113 against a real Postgres: the re-derive ops module brings stored rows in line with the corrected mappings
through the archive path (a new version marked as a correction, the old one closed and otherwise untouched, an attribute
updated in place, nothing on a second run), the calls' who-may-apply and EU closing time, the PLACSP control that counts
a procedure's later TED publications as linked and an award entry's own date as a date, and the German documents link."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db
from dgate.normalise import (
    Call,
    Opportunity,
    from_boamp,
    from_de_bkms,
    from_tenderned,
    strip_personal_data,
)
from dgate.ops import controls, wp113_rederive
from dgate.rawstore import build_store, storage_key
from dgate.sources import eu_portal
from dgate.sources.ted import content_hash
from tests.unit.test_wp113 import _bkms, _fns, _nl

pytestmark = pytest.mark.integration
UTC = timezone.utc


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield
    config.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def land(conn, source: str, raw: dict, first: Opportunity) -> int:
    """The payload in the raw store and the row as the mapper before WP-113 read it."""
    digest = content_hash(raw)
    src = db.source_id(conn, source)
    key = build_store().put(storage_key(source, first.native_id, content_hash=digest), raw)
    db.record_raw(conn, src, first.native_id, digest, key)
    oid, _ = db.upsert_opportunity(conn, first, digest, src)
    conn.commit()
    return oid


def versions(conn, oid: int):
    return conn.execute("""SELECT v.version, v.changed_fields, v.valid_to IS NOT NULL AS closed, v.payload->>'deadline_at' AS d,
                                  n.kind FROM opportunity_version v
                             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
                            WHERE v.opportunity_id = %s ORDER BY v.version""", (oid,)).fetchall()


def test_the_rederive_corrects_tenderned_and_boamp_through_the_archive(conn, fs_store):
    conn.execute("DELETE FROM remap_marker")
    conn.commit()
    nl_raw = strip_personal_data(_nl({"sluitingsDatum": "2026-11-16T12:00:00", "cpvCodes": [
        {"code": "34900000-6", "isHoofdOpdracht": False}, {"code": "42400000-0", "isHoofdOpdracht": True}]}))
    nl_new = from_tenderned(nl_raw)
    nl = land(conn, "nl_tenderned", nl_raw, replace(nl_new, deadline_at=datetime(2026, 8, 19, 10, tzinfo=UTC),
                                                    cpv_codes=["34900000", "42400000"]))
    fr_raw = strip_personal_data(_fns("2026-10-29T16:00:00", column="2026-10-29T16:00:00+00:00"))
    fr = land(conn, "fr_boamp", fr_raw, replace(from_boamp(fr_raw), deadline_at=datetime(2026, 10, 29, 16, tzinfo=UTC)))
    first_payload = conn.execute("SELECT payload FROM opportunity_version WHERE opportunity_id = %s", (nl,)).fetchone()["payload"]

    report = wp113_rederive.run(write=False, sources=("nl_tenderned", "fr_boamp"), calls=False)
    # the order of the codes is reported too; written with the version (the serving row follows the candidate)
    assert "versions 1" in report[0] and "deadline_at 1" in report[0] and "cpv_codes (attribute) 1" in report[0]
    assert "versions 1" in report[1] and "deadline_at 1" in report[1]
    assert [r["version"] for r in versions(conn, nl)] == [1]                 # the report wrote nothing

    wp113_rederive.run(write=True, sources=("nl_tenderned", "fr_boamp"), calls=False)
    row = conn.execute("SELECT deadline_at, cpv_codes FROM opportunity WHERE id = %s", (nl,)).fetchone()
    assert row["deadline_at"] == datetime(2026, 11, 16, 11, tzinfo=UTC)
    assert row["cpv_codes"][0] == "42400000"                                  # the flagged main code first
    got = versions(conn, nl)
    assert [(v["version"], v["changed_fields"], v["closed"], v["kind"]) for v in got] == [
        (1, [], True, None), (2, ["deadline_at"], False, "remapped")]
    # the first version is closed and otherwise as it was
    assert conn.execute("SELECT payload FROM opportunity_version WHERE opportunity_id = %s AND version = 1",
                        (nl,)).fetchone()["payload"] == first_payload
    assert conn.execute("SELECT deadline_at FROM opportunity WHERE id = %s", (fr,)).fetchone()["deadline_at"] == \
        datetime(2026, 10, 29, 15, tzinfo=UTC)
    again = wp113_rederive.run(write=True, sources=("nl_tenderned", "fr_boamp"), calls=False)
    assert all("examined 0" in line for line in again)


def test_the_cpv_order_alone_is_an_attribute_update(conn, fs_store):
    conn.execute("DELETE FROM remap_marker")
    conn.commit()
    raw = strip_personal_data(_nl({"cpvCodes": [{"code": "34900000-6", "isHoofdOpdracht": False},
                                                {"code": "42400000-0", "isHoofdOpdracht": True}]}))
    oid = land(conn, "nl_tenderned", raw, replace(from_tenderned(raw), cpv_codes=["34900000", "42400000"]))
    report = wp113_rederive.run(write=True, sources=("nl_tenderned",), calls=False)
    assert "versions 0" in report[0] and "attribute-only 1" in report[0] and "cpv_codes (attribute) 1" in report[0]
    assert conn.execute("SELECT cpv_codes, current_version FROM opportunity WHERE id = %s", (oid,)).fetchone() == {
        "cpv_codes": ["42400000", "34900000"], "current_version": 1}


def test_placsp_code_7_is_named_and_only_its_rows_are_read(conn, fs_store):
    conn.execute("DELETE FROM remap_marker")
    conn.commit()
    ids = {}
    for native, code in (("E-7", "7"), ("E-1", "Abierto")):
        opp = Opportunity(source_code="es_placsp", native_id=native, buyer_name_raw="Armada", country="ES", title_original="x",
                          procedure_type=code, cpv_codes=["35511000"], status="awarded", published_at=date(2026, 9, 1))
        ids[native] = land(conn, "es_placsp", db.opportunity_payload(opp), opp)
    report = wp113_rederive.run(write=True, sources=("es_placsp",), calls=False)
    assert "examined 1, versions 1" in report[0] and "procedure_type 1" in report[0]
    assert conn.execute("SELECT procedure_type FROM opportunity WHERE id = %s", (ids["E-7"],)).fetchone()["procedure_type"] == \
        "Derivado de acuerdo marco"


@pytest.fixture
def bkms_active(conn):
    """The German source served, as on production; `source` is not truncated, so it is put back as the migration seeds it."""
    conn.execute("UPDATE source SET active = TRUE WHERE code = 'de_bkms'")
    conn.commit()
    yield
    conn.rollback()
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'de_bkms'")
    conn.commit()


def test_the_german_notice_links_its_page_and_serves_the_documents(conn, fs_store, bkms_active, client):
    conn.execute("DELETE FROM remap_marker")
    conn.commit()
    raw = _bkms("https://www.evergabe-online.de/tenderdetails.html?id=543128")
    new = from_de_bkms(raw)
    oid = land(conn, "de_bkms", raw, replace(new, source_url="https://www.evergabe-online.de/tenderdetails.html?id=543128",
                                             documents_url=None, is_defence=True, sig_legal_basis=True))
    wp113_rederive.run(write=True, sources=("de_bkms",), calls=False)
    response = client.get(f"/v1/tenders/{oid}")
    assert response.status_code == 200, response.text
    got = response.json()
    assert got["source"]["url"].startswith("https://oeffentlichevergabe.de/ui/de/search/details?noticeId=")
    assert got["documentsUrl"] == "https://www.evergabe-online.de/tenderdetails.html?id=543128"


def test_calls_who_may_apply_and_the_document_closing_time(conn):
    vinnova = Call(programme_code="VINNOVA", native_id="2026-01502", title="Civil-military 2027",
                   eligibility_text="The call for proposals is aimed at Swedish small and medium-sized enterprises (SMEs).",
                   conditions_raw={"web_text_sv": []})
    db.upsert_call(conn, vinnova, "h-v", db.source_id(conn, "se_vinnova"))
    url = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/digital/wp-call/2026/call-fiche_x_en.pdf"
    eu = Call(programme_code="DIGITAL", native_id="9001", title="AI data", topic_code="DIGITAL-2026-AI-DATA-10",
              deadline_at=datetime(2026, 10, 1, 21, 59, 59, tzinfo=UTC), deadline_precision="date",
              conditions_raw={"documents": [{"url": url, "label": "Call document"}]})
    cid = db.upsert_call(conn, eu, "h-eu", db.source_id(conn, "eu_portal"))[0]
    conn.execute("INSERT INTO call_document_text (url, sha256, pages, chars, text) VALUES (%s, 'x', 1, 1, %s)",
                 (url, "Deadline for submission: 1 October 2026– 17:00:00 CEST\n"))
    conn.commit()

    lines = wp113_rederive.run(write=False, sources=())
    assert "'time_from_document': 1" in lines[1]
    wp113_rederive.run(write=True, sources=())
    row = conn.execute("SELECT who_may_apply_doc, sme_only FROM call WHERE native_id = '2026-01502'").fetchone()
    assert (row["who_may_apply_doc"], row["sme_only"]) == ("companies", True)
    assert conn.execute("SELECT deadline_at, deadline_precision FROM call WHERE id = %s", (cid,)).fetchone() == {
        "deadline_at": datetime(2026, 10, 1, 15, tzinfo=UTC), "deadline_precision": None}
    # the nightly run keeps it: the portal's date-only record is given the document's time again
    db.upsert_call(conn, eu_portal.with_document_time(conn, replace(eu)), "h-eu", db.source_id(conn, "eu_portal"))
    assert conn.execute("SELECT deadline_at FROM call WHERE id = %s", (cid,)).fetchone()["deadline_at"] == \
        datetime(2026, 10, 1, 15, tzinfo=UTC)


def test_the_placsp_control_counts_procedure_twins_and_entry_dates(conn):
    ted = db.source_id(conn, "ted")
    placsp = db.source_id(conn, "es_placsp")
    published = date.today() - timedelta(days=40)
    for native in ("100-2026", "200-2026"):          # the call notice and the award notice of one procedure
        oid, _ = db.upsert_opportunity(conn, Opportunity(
            source_code="ted", native_id=native, buyer_name_raw="Armada", country="ES", title_original="x",
            published_at=published, cpv_codes=["35511000"], status="open", is_defence=True, sig_legal_basis=True), f"h{native}", ted)
        conn.execute("UPDATE opportunity SET procedure_identifier = 'p-1' WHERE id = %s", (oid,))
    oid, _ = db.upsert_opportunity(conn, Opportunity(
        source_code="es_placsp", native_id="E-1", buyer_name_raw="Armada", country="ES", title_original="x",
        cpv_codes=["35511000"], status="awarded", ted_ref="100-2026", notice_date=published, notice_kind="award",
        is_defence=True, sig_cpv=True), "hp", placsp)
    conn.execute("UPDATE opportunity SET procedure_identifier = 'p-1' WHERE id = %s", (oid,))
    conn.commit()
    got = controls.check_placsp(conn, now=datetime.now(UTC))
    assert got["detail"]["ted_es_unlinked_14d"] == 0
    assert got["detail"]["placsp_null_date_rows"] == 0 and got["status"] == "ok"
