"""Work package WP-6 against a real Postgres: the nightly twin links, the requalify of every
source, the run owner, a notice that stops qualifying, a thin history record, PLACSP landed
once per content, a re-read that moves a date, a value and the lots, and the borrowed read
side.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline, reprocess, worker
from dgate.normalise import Opportunity
from dgate.ops import remap_source
from dgate.rawstore import build_store
from dgate.sources import boamp, placsp, tenderned

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
XML = (FIXTURES / "placsp_live_entries.atom").read_text(encoding="utf-8")
NATIVE = "2026/ETSAE0921/00001111E"


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def boamp_record(idweb: str, *, perimetre: str = "FNSimple", buyer: str = "Ministere des Armees",
                 deadline: str = "2026-10-15T12:00:00+00:00", cpv: str = "45000000",
                 donnees: dict | None = None) -> dict:
    return {
        "idweb": idweb, "objet": f"Marche {idweb}", "nomacheteur": buyer,
        "dateparution": "2026-09-19", "datelimitereponse": deadline,
        "perimetre": perimetre, "nature": "APPEL_OFFRE",
        "donnees": json.dumps(donnees or {"FNSimple": {"initial": {"natureMarche": {
            "codeCPV": {"objetPrincipal": {"classPrincipale": cpv}},
            "description": "Description du marche"}}}}),
    }


def feed(monkeypatch, *records):
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(records))


def flag_buyer(conn, name: str, country: str) -> int:
    org = db.resolve_organisation(conn, name, country)
    conn.execute("UPDATE organisation SET is_defence_buyer = TRUE WHERE id = %s", (org,))
    conn.commit()
    return org


def count(conn, sql: str, *args) -> int:
    return conn.execute(sql, args).fetchone()["n"]


# ------------------------------------------------------------- twin links


def put_twin_pair(conn) -> None:
    deadline = datetime.now(timezone.utc) + timedelta(days=40)
    procedure = "546636a5-bf94-45aa-a25f-25d76f8f0b91"
    for source, native in (("ted", "661706-2026"), ("es_placsp", "2026/AR40U/00002845E")):
        opp = Opportunity(
            source_code=source, native_id=native, buyer_name_raw="Armada", country="ES",
            title_original="Motores", published_at=date.today(), deadline_at=deadline,
            cpv_codes=["35511000"], status="open", is_defence=True, sig_cpv=True,
            value_amount=100.0, value_currency="EUR", procedure_identifier=procedure)
        src = db.source_id(conn, source)
        oid, _ = db.upsert_opportunity(conn, opp, f"h-{native}", src)
        conn.execute("UPDATE opportunity SET procedure_identifier = %s WHERE id = %s",
                     (procedure, oid))
    conn.commit()


def test_the_worker_job_links_twins_and_a_second_night_finds_nothing(conn):
    put_twin_pair(conn)
    first = worker.job_link_twins()
    assert first.status == "success" and "procedure_id 1" in first.detail
    row = conn.execute("SELECT ted_ref, twin_method FROM opportunity "
                       "WHERE native_id = '2026/AR40U/00002845E'").fetchone()
    assert (row["ted_ref"], row["twin_method"]) == ("661706-2026", "procedure_id")
    second = worker.job_link_twins()
    assert "procedure_id 0" in second.detail and "heuristic 0" in second.detail


# ---------------------------------------------------------------- requalify


def test_a_notice_dropped_at_ingest_is_inserted_once_its_buyer_is_listed(
        conn, fs_store, monkeypatch):
    """BOAMP had no requalify: 55 of 59 notices of French defence bodies were absent
    (data-coverage X1), and the buyer lists were extended after they were dropped."""
    feed(monkeypatch, boamp_record("26-9"))
    pipeline.run_boamp(days=2)
    assert count(conn, "SELECT count(*) n FROM opportunity") == 0
    assert count(conn, "SELECT count(*) n FROM raw_ingest") == 1
    flag_buyer(conn, "Ministere des Armees", "FR")
    store, today = build_store(), date.today()

    dry = reprocess.requalify_window(conn, store, "fr_boamp", today, today, dry_run=True)
    assert (dry["candidates"], dry["inserted"], dry["by_buyer"]) == (1, 1, 1)
    assert count(conn, "SELECT count(*) n FROM opportunity") == 0

    done = reprocess.requalify_window(conn, store, "fr_boamp", today, today, dry_run=False)
    assert done["inserted"] == 1
    row = conn.execute("SELECT sig_buyer, is_defence, status FROM opportunity").fetchone()
    assert row["sig_buyer"] and row["is_defence"] and row["status"] == "open"
    again = reprocess.requalify_window(conn, store, "fr_boamp", today, today, dry_run=False)
    assert (again["candidates"], again["inserted"]) == (0, 0)


def test_a_placsp_record_is_requalified_from_the_stored_record(conn, fs_store):
    opp = Opportunity(source_code="es_placsp", native_id="2026/X/1", country="ES",
                      buyer_name_raw="Mando de Apoyo Logistico", title_original="Suministro",
                      cpv_codes=["30200000"], status="open", published_at=date.today())
    pipeline._ingest_placsp([opp], "es_placsp")
    assert count(conn, "SELECT count(*) n FROM opportunity") == 0
    flag_buyer(conn, "Mando de Apoyo Logistico", "ES")
    done = reprocess.requalify_window(conn, build_store(), "es_placsp", date.today(),
                                      date.today(), dry_run=False)
    assert (done["candidates"], done["inserted"]) == (1, 1)
    assert conn.execute("SELECT native_id, sig_buyer FROM opportunity").fetchone() == {
        "native_id": "2026/X/1", "sig_buyer": True}


def test_a_window_is_done_one_day_at_a_time_and_resumes_under_the_same_rules(
        conn, fs_store, monkeypatch):
    feed(monkeypatch, boamp_record("26-9"))
    pipeline.run_boamp(days=2)
    store, today = build_store(), date.today()
    first = reprocess.requalify_window(conn, store, "fr_boamp", today - timedelta(days=4),
                                       today, dry_run=False)
    assert first["days"] == 5 and first["skipped_days"] == 0
    # the days that are two days old or more are marked; today and yesterday are not
    second = reprocess.requalify_window(conn, store, "fr_boamp", today - timedelta(days=4),
                                        today, dry_run=False)
    assert second["skipped_days"] == 3 and second["days"] == 2

    # a buyer list that changed is another set of rules: the days are read again
    flag_buyer(conn, "Un autre acheteur", "FR")
    third = reprocess.requalify_window(conn, store, "fr_boamp", today - timedelta(days=4),
                                       today, dry_run=False)
    assert third["skipped_days"] == 0 and third["days"] == 5


def test_the_command_line_form_takes_a_source_and_a_window(conn, fs_store, monkeypatch, capsys):
    feed(monkeypatch, boamp_record("26-9"))
    pipeline.run_boamp(days=2)
    flag_buyer(conn, "Ministere des Armees", "FR")
    today = date.today().isoformat()
    assert reprocess.main(["--requalify", "--source", "fr_boamp", "--from", today]) == 0
    assert "dry run" in capsys.readouterr().out
    assert count(conn, "SELECT count(*) n FROM opportunity") == 0
    assert reprocess.main(["--requalify", "--source", "fr_boamp", "--from", today, "--yes"]) == 0
    assert "fr_boamp: " in capsys.readouterr().out
    assert count(conn, "SELECT count(*) n FROM opportunity") == 1


def test_the_weekly_job_reports_what_it_inserted(conn, fs_store, monkeypatch):
    feed(monkeypatch, boamp_record("26-9"))
    pipeline.run_boamp(days=2)
    flag_buyer(conn, "Ministere des Armees", "FR")
    result = worker.job_requalify()
    assert result.status == "success" and "fr_boamp 1/1" in result.detail
    assert count(conn, "SELECT count(*) n FROM opportunity") == 1


# ------------------------------------------------------- the run's owner


def _run_row(conn, owner: str | None, hours_ago: float) -> int:
    return conn.execute(
        """INSERT INTO ingest_run (source_id, status, owner, started_at)
           VALUES ((SELECT id FROM source WHERE code = 'ted'), 'running', %s,
                   clock_timestamp() - interval '1 hour' * %s) RETURNING id""",
        (owner, hours_ago)).fetchone()["id"]


def test_a_start_up_closes_its_own_kinds_runs_and_the_stale_ones_only(conn):
    """The scheduled worker starting proves the earlier scheduled worker is dead. It
    proves nothing about a backfill an operator has open in another container."""
    mine = _run_row(conn, "worker:old-container:1", 0.5)
    operators = _run_row(conn, "cli:remap-chain:7", 0.5)
    legacy_stale = _run_row(conn, None, 40)
    cli_stale = _run_row(conn, "cli:x:9", 30)
    conn.commit()

    closed = db.close_interrupted_runs(conn, kind="worker")
    assert set(closed) == {mine, legacy_stale, cli_stale}
    still = conn.execute("SELECT status FROM ingest_run WHERE id = %s", (operators,)).fetchone()
    assert still["status"] == "running"
    # a `--once` process closes nothing but what is a day old
    other = _run_row(conn, "worker:other:2", 0.2)
    conn.commit()
    assert db.close_interrupted_runs(conn, kind=None) == []
    assert conn.execute("SELECT status FROM ingest_run WHERE id = %s", (other,)).fetchone()[
        "status"] == "running"


def test_a_run_records_who_opened_it(conn):
    run_id = db.start_run(conn, "ted", expected_min=0)
    owner = conn.execute("SELECT owner FROM ingest_run WHERE id = %s", (run_id,)).fetchone()[
        "owner"]
    assert owner.startswith("cli:") and owner.count(":") >= 2


# ----------------------------------- a notice that stops qualifying (M6)


def test_a_held_notice_that_stops_qualifying_is_still_updated(conn, fs_store, monkeypatch):
    """A later payload dropped the directive: the row kept its stale state for ever
    because every run skipped a notice the classifier no longer kept."""
    feed(monkeypatch, boamp_record("26-5", perimetre="DIRECTIVE-81"))
    pipeline.run_boamp(days=2)
    assert conn.execute("SELECT is_defence, deadline_at FROM opportunity").fetchone()[
        "is_defence"] is True

    feed(monkeypatch, boamp_record("26-5", perimetre="DIRECTIVE-24",
                                   deadline="2026-12-01T12:00:00+00:00"))
    pipeline.run_boamp(days=2)
    row = conn.execute("SELECT is_defence, sig_legal_basis, deadline_at, current_version "
                       "FROM opportunity").fetchone()
    assert row["current_version"] == 2
    assert row["is_defence"] is False and row["sig_legal_basis"] is False
    assert row["deadline_at"].date() == date(2026, 12, 1)       # the new state is the row's
    # and a notice that was never held and does not qualify is still not kept
    feed(monkeypatch, boamp_record("26-6", perimetre="DIRECTIVE-24", buyer="Mairie de Lyon"))
    pipeline.run_boamp(days=2)
    assert count(conn, "SELECT count(*) n FROM opportunity") == 1


# --------------------------------- a thin record in a history load (M5)


def test_a_history_load_does_not_archive_a_thin_copy_over_a_full_record(
        conn, fs_store, monkeypatch):
    full = {"publicatieId": "7", "publicatieDatum": "2026-10-09",
            "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
            "aanbestedingNaam": "Opdracht 7", "opdrachtgeverNaam": "Gemeente Voorbeeld",
            "sluitingsDatum": "2026-11-19T17:00:00",
            "publicatiecode": {"code": "EF18", "omschrijving":
                               "Aankondiging van een opdracht - defensierichtlijn, "
                               "standaardregeling"},
            "detail": {"publicatieId": 7, "cpvCodes": [
                {"isHoofdOpdracht": True, "code": "90500000-1", "omschrijving": "x"}]}}
    thin = {k: v for k, v in full.items() if k != "detail"} | {"detailError": "HTTP 404"}
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter([full]))
    pipeline.run_tenderned(days=2)
    assert conn.execute("SELECT cpv_codes FROM opportunity").fetchone()["cpv_codes"] == [
        "90500000"]

    monkeypatch.setattr(tenderned, "fetch_day", lambda day: iter([thin]))
    pipeline.run_history("nl_tenderned", date(2026, 10, 9), date(2026, 10, 9))
    row = conn.execute("SELECT cpv_codes, current_version FROM opportunity").fetchone()
    assert row["cpv_codes"] == ["90500000"] and row["current_version"] == 1
    # the thin copy is landed and indexed all the same
    assert count(conn, "SELECT count(*) n FROM raw_ingest") == 2


# ----------------------------------- PLACSP: landed once per content (M10)


def _defence_entry(xml: str = XML):
    opps, _ = placsp.parse_feed(xml.encode("utf-8"))
    return next(o for o in opps if o.native_id == NATIVE)


def test_an_unchanged_entry_is_landed_once_and_a_changed_one_again(conn, fs_store):
    pipeline._ingest_placsp([_defence_entry()], "es_placsp")
    pipeline._ingest_placsp([_defence_entry()], "es_placsp")
    assert count(conn, "SELECT count(*) n FROM raw_ingest") == 1
    amended = XML.replace("<cbc:EndDate>2026-11-16</cbc:EndDate>",
                          "<cbc:EndDate>2026-11-20</cbc:EndDate>").replace(
        "<updated>2026-10-10T14:41:55.557+02:00</updated>",
        "<updated>2026-10-12T09:15:00.000+02:00</updated>")
    pipeline._ingest_placsp([_defence_entry(amended)], "es_placsp")
    assert count(conn, "SELECT count(*) n FROM raw_ingest") == 2


# --------- a re-read moves a stored date, a value and the lots (DC1 b-e)


# The same notice amended on 12 October: the entry's update time is that day, and the call's
# own publication (an IssueDate of the 10th) is earlier than the feed's time.
AMENDED = (XML
           .replace("<updated>2026-10-10T14:41:55.557+02:00</updated>",
                    "<updated>2026-10-12T09:15:00.000+02:00</updated>"))


def _notes(conn, oid: int, version: int) -> list[str]:
    return [r["kind"] for r in conn.execute(
        """SELECT n.kind FROM opportunity_version v
             JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s AND v.version = %s""", (oid, version)).fetchall()]


def test_a_replayed_entry_corrects_the_date_the_value_and_the_lots_of_a_held_row(
        conn, fs_store):
    """What the September 2026 rows need: held as the old mapper read them (the feed's
    time as the publication date, the budget with VAT, no lots), they are brought to what
    the entry states by the replay, as one `remapped` version. `remap_source` cannot: the
    stored record has no entry in it."""
    new = _defence_entry(AMENDED)
    assert new.published_at == date(2026, 10, 10) and new.source_updated_at.day == 12
    held = dataclasses.replace(
        new, published_at=new.source_updated_at.date(), source_updated_at=None,
        value_amount=3655285.38, lot_count=None, is_defence=True, sig_cpv=True,
        procedure_type="4")
    oid, _ = db.upsert_opportunity(conn, held, "held-by-the-old-mapper",
                                   db.source_id(conn, "es_placsp"))
    conn.commit()

    pipeline._ingest_placsp([_defence_entry(AMENDED)], "es_placsp", replay=True)
    row = conn.execute("SELECT published_at, value_amount, current_version FROM opportunity "
                       "WHERE id = %s", (oid,)).fetchone()
    assert row["current_version"] == 2
    assert row["published_at"] == date(2026, 10, 10)          # the call's own date
    assert float(row["value_amount"]) == 3020897.01           # without VAT
    assert _notes(conn, oid, 2) == ["remapped"]


def test_a_publication_date_the_entry_does_not_state_is_cleared_by_the_re_read(conn, fs_store):
    """An entry that carries only award notices has no publication date, and the feed time
    the old mapper held in its place is not one: cleared, as a remapped version, so the
    row is listed with its date "not stated" and not under an award date."""
    entry = _defence_entry(AMENDED)
    stamp = entry.source_updated_at
    held = dataclasses.replace(entry, published_at=stamp.date(), source_updated_at=None,
                               is_defence=True, sig_cpv=True)
    oid, _ = db.upsert_opportunity(conn, held, "held-award-only", db.source_id(conn, "es_placsp"))
    conn.commit()
    award_only = dataclasses.replace(entry, published_at=None)
    pipeline._ingest_placsp([award_only], "es_placsp", replay=True)
    row = conn.execute("SELECT published_at, current_version FROM opportunity WHERE id = %s",
                       (oid,)).fetchone()
    assert (row["published_at"], row["current_version"]) == (None, 2)
    assert _notes(conn, oid, 2) == ["remapped"]


def test_a_lot_count_the_entry_states_is_written_to_a_held_row_without_a_version(
        conn, fs_store):
    new = dataclasses.replace(_defence_entry(), lot_count=None, is_defence=True, sig_cpv=True)
    oid, _ = db.upsert_opportunity(conn, new, "h-1", db.source_id(conn, "es_placsp"))
    conn.commit()
    pipeline._ingest_placsp([dataclasses.replace(new, lot_count=4)], "es_placsp", replay=True)
    row = conn.execute("SELECT lot_count, current_version FROM opportunity WHERE id = %s",
                       (oid,)).fetchone()
    assert (row["lot_count"], row["current_version"]) == (4, 1)


# -------------------- the stored-row selectors of remap_source (DC4, DC6)


def test_remap_can_be_pointed_at_the_rows_without_a_deadline(conn, fs_store):
    legacy = boamp_record("21-35386", deadline=None, donnees={
        "CONDITION_DELAI": {"RECEPT_OFFRES": "2021-04-16T16:00:00+01:00"}})
    other = boamp_record("21-35387", deadline="2021-04-20T10:00:00+00:00", donnees={})
    from dgate.sources.ted import content_hash

    ids = {}
    for record in (legacy, other):
        digest = content_hash(record)
        key = build_store().put(
            f"fr_boamp/2021/03/18/{record['idweb']}-{digest[:12]}.json", record)
        src = db.source_id(conn, "fr_boamp")
        db.record_raw(conn, src, record["idweb"], digest, key)
        stored = Opportunity(
            source_code="fr_boamp", native_id=record["idweb"], buyer_name_raw="Acheteur",
            title_original="Marche", country="FR", status="open", is_defence=True, sig_cpv=True,
            published_at=date(2021, 3, 18), deadline_at=None)
        ids[record["idweb"]], _ = db.upsert_opportunity(conn, stored, digest, src)
    conn.commit()
    conn.execute("DELETE FROM remap_marker")
    conn.commit()

    result = remap_source.run("fr_boamp", write=True, epoch=4, no_deadline=True)
    assert result.examined == 2 and result.versions == 2      # both held no deadline here
    deadline = conn.execute("SELECT deadline_at FROM opportunity WHERE id = %s",
                            (ids["21-35386"],)).fetchone()["deadline_at"]
    assert deadline == datetime(2021, 4, 16, 14, 0, tzinfo=timezone.utc)


def test_remap_can_be_pointed_at_one_stored_status(conn, fs_store):
    from dgate.sources.ted import content_hash

    record = {"id": "A-1", "buyer": "Komenda", "title": "t", "date": "2025-03-01",
              "notice_type": "TenderResultNotice", "organization_country": "PL",
              "procedure_result": "nieRozstrzygnieto;uniewaznienie"}
    digest = content_hash(record)
    src = db.source_id(conn, "pl_atlas")
    key = build_store().put(f"pl_atlas/2025/03/01/A-1-{digest[:12]}.json", record)
    db.record_raw(conn, src, "A-1", digest, key)
    stored = Opportunity(source_code="pl_atlas", native_id="A-1", buyer_name_raw="Komenda",
                         title_original="t", country="PL", status="closed", is_defence=True,
                         sig_cpv=True, published_at=date(2025, 3, 1))
    oid, _ = db.upsert_opportunity(conn, stored, digest, src)
    conn.commit()
    conn.execute("DELETE FROM remap_marker")
    conn.commit()

    assert remap_source.run("pl_atlas", write=True, epoch=4, status="awarded").examined == 0
    done = remap_source.run("pl_atlas", write=True, epoch=4, status="closed")
    assert (done.examined, done.versions) == (1, 1)
    assert conn.execute("SELECT status FROM opportunity WHERE id = %s", (oid,)).fetchone()[
        "status"] == "cancelled"


# ------------------------------------------------ the borrowed read side


def put(conn, source: str, native_id: str, *, procedure: str | None, deadline: datetime,
        ted_ref: str | None = None, published: date | None = date(2026, 10, 1)) -> int:
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw="Armada", country="ES",
        title_original=f"Notice {native_id}", published_at=published, deadline_at=deadline,
        cpv_codes=["35511000"], status="open", is_defence=True, sig_cpv=True,
        procedure_type=procedure, ted_ref=ted_ref)
    oid, _ = db.upsert_opportunity(conn, opp, f"h-{source}-{native_id}",
                                   db.source_id(conn, source))
    conn.commit()
    return oid


def test_a_national_notice_borrows_its_twins_procedure_and_deadline_with_provenance(
        conn, client):
    now = datetime.now(timezone.utc)
    put(conn, "ted", "661706-2026", procedure="restricted", deadline=now + timedelta(days=30))
    oid = put(conn, "pl_atlas", "TED-661706-2026", procedure=None,
              deadline=now + timedelta(days=900), ted_ref="661706-2026")
    body = client.get(f"/v1/tenders/{oid}").json()
    assert body["procedure"] == "Restricted procedure" and body["procedureFrom"] == "ted_twin"
    assert body["deadlineFrom"] == "ted_twin"
    assert body["deadline"][:10] == (now + timedelta(days=30)).date().isoformat()
    assert "deadline-differs-from-ted-twin" in body["anomalies"]
    # the notice's own procedure is never replaced
    own = put(conn, "pl_ezam", "2026/BZP 1", procedure="Basic procedure",
              deadline=now + timedelta(days=31), ted_ref="661706-2026")
    served = client.get(f"/v1/tenders/{own}").json()
    assert served["procedure"] == "Basic procedure" and served["procedureFrom"] is None
    assert served["deadlineFrom"] is None


def test_a_deadline_over_a_year_away_is_flagged_and_a_row_without_a_date_is_listed(
        conn, client):
    now = datetime.now(timezone.utc)
    far = put(conn, "es_placsp", "2026/FAR/1", procedure="Abierto",
              deadline=now + timedelta(days=500))
    undated = put(conn, "es_placsp", "2026/NODATE/1", procedure="Abierto",
                  deadline=now + timedelta(days=20), published=None)
    assert "deadline-more-than-1y" in client.get(f"/v1/tenders/{far}").json()["anomalies"]
    got = client.get(f"/v1/tenders/{undated}").json()
    assert got["publishedAt"] is None and got["publishedKnown"] is False
    listed = client.get("/v1/tenders", params={"status": "all", "scope": "all"}).json()
    assert "2026/NODATE/1" in {t["noticeId"] for t in listed["items"]}


# ---------------------------- repair_reversions keeps the classification (O1)


def test_a_correcting_version_keeps_the_serving_rows_classification(conn):
    from dgate.ops import repair_reversions

    src = db.source_id(conn, "ted")
    first = Opportunity(source_code="ted", native_id="1-2026", buyer_name_raw="Armada",
                        title_original="Motores", country="ES", published_at=date(2026, 10, 10),
                        status="open", is_defence=True, sig_cpv=True, cpv_codes=["35511000"])
    oid, _ = db.upsert_opportunity(conn, first, "hash-a", src)
    # older content that arrived later (the case the repair exists for)
    older = dataclasses.replace(first, published_at=date(2026, 10, 1), title_original="Motors")
    db.append_version(conn, oid, older, "hash-b", ["title_original", "published_at"], after=1)
    # classified later, as a buyer list growing does: not in any version's payload
    conn.execute("UPDATE opportunity SET sig_buyer = TRUE, buyer_class = 'defence' "
                 "WHERE id = %s", (oid,))
    conn.commit()

    assert repair_reversions.run(dry_run=True)["corrected"] == 1
    assert repair_reversions.run(dry_run=False)["corrected"] == 1
    row = conn.execute("SELECT title_original, sig_buyer, buyer_class, is_defence, "
                       "current_version FROM opportunity WHERE id = %s", (oid,)).fetchone()
    assert row["title_original"] == "Motores" and row["current_version"] == 3
    # the old payload has no classification: carried from the serving row, not blanked
    assert (row["sig_buyer"], row["buyer_class"], row["is_defence"]) == (True, "defence", True)
