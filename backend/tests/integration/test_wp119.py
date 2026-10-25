"""WP-119 against a real Postgres: each repair step of the 25 October writes, with the shapes the verification found
(D:/DEFENCEGATE TESTS/verify-oct25/data), and each rule that keeps them from coming back."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from dgate import db, funding
from dgate.normalise import Opportunity
from dgate.ops import award_values, buyer_families, org_repair, supplier_dedupe, undo_merges
from tests.integration.test_wp95 import award, award_notice, client, env, notice, org  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration

QUIET = {"out": lambda *_: None}
NIP, REGON = "5250007282", "000177916"


def _row(conn, oid):
    return conn.execute("SELECT * FROM organisation WHERE id = %s", (oid,)).fetchone()


def _merge(conn, keep, gone, method, detected_by):
    db.merge_organisations(conn, keep, gone, method=method, confidence=0.95, evidence="t", detected_by=detected_by,
                           allow_identifier_conflict=True)          # as ops.supplier_dedupe merges
    conn.commit()


# ------------------------------------------------------------------------------------- 1. award values

def test_the_recheck_puts_back_the_totals_the_narrowed_rules_no_longer_set_aside(conn, env):  # noqa: F811
    nl = org(conn, "ministerie van defensie", "NL", is_defence_buyer=True)
    fi = org(conn, "marine alutech", "FI")
    alutech = notice(conn, "ted", "676175-2026", buyer=nl, country="NL", value=(76000000.0, "EUR", "total"))
    alutech_award = award(conn, alutech, fi, "Marine Alutech Oy Ab", value=(2.0, "EUR", "contract"), country="FI")
    award_notice(conn, alutech, value_amount=2, value_currency="EUR", value_kind="contract", value_set_aside=76000000,
                 value_set_aside_reason="lots")
    pl = org(conn, "faser", "PL")
    faser = notice(conn, "ted", "394720-2025", buyer=nl, country="PL", value=(7247040000.0, "PLN", "total"))
    award(conn, faser, pl, "FASER S.A", value=(7247040.0, "PLN", "contract"), country="PL")
    award_notice(conn, faser, value_amount=7247040, value_currency="PLN", value_kind="contract",
                 value_set_aside=7247040000, value_set_aside_reason="lots")
    dutraco = org(conn, "dutraco gouda", "NL")
    frame = notice(conn, "ted", "451107-2025", buyer=nl, country="NL", value=(22922861.0, "EUR", "total"),
                   title="Raamovereenkomst Veldkleding")
    frame_award = award(conn, frame, dutraco, "Dutraco Gouda B.V.", value=(23918.70, "EUR", "estimate"), country="NL")
    award_notice(conn, frame, value_amount=23918.70, value_currency="EUR", value_kind="estimate",
                 value_set_aside=22922861, value_set_aside_reason="procedure")
    cn = notice(conn, "ted", "784584-2023", buyer=nl, country="NL", value=(23918.70, "EUR", "estimated"), subtype="18")
    for o in (frame, cn):
        conn.execute("UPDATE opportunity SET procedure_identifier = '20641a3c' WHERE id = %s", (o,))
    conn.commit()

    lines: list[str] = []
    report = award_values.run_recheck(conn, write=False, examples=lines)
    conn.rollback()
    assert (report["recheck_lots"], report["recheck_lots_restored"], report["recheck_procedure_restored"]) == (2, 1, 1)
    award_values.run_recheck(conn, write=True)
    n = conn.execute("SELECT * FROM award_notice WHERE opportunity_id = %s", (alutech,)).fetchone()
    assert (float(n["value_amount"]), n["value_kind"], n["value_set_aside"], n["value_set_aside_reason"]) == (
        76000000.0, "contract", None, None)
    a = conn.execute("SELECT value_amount, value_kind FROM award WHERE id = %s", (alutech_award,)).fetchone()
    assert (float(a["value_amount"]), a["value_kind"]) == (76000000.0, "contract")
    n = conn.execute("SELECT * FROM award_notice WHERE opportunity_id = %s", (frame,)).fetchone()
    assert (float(n["value_amount"]), n["value_kind"], n["value_set_aside"]) == (22922861.0, "framework", None)
    a = conn.execute("SELECT value_amount, value_kind FROM award WHERE id = %s", (frame_award,)).fetchone()
    assert (float(a["value_amount"]), a["value_kind"]) == (22922861.0, "framework")
    n = conn.execute("SELECT * FROM award_notice WHERE opportunity_id = %s", (faser,)).fetchone()
    assert (float(n["value_amount"]), n["value_set_aside_reason"]) == (7247040.0, "lots")      # a unit error: stays
    again = award_values.run_recheck(conn, write=True)
    assert again["recheck_lots"] == 1 and not again["recheck_lots_restored"]                    # nothing left to do


# ------------------------------------------------------------------------------------- 2. buyer as winner

def test_a_company_put_into_its_buyers_family_by_a_twin_notice_is_counted_again(conn, env):  # noqa: F811
    esid = org(conn, "esid rennes", "FR", is_defence_buyer=True)
    spie = org(conn, "spie facilities", "FR")
    pfc = org(conn, "pfc ouest rennes", "FR", is_defence_buyer=True)
    def_ouest = org(conn, "def ouest", "FR")
    ted = notice(conn, "ted", "109763-2024", buyer=esid, country="FR")
    copy = notice(conn, "fr_boamp", "24-21330", buyer=spie, country="FR")
    conn.execute("UPDATE opportunity SET ted_ref = '109763-2024', twin_method = 'procedure_id' WHERE id = %s", (copy,))
    spie_award = award(conn, ted, spie, "SPIE FACILITIES", value=(4000000.0, "EUR", "contract"), country="FR")
    other = notice(conn, "ted", "841870-2025", buyer=pfc, country="FR")
    conn.execute("UPDATE opportunity SET buyer_name_raw = 'PFC Ouest' WHERE id = %s", (other,))
    def_award = award(conn, other, def_ouest, "DEF OUEST", country="FR")
    # the state of 25 October: SPIE in ESID's family by the twin notice, both awards excluded as the buyer's
    conn.execute("INSERT INTO buyer_family_member (org_id, head_org_id, method, confidence) "
                 "VALUES (%s, %s, 'twin_notice', 0.85)", (spie, esid))
    conn.execute("UPDATE award SET excluded_reason = 'buyer_as_winner' WHERE id = ANY(%s)", ([spie_award, def_award],))
    conn.commit()

    assert all(m.org_id != spie for g in buyer_families.all_groups(conn) for m in g.members)   # the rule: no longer
    assert buyer_families.run(conn, write=True)["removed"] == 1
    report = org_repair.winners_check(conn, apply=False, **QUIET)
    assert report["counted_again"] == 2
    window = conn.execute("SELECT now() - interval '1 minute' AS a").fetchone()["a"]
    org_repair.winners_check(conn, apply=True, **QUIET)
    got = {r["id"]: r["excluded_reason"] for r in conn.execute("SELECT id, excluded_reason FROM award").fetchall()}
    assert got == {spie_award: None, def_award: None}
    assert org_repair.winners(conn, apply=False, **QUIET)["buyer_as_winner"] == 0           # the step leaves them be
    org_repair.undo(conn, window.isoformat(), (window + timedelta(hours=1)).isoformat(), apply=True, **QUIET)
    assert conn.execute("SELECT count(*) AS n FROM award WHERE excluded_reason = 'buyer_as_winner'").fetchone()["n"] == 2


# ------------------------------------------------------------------------------------- 3-5. the rejoin and the identifiers

def _rejoined(conn, name, country, head_reg, members):
    head = org(conn, name, country, national_reg_no=head_reg)
    rows = [org(conn, name, country, **extra) for extra in members]
    for r in rows:
        _merge(conn, head, r, org_repair.REJOIN, org_repair.DETECTED_BY)
    return head, rows


def test_a_rejoin_under_a_name_two_counties_bear_is_undone_and_others_stay(conn):
    powiat, apart = _rejoined(conn, "powiat tomaszowski", "PL", "590648451", [{}, {}])
    uni, kept = _rejoined(conn, "uniwersytet warszawski", "PL", "525001127", [{}])
    lines: list[str] = []
    report = org_repair.namesakes(conn, apply=False, out=lines.append)
    assert (report["groups"], report["rows"]) == (1, 2) and any("powiat tomaszowski" in s for s in lines)
    assert _row(conn, apart[0])["merged_into"] == powiat                                     # a report writes nothing
    org_repair.namesakes(conn, apply=True, **QUIET)
    assert [_row(conn, r)["merged_into"] for r in apart] == [None, None]
    assert _row(conn, kept[0])["merged_into"] == uni
    assert org_repair.namesakes(conn, apply=False, **QUIET)["rows"] == 0


def test_the_head_of_a_rejoin_takes_the_pic_and_the_undo_gives_it_back(conn):
    head = org(conn, "universitat de girona", "ES", national_reg_no="Q6750002E")
    member = org(conn, "universitat de girona", "ES", eu_pic="999887700")
    projects = [conn.execute("INSERT INTO project (source_id, native_id, title) VALUES "
                             "((SELECT id FROM source WHERE code = 'cordis'), %s, 'P') RETURNING id", (f"p{i}",)
                             ).fetchone()["id"] for i in range(3)]
    parts = [conn.execute("""INSERT INTO participation (project_id, organisation_id, role, resolution_method,
                                                         resolution_confidence) VALUES (%s, %s, 'participant', 'pic', 1)
                             RETURNING id""", (p, who)).fetchone()["id"]
             for p, who in ((projects[0], member), (projects[1], member), (projects[2], head))]
    # the state of 25 October: merged before the merge carried anything
    conn.execute("UPDATE organisation SET merged_into = %s, merge_method = %s, merge_confidence = 0.95, "
                 "merged_at = now() - interval '1 hour' WHERE id = %s", (head, org_repair.REJOIN, member))
    conn.execute("""INSERT INTO organisation_merge_candidate (organisation_id, candidate_org_id, match_method, confidence,
                                                              evidence, status, detected_by, decided_at)
                    VALUES (%s, %s, %s, 0.95, 't', 'merged', %s, now() - interval '1 hour')""",
                 (min(head, member), max(head, member), org_repair.REJOIN, org_repair.DETECTED_BY))
    conn.commit()

    report = org_repair.pics(conn, apply=False, **QUIET)
    assert (report["heads"], report["pic"], report["participations_read_through_the_merge"]) == (1, 1, 2)
    assert _row(conn, head)["eu_pic"] is None
    org_repair.pics(conn, apply=True, **QUIET)
    assert (_row(conn, head)["eu_pic"], _row(conn, member)["eu_pic"]) == ("999887700", None)
    owners = [r["organisation_id"] for r in conn.execute(
        "SELECT organisation_id FROM participation WHERE id = ANY(%s) ORDER BY id", (parts,)).fetchall()]
    assert owners == [member, member, head]                                   # WP-41: read through the merge
    assert org_repair.pics(conn, apply=False, **QUIET)["heads"] == 0                         # idempotent
    # undoing the rejoin gives the member its PIC back
    undo_merges.run(conn, apply=True, start=(date.today() - timedelta(days=1)).isoformat(),
                    end=(date.today() + timedelta(days=1)).isoformat(), methods=(org_repair.REJOIN,), expected=None,
                    detected_by=org_repair.DETECTED_BY, refresh=False, **QUIET)
    assert (_row(conn, head)["eu_pic"], _row(conn, member)["eu_pic"]) == (None, "999887700")


def test_a_merge_now_carries_the_pic_and_counts_a_winner_named_twice_once(conn, env):  # noqa: F811
    buyer = org(conn, "bundeswehr", "DE", is_defence_buyer=True)
    a = org(conn, "vogtmann herold co", "DE")
    b = org(conn, "vogtmann herold co", "DE", eu_pic="912345678")
    n = notice(conn, "ted", "492709-2023", buyer=buyer, country="DE")
    first = award(conn, n, a, "Vogtmann-Herold+Co.GmbH", country="DE")
    second = award(conn, n, b, "Vogtmann-Herold + Co. GmbH", country="DE")
    conn.commit()
    _merge(conn, a, b, "name_key", supplier_dedupe.DETECTED_BY)
    assert _row(conn, a)["eu_pic"] == "912345678"
    got = {r["id"]: r["excluded_reason"] for r in conn.execute("SELECT id, excluded_reason FROM award").fetchall()}
    assert got == {first: None, second: db.SAME_WINNER_TWICE}
    supplier_dedupe.undo_batch(conn, (date.today() - timedelta(days=1)).isoformat(),
                               (date.today() + timedelta(days=1)).isoformat(), apply=True, **QUIET)
    got = {r["id"]: r["excluded_reason"] for r in conn.execute("SELECT id, excluded_reason FROM award").fetchall()}
    assert got == {first: None, second: None} and _row(conn, b)["eu_pic"] == "912345678"


def test_cleared_numbers_the_rules_keep_are_restored_from_the_log_and_the_undo_clears_them(conn):
    hospital = org(conn, "szpital wojewodzki w opolu", "PL")
    merged_head = org(conn, "ministerstwo spraw zagranicznych", "PL")
    merged = org(conn, "ministerstwo spraw zagranicznych", "PL")
    conn.execute("UPDATE organisation SET merged_into = %s, merge_method = %s WHERE id = %s",
                 (merged_head, org_repair.REJOIN, merged))
    held_elsewhere = org(conn, "gmina x", "PL")
    org(conn, "gmina x holder", "PL", national_reg_no="1234563218")
    teryt = org(conn, "gmina duszniki", "PL")
    czech = org(conn, "ceska zbrojovka", "ES")
    town = org(conn, "gmina radymno", "PL")
    for oid, old in ((hospital, NIP + REGON), (merged, "177916"), (held_elsewhere, "1234563218" + "000177916"),
                     (teryt, "3024022"), (czech, "CZ25288040"), (town, "RO2712019000")):
        db.log_repair(conn, oid, "clear_false_identifier", old_value=old, new_value=None, method="wp115_register_check",
                      detected_by=org_repair.DETECTED_BY)
    conn.commit()

    report = org_repair.restore_ids(conn, apply=False, **QUIET)
    assert (report["nip_regon_pair_restored"], report["unpadded_regon_restored"], report["foreign_vat_restored"]) == (
        1, 1, 1)
    assert report["nip_regon_pair_held_by_another_row"] == 1 and "teryt" not in str(report)
    window = conn.execute("SELECT clock_timestamp() AS a").fetchone()["a"]     # after the clearing, as on production
    conn.commit()
    org_repair.restore_ids(conn, apply=True, **QUIET)
    assert _row(conn, hospital)["national_reg_no"] == NIP
    assert (_row(conn, merged_head)["national_reg_no"], _row(conn, merged)["national_reg_no"]) == (REGON, None)
    assert (_row(conn, czech)["vat_number"], _row(conn, czech)["national_reg_no"]) == ("CZ25288040", None)
    assert _row(conn, teryt)["national_reg_no"] is None and _row(conn, town)["vat_number"] is None
    assert org_repair.restore_ids(conn, apply=False, **QUIET).get("nip_regon_pair_already_there") == 1
    org_repair.undo(conn, window.isoformat(), (window + timedelta(hours=1)).isoformat(), apply=True, **QUIET)
    assert (_row(conn, hospital)["national_reg_no"], _row(conn, czech)["vat_number"]) == (None, None)


def test_the_false_ids_step_moves_a_foreign_vat_number_and_respells_a_pair(conn):
    czech = org(conn, "ceska zbrojovka", "ES", national_reg_no="CZ25288040")
    hospital = org(conn, "szpital wojewodzki w opolu", "PL", national_reg_no=NIP + REGON)
    conn.commit()
    org_repair.false_ids(conn, apply=True, **QUIET)
    assert (_row(conn, czech)["vat_number"], _row(conn, czech)["national_reg_no"]) == ("CZ25288040", None)
    assert _row(conn, hospital)["national_reg_no"] == NIP


# ------------------------------------------------------------------------------------- 6. one winner twice

def test_two_companies_named_side_by_side_are_taken_apart_and_spellings_counted_once(conn, env):  # noqa: F811
    buyer = org(conn, "agencja uzbrojenia", "PL", is_defence_buyer=True)
    sign = org(conn, "sign polska", "PL", national_reg_no="1132958143")
    sign4 = org(conn, "sign 4 security", "PL", national_reg_no="8522675066")
    works = org(conn, "works 11", "PL", national_reg_no="6462895170")
    workss = org(conn, "workss 11", "PL")
    sign_awards = []
    for native in ("262623-2024", "224193-2025"):
        n = notice(conn, "ted", native, buyer=buyer, country="PL")
        sign_awards += [award(conn, n, sign, "Sign Polska Sp. z o.o.", country="PL"),
                        award(conn, n, sign4, "Sign 4 Security Sp. z o.o.", country="PL")]
    n = notice(conn, "ted", "629838-2023", buyer=buyer, country="PL")
    keep = award(conn, n, works, "WORKS 11- Sp. z o.o.", country="PL")
    twice = award(conn, n, workss, "WORKSS - 11 Sp. z o.o.", country="PL")
    conn.commit()
    _merge(conn, sign, sign4, "company_number", supplier_dedupe.DETECTED_BY)
    _merge(conn, works, workss, supplier_dedupe.CURATED_REVIEW, supplier_dedupe.DETECTED_BY)
    # the state of 25 October: merged before a merge counted a winner named twice once
    conn.execute("UPDATE award SET excluded_reason = NULL")
    conn.commit()

    report = org_repair.twice(conn, apply=False, **QUIET)
    assert (report["notices"], report["rows_taken_apart"], report["awards_counted_once"]) == (3, [sign4], [twice])
    window = conn.execute("SELECT now() - interval '1 minute' AS a").fetchone()["a"]
    org_repair.twice(conn, apply=True, **QUIET)
    assert _row(conn, sign4)["merged_into"] is None and _row(conn, workss)["merged_into"] == works
    got = {r["id"]: r["excluded_reason"] for r in conn.execute("SELECT id, excluded_reason FROM award").fetchall()}
    assert got == {**{a: None for a in sign_awards}, keep: None, twice: db.SAME_WINNER_TWICE}
    assert org_repair.twice(conn, apply=False, **QUIET)["notices"] == 0
    org_repair.undo(conn, window.isoformat(), (window + timedelta(hours=1)).isoformat(), apply=True, **QUIET)
    assert conn.execute("SELECT excluded_reason FROM award WHERE id = %s", (twice,)).fetchone()["excluded_reason"] is None


# ------------------------------------------------------------------------------------- 7. the main CPV code

def test_the_archive_lists_the_serving_rows_main_code_first_with_a_note(conn, client):  # noqa: F811
    o = Opportunity(source_code="nl_tenderned", native_id="412367", buyer_name_raw="Ministerie van Defensie",
                    title_original="Software", country="NL", published_at=date(2026, 9, 1), status="awarded",
                    is_defence=True, cpv_codes=["35700000", "48100000", "72000000"])
    src = db.source_id(conn, "nl_tenderned")
    oid, _ = db.upsert_opportunity(conn, o, "h-412367", src)
    conn.execute("UPDATE opportunity SET cpv_codes = %s WHERE id = %s", (["72000000", "35700000", "48100000"], oid))
    conn.commit()
    body = client.get(f"/v1/opportunities/{oid}/versions").json()
    v = body["versions"][0]
    assert v["snapshot"]["cpv_codes"] == ["72000000", "35700000", "48100000"]
    assert [n["kind"] for n in v["notes"]] == ["main_code"]
    stored = conn.execute("SELECT payload->'cpv_codes' AS c FROM opportunity_version WHERE opportunity_id = %s",
                          (oid,)).fetchone()["c"]
    assert stored == ["35700000", "48100000", "72000000"]                      # the version row is untouched


# ------------------------------------------------------------------------------------- 8. refused since

def _run(conn, *, status, fetched, error=None, hours_ago):
    run_id = db.start_run(conn, "pl_ezam", expected_min=2000)
    db.finish_run(conn, run_id, fetched=fetched, new=0, changed=0, status=status, error=error)
    conn.execute("UPDATE ingest_run SET started_at = now() - make_interval(secs => %s), "
                 "finished_at = now() - make_interval(secs => %s) + interval '20 seconds' WHERE id = %s",
                 (hours_ago * 3600, hours_ago * 3600, run_id))
    conn.commit()
    return conn.execute("SELECT started_at FROM ingest_run WHERE id = %s", (run_id,)).fetchone()["started_at"]


def test_refused_since_is_when_the_runs_stopped_fetching_not_when_they_first_said_why(conn):
    """pl_ezam: last success 23 Oct 10:27; empty runs from 24 Oct 06:45; the refusal written from 25 Oct 06:51."""
    _run(conn, status="success", fetched=8314, hours_ago=44)
    first_empty = _run(conn, status="partial", fetched=0, error="publication days not read to their end", hours_ago=24)
    _run(conn, status="partial", fetched=0, error="publication days not read to their end", hours_ago=20)
    refused = "re-read stopped after 3 failures in a row; " + db.refused_access(403)
    _run(conn, status="partial", fetched=0, error=refused, hours_ago=2)
    _run(conn, status="partial", fetched=0, error=refused, hours_ago=1)
    assert funding.run_signals(conn)["pl_ezam"]["refusedSince"] == first_empty
    # a source that fetched nothing but was never refused has no refusal date
    conn.execute("UPDATE ingest_run SET error_message = 'x' WHERE error_message LIKE 're-read stopped%%'")
    conn.commit()
    assert funding.run_signals(conn)["pl_ezam"]["refusedSince"] is None
