"""Verification round of 13 October 2026, package WP-2, against a real Postgres: a
defence body's new notices no longer land on an unflagged namesake (coverage:C1), a
ministry's registration number no longer collapses its services (correctness:D8), the
tool that corrects the organisations already held, and the serving rows that read them.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import db, reprocess
from dgate.normalise import Opportunity
from dgate.ops import buyer_cleanup
from dgate.pipeline import _finalise

pytestmark = pytest.mark.integration

MINISTRY_SIRET = "11000201100044"       # the Ministry of the Armed Forces, as BOAMP states it


def _count(conn, sql, *params) -> int:
    return conn.execute(sql, params).fetchone()["n"]


def _flag(conn, org_id, source="derived_rule", confidence=0.95):
    conn.execute(
        """UPDATE organisation SET is_defence_buyer = TRUE, defence_buyer_source = %s,
                  defence_buyer_confidence = %s WHERE id = %s""",
        (source, confidence, org_id))
    conn.commit()


def _org(conn, org_id):
    return conn.execute("SELECT * FROM organisation WHERE id = %s", (org_id,)).fetchone()


def _notice(conn, native_id, buyer, country, cpv=(), identifier=None, source="ted"):
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=native_id,
        country=country, published_at=date(2026, 10, 1), cpv_codes=list(cpv),
        buyer_identifier=identifier, status="open")
    src = db.source_id(conn, source)
    opp = _finalise(conn, opp, src)
    oid = None
    if opp.is_defence:
        oid, _ = db.upsert_opportunity(conn, opp, f"hash-{native_id}", src)
    conn.commit()
    return oid, opp


# ------------------------------------------------------- C1: new notices

def test_a_new_notice_with_another_number_inherits_the_flag_of_its_namesake(conn):
    """BE Ministere de la Defense: one flagged row (suffix 6405), then notices that state
    6401 or 6409. They used to file under new, unflagged organisations."""
    flagged = db.resolve_organisation(conn, "Ministère de la Défense", "BE",
                                      identifier="0308357555 6405")
    _flag(conn, flagged)
    _, opp = _notice(conn, "100-2026", "Ministère de la Défense", "BE", cpv=["90911100"],
                     identifier="0308357555 6401")
    assert opp.sig_buyer and opp.is_defence and opp.buyer_class == "defence"
    other = opp.buyer_org_id
    assert other != flagged
    row = _org(conn, other)
    assert row["is_defence_buyer"] and row["defence_buyer_source"] == "namesake"
    assert row["defence_buyer_reason"] == f"same name as organisation {flagged}"
    assert float(row["defence_buyer_confidence"]) == db.CONF_NAMESAKE_FLAG
    # the pair is on record for a person, as before
    assert _count(conn, "SELECT count(*) n FROM organisation_merge_candidate "
                        "WHERE match_method = 'same_name_different_identifier'") == 1


def test_an_unflagged_duplicate_that_already_exists_is_flagged_when_it_is_reached(conn):
    flagged = db.resolve_organisation(conn, "Irish Defence Forces", "IE", identifier="6517956C")
    dup = db.resolve_organisation(conn, "Irish Defence Forces", "IE", identifier="6517596C")
    assert dup != flagged and not _org(conn, dup)["is_defence_buyer"]
    _flag(conn, flagged)
    _, opp = _notice(conn, "7-2026", "Irish Defence Forces", "IE", cpv=["60100000"],
                     identifier="6517596C")
    assert opp.buyer_org_id == dup and opp.sig_buyer
    assert _org(conn, dup)["defence_buyer_source"] == "namesake"


def test_a_namesake_in_another_country_is_not_inherited_from(conn):
    flagged = db.resolve_organisation(conn, "Ministerstvo obrany", "CZ")
    _flag(conn, flagged)
    other = db.resolve_organisation(conn, "Ministerstvo obrany", "SK")
    assert not _org(conn, other)["is_defence_buyer"]


def test_the_ministrys_number_no_longer_collapses_its_services(conn):
    """D8: 'minarm air siae' holds the Ministry's SIRET; the other services state it too."""
    holder = db.resolve_organisation(conn, "MINARM/AIR/SIAé", "FR", identifier=MINISTRY_SIRET)
    _flag(conn, holder)
    pfc = db.resolve_organisation(conn, "MINARM/SCA/PFC-RBT", "FR", identifier=MINISTRY_SIRET)
    lyon = db.resolve_organisation(conn, "MINARM/SGA/DCSID/ESID Lyon", "FR",
                                   identifier=MINISTRY_SIRET)
    toulon = db.resolve_organisation(conn, "MINARM/SGA/DCSID/ESID TOULON", "FR",
                                     identifier=MINISTRY_SIRET)
    assert len({holder, pfc, lyon, toulon}) == 4
    # the number stays with its first holder, and the others do not take it
    held = conn.execute("SELECT id FROM organisation WHERE national_reg_no = %s",
                        (MINISTRY_SIRET,)).fetchall()
    assert [r["id"] for r in held] == [holder]
    # and what the guard keeps apart is noted for a person
    assert _count(conn, "SELECT count(*) n FROM organisation_merge_candidate "
                        "WHERE match_method = 'identifier_name_mismatch'") >= 3
    # a spelling variant of the holder itself is still reached by the number
    again = db.resolve_organisation(conn, "Minarm Air SIAé - Ministère des Armées", "FR",
                                    identifier=MINISTRY_SIRET)
    assert again == holder


def test_sid_sud_est_with_its_own_number_is_a_flagged_body_of_its_own(conn):
    """The history rows of 'SID Sud-Est' sit on the Ministry's organisation (merged by
    identifier on 12 October); its notices since 19 September state a SIRET of its own and
    were filed under a new unflagged organisation."""
    holder = db.resolve_organisation(conn, "MINARM/AIR/SIAé", "FR", identifier=MINISTRY_SIRET)
    sid = db.resolve_organisation(conn, "SID Sud-Est", "FR")
    db.merge_organisations(conn, holder, sid, method="identifier", confidence=0.95,
                           evidence="identifier 11000201100044 in FR", detected_by="test")
    _flag(conn, holder)
    _, opp = _notice(conn, "26-91277", "SID Sud-Est", "FR", cpv=["45000000"],
                     identifier="SIRET 110 002 011 00170")
    assert opp.is_defence and opp.sig_buyer
    assert opp.buyer_org_id not in (holder, sid)
    assert _org(conn, opp.buyer_org_id)["is_defence_buyer"]


# --------------------------------------------------------------- the tool

def _plan_fixture(conn):
    """A flagged ministry with: a number-less namesake, a namesake with another number,
    and a namesake of an umbrella holder."""
    keep = db.resolve_organisation(conn, "Ministere de la Defense", "BE", identifier="03083575556405")
    dup_plain = conn.execute(
        "INSERT INTO organisation (canonical_name, country) VALUES (%s, %s) RETURNING id",
        ("ministere de la defense", "BE")).fetchone()["id"]
    dup_number = conn.execute(
        "INSERT INTO organisation (canonical_name, country, national_reg_no) "
        "VALUES (%s, %s, %s) RETURNING id",
        ("ministere de la defense", "BE", "03083575556401")).fetchone()["id"]
    conn.commit()
    _flag(conn, keep)
    # a notice on each, so the move is visible
    for n, org in enumerate((dup_plain, dup_number)):
        opp = Opportunity(source_code="ted", native_id=f"BE-{n}", buyer_name_raw="x",
                          title_original="t", country="BE", published_at=date(2026, 10, 1),
                          cpv_codes=["35330000"], is_defence=True, status="open")
        opp.buyer_org_id = org
        db.upsert_opportunity(conn, opp, f"h{n}", db.source_id(conn, "ted"))
    conn.commit()
    return keep, dup_plain, dup_number


def test_the_tool_merges_what_can_be_merged_and_flags_the_rest(conn):
    keep, plain, numbered = _plan_fixture(conn)

    dry = buyer_cleanup.run(conn, apply=False, out=lambda *_: None)
    assert dry["namesakes"] == 2
    assert not _org(conn, plain)["merged_into"]                    # a dry run writes nothing

    done = buyer_cleanup.run(conn, apply=True, out=lambda *_: None)
    assert (done["merged"], done["flagged"], done["failed"]) == (1, 1, 0)
    merged = _org(conn, plain)
    assert merged["merged_into"] == keep
    assert (merged["merge_method"], float(merged["merge_confidence"])) == ("namesake_flagged", 0.95)
    assert _org(conn, numbered)["is_defence_buyer"] and not _org(conn, numbered)["merged_into"]
    assert _org(conn, numbered)["defence_buyer_source"] == "namesake"
    assert _count(conn, "SELECT count(*) n FROM opportunity WHERE buyer_org_id = %s", keep) == 1
    # nothing deleted; no version touched
    assert _count(conn, "SELECT count(*) n FROM organisation") == 3
    assert _count(conn, "SELECT count(*) n FROM opportunity_version WHERE valid_to IS NOT NULL") == 0

    # idempotent
    again = buyer_cleanup.run(conn, apply=True, out=lambda *_: None)
    assert (again["namesakes"], again["merged"], again["flagged"]) == (0, 0, 0)


def test_the_tool_can_merge_namesakes_that_state_another_number_when_asked(conn):
    keep, plain, numbered = _plan_fixture(conn)
    done = buyer_cleanup.run(conn, apply=True, merge_conflicting=True, out=lambda *_: None)
    assert done["merged"] == 2 and done["flagged"] == 0
    absorbed = _org(conn, numbered)
    assert absorbed["merged_into"] == keep and absorbed["national_reg_no"] == "03083575556401"
    # a notice that states the absorbed row's number still reaches the survivor
    assert db.resolve_organisation(conn, "Ministère de la Défense", "BE",
                                   identifier="03083575556401") == keep


def test_the_tool_never_merges_into_a_shared_identifier_holder(conn):
    holder = db.resolve_organisation(conn, "MINARM/AIR/SIAé", "FR", identifier=MINISTRY_SIRET)
    service = db.resolve_organisation(conn, "MINARM/SGA/DCSID/ESID Lyon", "FR")
    namesake = conn.execute(
        "INSERT INTO organisation (canonical_name, country) VALUES (%s, %s) RETURNING id",
        ("minarm sga dcsid esid lyon", "FR")).fetchone()["id"]
    conn.commit()
    # the 12 October backfill's merge: a service filed under the Ministry's number
    db.merge_organisations(conn, holder, service, method="identifier", confidence=0.95,
                           evidence="identifier in FR", detected_by="test")
    _flag(conn, holder)

    report: list[str] = []
    done = buyer_cleanup.run(conn, apply=True, out=report.append)
    assert done["shared_identifier_holders"] == 1
    assert any(f"{holder}" in line and "1 absorbed" in line for line in report)
    row = _org(conn, namesake)
    assert row["is_defence_buyer"] and row["merged_into"] is None     # flagged, not merged
    assert _org(conn, service)["merged_into"] == holder               # history untouched


def test_the_tool_withdraws_a_derived_flag_the_rules_reject_and_only_that(conn, tmp_path,
                                                                           monkeypatch):
    coe = db.resolve_organisation(
        conn, "DGA Council of Europe Directorate General of Administration", "FR")
    dga = db.resolve_organisation(conn, "DGA/DO/S2A", "FR")
    seeded = db.resolve_organisation(conn, "Hand picked buyer", "FR")
    # flagged by an earlier version of the derived file; no rule matches it now, and a rule
    # that merely stopped matching is not a reason to withdraw a flag
    old = db.resolve_organisation(
        conn, "Direzione degli Armamenti Aeronautici e per l'Aeronavigabilità", "IT")
    for org in (coe, dga, old):
        _flag(conn, org)
    _flag(conn, seeded, source="derived_rule")
    (tmp_path / "defence_buyers_derived_FR.csv").write_text(
        "country,name,identifier,reason,confidence,reviewed\n"
        "FR,hand picked buyer,,military_unit,0.85,true\n", encoding="utf-8")
    monkeypatch.setattr(buyer_cleanup, "reviewed_names",
                        lambda directory=None: {("FR", "hand picked buyer")})

    rows = buyer_cleanup.rejected_flags(conn)
    assert [r["id"] for r in rows] == [coe]
    buyer_cleanup.run(conn, apply=True, out=lambda *_: None)
    gone = _org(conn, coe)
    assert not gone["is_defence_buyer"] and gone["defence_buyer_source"] == "unflagged_by_rule"
    assert "was derived_rule" in gone["defence_buyer_reason"]
    assert all(_org(conn, o)["is_defence_buyer"] for o in (dga, seeded, old))
    assert buyer_cleanup.run(conn, apply=True, out=lambda *_: None)["rejected_flags"] == 0


# ------------------------------------- the serving rows read all of it

def test_reclassify_serving_follows_the_flag_the_class_and_the_new_codes(conn):
    """A stored row whose organisation is now flagged becomes a buyer-signal row of class
    `defence`; a municipal military CPV stays demoted; the repair CPVs added on 13 October
    are military; and a road authority's 35710000 leaves core. No version is written."""
    flagged = db.resolve_organisation(conn, "Some Unnamed Depot", "HU")
    _flag(conn, flagged)

    def stored(native_id, buyer, country, cpv, org=None):
        opp = Opportunity(source_code="ted", native_id=native_id, buyer_name_raw=buyer,
                          title_original=native_id, country=country,
                          published_at=date(2026, 10, 1), cpv_codes=list(cpv), is_defence=True,
                          sig_cpv=True, status="open")
        opp.buyer_org_id = org or db.resolve_organisation(conn, buyer, country)
        oid, _ = db.upsert_opportunity(conn, opp, f"h-{native_id}", db.source_id(conn, "ted"))
        # the row as it was left before this package: no buyer signal, class `other`
        conn.execute("UPDATE opportunity SET sig_buyer = FALSE, buyer_class = 'other', "
                     "sig_cpv_military = FALSE, sig_cpv_adjacent = FALSE, dual_use = FALSE "
                     "WHERE id = %s", (oid,))
        conn.commit()
        return oid

    depot = stored("D-1", "Some Unnamed Depot", "HU", ["90911100"], org=flagged)
    road = stored("R-1", "Generalny Dyrektor Dróg Krajowych i Autostrad", "PL", ["35710000"])
    repair = stored("V-1", "Zakład Naprawczy Sp. z o.o.", "PL", ["50630000"])
    unknown = stored("U-1", "Some Engineering Works Ltd", "GB", ["35613000"])
    town = stored("T-1", "Ville d'Orléans", "FR", ["35321100"])
    versions = _count(conn, "SELECT count(*) n FROM opportunity_version")

    def row(oid):
        return conn.execute(
            "SELECT is_defence, sig_buyer, sig_cpv_military, sig_cpv_adjacent, dual_use, "
            "buyer_class FROM opportunity WHERE id = %s", (oid,)).fetchone()

    dry = reprocess.reclassify_serving(conn, dry_run=True)
    assert dry["changed"] == 5 and row(depot)["buyer_class"] == "other"       # nothing written
    reprocess.reclassify_serving(conn, dry_run=False)

    assert (row(depot)["sig_buyer"], row(depot)["buyer_class"]) == (True, "defence")
    assert row(road)["dual_use"] and row(road)["buyer_class"] == "infrastructure"
    assert row(repair)["sig_cpv_adjacent"] and row(repair)["sig_cpv_military"]
    assert not row(repair)["dual_use"]                    # a company, class other, code adjacent
    assert row(unknown)["dual_use"] and row(unknown)["buyer_class"] == "other"
    assert row(town)["dual_use"] and row(town)["buyer_class"] == "municipal"
    assert _count(conn, "SELECT count(*) n FROM opportunity_version") == versions
    assert reprocess.reclassify_serving(conn, dry_run=False)["changed"] == 0
