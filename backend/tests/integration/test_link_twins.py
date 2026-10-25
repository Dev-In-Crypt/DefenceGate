"""The same procurement across sources is listed once (QA finding, 12 October 2026).

PLACSP 2026/AR40U/00002845E and TED 661706-2026 are one Spanish frigate-engine tender
(same buyer, value and deadline) and were listed separately: only sources that state
a TED number carried `ted_ref`. `link_twins` ties the rest, by procedure identifier
where both sides have one and by a strict rule where neither does.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline
from dgate.normalise import Opportunity
from dgate.ops import link_ted, link_twins
from dgate.rawstore import build_store
from dgate.sources import boamp, placsp

pytestmark = pytest.mark.integration

DEADLINE = datetime(2026, 10, 12, 21, 59, tzinfo=timezone.utc) + timedelta(days=60)
PROCEDURE = "546636a5-bf94-45aa-a25f-25d76f8f0b91"
BUYER = "Dirección de Gestión Económica de la Jefatura de Apoyo Logístico de la Armada"


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture()
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield
    config.reset_cache()


def put(conn, source: str, native_id: str, *, buyer: str = BUYER, country: str = "ES",
        value: float | None = 9815268.0, currency: str | None = "EUR",
        deadline: datetime | None = DEADLINE, published: date = date(2026, 10, 1),
        cpv: tuple[str, ...] = ("35511000",), procedure: str | None = None,
        status: str = "open", ted_ref: str | None = None, related: str | None = None,
        title: str | None = None) -> int:
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw=buyer,
        title_original=title or f"Notice {native_id}", country=country, published_at=published,
        deadline_at=deadline, cpv_codes=list(cpv), status=status, is_defence=True, sig_cpv=True,
        value_amount=value, value_currency=currency if value is not None else None,
        procedure_identifier=procedure, ted_ref=ted_ref, related_native_id=related)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    # attributes are not archived; written like the repair tools do
    conn.execute("UPDATE opportunity SET procedure_identifier = %s WHERE id = %s", (procedure, oid))
    conn.commit()
    return oid


def row(conn, source: str, native_id: str) -> dict:
    return conn.execute(
        "SELECT o.ted_ref, o.twin_method, o.twin_confidence FROM opportunity o "
        "JOIN source s ON s.id = o.source_id WHERE s.code = %s AND o.native_id = %s",
        (source, native_id)).fetchone()


def listed(client, **params) -> list[str]:
    body = client.get("/v1/tenders", params={"status": "all", "scope": "all", **params}).json()
    return sorted(t["noticeId"] for t in body["items"])


# ----------------------------------------------------- the QA case

def test_the_frigate_engine_tender_is_listed_once_after_linking(conn, client):
    put(conn, "ted", "661706-2026", procedure=PROCEDURE)
    put(conn, "es_placsp", "2026/AR40U/00002845E", procedure=PROCEDURE)
    put(conn, "es_placsp", "2026/OTHER/1", value=100.0, cpv=("35400000",))
    assert listed(client) == ["2026/AR40U/00002845E", "2026/OTHER/1", "661706-2026"]

    counts = link_twins.run(conn, write=True)
    assert counts == {"stated_ted_ref": 0, "procedure_id": 1, "heuristic": 0}
    assert dict(row(conn, "es_placsp", "2026/AR40U/00002845E")) == {
        "ted_ref": "661706-2026", "twin_method": "procedure_id", "twin_confidence": 0.98}
    assert listed(client) == ["2026/OTHER/1", "661706-2026"]
    ted = next(t for t in client.get("/v1/tenders", params={"status": "all", "scope": "all"}
                                     ).json()["items"] if t["noticeId"] == "661706-2026")
    assert [s["source"] for s in ted["sameNotice"]] == ["es_placsp"]


def test_a_dry_run_writes_nothing_and_a_second_run_finds_nothing(conn):
    put(conn, "ted", "661706-2026", procedure=PROCEDURE)
    put(conn, "es_placsp", "2026/AR40U/00002845E", procedure=PROCEDURE)
    assert link_twins.run(conn)["procedure_id"] == 1
    assert row(conn, "es_placsp", "2026/AR40U/00002845E")["ted_ref"] is None
    link_twins.run(conn, write=True)
    assert link_twins.run(conn, write=True) == {"stated_ted_ref": 0, "procedure_id": 0,
                                                 "heuristic": 0}
    versions = conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"]
    assert versions == 2          # a link is not a version-worthy fact


def test_the_identifier_compares_without_braces_or_capitals(conn):
    put(conn, "ted", "661706-2026", procedure=PROCEDURE)
    put(conn, "fr_boamp", "26-91603", procedure="{" + PROCEDURE.upper() + "}", country="FR")
    link_twins.run(conn, write=True, methods=("procedure_id",))
    assert row(conn, "fr_boamp", "26-91603")["ted_ref"] == "661706-2026"


def test_a_stated_ted_ref_is_never_replaced_and_is_recorded_as_stated(conn):
    put(conn, "ted", "111-2026", procedure="aaaaaaaa-0000-0000-0000-000000000001")
    put(conn, "ted", "222-2026", procedure=PROCEDURE)
    put(conn, "nl_tenderned", "443966", country="NL", ted_ref="111-2026", procedure=PROCEDURE)
    counts = link_twins.run(conn, write=True)
    assert counts["stated_ted_ref"] == 1 and counts["procedure_id"] == 0
    assert dict(row(conn, "nl_tenderned", "443966")) == {
        "ted_ref": "111-2026", "twin_method": "stated_ted_ref", "twin_confidence": 1.0}


def test_a_stated_reference_to_a_notice_we_do_not_hold_is_left_alone(conn):
    put(conn, "nl_tenderned", "443966", country="NL", ted_ref="123-2026")
    assert link_twins.run(conn, write=True)["stated_ted_ref"] == 0
    assert row(conn, "nl_tenderned", "443966")["twin_method"] is None


def test_the_call_and_its_corrigendum_share_a_procedure_and_the_newest_is_linked(conn):
    put(conn, "ted", "600001-2026", procedure=PROCEDURE, published=date(2026, 9, 1))
    put(conn, "ted", "611111-2026", procedure=PROCEDURE, published=date(2026, 9, 20))
    put(conn, "es_placsp", "2026/AR40U/1", procedure=PROCEDURE)
    link_twins.run(conn, write=True)
    assert row(conn, "es_placsp", "2026/AR40U/1")["ted_ref"] == "611111-2026"


def test_source_and_limit_narrow_the_run(conn):
    put(conn, "ted", "661706-2026", procedure=PROCEDURE)
    put(conn, "es_placsp", "A", procedure=PROCEDURE)
    put(conn, "fr_boamp", "B", procedure=PROCEDURE, country="FR")
    assert link_twins.run(conn, write=True, source="fr_boamp")["procedure_id"] == 1
    assert row(conn, "es_placsp", "A")["ted_ref"] is None
    assert link_twins.run(conn, write=True, limit=0)["procedure_id"] == 0
    assert link_twins.run(conn, write=True, limit=5)["procedure_id"] == 1
    assert row(conn, "es_placsp", "A")["ted_ref"] == "661706-2026"


# --------------------------------------------------------- heuristic

def test_the_heuristic_links_one_candidate_on_each_side(conn, client):
    put(conn, "ted", "661706-2026")
    put(conn, "es_placsp", "2026/AR40U/00002845E", published=date(2026, 9, 25))
    assert link_twins.run(conn, write=True)["heuristic"] == 1
    assert dict(row(conn, "es_placsp", "2026/AR40U/00002845E")) == {
        "ted_ref": "661706-2026", "twin_method": "heuristic", "twin_confidence": 0.9}
    assert listed(client) == ["661706-2026"]


def test_an_ambiguous_candidate_is_not_linked(conn, client):
    """Two TED notices could be the twin: neither is guessed, both stay listed."""
    put(conn, "ted", "661706-2026")
    put(conn, "ted", "661707-2026")                       # same buyer, value, deadline
    put(conn, "es_placsp", "2026/AR40U/00002845E")
    assert link_twins.run(conn, write=True)["heuristic"] == 0
    assert row(conn, "es_placsp", "2026/AR40U/00002845E")["ted_ref"] is None
    assert len(listed(client)) == 3


def test_two_national_notices_that_look_the_same_are_not_linked(conn):
    put(conn, "ted", "661706-2026")
    put(conn, "es_placsp", "2026/AR40U/1")
    put(conn, "es_placsp", "2026/AR40U/2")
    assert link_twins.run(conn, write=True)["heuristic"] == 0


@pytest.mark.parametrize("change", [
    {"value": 9815268.01},
    {"currency": "USD"},
    {"deadline": DEADLINE + timedelta(minutes=1)},
    {"published": date(2026, 9, 10)},                     # 21 days before the TED notice
    {"cpv": ("35400000",)},                               # shares only four digits
    {"buyer": "Otro organismo"},
    {"country": "PT"},
    {"value": None},
])
def test_one_difference_is_enough_not_to_link(conn, change):
    put(conn, "ted", "661706-2026", published=date(2026, 10, 1))
    put(conn, "es_placsp", "2026/AR40U/00002845E", **change)
    assert link_twins.run(conn, write=True, methods=("heuristic",))["heuristic"] == 0


def test_a_buyer_spelled_with_other_case_and_spacing_still_matches(conn):
    put(conn, "ted", "661706-2026")
    put(conn, "es_placsp", "2026/AR40U/00002845E", buyer="  " + BUYER.upper().replace(" ", "  "))
    assert link_twins.run(conn, write=True)["heuristic"] == 1


def test_a_row_with_an_identifier_is_never_matched_by_the_heuristic(conn):
    """It has a better key; if TED does not hold that procedure the notice is not on TED
    under it, and looking alike must not override the identifier."""
    put(conn, "ted", "661706-2026", procedure="aaaaaaaa-0000-0000-0000-000000000001")
    put(conn, "es_placsp", "2026/AR40U/00002845E", procedure=PROCEDURE)
    assert link_twins.run(conn, write=True) == {"stated_ted_ref": 0, "procedure_id": 0,
                                                 "heuristic": 0}


def test_a_rectificatif_does_not_make_its_parent_ambiguous(conn):
    put(conn, "ted", "661706-2026", country="FR")
    put(conn, "fr_boamp", "26-100", country="FR")
    put(conn, "fr_boamp", "26-101", country="FR", related="26-100")
    link_twins.run(conn, write=True)
    assert row(conn, "fr_boamp", "26-100")["twin_method"] == "heuristic"
    assert row(conn, "fr_boamp", "26-101")["twin_method"] == "heuristic"


# -------------------------------------------------- filling identifiers

def test_boamp_procedure_identifiers_are_read_from_the_landed_payloads(conn, fs_store, monkeypatch):
    record = {"idweb": "26-91603", "objet": "Marche", "nomacheteur": "Ministere des Armees",
              "dateparution": "2026-09-19", "datelimitereponse": "2026-12-15T12:00:00+00:00",
              "perimetre": "DIRECTIVE-81", "nature": "APPEL_OFFRE", "etat": "INITIAL",
              "contractfolderid": PROCEDURE.upper(), "donnees": "{}"}
    monkeypatch.setattr(boamp, "search", lambda params, **kw: iter([record]))
    pipeline.run_history("fr_boamp", date(2026, 9, 19), date(2026, 9, 19))
    conn.execute("UPDATE opportunity SET procedure_identifier = NULL")
    conn.commit()
    link = link_twins.fill_from_raw
    assert link(conn, build_store(), write=False) == {"fr_boamp": 1}
    assert conn.execute("SELECT procedure_identifier FROM opportunity"
                        ).fetchone()["procedure_identifier"] is None
    link(conn, build_store(), write=True)
    assert conn.execute("SELECT procedure_identifier FROM opportunity"
                        ).fetchone()["procedure_identifier"] == PROCEDURE
    assert conn.execute("SELECT ted_ref FROM opportunity").fetchone()["ted_ref"] is None


def test_placsp_identifiers_are_filled_from_the_archives_without_inserting(conn, monkeypatch):
    put(conn, "es_placsp", "2026/AR40U/00002845E")
    put(conn, "es_placsp", "2026/HAS/1", procedure="bbbbbbbb-0000-0000-0000-000000000002")
    seen = []

    def archive(url, dataset, **kw):
        seen.append(url)
        for native_id, ident in (("2026/AR40U/00002845E", PROCEDURE),
                                 ("2026/HAS/1", PROCEDURE),
                                 ("2026/NOT/HELD", PROCEDURE)):
            yield Opportunity(source_code=dataset.source_code, native_id=native_id,
                              buyer_name_raw="x", title_original="x", procedure_identifier=ident)

    monkeypatch.setattr(placsp, "fetch_archive", archive)
    assert link_twins.fill_from_archives(conn, [(2026, 10)], write=False, sleep=0) == 1
    assert row(conn, "es_placsp", "2026/AR40U/00002845E")["ted_ref"] is None
    assert link_twins.fill_from_archives(conn, [(2026, 10)], write=True, sleep=0) == 1
    ids = {r["native_id"]: r["procedure_identifier"] for r in conn.execute(
        "SELECT native_id, procedure_identifier FROM opportunity")}
    assert ids == {"2026/AR40U/00002845E": PROCEDURE,
                   "2026/HAS/1": "bbbbbbbb-0000-0000-0000-000000000002"}
    assert len(set(seen)) == 2     # one archive per dataset
    assert link_twins.fill_from_archives(conn, [(2026, 10)], write=True, sleep=0) == 0


def test_months_are_counted_across_a_year_end():
    assert link_twins._months((2026, 11), (2027, 2)) == [(2026, 11), (2026, 12), (2027, 1),
                                                         (2027, 2)]


def test_the_migration_adds_both_columns(conn):
    cols = {r["column_name"]: r["data_type"] for r in conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'opportunity' AND column_name LIKE 'twin_%'")}
    assert cols == {"twin_method": "text", "twin_confidence": "real"}
    assert link_ted.LINK_COLUMNS[-1] == "procedure_identifier"


def test_the_command_is_a_dry_run_unless_told_to_write(conn, caplog):
    caplog.set_level("INFO", logger="link_twins")
    put(conn, "ted", "661706-2026", procedure=PROCEDURE)
    put(conn, "es_placsp", "2026/AR40U/00002845E", procedure=PROCEDURE)
    assert link_twins.main([]) == 0
    assert row(conn, "es_placsp", "2026/AR40U/00002845E")["ted_ref"] is None
    assert any("would be linked" in m for m in caplog.messages)
    assert link_twins.main(["--yes", "--method", "procedure_id"]) == 0
    assert row(conn, "es_placsp", "2026/AR40U/00002845E")["ted_ref"] == "661706-2026"


# ----------------------------------------------------- WP-138: a framework's call-offs

CALL_OFFS = "9771a463-435b-41cf-be4c-7407b6ae7adf"
TED_HEAD = "Deutschland – Überlassung von Personal einschließlich Zeitarbeitskräfte – "


def call_offs(conn) -> dict[str, int]:
    """Two call-offs of one staffing framework, each on TED and in a national source; the second call-off's national
    copy keeps the buyer's line break and double space. All four are award notices of one procedure."""
    common = {"procedure": CALL_OFFS, "status": "awarded", "deadline": None, "country": "FR"}
    return {"t1": put(conn, "ted", "674255-2026", title=TED_HEAD + "2000281264 ANÜ Operations Specialist (P4) Bonn",
                      published=date(2026, 10, 1), value=27.1, **common),
            "t2": put(conn, "ted", "689828-2026", title=TED_HEAD + "2000284335 ANÜ Senior Project Manager (P9) Berlin",
                      published=date(2026, 10, 7), value=74.13, **common),
            "n1": put(conn, "fr_boamp", "N-1", title="2000281264 ANÜ Operations Specialist (P4) Bonn",
                      published=date(2026, 9, 30), value=27.1, **common),
            "n2": put(conn, "fr_boamp", "N-2", title="2000284335 ANÜ Senior  Project Manager\n(P9) Berlin",
                      published=date(2026, 10, 6), value=74.13, **common)}


def test_each_call_off_is_linked_to_its_own_ted_notice_and_each_is_listed_once(conn, client):
    """r8-data problem 2: every call-off of BWI's framework named the newest TED notice of the procedure, listed the
    other call-offs as "the same notice" and borrowed that notice's value. Each is its own notice."""
    rows = call_offs(conn)
    assert link_twins.run(conn, write=True)["procedure_id"] == 2
    assert row(conn, "fr_boamp", "N-1")["ted_ref"] == "674255-2026"
    assert row(conn, "fr_boamp", "N-2")["ted_ref"] == "689828-2026"
    # both TED call-offs are listed (two titles: two notices), each national copy under its own
    assert listed(client) == ["674255-2026", "689828-2026"]
    page = client.get(f"/v1/tenders/{rows['n1']}").json()
    assert [(s["source"], s["noticeId"]) for s in page["sameNotice"]] == [("ted", "674255-2026")]


def test_old_links_to_the_newest_call_off_move_to_the_call_offs_own_notice(conn, client):
    rows = call_offs(conn)
    for oid in (rows["n1"], rows["n2"]):          # what link_procedure wrote before WP-138
        conn.execute("UPDATE opportunity SET ted_ref = '689828-2026', twin_method = 'procedure_id' WHERE id = %s",
                     (oid,))
    conn.commit()
    # two call-offs of one source naming one TED notice are not each other's "same notice"
    assert [s["noticeId"] for s in client.get(f"/v1/tenders/{rows['n1']}").json()["sameNotice"]] == ["689828-2026"]
    stated = put(conn, "nl_tenderned", "443966", title="2000281264 ANÜ Operations Specialist (P4) Bonn",
                 procedure=CALL_OFFS, status="awarded", ted_ref="689828-2026", country="FR")
    assert link_twins.relink_procedure(conn) == 1                       # a dry run writes nothing
    assert row(conn, "fr_boamp", "N-1")["ted_ref"] == "689828-2026"
    assert link_twins.relink_procedure(conn, write=True) == 1
    assert row(conn, "fr_boamp", "N-1")["ted_ref"] == "674255-2026"
    assert row(conn, "fr_boamp", "N-2")["ted_ref"] == "689828-2026"     # already its own notice
    # a link the source stated is never moved
    assert conn.execute("SELECT ted_ref FROM opportunity WHERE id = %s", (stated,)).fetchone()["ted_ref"] == "689828-2026"
    assert link_twins.relink_procedure(conn, write=True) == 0            # a second run finds nothing
    assert link_twins.main(["--relink", "--method", "procedure_id"]) == 0
