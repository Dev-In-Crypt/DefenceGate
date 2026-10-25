"""WP-129: a person-reviewed list of merge candidates, and the generic municipal-company names of the rejoin rule."""

from __future__ import annotations

import pytest

from dgate.ops import accept_merge_candidates as amc
from dgate.ops.org_repair import agrees, ambiguous_name

NIP, REGON = "5250007282", "000177916"


def _org(i, name, *, reg=None, vat=None, country="PL", notices=0, **kw):
    return {"id": i, "country": country, "name": name, "display_name": None, "suppressed": False, "person": False,
            "reg": reg, "vat": vat, "pic": None, "notices": notices, "raw_names": [], "legal_form": None,
            "org_role": "buyer", "is_defence_buyer": False, "buys": True, **kw}


def _pair(cid, a, b):
    return {"id": cid, "a": a, "b": b, "confidence": 0.90, "match_method": "cleared_register_number",
            "evidence": f"{a}~{b}", "status": "pending"}


def _accept(*ids, **by_id):
    return {i: {"decision": "ACCEPT", "head": None, "confidence": None, "reason": "r", **by_id.get(f"c{i}", {})}
            for i in ids}


def test_the_ids_file_reads_a_bare_list_and_the_reviewers_csv(tmp_path):
    bare = tmp_path / "ids.txt"
    bare.write_text("# reviewed 25 Oct\n2508797\n\n2508862,195698\n", encoding="utf-8")
    assert amc.read_reviewed(str(bare)) == {
        2508797: {"decision": "ACCEPT", "head": None, "confidence": None, "reason": ""},
        2508862: {"decision": "ACCEPT", "head": 195698, "confidence": None, "reason": ""}}
    full = tmp_path / "decisions.csv"
    full.write_text("﻿candidate_id,org_a,org_a_name,decision,confidence,evidence\n"
                    '1,7,"gmina x, y",REJECT,0.85,"a parent and its unit"\n2,8,z,UNSURE,0.50,open\n3,9,w,,,\n',
                    encoding="utf-8")
    got = amc.read_reviewed(str(full))
    assert (got[1]["decision"], got[1]["confidence"], got[1]["reason"]) == ("REJECT", 0.85, "a parent and its unit")
    assert (got[2]["decision"], got[3]["decision"], got[3]["confidence"]) == ("UNSURE", "ACCEPT", None)
    full.write_text("candidate_id,decision\n1,MAYBE\n", encoding="utf-8")
    with pytest.raises(ValueError):
        amc.read_reviewed(str(full))


def test_a_nip_beside_a_regon_is_one_body_two_numbers_of_one_kind_are_two():
    assert amc.number_kinds(_org(1, "x", reg=REGON, vat="PL" + NIP)) == [("regon", REGON), ("nip", NIP)]
    assert amc.number_kinds(_org(1, "x", reg="0000123456")) == [("krs", "0000123456")]
    assert amc._number_clash([_org(1, "a", reg=NIP), _org(2, "b", reg=REGON)]) is None
    assert amc._number_clash([_org(1, "a", reg=NIP), _org(2, "b", reg="1234563218")]) == "different_nip"
    assert amc._number_clash([_org(1, "a", reg=REGON, vat=NIP), _org(2, "b", reg="1234563218")]) == "different_nip"
    assert amc._number_clash([_org(1, "a", reg="A1", country="ES"), _org(2, "b", reg="B2", country="ES")]) == (
        "different_reg")


def test_the_review_decides_the_judgement_rules_the_facts_still_refuse():
    orgs = {o["id"]: o for o in (
        _org(1, "gmina cekcyn", reg=NIP), _org(2, "gmina cekcyn", reg=REGON),            # a public body: reviewed
        _org(3, "nadlesnictwo nowy targ"), _org(4, "lasy panstwowe nadlesnictwo nowy targ", reg=NIP),
        _org(5, "skarb panstwa nadlesnictwo nowy targ"),                                 # a group of three
        _org(6, "zaklad karny", reg=REGON, notices=5), _org(7, "zaklad karny we wronki"),
        _org(8, "gmina a", reg=NIP), _org(9, "gmina a", reg="1234563218"),               # two NIPs: two bodies
        _org(10, "gmina b"), _org(11, "gmina b", suppressed=True),
        _org(12, "gmina c"), _org(13, "gmina c", country="CZ"),
        _org(14, "x"), _org(15, "y", reg=REGON))}
    pairs = [_pair(101, 1, 2), _pair(102, 3, 4), _pair(103, 4, 5), _pair(104, 6, 7), _pair(105, 8, 9),
             _pair(106, 10, 11), _pair(107, 12, 13), _pair(108, 14, 15)]
    reviewed = _accept(101, 102, 103, 104, 105, 106, 107, 108, c101={"confidence": 0.95},
                       c108={"decision": "REJECT"})
    groups, refused, overridden = amc.plan_reviewed(pairs, orgs, reviewed)
    assert refused == {"different_nip": 1, "suppressed": 1, "different_countries": 1}
    assert overridden["public_body"] >= 1 and overridden["different_reg"] == 1
    heads = {g["head"]: (g["members"], g["confidence"]) for g in groups}
    assert heads == {4: ([3, 5], 0.9), 1: ([2], 0.95), 7: ([6], 0.9)}     # the prison's own name, not 'zaklad karny'
    groups, _, _ = amc.plan_reviewed(pairs, orgs, _accept(104, c104={"head": 6}))
    assert [(g["head"], g["members"]) for g in groups] == [(6, [7])]                   # the file's head decides
    _, refused, _ = amc.plan_reviewed(pairs, orgs, _accept(104, c104={"head": 99}))
    assert refused == {"head_not_in_group": 1}


def test_a_municipal_service_company_without_its_town_is_a_generic_name():
    assert ambiguous_name("PL", "miejski zaklad uslug komunalnych")
    assert ambiguous_name("PL", "miejski zarzad uslug komunalnych")
    assert not ambiguous_name("PL", "miejski zaklad uslug komunalnych sp z o o w walbrzychu")


def test_a_cleared_value_agrees_with_its_head_when_a_part_of_it_is_the_heads_number():
    assert agrees(NIP + REGON, "PL", (NIP, None))
    assert agrees(NIP + REGON, "PL", (REGON, None))
    assert agrees("177916", "PL", (REGON, None))                        # a REGON without its leading zeros
    assert not agrees(NIP + REGON, "PL", ("311601084", None))
    assert not agrees("6643453672", "PL", ("311601084", None)) and not agrees(None, "PL", (NIP,))
