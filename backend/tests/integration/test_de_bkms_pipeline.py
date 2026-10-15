"""The German notice service against a real Postgres.

What this checks is the path the unit tests cannot: a source that is seeded inactive is
collected only on `--force`, what it lands never reaches a public read until the owner
switches it on (and goes away again when it is switched off), the count check turns a bad
day into `partial`, an amendment is a version, and the TED twin is linked.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline, stats, worker
from dgate.normalise import Opportunity
from dgate.ops import link_twins, suppress
from dgate.rawstore import build_store
from dgate.sources import de_bkms

pytestmark = pytest.mark.integration

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "de_bkms"
NOTICE = "129f4d26-440e-4017-91b5-df3a10cf3f30"
PROCEDURE = "d8e98b07-ad6e-4f35-92c6-0760efbc6039"
TODAY = date(2026, 10, 15)


def _xml(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _rec(name: str, notice: str, version: str = "01", xml: str | None = None) -> dict:
    return {"file": f"{notice}-{version}.xml", "notice_id": notice, "version": version,
            "xml": xml if xml is not None else _xml(name)}


class FakeDay:
    def __init__(self, records, entries=None):
        self._records = records
        self.entries = len(records) if entries is None else entries

    def records(self):
        return iter(self._records)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


@pytest.fixture(autouse=True)
def _env(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setattr(de_bkms, "REQUEST_PAUSE", 0)
    monkeypatch.setenv("DGATE_FLOOR_DE_BKMS", "0")      # the fixtures are two files, not 700
    config.reset_cache()
    stats.reset_cache()
    # `source` is not truncated between tests: put it back as the migration seeds it.
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'de_bkms'")
    conn.commit()
    yield
    conn.rollback()
    conn.execute("UPDATE source SET active = FALSE WHERE code = 'de_bkms'")
    conn.commit()
    config.reset_cache()
    stats.reset_cache()


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c


def _feed(monkeypatch, days: dict[date, list[dict] | FakeDay]):
    def open_day(day, *, client, attempts=4):
        got = days.get(day)
        if got is None:
            return None
        return got if isinstance(got, FakeDay) else FakeDay(got)

    monkeypatch.setattr(de_bkms, "open_day", open_day)


def _run(monkeypatch, records, *, force=True, days=0, today=TODAY):
    _feed(monkeypatch, {today: records})
    pipeline.run_de_bkms(days=days, force=force, today=today)


def _runs(conn):
    return conn.execute(
        "SELECT r.status, r.error_message, r.records_fetched FROM ingest_run r "
        "JOIN source s ON s.id = r.source_id WHERE s.code = 'de_bkms' ORDER BY r.id").fetchall()


def _served(client) -> list[str]:
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all"}).json()
    return [t["noticeId"] for t in body["items"]]


DEFENCE = [_rec("cn_standard_defence.xml", NOTICE),
           _rec("legacy_national.xml", "25920552", "1")]


# ------------------------------------------------------------- the licence gate

def test_the_source_is_seeded_inactive_and_without_a_licence_answer(conn):
    row = conn.execute("SELECT active, commercial_ok, kind, country, history_from "
                       "FROM source WHERE code = 'de_bkms'").fetchone()
    assert row["active"] is False and row["commercial_ok"] is None
    assert (row["kind"], row["country"], row["history_from"]) == ("tender", "DE", date(2023, 10, 25))


def test_the_scheduled_job_and_the_run_do_nothing_while_inactive(conn, monkeypatch):
    _feed(monkeypatch, {TODAY: DEFENCE})
    pipeline.run_de_bkms(days=0, today=TODAY)                  # not forced
    result = worker.job_de_bkms()
    assert result.status == "success" and "inactive" in result.detail
    assert _runs(conn) == []
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 0


def test_a_forced_run_lands_data_but_no_public_read_serves_it(client, conn, monkeypatch):
    _run(monkeypatch, DEFENCE)
    assert [r["status"] for r in _runs(conn)] == ["success"]
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 2
    row = conn.execute(
        "SELECT id, native_id, is_defence, suppressed FROM opportunity").fetchone()
    assert (row["native_id"], row["is_defence"], row["suppressed"]) == (NOTICE, True, True)

    assert _served(client) == []
    assert client.get("/v1/opportunities", params={"scope": "all"}).json() == []
    assert client.get(f"/v1/opportunities/{row['id']}").status_code == 410
    assert client.get(f"/v1/tenders/{row['id']}/versions").status_code == 410
    health = client.get("/v1/health").json()
    assert "de_bkms" not in json.dumps(health)
    # the archive keeps the observation
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1


def test_switching_the_source_on_serves_it_and_off_withholds_it_again(client, conn, monkeypatch):
    _run(monkeypatch, DEFENCE)
    oid = conn.execute("SELECT id FROM opportunity").fetchone()["id"]
    assert _served(client) == []

    conn.execute("UPDATE source SET active = TRUE WHERE code = 'de_bkms'")
    conn.commit()
    assert _served(client) == [NOTICE]
    assert client.get(f"/v1/tenders/{oid}").status_code == 200

    conn.execute("UPDATE source SET active = FALSE WHERE code = 'de_bkms'")
    conn.commit()
    assert _served(client) == []


def test_lifting_a_takedown_does_not_release_a_row_of_an_inactive_source(client, conn,
                                                                         monkeypatch):
    _run(monkeypatch, DEFENCE)
    entry = suppress.add(conn, kind="notice", source="de_bkms", native_id=NOTICE,
                         organisation=None, reason="personal_data",
                         requested_at=datetime.now(timezone.utc), decided_by="Owner", note="")
    conn.commit()
    assert suppress.lift(conn, entry, by="Owner", note="mistaken")
    conn.commit()
    assert conn.execute("SELECT suppressed FROM opportunity").fetchone()["suppressed"] is True
    assert _served(client) == []


def test_other_sources_are_not_held_back(client, conn):
    opp = Opportunity(source_code="ted", native_id="1-2026", buyer_name_raw="Ministry of Defence",
                      title_original="Armoured vehicles", country="FR", status="open",
                      published_at=TODAY, cpv_codes=["35400000"], is_defence=True, sig_cpv=True,
                      sig_cpv_military=True, buyer_class="defence")
    src = db.source_id(conn, "ted")
    db.upsert_opportunity(conn, opp, "h", src)
    conn.commit()
    assert _served(client) == ["1-2026"]


# ---------------------------------------------------------- landing and history

def test_the_landed_payload_carries_no_contact_and_unchanged_reruns_add_nothing(
        conn, monkeypatch):
    _run(monkeypatch, DEFENCE)
    keys = [r["storage_key"] for r in conn.execute("SELECT storage_key FROM raw_ingest")]
    landed = json.dumps([build_store().get(k) for k in keys], ensure_ascii=False)
    for gone in ("Erika Mustermann", "example.invalid", "+49 261"):
        assert gone not in landed
    _run(monkeypatch, DEFENCE)
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1
    assert [r["status"] for r in _runs(conn)] == ["success", "success"]


def test_an_amendment_is_a_new_version_of_the_same_notice(conn, monkeypatch):
    _run(monkeypatch, [_rec("cn_standard_defence.xml", NOTICE)])
    amended = _xml("cn_standard_defence.xml").replace(
        "2026-10-26+01:00", "2026-11-02+01:00").replace("<cbc:VersionID>01<", "<cbc:VersionID>02<")
    _run(monkeypatch, [_rec("", NOTICE, "02", xml=amended)])
    assert [r["native_id"] for r in conn.execute("SELECT native_id FROM opportunity")] == [NOTICE]
    versions = conn.execute(
        "SELECT version, changed_fields, payload->>'notice_version' AS notice_version "
        "FROM opportunity_version ORDER BY version").fetchall()
    assert [v["version"] for v in versions] == [1, 2]
    assert [v["notice_version"] for v in versions] == ["1", "2"]
    assert "deadline_at" in versions[1]["changed_fields"]


def test_a_history_load_needs_force_while_inactive_and_starts_at_the_eforms_date(
        conn, monkeypatch):
    monkeypatch.setattr(de_bkms, "fetch_day", lambda day, client=None: iter(DEFENCE))
    with pytest.raises(RuntimeError, match="inactive"):
        pipeline.run_history("de_bkms", date(2026, 10, 12), date(2026, 10, 13))
    with pytest.raises(ValueError, match="not eForms"):
        pipeline.run_history("de_bkms", date(2023, 10, 24), date(2023, 10, 25), force=True)
    assert pipeline.run_history("de_bkms", date(2026, 10, 12), date(2026, 10, 13),
                                force=True) == 2
    assert conn.execute("SELECT count(*) n FROM backfill_day").fetchone()["n"] == 2
    # resumable: the second command finds both days done
    assert pipeline.run_history("de_bkms", date(2026, 10, 12), date(2026, 10, 13),
                                force=True) == 0


# ------------------------------------------------------------------ count check

def test_an_unreadable_file_is_landed_counted_and_makes_the_run_partial(conn, monkeypatch):
    bad = {"file": "9-1.xml", "notice_id": "9", "version": "1", "unreadable": "too large"}
    _run(monkeypatch, [*DEFENCE, bad])
    run = _runs(conn)[0]
    assert run["status"] == "partial" and "1 files were not readable" in run["error_message"]
    assert conn.execute("SELECT count(*) n FROM raw_ingest").fetchone()["n"] == 3


def test_a_zip_that_held_more_than_was_landed_is_partial(conn, monkeypatch):
    _feed(monkeypatch, {TODAY: FakeDay(DEFENCE, entries=5)})
    pipeline.run_de_bkms(days=0, force=True, today=TODAY)
    run = _runs(conn)[0]
    assert run["status"] == "partial" and "5 files in the zip, 2 landed" in run["error_message"]


def test_a_short_past_day_is_partial_but_today_is_not_judged(conn, monkeypatch):
    yesterday = date(2026, 10, 14)
    _feed(monkeypatch, {yesterday: DEFENCE, TODAY: DEFENCE})
    pipeline.run_de_bkms(days=1, force=True, today=TODAY)
    run = _runs(conn)[0]
    assert run["status"] == "partial"
    assert f"{yesterday}: 2 files, under {pipeline.DE_BKMS_DAY_FLOOR}" in run["error_message"]
    assert str(TODAY) not in run["error_message"]


def test_a_missing_past_day_fails_the_run_but_a_missing_today_does_not(conn, monkeypatch):
    _feed(monkeypatch, {TODAY: DEFENCE})
    with pytest.raises(RuntimeError, match="no file for 2026-10-14"):
        pipeline.run_de_bkms(days=1, force=True, today=TODAY)
    assert _runs(conn)[-1]["status"] == "failed"
    _feed(monkeypatch, {date(2026, 10, 14): DEFENCE})
    pipeline.run_de_bkms(days=1, force=True, today=TODAY)
    assert _runs(conn)[-1]["status"] == "partial"      # the day itself is short, today is absent


# ------------------------------------------------------------------- twin link

def test_the_notice_is_linked_to_its_ted_twin_by_the_procedure_identifier(conn, monkeypatch):
    ted = Opportunity(source_code="ted", native_id="710974-2026", buyer_name_raw="BAAINBw",
                      title_original="Schulung", country="DE", status="open", is_defence=True,
                      published_at=TODAY, cpv_codes=["80000000"], procedure_identifier=PROCEDURE,
                      sig_legal_basis=True, legal_basis="32009L0081")
    src = db.source_id(conn, "ted")
    db.upsert_opportunity(conn, ted, "ted-h", src)
    conn.commit()

    _run(monkeypatch, DEFENCE)
    assert link_twins.run(conn, write=True, methods=("procedure_id",))["procedure_id"] == 1
    row = conn.execute(
        "SELECT ted_ref, twin_method, twin_confidence FROM opportunity WHERE native_id = %s",
        (NOTICE,)).fetchone()
    assert (row["ted_ref"], row["twin_method"], float(row["twin_confidence"])) == (
        "710974-2026", "procedure_id", 0.98)
