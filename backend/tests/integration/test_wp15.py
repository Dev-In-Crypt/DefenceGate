"""WP-15 against a real Postgres: a national notice inherits the defence verdict of the TED
notice it states (lost after landing), the nightly completeness controls, a run that skipped
a page is `partial`, and the FR link the strict heuristic never offered.

Shapes: the Polish record is the stored BZP payload of 2026/S 68-238462 (contacts removed),
the others are the connectors' own shapes with the TED reference the source states.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline, reprocess, worker
from dgate.normalise import Opportunity
from dgate.ops import controls, link_twins
from dgate.sources import aid, boamp, ezamowienia, tenderned

pytestmark = pytest.mark.integration

PROCEDURE = "f7cb26b5-318f-4009-9c62-91497d2c09b8"

# 2026/S 68-238462, read from the raw store on 15 October 2026; contact fields removed.
BZP_RECORD = {
    "baseNoticeMOIdentifier": None, "bzpNumber": "2026/S 68-238462", "bzpTenderPlanNumber": None,
    "clientType": "body-pl", "cpvCode": "45000000", "htmlBody": None,
    "isManuallyLinkedWithTender": False, "isTenderAmountBelowEU": False,
    "moIdentifier": "c4abd453-d8c6-4971-bf94-e00825543011", "noticeNumber": "2026/S 68-238462",
    "noticeType": "eforms-16", "noticeTypeTed": "cn-standard",
    "objectId": "08de950c-89d9-d5f9-5fad-950001195538",
    "orderObject": "Polska - Roboty budowlane - budowa budynku biurowo-sztabowego",
    "orderType": "Works", "organizationCity": "Bydgoszcz", "organizationCountry": "POL",
    "organizationName": "Rejonowy Zarzad Infrastruktury w Bydgoszczy",
    "outdated": False, "pdfUrl": "https://ted.europa.eu/pl/notice/238462-2026/pdf",
    "procedureResult": "Unijna", "publicationDate": "2026-04-08T00:00:00Z",
    "submittingOffersDate": "2026-04-23T08:00:00Z", "tenderType": "open",
}


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


def put_ted(conn, native_id: str, *, defence: bool = True, procedure: str | None = None,
            buyer: str = "Rejonowy Zarzad Infrastruktury", country: str = "PL",
            deadline: datetime | None = None, value: float | None = None,
            cpv: tuple[str, ...] = ("35000000",), published: date = date(2026, 4, 7)) -> int:
    opp = Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw=buyer, country=country,
        title_original=f"TED {native_id}", published_at=published, deadline_at=deadline,
        cpv_codes=list(cpv), status="open", is_defence=defence, sig_cpv=defence,
        # A defence TED twin is one in the default list on its own signals (WP-72: a twin that is
        # only dual-use no longer lifts its national copy; test_wp72 covers that case).
        sig_legal_basis=defence,
        value_amount=value, value_currency="EUR" if value else None)
    src = db.source_id(conn, "ted")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"h-{native_id}", src)
    if procedure:
        conn.execute("UPDATE opportunity SET procedure_identifier = %s WHERE id = %s",
                     (procedure, oid))
    conn.commit()
    return oid


def served(conn, source: str, native_id: str):
    return conn.execute(
        """SELECT o.is_defence, o.sig_linked_defence, o.sig_cpv_military, o.sig_buyer, o.ted_ref
             FROM opportunity o JOIN source s ON s.id = o.source_id
            WHERE s.code = %s AND o.native_id = %s""", (source, native_id)).fetchone()


def count(conn, sql: str) -> int:
    return conn.execute(sql).fetchone()["n"]


def feed_ezam(monkeypatch, *records):
    monkeypatch.setattr(ezamowienia, "fetch_window",
                        lambda days_back=2, failed=None, **kw: iter(records))


# ----------------------------------------------- (1) lost after landing: Poland

def test_a_bzp_notice_republished_from_a_ted_defence_notice_is_kept(conn, fs_store, monkeypatch):
    put_ted(conn, "238462-2026")
    feed_ezam(monkeypatch, BZP_RECORD)
    pipeline.run_ezamowienia(days=2, refresh_limit=0)
    row = served(conn, "pl_ezam", "2026/S 68-238462")
    assert row is not None
    assert (row["is_defence"], row["sig_linked_defence"], row["ted_ref"]) == (
        True, True, "238462-2026")
    # the verdict is inherited, not an invented CPV or buyer signal
    assert not row["sig_cpv_military"] and not row["sig_buyer"]


def test_it_is_still_dropped_when_the_ted_twin_is_not_defence_or_not_held(
        conn, fs_store, monkeypatch):
    put_ted(conn, "238462-2026", defence=False)
    feed_ezam(monkeypatch, BZP_RECORD)
    pipeline.run_ezamowienia(days=2, refresh_limit=0)
    assert count(conn, "SELECT count(*) n FROM opportunity WHERE source_id = "
                       "(SELECT id FROM source WHERE code = 'pl_ezam')") == 0
    assert count(conn, "SELECT count(*) n FROM raw_ingest") == 1


def test_requalify_recovers_the_notice_once_its_twin_is_known(conn, fs_store, monkeypatch, capsys):
    feed_ezam(monkeypatch, BZP_RECORD)
    pipeline.run_ezamowienia(days=2, refresh_limit=0)           # the twin is not held yet
    assert served(conn, "pl_ezam", "2026/S 68-238462") is None
    put_ted(conn, "238462-2026")

    assert reprocess.main(["--requalify", "--twin-linked", "--source", "pl_ezam"]) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "inserted: 1" in out and "by_linked: 1" in out
    assert served(conn, "pl_ezam", "2026/S 68-238462") is None

    assert reprocess.main(["--requalify", "--twin-linked", "--source", "pl_ezam", "--yes"]) == 0
    assert served(conn, "pl_ezam", "2026/S 68-238462")["sig_linked_defence"] is True
    # idempotent: a second run finds nothing to do
    reprocess.main(["--requalify", "--twin-linked", "--source", "pl_ezam", "--yes"])
    assert "candidates: 0" in capsys.readouterr().out.split("applied")[-1]


def test_the_weekly_window_reads_a_day_again_after_the_rule_changed(conn, monkeypatch):
    one = reprocess.rules_fingerprint(conn)
    monkeypatch.setattr(reprocess, "RULES_EPOCH", "something-else")
    assert reprocess.rules_fingerprint(conn) != one


# --------------------------------------- (1) the other sources, by what they state

def boamp_record(idweb: str, folder: str | None) -> dict:
    rec = {
        "idweb": idweb, "objet": f"Marche {idweb}", "nomacheteur": "SID Sud-Est",
        "dateparution": "2026-08-04", "datelimitereponse": "2026-09-02T14:00:00+00:00",
        "perimetre": "DIRECTIVE-24", "nature": "APPEL_OFFRE",
        "donnees": json.dumps({"FNSimple": {"initial": {"natureMarche": {
            "codeCPV": {"objetPrincipal": {"classPrincipale": "45210000"}}}}}}),
    }
    if folder:
        rec["contractfolderid"] = folder
    return rec


def test_a_boamp_notice_inherits_through_the_procedure_identifier(conn, fs_store, monkeypatch):
    put_ted(conn, "537243-2026", procedure=PROCEDURE, country="FR", buyer="SID Sud-Est",
            cpv=("45210000",))
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter([
        boamp_record("26-77210", PROCEDURE), boamp_record("26-1", None)]))
    pipeline.run_boamp(days=2)
    row = served(conn, "fr_boamp", "26-77210")
    assert row and row["is_defence"] and row["sig_linked_defence"]
    assert served(conn, "fr_boamp", "26-1") is None      # states nothing: nothing inherited


def _tn_record(pid: str, ted_number: str | None) -> dict:
    detail: dict = {"publicatieId": int(pid), "cpvCodes": [
        {"isHoofdOpdracht": True, "code": "90500000-1", "omschrijving": "Afval"}]}
    if ted_number:
        detail["pbNummerTed"] = ted_number
    return {
        "publicatieId": pid, "publicatieDatum": "2026-10-09",
        "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
        "aanbestedingNaam": f"Opdracht {pid}", "opdrachtgeverNaam": "Gemeente Voorbeeld",
        "sluitingsDatum": "2026-11-19T17:00:00",
        "publicatiecode": {"code": "EF18", "omschrijving": "Aankondiging - algemene richtlijn"},
        "detail": detail,
    }


def test_a_tenderned_notice_inherits_through_its_ted_number(conn, fs_store, monkeypatch):
    put_ted(conn, "238462-2026", country="NL", buyer="Gemeente Voorbeeld")
    monkeypatch.setattr(tenderned, "fetch_window", lambda days_back=2: iter([
        _tn_record("700001", "00238462-2026"), _tn_record("700002", None)]))
    pipeline.run_tenderned(days=2)
    row = served(conn, "nl_tenderned", "700001")
    assert row and row["is_defence"] and row["sig_linked_defence"]
    assert served(conn, "nl_tenderned", "700002") is None


def test_a_placsp_record_inherits_through_its_procedure_identifier(conn, fs_store):
    put_ted(conn, "661706-2026", procedure=PROCEDURE, country="ES", buyer="Armada",
            cpv=("35511000",))
    opp = Opportunity(source_code="es_placsp", native_id="2026/AR40U/00002845E", country="ES",
                      buyer_name_raw="Ayuntamiento de Algun Sitio", title_original="Servicio",
                      cpv_codes=["45000000"], status="open", published_at=date(2026, 10, 1),
                      procedure_identifier=PROCEDURE.upper())
    pipeline._ingest_placsp([opp], "es_placsp")
    row = served(conn, "es_placsp", "2026/AR40U/00002845E")
    assert row and row["is_defence"] and row["sig_linked_defence"]


# -------------------------------------- (4) the FR link the heuristic never offered

def _national(conn, native_id: str, *, procedure: str | None, deadline: datetime,
              buyer: str = "SID Sud-Est", value: float | None = None) -> int:
    opp = Opportunity(
        source_code="fr_boamp", native_id=native_id, buyer_name_raw=buyer, country="FR",
        title_original=native_id, published_at=date(2026, 8, 4), deadline_at=deadline,
        cpv_codes=["45210000"], status="open", is_defence=True, sig_buyer=True,
        value_amount=value, value_currency="EUR" if value else None)
    src = db.source_id(conn, "fr_boamp")
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, "FR", src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"h-{native_id}", src)
    conn.execute("UPDATE opportunity SET procedure_identifier = %s WHERE id = %s",
                 (procedure, oid))
    conn.commit()
    return oid


def _ref(conn, native_id: str):
    return conn.execute("SELECT ted_ref, twin_method, twin_confidence FROM opportunity "
                        "WHERE native_id = %s", (native_id,)).fetchone()


def test_sid_sud_est_is_linked_though_boamp_states_an_identifier_ted_lacks(conn):
    """BOAMP 26-77210 (4 Aug 2026): procedure identifier stated, TED 537243-2026 has none,
    no value on either side, deadline 16:00 local against 23:59 Paris."""
    put_ted(conn, "537243-2026", country="FR", buyer="SID Sud-Est", cpv=("45210000",),
            deadline=datetime(2026, 9, 2, 21, 59, tzinfo=timezone.utc),
            published=date(2026, 8, 3))
    _national(conn, "26-77210", procedure=PROCEDURE,
              deadline=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc))
    assert link_twins.run(conn, write=False)["heuristic"] == 1
    link_twins.run(conn, write=True)
    row = _ref(conn, "26-77210")
    assert (row["ted_ref"], row["twin_method"], row["twin_confidence"]) == (
        "537243-2026", "heuristic", pytest.approx(0.8))
    assert link_twins.run(conn, write=True)["heuristic"] == 0


def test_two_candidates_on_either_side_are_not_linked(conn):
    put_ted(conn, "1-2026", country="FR", buyer="SID Sud-Est", cpv=("45210000",),
            deadline=datetime(2026, 9, 2, 21, 59, tzinfo=timezone.utc), published=date(2026, 8, 3))
    put_ted(conn, "2-2026", country="FR", buyer="SID Sud-Est", cpv=("45210000",),
            deadline=datetime(2026, 9, 2, 21, 0, tzinfo=timezone.utc), published=date(2026, 8, 3))
    _national(conn, "26-1", procedure=PROCEDURE,
              deadline=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc))
    link_twins.run(conn, write=True)
    assert _ref(conn, "26-1")["ted_ref"] is None


def test_a_row_whose_identifier_a_ted_row_shares_still_links_by_procedure(conn):
    put_ted(conn, "9-2026", country="FR", buyer="SID Sud-Est", procedure=PROCEDURE)
    _national(conn, "26-9", procedure=PROCEDURE,
              deadline=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc))
    link_twins.run(conn, write=True)
    assert _ref(conn, "26-9")["twin_method"] == "procedure_id"


# ------------------------------------ (3) a run that skipped a page is partial

def test_an_aid_page_that_could_not_be_read_makes_the_run_partial(conn, fs_store, monkeypatch):
    page = {"url": "https://www.defense.gouv.fr/aid/appels-projets/cours/astrid", "slug": "astrid",
            "list": "cours", "title": "ASTRID 2026", "summary": "Resume", "published": "2026-03-17",
            "modified": "2026-03-17",
            "text": "Ouverture : 16/12/2025 a 09:00 CET Limite de depot des projets : "
                    "02/03/2030 a 15:00 CET"}
    pages = aid.Pages([page])
    pages.failed.append("/aid/appels-projets/cours/gone")
    monkeypatch.setattr(aid, "fetch_all", lambda client=None: pages)
    pipeline.run_aid()
    run = conn.execute("SELECT status, error_message FROM ingest_run ORDER BY id DESC").fetchone()
    assert run["status"] == "partial" and "1 pages could not be read" in run["error_message"]


def test_a_pl_day_that_could_not_be_read_is_partial_and_not_compared(conn, fs_store, monkeypatch):
    monkeypatch.setenv("DGATE_COMPLETENESS_CHECK", "1")
    config.reset_cache()
    day = date.today() - timedelta(days=1)

    def window(days_back=2, failed=None, **kw):
        failed.append(day)
        return iter(())

    monkeypatch.setattr(ezamowienia, "fetch_window", window)
    pipeline.run_ezamowienia(days=2, refresh_limit=0)
    run = conn.execute("SELECT status, error_message FROM ingest_run").fetchone()
    assert run["status"] == "partial" and "not read to their end" in run["error_message"]


# ------------------------------------------- (2) the nightly day-total control

def boamp_day(idweb: str, day: date) -> dict:
    rec = boamp_record(idweb, None)
    rec["dateparution"] = day.isoformat()
    return rec


def test_a_boamp_day_short_of_the_portal_total_makes_the_run_partial_and_is_on_health(
        conn, fs_store, monkeypatch, client):
    monkeypatch.setenv("DGATE_COMPLETENESS_CHECK", "1")
    config.reset_cache()
    yday = date.today() - timedelta(days=1)
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(
        [boamp_day(f"26-{i}", yday) for i in range(10)]))
    monkeypatch.setattr(controls, "_officials",
                        lambda: {"fr_boamp": lambda day, client: 40})
    pipeline.run_boamp(days=2)
    run = conn.execute("SELECT status, error_message, detail FROM ingest_run").fetchone()
    assert run["status"] == "partial"
    assert f"{yday}: landed 10 of 40 (-30)" in run["error_message"]
    assert run["detail"]["completeness"]["days"][yday.isoformat()] == {
        "landed": 10, "official": 40, "short": 30, "alert": True}
    health = client.get("/v1/health").json()
    line = next(s for s in health["sources"] if s["code"] == "fr_boamp")
    assert line["completeness"] == {"day": yday.isoformat(), "landed": 10, "official": 40,
                                    "short": True}


def test_a_complete_day_leaves_the_run_a_success(conn, fs_store, monkeypatch):
    monkeypatch.setenv("DGATE_COMPLETENESS_CHECK", "1")
    config.reset_cache()
    yday = date.today() - timedelta(days=1)
    monkeypatch.setattr(boamp, "fetch_window", lambda days_back=2: iter(
        [boamp_day(f"26-{i}", yday) for i in range(10)]))
    monkeypatch.setattr(controls, "_officials", lambda: {"fr_boamp": lambda day, client: 10})
    pipeline.run_boamp(days=2)
    run = conn.execute("SELECT error_message, detail FROM ingest_run").fetchone()
    # (the run is under its own coverage floor of 250; that is not what is asserted here)
    assert "fewer notices" not in (run["error_message"] or "")
    assert run["detail"]["completeness"]["short"] is False


def test_the_unit_of_the_control_is_the_stated_threshold():
    assert controls.verdict(100, 100)["alert"] is False
    assert controls.verdict(95, 100)["alert"] is True       # 5 rows but 5 %: over 2 %
    assert controls.verdict(2990, 3000)["alert"] is True    # 10 rows
    assert controls.verdict(2996, 3000)["alert"] is False   # 4 rows, 0.13 %
    assert controls.verdict(3040, 3000)["alert"] is False   # a surplus is not a loss


def test_a_counter_that_cannot_be_read_is_recorded_not_alerted():
    def broken(day):
        raise RuntimeError("503")

    detail, problem = controls.check_days(
        "pl_ezam", {date(2026, 10, 1): 100}, official=broken, today=date(2026, 10, 15), pause=0)
    assert problem is None
    assert detail["days"]["2026-10-01"] == {"landed": 100, "error": "RuntimeError"}


def test_today_and_unread_days_are_not_compared():
    seen = []
    detail, problem = controls.check_days(
        "pl_ezam", {date(2026, 10, 14): 1, date(2026, 10, 15): 1, date(2026, 10, 13): 1},
        skip={date(2026, 10, 13)}, official=lambda d: seen.append(d) or 1,
        today=date(2026, 10, 15), pause=0)
    assert seen == [date(2026, 10, 14)] and problem is None


# --------------------------------------------------- Atlas and PLACSP controls

def _record(version: str, checksum: str) -> dict:
    return {"metadata": {"version": version},
            "files": [{"key": "tenders_2025.parquet", "checksum": checksum}]}


def test_atlas_baseline_then_change_alerts_once(conn):
    now = datetime(2026, 10, 15, 7, tzinfo=timezone.utc)
    first = controls.check_atlas(conn, fetch=lambda: _record("2026.Q2", "md5:a"), now=now)
    assert first["status"] == "ok"
    assert controls.check_atlas(conn, fetch=lambda: _record("2026.Q3", "md5:b"),
                                now=now + timedelta(days=1)) is None      # weekly, not daily
    second = controls.check_atlas(conn, fetch=lambda: _record("2026.Q3", "md5:b"),
                                  now=now + timedelta(days=7))
    assert second["status"] == "alert" and second["detail"]["was"] == "2026.Q2"
    # the new state is the baseline: the next look is ok again
    third = controls.check_atlas(conn, fetch=lambda: _record("2026.Q3", "md5:b"),
                                 now=now + timedelta(days=14))
    assert third["status"] == "ok"


def test_placsp_measures_and_the_alert_clock(conn, client):
    put_ted(conn, "10-2026", country="ES", buyer="Armada", cpv=("35511000",),
            published=date.today() - timedelta(days=30))
    put_ted(conn, "11-2026", country="ES", buyer="Armada", cpv=("35511000",),
            published=date.today() - timedelta(days=3))          # too young to count
    src = db.source_id(conn, "es_placsp")
    for i, pub in enumerate([date(2026, 9, 1), None, None, date(2026, 9, 2)]):
        db.upsert_opportunity(conn, Opportunity(
            source_code="es_placsp", native_id=f"P{i}", buyer_name_raw="Armada", country="ES",
            title_original="x", cpv_codes=["35511000"], status="open", published_at=pub,
            is_defence=True, sig_cpv=True), f"h{i}", src)
    conn.commit()
    now = datetime(2026, 10, 15, 7, tzinfo=timezone.utc)
    got = controls.check_placsp(conn, now=now)
    assert got["detail"]["ted_es_unlinked_14d"] == 1
    assert got["detail"]["placsp_null_date_rate"] == 0.5 and got["status"] == "alert"
    assert [r["control"] for r in controls.due_alerts(conn, now)] == ["placsp_links"]
    assert controls.due_alerts(conn, now + timedelta(hours=24)) == []
    assert len(controls.due_alerts(conn, now + timedelta(hours=73))) == 1
    health = client.get("/v1/health").json()
    assert health["controls"]["placsp_links"]["placsp_null_date_rate"] == 0.5


def test_the_worker_job_tells_the_operator_once(conn, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(worker, "notify", lambda text, **kw: sent.append(text) or True)
    monkeypatch.setattr(controls, "fetch_zenodo_record", lambda: _record("2026.Q2", "md5:a"))
    monkeypatch.setattr(controls, "check_atlas", lambda conn: None)
    src = db.source_id(conn, "es_placsp")
    db.upsert_opportunity(conn, Opportunity(
        source_code="es_placsp", native_id="P0", buyer_name_raw="Armada", country="ES",
        title_original="x", cpv_codes=["35511000"], status="open", published_at=None,
        is_defence=True, sig_cpv=True), "h0", src)
    conn.commit()
    assert worker.job_controls().ok
    assert len(sent) == 1 and "placsp_links" in sent[0]
    assert worker.job_controls().ok and len(sent) == 1
