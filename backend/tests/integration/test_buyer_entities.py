"""Work package E, against a real Postgres: identifier-first resolution, merges that
delete nothing, the derived buyer list as a signal, the classification of the rows
already held, and the TED notices the current rules qualify.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from dgate import api, db, reprocess
from dgate.normalise import Opportunity, from_ted
from dgate.ops import backfill_buyer_identifiers as backfill
from dgate.ops import merge_candidates
from dgate.pipeline import _finalise, seed_buyers
from dgate.rawstore import FileRawStore, bundle_key, record_key
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration


def _count(conn, sql, *params) -> int:
    return conn.execute(sql, params).fetchone()["n"]


def _ingest(conn, source="ted", native_id="1-2026", buyer="Some Buyer", country="DE",
            cpv=(), legal=None, identifier=None, ted_ref=None, clearance=False):
    """Classify and archive one hand-built notice, as the pipeline would."""
    opp = Opportunity(
        source_code=source, native_id=native_id, buyer_name_raw=buyer, title_original=native_id,
        country=country, published_at=date(2026, 10, 1), cpv_codes=list(cpv),
        legal_basis=legal, buyer_identifier=identifier, ted_ref=ted_ref,
        security_clearance_required=clearance)
    src = db.source_id(conn, source)
    opp = _finalise(conn, opp, src)
    if not opp.is_defence:
        conn.commit()
        return None, opp
    oid, _ = db.upsert_opportunity(conn, opp, f"hash-{source}-{native_id}", src)
    conn.commit()
    return oid, opp


# ------------------------------------------------------ identifier first

def test_one_identifier_under_two_spellings_is_one_organisation(conn):
    a = db.resolve_organisation(conn, "Ministerstvo obrany", "CZ", identifier="00179906")
    b = db.resolve_organisation(conn, "Česká republika - Ministerstvo obrany", "CZ",
                                identifier="IČO 00179906")
    assert a == b
    org = conn.execute("SELECT national_reg_no, identifier_method FROM organisation WHERE id = %s",
                       (a,)).fetchone()
    assert (org["national_reg_no"], org["identifier_method"]) == ("00179906", "identifier")
    alias = conn.execute(
        "SELECT match_method, confidence FROM organisation_alias WHERE normalised_name = %s",
        ("ceska republika - ministerstvo obrany",)).fetchone()
    assert alias["match_method"] == "identifier" and float(alias["confidence"]) == 0.97


def test_a_new_identifier_attaches_to_the_organisation_the_name_resolves_to(conn):
    first = db.resolve_organisation(conn, "Gemeinde Westendorf", "DE")
    again = db.resolve_organisation(conn, "Gemeinde Westendorf", "DE", identifier="DE 226 852 359")
    assert first == again
    row = conn.execute(
        "SELECT national_reg_no, identifier_confidence FROM organisation WHERE id = %s",
        (first,)).fetchone()
    assert row["national_reg_no"] == "226852359"
    assert float(row["identifier_confidence"]) == 0.90


def test_the_same_name_with_another_identifier_is_another_body(conn):
    hessen = db.resolve_organisation(conn, "Gemeinde Neustadt", "DE", identifier="DE123456789")
    sachsen = db.resolve_organisation(conn, "Gemeinde Neustadt", "DE", identifier="DE987654321")
    assert hessen != sachsen
    # a notice that gives no number still lands on the first, as before
    assert db.resolve_organisation(conn, "Gemeinde Neustadt", "DE") == hessen
    # and each number finds its own body
    assert db.resolve_organisation(conn, "Neustadt Gemeinde", "DE",
                                   identifier="DE987654321") == sachsen
    pair = conn.execute("SELECT match_method FROM organisation_merge_candidate").fetchall()
    assert [r["match_method"] for r in pair] == ["same_name_different_identifier"]


def test_an_identifier_under_an_unrelated_name_is_not_trusted(conn):
    """A central purchasing body's number on a member's notice must not file the
    member under the purchasing body."""
    cpb = db.resolve_organisation(conn, "Zentrale Beschaffungsstelle Nord", "DE",
                                  identifier="DE246813579")
    member = db.resolve_organisation(conn, "Gemeinde Westendorf", "DE", identifier="DE246813579")
    assert member != cpb
    pair = conn.execute("SELECT match_method, status FROM organisation_merge_candidate").fetchall()
    assert [(r["match_method"], r["status"]) for r in pair] == [
        ("identifier_name_mismatch", "pending")]


def test_junk_identifiers_change_nothing(conn):
    a = db.resolve_organisation(conn, "Gemeinde Westendorf", "DE", identifier="COM")
    b = db.resolve_organisation(conn, "Gemeinde Westendorf", "DE", identifier="ORG-0001")
    assert a == b
    assert conn.execute("SELECT national_reg_no FROM organisation WHERE id = %s",
                        (a,)).fetchone()["national_reg_no"] is None


def test_a_name_nearly_equal_to_one_held_is_a_candidate_never_a_merge(conn):
    one = db.resolve_organisation(
        conn, "Wojewodzki Szpital Specjalistyczny im Jana Pawla II w Zamosciu", "PL")
    two = db.resolve_organisation(
        conn, "Wojewodzki Szpital Specjalistyczny im Jana Pawla II w Zamosciu 1", "PL")
    assert one != two
    rows = conn.execute("SELECT * FROM organisation_merge_candidate").fetchall()
    assert len(rows) == 1 and rows[0]["match_method"] == "trigram"
    assert float(rows[0]["confidence"]) >= 0.90 and rows[0]["status"] == "pending"
    assert (rows[0]["organisation_id"], rows[0]["candidate_org_id"]) == (one, two)


# ------------------------------------------------------------------ merges

def test_a_merge_keeps_every_row_and_points_everything_at_the_survivor(conn):
    keep = db.resolve_organisation(conn, "Ministerstvo obrany", "CZ")
    gone = db.resolve_organisation(conn, "Ministerstvo obrany CR", "CZ")
    oid, _ = _ingest(conn, native_id="9-2026", buyer="Ministerstvo obrany CR", country="CZ",
                     cpv=["35330000"])
    assert keep != gone
    moved = db.merge_organisations(conn, keep, gone, method="identifier", confidence=0.95,
                                   evidence="identifier 00179906 in CZ", detected_by="test")
    conn.commit()
    assert moved["notices"] == 1 and moved["aliases"] >= 1

    assert _count(conn, "SELECT count(*) n FROM organisation WHERE id IN (%s, %s)", keep, gone) == 2
    absorbed = conn.execute(
        "SELECT merged_into, merge_method, merge_confidence, merged_at FROM organisation WHERE id = %s",
        (gone,)).fetchone()
    assert absorbed["merged_into"] == keep and absorbed["merge_method"] == "identifier"
    assert float(absorbed["merge_confidence"]) == 0.95 and absorbed["merged_at"]
    assert conn.execute("SELECT buyer_org_id FROM opportunity WHERE id = %s",
                        (oid,)).fetchone()["buyer_org_id"] == keep
    alias = conn.execute(
        "SELECT organisation_id, prev_organisation_id FROM organisation_alias "
        "WHERE normalised_name = 'ministerstvo obrany cr'").fetchone()
    assert (alias["organisation_id"], alias["prev_organisation_id"]) == (keep, gone)
    # the archive still says what it said: the version payload keeps the id it had
    payload = conn.execute("SELECT payload FROM opportunity_version WHERE opportunity_id = %s",
                           (oid,)).fetchone()["payload"]
    assert payload["buyer_org_id"] == gone
    # the merge is on record as a decided candidate
    cand = conn.execute("SELECT status, match_method FROM organisation_merge_candidate").fetchone()
    assert (cand["status"], cand["match_method"]) == ("merged", "identifier")
    # and the name now resolves to the survivor
    assert db.resolve_organisation(conn, "Ministerstvo obrany CR", "CZ") == keep


def test_a_merge_carries_the_defence_buyer_flag_and_refuses_what_it_should(conn):
    keep = db.resolve_organisation(conn, "Baainbw", "DE")
    gone = db.resolve_organisation(conn, "Bundesamt fur Ausrustung", "DE")
    conn.execute("UPDATE organisation SET is_defence_buyer = TRUE WHERE id = %s", (gone,))
    other_country = db.resolve_organisation(conn, "Baainbw", "AT")
    with pytest.raises(ValueError):
        db.merge_organisations(conn, keep, other_country, method="identifier", confidence=0.9,
                               evidence="x", detected_by="test")
    with pytest.raises(ValueError):
        db.merge_organisations(conn, keep, keep, method="identifier", confidence=0.9,
                               evidence="x", detected_by="test")
    db.merge_organisations(conn, keep, gone, method="identifier", confidence=0.9,
                           evidence="x", detected_by="test")
    assert db.is_defence_buyer(conn, keep)
    with pytest.raises(ValueError):
        db.merge_organisations(conn, keep, gone, method="identifier", confidence=0.9,
                               evidence="x", detected_by="test")


def test_two_different_registered_numbers_are_never_merged(conn):
    a = db.resolve_organisation(conn, "Gemeinde Neustadt", "DE", identifier="DE123456789")
    b = db.resolve_organisation(conn, "Gemeinde Neustadt", "DE", identifier="DE987654321")
    with pytest.raises(ValueError):
        db.merge_organisations(conn, a, b, method="x", confidence=0.9, evidence="x",
                               detected_by="test")


# ----------------------------------------------- the identifier backfill

def _bundled_notice(i, name, ident, country="CZE"):
    return {"publication-number": f"{i}-2026", "buyer-name": {"ces": [name]},
            "buyer-identifier": [ident], "buyer-country": [country]}


def test_the_backfill_merges_organisations_that_state_one_identifier(conn, tmp_path):
    store = FileRawStore(tmp_path / "raw")
    spellings = ["Ministerstvo obrany", "Česká republika - Ministerstvo obrany",
                 "Ministerstvo obrany ČR", "Ministerstvo zdravotnictvi"]
    idents = ["00179906", "00179906", "IČO 00179906", "00024341"]
    bundle = bundle_key("ted", date(2026, 9, 1))
    store.put_records(bundle, [_bundled_notice(n, s, i) for n, (s, i) in
                               enumerate(zip(spellings, idents, strict=True))])
    src = db.source_id(conn, "ted")
    org_ids = []
    for n, name in enumerate(spellings):
        oid, opp = _ingest(conn, native_id=f"{n}-2026", buyer=name, country="CZ",
                           legal="32009L0081")
        org_ids.append(opp.buyer_org_id)
        db.record_raw(conn, src, f"{n}-2026", f"h{n}", record_key(bundle, n))
    conn.commit()
    assert len(set(org_ids)) == 4

    lines: list[str] = []
    dry = backfill.run(conn, store, apply=False, out=lines.append)
    assert dry == {"merged_groups": 0, "merged_orgs": 0, "attached": 0, "candidates": 0}
    assert _count(conn, "SELECT count(*) n FROM organisation WHERE merged_into IS NOT NULL") == 0
    text = "\n".join(lines)
    assert "identifiers shared by two or more organisations: 1" in text
    assert "merge: 1 groups, 2 organisation rows become aliases" in text
    assert "dry run: nothing written" in text

    done = backfill.run(conn, store, apply=True, out=lambda *_: None)
    assert (done["merged_groups"], done["merged_orgs"]) == (1, 2)
    live = conn.execute("SELECT id, national_reg_no FROM organisation "
                        "WHERE merged_into IS NULL AND country = 'CZ' ORDER BY id").fetchall()
    assert len(live) == 2
    assert {r["national_reg_no"] for r in live} == {"00179906", "00024341"}
    assert _count(conn, "SELECT count(*) n FROM organisation") >= 4     # nothing deleted
    assert _count(conn, "SELECT count(DISTINCT buyer_org_id) n FROM opportunity") == 2
    # re-running finds nothing more to do
    again = backfill.run(conn, store, apply=True, out=lambda *_: None)
    assert again["merged_orgs"] == 0


def _land(conn, store, bundle, names, ident, start=0):
    """Hand-built notices of one identifier under several spellings, archived and landed."""
    src = db.source_id(conn, "ted")
    store.put_records(bundle, [_bundled_notice(start + n, s, ident)
                               for n, s in enumerate(names)])
    org_ids = []
    for n, name in enumerate(names, start):
        _, opp = _ingest(conn, native_id=f"{n}-2026", buyer=name, country="CZ",
                         legal="32009L0081")
        org_ids.append(opp.buyer_org_id)
        db.record_raw(conn, src, f"{n}-2026", f"h{n}", record_key(bundle, n - start))
    conn.commit()
    return org_ids


def test_one_group_that_cannot_be_merged_does_not_end_the_run(conn, tmp_path):
    """Review finding of 13 October 2026: `merge_organisations` raises for two different
    registered numbers, and the one exception rolled back an hour of merges. The member
    that carries another number is left out, the rest of its group and the other groups
    are merged, and each group is committed on its own."""
    store = FileRawStore(tmp_path / "raw")
    # the larger group first: three spellings, one of which carries another number
    first = _land(conn, store, bundle_key("ted", date(2026, 9, 1)),
                  ["Ministerstvo obrany", "Ceska republika - Ministerstvo obrany",
                   "Ministerstvo obrany CR"], "13572468")
    second = _land(conn, store, bundle_key("ted", date(2026, 9, 2)),
                   ["Ministerstvo zdravotnictvi", "Ceske Ministerstvo zdravotnictvi"],
                   "24681357", start=10)
    other_number = first[1]
    conn.execute("UPDATE organisation SET national_reg_no = '99999999' WHERE id = %s",
                 (other_number,))
    conn.commit()

    done = backfill.run(conn, store, apply=True, out=lambda *_: None)

    assert done["failed_groups"] == 0 and done["skipped"] == 1
    assert (done["merged_groups"], done["merged_orgs"]) == (2, 2)
    row = conn.execute("SELECT merged_into FROM organisation WHERE id = %s",
                       (other_number,)).fetchone()
    assert row["merged_into"] is None, "the body with another number stays itself"
    merged = {r["id"] for r in conn.execute(
        "SELECT id FROM organisation WHERE merged_into IS NOT NULL").fetchall()}
    assert len(merged) == 2 and merged & set(first) and merged & set(second)


def test_an_organisation_merged_since_the_plan_was_made_is_skipped(conn, tmp_path, monkeypatch):
    store = FileRawStore(tmp_path / "raw")
    ids = _land(conn, store, bundle_key("ted", date(2026, 9, 1)),
                ["Ministerstvo obrany", "Ceska republika - Ministerstvo obrany",
                 "Ministerstvo obrany CR"], "13572468")
    real = backfill.build_groups

    def planned_then_taken(*args, **kwargs):
        groups, singles, stats = real(*args, **kwargs)
        group = groups[0]
        db.merge_organisations(conn, group.survivor.id, group.absorbed[0].id,
                               method="identifier", confidence=0.9,
                               evidence="merged by someone else",
                               detected_by="test")
        return groups, singles, stats

    monkeypatch.setattr(backfill, "build_groups", planned_then_taken)
    done = backfill.run(conn, store, apply=True, out=lambda *_: None)
    assert done["failed_groups"] == 0 and done["skipped"] == 1
    assert done["merged_orgs"] == 1, "only the one that was still free"
    assert conn.execute("SELECT count(*) n FROM organisation WHERE merged_into IS NOT NULL"
                        ).fetchone()["n"] == 2
    assert len(ids) == 3


def test_a_group_whose_names_share_nothing_is_written_as_a_candidate(conn, tmp_path):
    store = FileRawStore(tmp_path / "raw")
    bundle = bundle_key("ted", date(2026, 9, 2))
    names = ["Ministerstvo obrany", "Krajska nemocnice Liberec"]
    store.put_records(bundle, [_bundled_notice(n, s, "12345678") for n, s in enumerate(names)])
    src = db.source_id(conn, "ted")
    for n, name in enumerate(names):
        _ingest(conn, native_id=f"{n}-2026", buyer=name, country="CZ", legal="32009L0081")
        db.record_raw(conn, src, f"{n}-2026", f"h{n}", record_key(bundle, n))
    conn.commit()
    done = backfill.run(conn, store, apply=True, out=lambda *_: None)
    assert done["merged_orgs"] == 0 and done["candidates"] == 1
    assert _count(conn, "SELECT count(*) n FROM organisation WHERE merged_into IS NOT NULL") == 0


def test_the_compatible_names_of_a_group_merge_and_only_the_rest_wait(conn, tmp_path):
    store = FileRawStore(tmp_path / "raw")
    bundle = bundle_key("ted", date(2026, 9, 3))
    names = ["Ministerstvo obrany", "Ceska republika - Ministerstvo obrany",
             "Krajska nemocnice Liberec"]
    store.put_records(bundle, [_bundled_notice(n, s, "12345678") for n, s in enumerate(names)])
    src = db.source_id(conn, "ted")
    for n, name in enumerate(names):
        _ingest(conn, native_id=f"{n}-2026", buyer=name, country="CZ", legal="32009L0081")
        db.record_raw(conn, src, f"{n}-2026", f"h{n}", record_key(bundle, n))
    conn.commit()
    done = backfill.run(conn, store, apply=True, out=lambda *_: None)
    assert (done["merged_orgs"], done["candidates"]) == (1, 1)
    merged = conn.execute("SELECT canonical_name FROM organisation "
                          "WHERE merged_into IS NOT NULL").fetchall()
    assert len(merged) == 1 and "ministerstvo obrany" in merged[0]["canonical_name"]


def test_a_notice_with_two_buyers_gives_no_identifier():
    two = {"buyer-name": {"ces": ["A", "B"]}, "buyer-identifier": ["12345678", "87654321"]}
    assert backfill.notice_identifier(two, "CZ") is None
    one = {"buyer-name": {"ces": ["A"]}, "buyer-identifier": ["12345678", "12345678"]}
    assert backfill.notice_identifier(one, "CZ") == "12345678"


def test_the_cover_reads_fewer_bundles_than_there_are():
    pairs = [(1, "b1"), (2, "b1"), (3, "b1"), (1, "b2"), (4, "b3"), (3, "b3")]
    chosen = backfill.cover(pairs)
    assert set(chosen) == {"b1", "b3"}


def test_a_second_round_reads_again_only_for_organisations_without_an_identifier():
    def notice(ident):
        return json.dumps({"buyer-name": {"ces": ["A"]}, "buyer-identifier": [ident]})

    lines = {"b1": [notice("COM"), notice("12345678")],     # org 1: junk, org 2: usable
             "b2": [notice("87654321")]}                     # org 1's other notice
    per = {1: [("b1", 0, "CZ"), ("b2", 0, "CZ")], 2: [("b1", 1, "CZ")]}
    reads: list[str] = []

    def read(bundle):
        reads.append(bundle)
        return lines[bundle]

    idents, stats = backfill.collect_identifiers(per, read, rounds=3, log_every=0)
    assert {o: set(c) for o, c in idents.items()} == {1: {"87654321"}, 2: {"12345678"}}
    assert reads == ["b1", "b2"] and stats["rounds"] == 2
    assert stats["no_identifier"] == 1


def test_merge_candidates_finds_spelling_variants_without_merging(conn):
    a = db.resolve_organisation(conn, "Ministerstvo obrany", "CZ")
    b = db.resolve_organisation(conn, "Ceska republika - Ministerstvo obrany", "CZ")
    c = db.resolve_organisation(conn, "Ministerstvo obrany - Ceska republika", "CZ")
    _ingest(conn, native_id="1-2026", buyer="Ministerstvo obrany", country="CZ", legal="32009L0081")
    out: list[str] = []
    res = merge_candidates.run(conn, apply=True, out=out.append)
    assert res["folded_name"] == 2
    pairs = conn.execute("SELECT organisation_id, candidate_org_id, match_method, status "
                         "FROM organisation_merge_candidate WHERE match_method = 'folded_name' "
                         "ORDER BY candidate_org_id").fetchall()
    assert [(p["organisation_id"], p["candidate_org_id"]) for p in pairs] == [(a, b), (a, c)]
    assert {p["status"] for p in pairs} == {"pending"}
    assert _count(conn, "SELECT count(*) n FROM organisation WHERE merged_into IS NOT NULL") == 0


# ---------------------------------------------------- the derived buyer list

def test_a_derived_buyer_becomes_a_signal_and_a_confident_row_is_enough(conn, tmp_path,
                                                                         monkeypatch):
    (tmp_path / "defence_buyers_derived_RO.csv").write_text(
        "country,name,identifier,reason,confidence,reviewed\n"
        "RO,ministerul apararii nationale - unitatea militara 02550,,military_unit,0.85,false\n"
        "RO,weak word name bundeswehr,,defence_word,0.70,false\n",
        encoding="utf-8")
    from dgate import pipeline

    monkeypatch.setattr(pipeline, "SEEDS_FILE", tmp_path / "defence_buyers.csv")
    seed_buyers(tmp_path / "defence_buyers.csv")     # absent: the built-in list, plus derived
    conn.commit()
    org = db.resolve_organisation(
        conn, "Ministerul Apărării Naționale - Unitatea Militară 02550", "RO")
    assert db.is_defence_buyer(conn, org)
    row = conn.execute(
        "SELECT defence_buyer_source, defence_buyer_reason, defence_buyer_confidence "
        "FROM organisation WHERE id = %s", (org,)).fetchone()
    assert (row["defence_buyer_source"], row["defence_buyer_reason"]) == (
        "derived_rule", "military_unit")
    assert float(row["defence_buyer_confidence"]) == 0.85
    weak = db.resolve_organisation(conn, "weak word name bundeswehr", "RO")
    assert not db.is_defence_buyer(conn, weak)
    # and a notice from that body, whatever it buys, is now a defence notice
    _, opp = _ingest(conn, native_id="5-2026", buyer="Ministerul Apărării Naționale - "
                     "Unitatea Militară 02550", country="RO", cpv=["90911100"],
                     legal="32014L0024")
    assert opp.is_defence and opp.sig_buyer and not opp.sig_cpv_military


# --------------------------------------- the rows already held, reclassified

def _row(conn, oid):
    return conn.execute(
        "SELECT is_defence, dual_use, buyer_class, sig_cpv_military, sig_cpv, sig_clearance "
        "FROM opportunity WHERE id = %s", (oid,)).fetchone()


def _legacy(conn, native_id, *, buyer, cpv, clearance=False, country="DE"):
    """A row as the rules before 12 October 2026 left it: every signal from sig_cpv."""
    opp = Opportunity(
        source_code="ted", native_id=native_id, buyer_name_raw=buyer, title_original=native_id,
        country=country, published_at=date(2026, 10, 1), cpv_codes=list(cpv), is_defence=True,
        sig_cpv=True, sig_clearance=clearance,
        status="open")      # set, not defaulted: the default is `unknown` since 13 October
    opp.buyer_org_id = db.resolve_organisation(conn, buyer, country)
    oid, _ = db.upsert_opportunity(conn, opp, f"legacy-{native_id}", db.source_id(conn, "ted"))
    conn.execute("UPDATE opportunity SET sig_cpv_military = FALSE, buyer_class = NULL, "
                 "dual_use = FALSE WHERE id = %s", (oid,))
    conn.commit()
    return oid


def test_reclassifying_the_serving_rows(conn):
    guard = _legacy(conn, "G-1", buyer="Landratsamt Musterkreis", cpv=["35120000"], clearance=True)
    town = _legacy(conn, "T-1", buyer="Stadt Nürnberg", cpv=["35810000"])
    police = _legacy(conn, "P-1", buyer="Polizeiverwaltungsamt Logistikzentrum", cpv=["35810000"])
    army = _legacy(conn, "A-1", buyer="Bundeswehr Dienstleistungszentrum Ulm", cpv=["35330000"])

    dry = reprocess.reclassify_serving(conn, dry_run=True)
    assert dry["scanned"] == 4 and dry["changed"] >= 3
    assert dry["defence_to_not"] == 1 and dry["demoted_to_dual_use"] == 1
    assert _row(conn, guard)["is_defence"] is True            # a dry run writes nothing

    done = reprocess.reclassify_serving(conn, dry_run=False)
    assert done["defence_to_not"] == 1
    g, t, p, a = (_row(conn, o) for o in (guard, town, police, army))
    assert g["is_defence"] is False and g["sig_clearance"] is True       # kept, not deleted
    assert t["is_defence"] and t["dual_use"] and t["buyer_class"] == "municipal"
    assert p["is_defence"] and not p["dual_use"] and p["buyer_class"] == "security"
    assert a["is_defence"] and a["sig_cpv_military"] and not a["dual_use"]
    # no version was written and none was removed
    assert _count(conn, "SELECT count(*) n FROM opportunity_version") == 4
    # idempotent
    assert reprocess.reclassify_serving(conn, dry_run=False)["changed"] == 0


def test_the_api_serves_core_without_civil_cpv_or_dual_use_and_labels_the_rest(conn):
    _legacy(conn, "CORE-1", buyer="Bundeswehr Dienstleistungszentrum Ulm", cpv=["35330000"])
    _legacy(conn, "TOWN-1", buyer="Stadt Nürnberg", cpv=["35810000"])
    _legacy(conn, "CIVIL-1", buyer="Landratsamt Musterkreis", cpv=["35110000"])
    reprocess.reclassify_serving(conn, dry_run=False)
    with TestClient(api.app) as client:
        def ids(**params):
            body = client.get("/v1/opportunities", params={"status": "open", **params}).json()
            return {o["native_id"]: o for o in body}

        core = ids(scope="core")
        assert "CORE-1" in core
        assert "TOWN-1" not in core and "CIVIL-1" not in core
        everything = ids(scope="all")
        assert everything["TOWN-1"]["dual_use"] is True
        assert everything["TOWN-1"]["buyer_class"] == "municipal"


# ------------------------------------- raw TED notices the rules now qualify

def _raw_ted(i, name, cpv, country="ROU", legal="32014L0024"):
    return {"publication-number": f"{i}-2026", "notice-identifier": f"id-{i}",
            "notice-title": {"eng": f"Notice {i}"}, "buyer-name": {"ron": [name]},
            "buyer-country": [country], "classification-cpv": cpv, "legal-basis": [legal],
            "dispatch-date": "2026-09-01Z", "official-language": ["RON"],
            # a notice type is part of every real TED notice; without it the status is
            # `unknown` (never open) and the legacy listing, which shows open ones, omits it
            "notice-type": "cn-standard"}


def test_requalifying_raw_ted_notices_inserts_what_the_new_rules_qualify(conn, tmp_path,
                                                                          monkeypatch):
    store = FileRawStore(tmp_path / "raw")
    bundle = bundle_key("ted", date(2026, 9, 1))
    unit = "Ministerul Apărării Naționale - Unitatea Militară 02550"
    notices = [_raw_ted(1, unit, ["90911100"]),                      # a listed body, civil CPV
               _raw_ted(2, "Primăria Sibiu", ["35810000"]),          # a town, military CPV
               _raw_ted(3, "SC Curatenie SRL", ["90911100"])]        # nothing
    store.put_records(bundle, notices)
    src = db.source_id(conn, "ted")
    for n, notice in enumerate(notices):
        db.record_raw(conn, src, notice["publication-number"], content_hash(notice),
                      record_key(bundle, n))
        # what the daily job did before the list named the unit: land, classify,
        # keep only what qualified
        opp = _finalise(conn, from_ted(notice), src)
        if opp.is_defence:
            db.upsert_opportunity(conn, opp, content_hash(notice), src)
    conn.commit()
    assert _count(conn, "SELECT count(*) n FROM opportunity WHERE source_id = %s", src) == 1

    # the buyer list now names the unit
    unit_org = db.resolve_organisation(conn, unit, "RO")
    conn.execute("UPDATE organisation SET is_defence_buyer = TRUE WHERE id = %s", (unit_org,))
    conn.commit()

    dry = reprocess.requalify_ted(conn, store, since=date(2026, 9, 1), until=date(2026, 9, 30),
                                  dry_run=True)
    assert dry["candidates"] == 2          # the unit's notice and the cleaning contract
    assert dry["inserted"] == 1 and dry["by_buyer"] == 1
    assert dry["by_dual_use"] == 0 and dry["not_qualified"] == 1
    assert _count(conn, "SELECT count(*) n FROM opportunity WHERE source_id = %s", src) == 1

    # a month elsewhere finds nothing
    other = reprocess.requalify_ted(conn, store, since=date(2025, 1, 1), until=date(2025, 1, 31),
                                    dry_run=True)
    assert other["candidates"] == 0

    done = reprocess.requalify_ted(conn, store, since=date(2026, 9, 1), until=date(2026, 9, 30),
                                   dry_run=False)
    assert done["inserted"] == 1
    rows = conn.execute("SELECT native_id, sig_buyer, dual_use, is_defence FROM opportunity "
                        "WHERE source_id = %s ORDER BY native_id", (src,)).fetchall()
    assert [r["native_id"] for r in rows] == ["1-2026", "2-2026"]
    assert rows[0]["sig_buyer"] and rows[1]["dual_use"]
    # run again: the qualified notice is held; only the one that never qualified remains
    again = reprocess.requalify_ted(conn, store, since=date(2026, 9, 1), until=date(2026, 9, 30),
                                    dry_run=False)
    assert (again["candidates"], again["inserted"]) == (1, 0)


def test_a_national_notice_makes_its_ted_twin_defence(conn, tmp_path):
    store = FileRawStore(tmp_path / "raw")
    bundle = bundle_key("ted", date(2026, 9, 1))
    twin = _raw_ted(77, "Primăria Cluj", ["90911100"], country="ROU")
    store.put_records(bundle, [twin])
    src = db.source_id(conn, "ted")
    db.record_raw(conn, src, "77-2026", content_hash(twin), record_key(bundle, 0))
    conn.commit()
    # the national source's defence notice, which says it was forwarded as 77-2026
    _ingest(conn, source="pl_ezam", native_id="BZP-1", buyer="Jednostka Wojskowa 1234",
            country="PL", cpv=["35330000"], ted_ref="77-2026")
    assert _count(conn, "SELECT count(*) n FROM opportunity WHERE source_id = %s", src) == 0

    dry = reprocess.requalify_ted(conn, store, linked_only=True, dry_run=True)
    assert dry["candidates"] == 1 and dry["by_linked"] == 1
    done = reprocess.requalify_ted(conn, store, linked_only=True, dry_run=False)
    assert done["inserted"] == 1
    row = conn.execute("SELECT sig_linked_defence, is_defence, sig_cpv_military FROM opportunity "
                       "WHERE source_id = %s", (src,)).fetchone()
    assert row["sig_linked_defence"] and row["is_defence"] and not row["sig_cpv_military"]
    # served as `supply`, not `core`: the notice itself says nothing about defence
    with TestClient(api.app) as client:
        body = client.get("/v1/opportunities", params={"scope": "supply"}).json()
        assert [o["native_id"] for o in body if o["source"] == "ted"] == ["77-2026"]
