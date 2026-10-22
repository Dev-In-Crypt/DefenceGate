"""WP-72 against a real Postgres: a twin carries relevance only when it is relevant on its own (and
the ops module that clears the stored links), calls served by the status their dates settle, the
German notice link through the re-map, the merge candidates a shared identifier proves, and the
tenders list of one country or one buyer with the plain `=` filter."""

from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline
from dgate.classify import own_relevance_sql, relevant_on_its_own
from dgate.normalise import Call, Opportunity, from_de_bkms, strip_personal_data
from dgate.ops import accept_merge_candidates, linked_defence, remap_source
from dgate.rawstore import build_store, storage_key
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "de_bkms"


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield
    config.reset_cache()


def put(conn, source: str, native_id: str, *, ted_ref: str | None = None, procedure: str | None = None,
        buyer: str = "Generalna Dyrekcja Drog Krajowych i Autostrad", country: str = "PL",
        **signals) -> int:
    sig = dict(is_defence=False, sig_legal_basis=False, sig_cpv_military=False, sig_buyer=False,
               dual_use=False, buyer_class=None, sig_linked_defence=False)
    sig.update(signals)
    opp = Opportunity(source_code=source, native_id=native_id, buyer_name_raw=buyer, country=country,
                      title_original=f"{source} {native_id}", published_at=date(2026, 5, 4),
                      cpv_codes=["45233120", "35710000"], status="open", ted_ref=ted_ref, **sig)
    src = db.source_id(conn, source)
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country, src_id=src)
    oid, _ = db.upsert_opportunity(conn, opp, f"h-{source}-{native_id}", src)
    conn.execute(
        """UPDATE opportunity SET procedure_identifier = %s, sig_cpv_military = %s, dual_use = %s,
                  buyer_class = %s, sig_linked_defence = %s WHERE id = %s""",
        (procedure, sig["sig_cpv_military"], sig["dual_use"], sig["buyer_class"],
         sig["sig_linked_defence"], oid))
    conn.commit()
    return oid


DUAL_USE = dict(is_defence=True, sig_cpv_military=True, dual_use=True, buyer_class="other")
CORE = dict(is_defence=True, sig_legal_basis=True, buyer_class="defence")


def national(native_id: str, ted_ref: str | None = None, procedure: str | None = None) -> Opportunity:
    return Opportunity(source_code="pl_ezam", native_id=native_id, country="PL",
                       buyer_name_raw="GDDKiA", title_original="Budowa autostrady A2",
                       ted_ref=ted_ref, procedure_identifier=procedure)


# ------------------------------------------------------------- (2) the twin rule

def test_a_dual_use_ted_twin_does_not_lift_its_national_copy(conn):
    put(conn, "ted", "100-2026", **DUAL_USE)
    put(conn, "ted", "200-2026", **CORE)
    put(conn, "ted", "300-2026", procedure="ABC-1", **CORE)
    assert pipeline._twin_is_defence(conn, national("2026/BZP 1", ted_ref="100-2026")) is False
    assert pipeline._twin_is_defence(conn, national("2026/BZP 2", ted_ref="200-2026")) is True
    assert pipeline._twin_is_defence(conn, national("2026/BZP 3", procedure="{abc-1}")) is True


def test_two_twins_do_not_qualify_each_other_through_their_links(conn):
    # the national row is relevant only through its link: it does not count back for the TED row
    put(conn, "pl_ezam", "2026/BZP 4", ted_ref="400-2026", is_defence=True, sig_linked_defence=True)
    ted = Opportunity(source_code="ted", native_id="400-2026", country="PL", buyer_name_raw="x",
                      title_original="x")
    assert pipeline._twin_is_defence(conn, ted) is False
    put(conn, "pl_ezam", "2026/BZP 5", ted_ref="500-2026", is_defence=True, sig_buyer=True)
    assert pipeline._twin_is_defence(conn, replace(ted, native_id="500-2026")) is True


def test_the_sql_and_the_python_rule_agree_on_every_signal_combination(conn):
    combos = list(itertools.product([False, True], [False, True], [False, True], [False, True],
                                     [None, "defence", "security", "municipal", "other"]))
    for n, (lb, mil, du, buyer, cls) in enumerate(combos):
        put(conn, "ted", f"{n}-2025", is_defence=True, sig_legal_basis=lb, sig_cpv_military=mil,
            dual_use=du and mil, sig_buyer=buyer, buyer_class=cls)
    got = {r["native_id"]: r["own"] for r in conn.execute(
        f"SELECT o.native_id, {own_relevance_sql('o')} AS own FROM opportunity o").fetchall()}
    for n, (lb, mil, du, buyer, cls) in enumerate(combos):
        assert got[f"{n}-2025"] == relevant_on_its_own(
            legal_basis=lb, military_cpv=mil, dual_use=du and mil, buyer=buyer, buyer_class=cls), \
            (lb, mil, du, buyer, cls)


def test_the_ops_module_clears_the_stored_links_whose_twin_no_longer_counts(conn):
    put(conn, "ted", "100-2026", **DUAL_USE)
    put(conn, "ted", "200-2026", **CORE)
    gone = put(conn, "pl_ezam", "2026/BZP 1", ted_ref="100-2026", is_defence=True, sig_linked_defence=True)
    kept = put(conn, "pl_ezam", "2026/BZP 2", ted_ref="200-2026", is_defence=True, sig_linked_defence=True)
    listed = put(conn, "pl_ezam", "2026/BZP 3", ted_ref="100-2026", is_defence=True, sig_buyer=True,
                 sig_linked_defence=True)

    def state(oid):
        return conn.execute("SELECT is_defence, sig_linked_defence FROM opportunity WHERE id = %s",
                            (oid,)).fetchone()

    dry = linked_defence.run(conn, out=lambda *_: None)
    assert (dry["linked"], dry["kept"], dry["cleared"]) == (3, 1, 2)
    assert dry["by_source"] == {"pl_ezam": 2} and dry["leaves_defence"] == 1
    assert state(gone) == {"is_defence": True, "sig_linked_defence": True}       # dry run: nothing

    linked_defence.run(conn, apply=True, out=lambda *_: None)
    assert state(gone) == {"is_defence": False, "sig_linked_defence": False}
    assert state(listed) == {"is_defence": True, "sig_linked_defence": False}    # its buyer keeps it
    assert state(kept) == {"is_defence": True, "sig_linked_defence": True}
    assert conn.execute("SELECT count(*) AS n FROM opportunity_version").fetchone()["n"] == 5  # no version
    again = linked_defence.run(conn, apply=True, out=lambda *_: None)
    assert (again["linked"], again["cleared"]) == (1, 0)


# ------------------------------------------------------------- (3) calls

def _call(conn, native_id: str, *, status: str, opens: date | None, days: int) -> None:
    call = Call(programme_code="EDF", native_id=native_id, title=f"Topic {native_id}",
                topic_code=f"EDF-2026-{native_id}", status=status, regime="defence", opens_at=opens,
                deadline_at=datetime.now(timezone.utc) + timedelta(days=days))
    db.upsert_call(conn, call, f"hash-{native_id}", db.source_id(conn, "eu_portal"))
    conn.commit()


def test_calls_are_listed_by_the_status_their_dates_settle(client, conn):
    today = date.today()
    _call(conn, "opened", status="forthcoming", opens=today - timedelta(days=90), days=7)
    _call(conn, "later", status="forthcoming", opens=today + timedelta(days=30), days=60)
    _call(conn, "lapsed", status="forthcoming", opens=today - timedelta(days=60), days=-50)
    _call(conn, "stale-open", status="open", opens=None, days=-13)

    def ids(q):
        return [(c["native_id"], c["status"]) for c in client.get(f"/v1/calls{q}").json()]

    assert ids("") == [("opened", "open")]
    assert ids("?status=forthcoming") == [("later", "forthcoming")]
    assert ids("?status=closed") == [("lapsed", "closed"), ("stale-open", "closed")]
    one = client.get("/v1/calls").json()[0]["id"]
    assert client.get(f"/v1/calls/{one}").json()["status"] == "open"


# ------------------------------------------------------------- (4) the German notice link

def test_the_remap_gives_a_held_german_notice_its_link_once(conn, fs_store):
    conn.execute("DELETE FROM remap_marker")        # not in the truncated tables
    xml = (FIX / "cn_standard_defence.xml").read_text(encoding="utf-8").replace(
        "<cac:TenderingTerms>",
        "<cac:TenderingTerms><cac:CallForTendersDocumentReference><cac:Attachment><cac:ExternalReference>"
        "<cbc:URI>https://www.evergabe-online.de/tenderdetails.html?id=812345</cbc:URI>"
        "</cac:ExternalReference></cac:Attachment></cac:CallForTendersDocumentReference>", 1)
    raw = strip_personal_data({"file": "x-01.xml", "notice_id": None, "version": "01", "xml": xml})
    new = from_de_bkms(raw)
    digest = content_hash(raw)
    src = db.source_id(conn, "de_bkms")
    key = build_store().put(storage_key("de_bkms", new.native_id, content_hash=digest), raw)
    db.record_raw(conn, src, new.native_id, digest, key)
    oid, _ = db.upsert_opportunity(conn, replace(new, source_url=None), digest, src)   # as first mapped
    conn.commit()

    assert remap_source.run("de_bkms", write=False).versions == 1
    done = remap_source.run("de_bkms", write=True)
    assert (done.versions, done.failed, dict(done.by_field)) == (1, 0, {"source_url": 1})
    row = conn.execute("SELECT source_url, current_version FROM opportunity WHERE id = %s", (oid,)).fetchone()
    assert row == {"source_url": "https://www.evergabe-online.de/tenderdetails.html?id=812345",
                   "current_version": 2}
    assert remap_source.run("de_bkms", write=True).examined == 0


# ------------------------------------------------------------- (5) merge candidates

def _organisation(conn, name: str, *, reg: str | None = None, country: str = "FR") -> int:
    return conn.execute(
        """INSERT INTO organisation (canonical_name, country, confidence, review_status, national_reg_no)
           VALUES (%s, %s, 0.95, 'auto', %s) RETURNING id""", (name, country, reg)).fetchone()["id"]


def test_identifier_candidates_are_merged_with_method_and_confidence_and_the_rest_waits(conn):
    # companies: a commune and its mairie are public bodies, never merged by a number (WP-74)
    # since WP-76: a company SIRET (one beginning 2 is a local authority's) and names that agree
    commune = _organisation(conn, "chantiers de l atlantique", reg="44440103600121")
    mairie = _organisation(conn, "chantiers de l atlantique s a")
    a = _organisation(conn, "hopital a", reg="111")
    b = _organisation(conn, "hopital a site b", reg="222")
    x = _organisation(conn, "service x")
    y = _organisation(conn, "service x bis")
    db.add_merge_candidate(conn, commune, mairie, method="identifier", confidence=0.97,
                           evidence="same SIRET", detected_by="test")
    db.add_merge_candidate(conn, a, b, method="identifier", confidence=0.97,
                           evidence="conflict", detected_by="test")
    db.add_merge_candidate(conn, x, y, method="trigram", confidence=0.99,
                           evidence="similar", detected_by="test")
    db.add_merge_candidate(conn, x, y, method="identifier", confidence=0.95,
                           evidence="weaker", detected_by="test")
    conn.commit()

    dry = accept_merge_candidates.run(conn, out=lambda *_: None)
    assert (dry["strong_candidates"], dry["accepted_candidates"], dry["rows_to_merge"]) == (2, 1, 1)
    assert dry["refused"] == {"different_reg": 1} and len(dry["sample"]) == 1
    assert conn.execute("SELECT count(*) AS n FROM organisation WHERE merged_into IS NOT NULL").fetchone()["n"] == 0

    done = accept_merge_candidates.run(conn, apply=True, out=lambda *_: None)
    assert done["merged"] == 1
    merged = conn.execute("SELECT id, merged_into, merge_method, merge_confidence FROM organisation "
                          "WHERE merged_into IS NOT NULL").fetchall()
    assert len(merged) == 1 and merged[0]["merge_method"] == "identifier+name"   # what agreed (WP-76)
    assert float(merged[0]["merge_confidence"]) == 0.98
    assert {merged[0]["id"], merged[0]["merged_into"]} == {commune, mairie}
    status = {(r["match_method"], float(r["confidence"])): r["status"] for r in conn.execute(
        "SELECT match_method, confidence, status FROM organisation_merge_candidate "
        "WHERE organisation_id <> %s OR candidate_org_id <> %s", (min(a, b), max(a, b))).fetchall()}
    assert status[("identifier", 0.97)] == "merged"
    assert status[("trigram", 0.99)] == "pending" and status[("identifier", 0.95)] == "pending"
    again = accept_merge_candidates.run(conn, apply=True, out=lambda *_: None)
    assert (again["accepted_candidates"], again["merged"]) == (0, 0)


# ------------------------------------------------------------- (1) the list filters

def test_the_list_of_one_country_and_of_a_buyer_family_returns_the_same_notices(client, conn):
    mt = put(conn, "ted", "1-2026", country="MT", buyer="Armed Forces of Malta", **CORE)
    put(conn, "ted", "2-2026", country="PL", **CORE)
    head = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (mt,)).fetchone()["buyer_org_id"]
    other = put(conn, "ted", "3-2026", country="MT", buyer="AFM Procurement Branch", **CORE)
    member = conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s", (other,)).fetchone()["buyer_org_id"]

    def natives(q):
        return sorted(i["noticeId"] for i in client.get(f"/v1/tenders?status=all&{q}").json()["items"])

    assert natives("country=MT") == ["1-2026", "3-2026"]
    assert natives("country=MT,PL") == ["1-2026", "2-2026", "3-2026"]
    assert natives(f"buyer={head}") == ["1-2026"]
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) "
                 "VALUES (%s, %s, 'test', 0.9)", (member, head))
    conn.commit()
    assert natives(f"buyer={head}") == natives(f"buyer={member}") == ["1-2026", "3-2026"]
