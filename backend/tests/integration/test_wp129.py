"""WP-129 against a real Postgres: a person-reviewed list of merge candidates is merged, rejected and undone, and the
rejoins into a generic municipal-company name are undone unless the cleared number was the head's."""

from __future__ import annotations

import pytest

from dgate import db
from dgate.ops import accept_merge_candidates as amc
from dgate.ops import org_repair
from tests.integration.test_wp95 import org

pytestmark = pytest.mark.integration

QUIET = {"out": lambda *_: None}
NIP, REGON, NIP2, PRISON = "5250007282", "000177916", "1234563218", "630000001"


def _cand(conn, a, b, method="cleared_register_number", conf=0.90):
    db.add_merge_candidate(conn, a, b, method=method, confidence=conf, evidence=f"{a}~{b}", detected_by="t")
    return conn.execute("""SELECT id FROM organisation_merge_candidate WHERE organisation_id = %s
                            AND candidate_org_id = %s AND match_method = %s""",
                        (min(a, b), max(a, b), method)).fetchone()["id"]


def _row(conn, oid):
    return conn.execute("SELECT * FROM organisation WHERE id = %s", (oid,)).fetchone()


def _status(conn, cid):
    return conn.execute("SELECT status, evidence FROM organisation_merge_candidate WHERE id = %s", (cid,)).fetchone()


def test_a_reviewed_list_is_merged_rejected_and_undone_by_its_window(conn, tmp_path):
    g1, g2 = org(conn, "gmina cekcyn", "PL", national_reg_no=NIP, org_role="buyer"), org(
        conn, "gmina cekcyn", "PL", national_reg_no=REGON)                   # a public body: NIP and REGON
    n1, n2, n3 = (org(conn, "nadlesnictwo nowy targ", "PL"),
                  org(conn, "lasy panstwowe nadlesnictwo nowy targ", "PL", national_reg_no=NIP2),
                  org(conn, "skarb panstwa nadlesnictwo nowy targ", "PL"))
    k1, k2 = (org(conn, "zaklad karny", "PL", national_reg_no=PRISON, identifier_method="identifier"),
              org(conn, "zaklad karny we wronki", "PL"))                    # a number as resolution stamps it
    x1, x2 = org(conn, "politechnika gdanska", "PL"), org(conn, "politechnika gdanska wydzial", "PL")
    u1, u2 = org(conn, "politechnika warszawska", "PL"), org(conn, "politechnika warszawska szkola biznesu", "PL")
    c = [_cand(conn, g1, g2), _cand(conn, n1, n2), _cand(conn, n2, n3), _cand(conn, k1, k2), _cand(conn, x1, x2),
         _cand(conn, u1, u2)]
    others = [_cand(conn, g1, g2, "identifier", 0.97), _cand(conn, g1, g2, "same_name_different_identifier", 0.50)]
    conn.commit()
    ids = tmp_path / "decisions.csv"
    ids.write_text("candidate_id,decision,confidence,evidence\n"
                   f"{c[0]},ACCEPT,0.95,one gmina\n{c[1]},ACCEPT,,\n{c[2]},ACCEPT,,\n{c[3]},ACCEPT,0.85,one prison\n"
                   f"{c[4]},REJECT,0.85,a faculty and its university\n{c[5]},UNSURE,0.50,open\n", encoding="utf-8")
    reviewed = amc.read_reviewed(str(ids))

    dry = amc.run_reviewed(conn, reviewed, **QUIET)
    assert (dry["groups"], dry["accepted_candidates"], dry["rows_to_merge"]) == (3, 4, 4)
    assert (dry["other_candidates_to_merged"], dry["to_reject"], dry["unsure_left_pending"]) == (2, 1, 1)
    assert dict(dry["heads"]) == {n2: [n1, n3], g1: [g2], k2: [k1]}           # the prison's own name heads
    assert _row(conn, g2)["merged_into"] is None                                # a report writes nothing

    done = amc.run_reviewed(conn, reviewed, apply=True, **QUIET)
    assert done["merged"] == 4 and done["rejected"] == 1
    g = _row(conn, g2)
    assert (g["merged_into"], g["merge_method"], float(g["merge_confidence"])) == (g1, amc.REVIEWED, 0.95)
    assert (g["national_reg_no"], _row(conn, g1)["national_reg_no"]) == (REGON, NIP)    # each keeps its register
    assert (_row(conn, n1)["merged_into"], float(_row(conn, n3)["merge_confidence"])) == (n2, 0.90)
    head = _row(conn, k2)
    assert (head["national_reg_no"], head["identifier_method"], _row(conn, k1)["national_reg_no"]) == (
        PRISON, amc.REVIEWED, None)                                              # the number went to the head
    assert [_status(conn, i)["status"] for i in (*c[:4], *others)] == ["merged"] * 6
    rejected = _status(conn, c[4])
    assert rejected["status"] == "rejected" and rejected["evidence"].endswith("a faculty and its university")
    assert _status(conn, c[5])["status"] == "pending"
    again = amc.run_reviewed(conn, reviewed, apply=True, **QUIET)
    assert (again["merged"], again["refused"], again["rejected"]) == (0, {"not_pending": 4}, 0)

    undone = amc.undo_batch(conn, *done["batch_window"], apply=True, **QUIET)
    # the four reviewed pairs and the 0.50 one; the 'identifier' pair goes back through undo_merges
    assert undone["rows"] == 4 and undone["other_candidates_pending"] == 5
    assert [_row(conn, i)["merged_into"] for i in (g2, n1, n3, k1)] == [None] * 4
    assert (_row(conn, k1)["national_reg_no"], _row(conn, k2)["national_reg_no"]) == (PRISON, None)
    assert [_status(conn, i)["status"] for i in (*c[:4], *others)] == ["pending"] * 6
    assert _status(conn, c[4])["status"] == "rejected"                            # a person's decision stays


def test_a_rejoin_into_a_generic_municipal_company_is_undone_unless_its_cleared_number_was_the_heads(conn):
    head = org(conn, "miejski zaklad uslug komunalnych", "PL", national_reg_no="311601084")
    walbrzych, other = org(conn, "miejski zaklad uslug komunalnych", "PL"), org(
        conn, "miejski zaklad uslug komunalnych", "PL")
    head2 = org(conn, "miejski zarzad uslug komunalnych", "PL", national_reg_no=NIP)
    same = org(conn, "miejski zarzad uslug komunalnych", "PL")
    for oid, old in ((walbrzych, NIP2 + REGON), (other, "6643453672"), (same, NIP + REGON)):
        db.log_repair(conn, oid, "clear_false_identifier", old_value=old, new_value=None,
                      method="wp115_register_check", detected_by=org_repair.DETECTED_BY)
    for keep, gone in ((head, walbrzych), (head, other), (head2, same)):
        db.merge_organisations(conn, keep, gone, method=org_repair.REJOIN, confidence=0.95, evidence="t",
                               detected_by=org_repair.DETECTED_BY)
    conn.commit()
    lines: list[str] = []
    report = org_repair.namesakes(conn, apply=False, out=lines.append)
    assert (report["groups"], report["rows"], report["kept_number_agrees"]) == (1, 2, 1)
    assert any("miejski zaklad uslug komunalnych" in s for s in lines)
    org_repair.namesakes(conn, apply=True, **QUIET)
    assert [_row(conn, i)["merged_into"] for i in (walbrzych, other, same)] == [None, None, head2]
    assert org_repair.namesakes(conn, apply=False, **QUIET)["rows"] == 0
