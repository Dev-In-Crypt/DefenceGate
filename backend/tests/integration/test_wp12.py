"""WP-12 against a real Postgres: the PLACSP notice date (carried, stored, served, remapped)
and the French buyer vocabulary on the BOAMP path."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline, reprocess
from dgate.normalise import Opportunity
from dgate.ops import remap_source
from dgate.rawstore import build_store, storage_key
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration

FUTURE = datetime.now(timezone.utc) + timedelta(days=30)


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


@pytest.fixture(autouse=True)
def clean_markers(conn):
    conn.execute("DELETE FROM remap_marker")
    conn.commit()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def land(conn, source: str, native_id: str, payload: dict) -> str:
    digest = content_hash(payload)
    key = build_store().put(storage_key(source, native_id, content_hash=digest), payload)
    db.record_raw(conn, db.source_id(conn, source), native_id, digest, key)
    return digest


def row(conn, oid: int) -> dict:
    return conn.execute("SELECT * FROM opportunity WHERE id = %s", (oid,)).fetchone()


def versions(conn, oid: int) -> list[dict]:
    return conn.execute(
        """SELECT v.version, v.changed_fields,
                  array_remove(array_agg(n.kind), NULL) AS kinds
             FROM opportunity_version v
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s GROUP BY v.id ORDER BY v.version""", (oid,)).fetchall()


def call(**kw) -> Opportunity:
    base = dict(source_code="es_placsp", native_id="2026/EA27/1", buyer_name_raw="Junta de Compras",
                title_original="Suministro", country="ES", status="open", status_native="PUB",
                published_at=date(2026, 7, 28),
                deadline_at=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
                source_updated_at=datetime(2026, 7, 28, 13, 12, tzinfo=timezone.utc),
                notice_date=date(2026, 7, 28), notice_kind="call",
                is_defence=True, sig_legal_basis=True)
    base.update(kw)
    return Opportunity(**base)


# ------------------------------------------------------------- the ingest path

def test_a_later_award_entry_keeps_the_call_date_and_states_its_own(conn):
    src = db.source_id(conn, "es_placsp")
    oid, _ = db.upsert_opportunity(conn, call(), "h1", src)
    award = call(published_at=None, status="awarded", status_native="ADJ",
                 source_updated_at=datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc),
                 notice_date=date(2026, 9, 12), notice_kind="award")
    same, action = db.upsert_opportunity(conn, award, "h2", src)
    conn.commit()
    assert (same, action) == (oid, "changed")
    served = row(conn, oid)
    assert served["published_at"] == date(2026, 7, 28)        # the call's date is not lost
    assert (served["notice_date"], served["notice_kind"]) == (date(2026, 9, 12), "award")
    v2 = versions(conn, oid)[1]
    assert v2["changed_fields"] == ["status"]


def test_an_award_only_folder_has_no_publication_date_and_a_labelled_notice_date(conn):
    src = db.source_id(conn, "es_placsp")
    award = call(native_id="2025/AWARD/1", published_at=None, status="awarded",
                 status_native="RES", notice_date=date(2026, 9, 12), notice_kind="award",
                 source_updated_at=datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc))
    oid, _ = db.upsert_opportunity(conn, award, "h1", src)
    conn.commit()
    served = row(conn, oid)
    assert served["published_at"] is None
    assert (served["notice_date"], served["notice_kind"]) == (date(2026, 9, 12), "award")


def test_a_published_date_after_the_deadline_is_not_carried(conn):
    src = db.source_id(conn, "es_placsp")
    oid, _ = db.upsert_opportunity(
        conn, call(published_at=date(2026, 9, 20)), "h1", src)
    later = call(published_at=None, status="awarded", status_native="ADJ",
                 source_updated_at=datetime(2026, 9, 22, tzinfo=timezone.utc))
    db.upsert_opportunity(conn, later, "h2", src)
    conn.commit()
    assert row(conn, oid)["published_at"] is None


def test_the_notice_date_follows_a_newer_entry_without_a_version(conn):
    src = db.source_id(conn, "es_placsp")
    oid, _ = db.upsert_opportunity(conn, call(), "h1", src)
    newer = replace(call(), notice_date=date(2026, 8, 2), notice_kind="update",
                    source_updated_at=datetime(2026, 8, 2, 9, 0, tzinfo=timezone.utc))
    same, action = db.upsert_opportunity(conn, newer, "h2", src)
    conn.commit()
    assert (same, action) == (oid, "unchanged")
    assert (row(conn, oid)["notice_date"], row(conn, oid)["notice_kind"]) == (
        date(2026, 8, 2), "update")
    older = replace(call(), notice_date=date(2026, 7, 1), notice_kind="prior",
                    source_updated_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    # an entry older than the held one is history arriving late: not the current notice
    db.upsert_opportunity(conn, older, "h3", src)
    conn.commit()
    assert row(conn, oid)["notice_date"] == date(2026, 8, 2)


# ------------------------------------------------------------------ the API

def test_the_tender_states_its_notice_and_sorts_by_it(client, conn):
    src = db.source_id(conn, "es_placsp")
    for nid, pub, nd, kind in (
            ("ES-A", date(2026, 9, 1), date(2026, 9, 1), "call"),
            ("ES-B", None, date(2026, 9, 12), "award"),
            ("ES-C", None, None, None)):
        opp = call(native_id=nid, published_at=pub, notice_date=nd, notice_kind=kind,
                   deadline_at=FUTURE, status="open", status_native="PUB")
        opp.buyer_org_id = db.resolve_organisation(conn, opp.buyer_name_raw, "ES", src_id=src)
        db.upsert_opportunity(conn, opp, f"hash-{nid}", src)
    conn.commit()
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all",
                                             "sort": "published-desc"}).json()
    by = {t["noticeId"]: t for t in body["items"]}
    assert [t["noticeId"] for t in body["items"]] == ["ES-B", "ES-A", "ES-C"]
    b = by["ES-B"]
    assert (b["publishedKnown"], b["publishedAt"]) == (False, None)
    assert b["noticeKind"] == "award" and b["noticeDate"].startswith("2026-09-12")
    assert by["ES-A"]["noticeKind"] == "call" and by["ES-A"]["publishedKnown"] is True
    assert by["ES-C"]["noticeDate"] is None and by["ES-C"]["noticeKind"] is None


# --------------------------------------------------- remap tool, epoch 2

def _fold_lost_call_date(conn, fs_store):
    """A folder as the first mappers left it: the call (v1, published 28 July), then a
    cancellation entry whose version dropped the date."""
    src = db.source_id(conn, "es_placsp")
    first = call()
    d1 = land(conn, "es_placsp", first.native_id, db.opportunity_payload(first))
    oid, _ = db.upsert_opportunity(conn, first, d1, src)
    lost = replace(first, published_at=None, status="cancelled", status_native="ANUL",
                   notice_date=None, notice_kind=None,
                   source_updated_at=datetime(2026, 7, 29, 7, 52, tzinfo=timezone(timedelta(hours=2))))
    d2 = land(conn, "es_placsp", first.native_id, db.opportunity_payload(lost))
    db.append_version(conn, oid, lost, d2, ["published_at", "status"], after=1)
    conn.commit()
    return oid


def test_epoch_2_restores_the_call_date_and_dates_the_notice(conn, fs_store):
    oid = _fold_lost_call_date(conn, fs_store)
    assert row(conn, oid)["published_at"] is None

    dry = remap_source.run("es_placsp", write=False, epoch=2)
    assert dry.versions == 1 and row(conn, oid)["published_at"] is None

    first = remap_source.run("es_placsp", write=True, epoch=2)
    assert (first.versions, first.failed) == (1, 0)
    served = row(conn, oid)
    assert served["published_at"] == date(2026, 7, 28)
    assert (served["notice_date"], served["notice_kind"]) == (date(2026, 7, 29), "cancellation")
    got = versions(conn, oid)
    assert [v["version"] for v in got] == [1, 2, 3]
    assert got[2]["changed_fields"] == ["published_at"] and got[2]["kinds"] == ["remapped"]
    assert remap_source.run("es_placsp", write=True, epoch=2).examined == 0


def test_epoch_2_dates_an_award_only_folder_without_inventing_a_publication(conn, fs_store):
    src = db.source_id(conn, "es_placsp")
    award = call(native_id="2025/AWARD/9", published_at=None, status="awarded",
                 status_native="RES", notice_date=None, notice_kind=None,
                 source_updated_at=datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc))
    digest = land(conn, "es_placsp", award.native_id, db.opportunity_payload(award))
    oid, _ = db.upsert_opportunity(conn, award, digest, src)
    conn.commit()
    assert row(conn, oid)["notice_date"] is None

    result = remap_source.run("es_placsp", write=True, epoch=2)
    assert (result.versions, result.failed) == (0, 0)         # an attribute: no version
    served = row(conn, oid)
    assert served["published_at"] is None
    assert (served["notice_date"], served["notice_kind"]) == (date(2026, 9, 12), "award")
    assert len(versions(conn, oid)) == 1


def test_epoch_2_does_not_restore_a_date_that_is_after_the_deadline(conn, fs_store):
    src = db.source_id(conn, "es_placsp")
    first = call(published_at=date(2026, 9, 20))             # after its 30 Aug deadline
    d1 = land(conn, "es_placsp", first.native_id, db.opportunity_payload(first))
    oid, _ = db.upsert_opportunity(conn, first, d1, src)
    lost = replace(first, published_at=None, status="awarded", status_native="ADJ")
    d2 = land(conn, "es_placsp", first.native_id, db.opportunity_payload(lost))
    db.append_version(conn, oid, lost, d2, ["published_at", "status"], after=1)
    conn.commit()
    remap_source.run("es_placsp", write=True, epoch=2)
    assert row(conn, oid)["published_at"] is None


# ------------------------------------------------------- the BOAMP vocabulary

def _boamp(idweb: str, buyer: str, cpv: str = "45000000") -> dict:
    return {
        "idweb": idweb, "objet": f"Marche {idweb}", "nomacheteur": buyer,
        "dateparution": "2026-09-21", "datelimitereponse": "2026-10-30T12:00:00+00:00",
        "perimetre": "FNSimple", "nature": "APPEL_OFFRE", "famille": "FNS",
        "donnees": json.dumps({"FNSimple": {"initial": {"natureMarche": {
            "codeCPV": {"objetPrincipal": {"classPrincipale": cpv}}}}}}),
    }


def test_a_body_the_name_rules_name_is_flagged_when_its_notice_arrives(conn):
    """The seeds list names that were seen; a new spelling of a Ministry service must not
    wait for the next seed run (coverage:X1)."""
    from dgate.normalise import from_boamp

    src = db.source_id(conn, "fr_boamp")
    opp = from_boamp(_boamp("26-91277", "SID Sud-Est"))
    opp = pipeline._finalise(conn, opp, src)
    assert opp.sig_buyer and opp.is_defence and opp.buyer_class == "defence"
    org = conn.execute("SELECT is_defence_buyer, defence_buyer_source, defence_buyer_reason "
                       "FROM organisation WHERE id = %s", (opp.buyer_org_id,)).fetchone()
    assert org["is_defence_buyer"] and org["defence_buyer_source"] == "derived_rule"
    assert org["defence_buyer_reason"] == "defence_infrastructure_service"


def test_a_municipality_or_a_hospital_is_not_flagged_by_the_name_rules(conn):
    from dgate.normalise import from_boamp

    src = db.source_id(conn, "fr_boamp")
    names = ("Commune de Ghisonaccia", "Hôpital d'instruction des armées Percy",
             "Gendarmerie nationale - Commandement de la Guyane")
    for i, name in enumerate(names):
        opp = pipeline._finalise(conn, from_boamp(_boamp(f"26-{i}", name)), src)
        assert not opp.sig_buyer, name
        assert not db.is_defence_buyer(conn, opp.buyer_org_id), name


def test_a_landed_notice_of_a_new_spelling_is_recovered_by_requalify(conn, fs_store):
    """The coverage report's example: a SID notice landed, not stored, qualifies now."""
    payload = _boamp("26-91277", "SID Sud-Est")
    src = db.source_id(conn, "fr_boamp")
    key = build_store().put(storage_key("fr_boamp", "26-91277", when=date(2026, 9, 21),
                                        content_hash=content_hash(payload)), payload)
    db.record_raw(conn, src, "26-91277", content_hash(payload), key)
    conn.commit()
    counts = reprocess.requalify_source(conn, build_store(), "fr_boamp",
                                        since=date(2026, 9, 21), until=date(2026, 9, 21),
                                        dry_run=False)
    assert counts["candidates"] == 1 and counts["inserted"] == 1 and counts["by_buyer"] == 1
    held = conn.execute("SELECT is_defence, sig_buyer, buyer_class FROM opportunity "
                        "WHERE native_id = '26-91277'").fetchone()
    assert held["is_defence"] and held["sig_buyer"]
