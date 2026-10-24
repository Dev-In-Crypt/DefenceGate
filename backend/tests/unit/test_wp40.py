"""WP-40: the rules and facts fixes of round 2 (verifier V2-B, 18 October 2026, docs/verification/product/verify2-rules.md).

The regression set is `fixtures/wp40_calls.json`: the stored eligibility facts and call texts of 92 calls, a read-only export of
production, run through the real serving path (`eligibility.assemble`) and the real flags (`cascade.decide`, `ukraine.decide`).
Every test here fails on the code before this package.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dgate import cascade, eligibility, regulation, rules_apply, ukraine
from dgate.eligibility import Source
from dgate.readiness.seed import load_file
from dgate.regime import EDF, HORIZON, action_of, regime_of

FX = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "wp40_calls.json").read_text(encoding="utf-8"))
CALLS = {c["id"]: c for c in FX["calls"]}
AT = datetime(2026, 10, 18, tzinfo=timezone.utc)
CONTENT = load_file()
TRACKER = {e["code"]: e for e in regulation.load_file()}


def served(cid: int) -> dict:
    c = CALLS[cid]
    held = {k: {"url": k, "extracted_at": AT, "fields": r["fields"]} for k, r in FX["rows"].items()}
    srcs = [Source(s["scope"], s["key"], s["label"], None, s["document"], c["topic"] if s["scope"] == "call_document" else None)
            for s in c["sources"]]
    return eligibility.assemble(srcs, held, c["topic"], eligibility.action_kind(c["type"]))


def call_dict(cid: int) -> dict:
    c = CALLS[cid]
    return {"programme_code": c["programme"], "topic_code": c["topic"], "eligibility_text": c["text"]}


def cascade_flag(cid: int):
    s = served(cid)
    return cascade.decide(call_dict(cid), s["facts"], s["other_topic"])


def ukraine_flag(cid: int):
    return ukraine.decide(call_dict(cid), served(cid)["facts"])


# ======================================================================= B3: the same sentence, the same cascade flag

THIS_TOPIC = "For this topic, financial support to third parties is allowed"
YES = {80, 82, 83, 84, 85, 86, 87, 88, 90, 94, 95, 96, 97, 98, 103, 104, 106, 107, 122, 149}
NO = {10, 19, 29, 109, 113, 193}


def test_every_call_whose_document_says_fstp_is_allowed_for_this_topic_is_flagged_whatever_the_note_says():
    seen = set()
    for cid in CALLS:
        fact = served(cid)["facts"].get("cascade_funding")
        if fact and fact["scope"] == "call_document" and fact["quote"].startswith(THIS_TOPIC):
            seen.add(cid)
            assert cascade_flag(cid)[:2] == (True, "call_document"), (cid, fact["note"])
    # the notes differ ("only within the set ceiling" on 80 82 85 86 88 95 96 97 104; none on 84 87 94 98 103 ...): the flag does not
    assert {80, 82, 85, 86, 88, 95, 96, 97, 104} <= seen and {84, 87, 94, 98, 103} <= seen


def test_the_cascade_flag_of_the_calls_the_verifier_read():
    assert {cid for cid in YES if cascade_flag(cid)[0] is not True} == set()
    assert {cid for cid in NO if cascade_flag(cid)[0] is not False} == set()


def test_a_topic_code_spelled_with_a_space_in_the_document_is_still_this_topic():
    # call 149: the document writes "DIGITAL -ECCC-2027-DEPLOY-CYBER-11-NCC"
    assert "DIGITAL -ECCC-2027-DEPLOY-CYBER-11-NCC" in served(149)["facts"]["cascade_funding"]["quote"]
    assert cascade_flag(149)[:2] == (True, "call_document")


def fact(value, quote, note=None):
    return {"cascade_funding": {"value": value, "quote": quote, "note": note, "confidence": 1.0, "scope": "call_document"}}


@pytest.mark.parametrize("note,answer", [
    ("Allowed only within the set ceiling.", True),
    ("Subject to Annex 4 conditions, only up to EUR 60,000 per third party.", True),
    ("Allowed for the NCC topic only.", None),                  # a limit to some calls: still a qualification
    ("Only the NCC topic may use it.", None),
])
def test_only_in_a_note_limits_the_answer_when_it_limits_which_calls(note, answer):
    got = cascade.decide({"topic_code": "T", "eligibility_text": ""}, fact(True, "Financial support to third parties is allowed.", note))
    assert got[0] is answer


def test_the_sentence_that_says_for_this_topic_is_not_overruled_by_a_note():
    quote = "For this topic, financial support to third parties is allowed, but only within the set ceiling (see section 10)"
    assert cascade.decide({"topic_code": "T", "eligibility_text": ""}, fact(True, quote, "Allowed for the NCC topic only."))[0] is True


# ======================================================================= B5, B6: the action type decides which sentence is about the call

@pytest.mark.parametrize("code,kind", [
    ("HORIZON-RIA HORIZON  Research and Innovation Actions", "RIA"), ("HORIZON-IA HORIZON Innovation Actions", "IA"),
    ("HORIZON-JU-RIA HORIZON JU Research and Innovation Actions", "RIA"), ("HORIZON-CSA HORIZON Coordination and Support Actions", "CSA"),
    ("DIGITAL-CSA DIGITAL Coordination and Support Actions", "CSA"), ("HORIZON-TMA-MSCA-DN HORIZON TMA MSCA Doctoral Networks", "TMA"),
    ("HORIZON-PCP HORIZON Pre-commercial Procurement", "PCP"), ("HORIZON-EIC-ACC HORIZON EIC Accelerator", "ACC"),
    ("HORIZON-EIC HORIZON EIC Grants", None), ("EDF-LS EDF Lump Sum Grants", None), (None, None), ("", None)])
def test_the_kind_of_action_from_the_portals_type(code, kind):
    assert eligibility.action_kind(code) == kind


def test_the_coordination_and_support_sentence_is_not_a_fact_of_a_research_or_innovation_action():
    for cid in (30, 31, 32, 33, 34, 35, 36, 37, 59, 138, 140):
        assert eligibility.action_kind(CALLS[cid]["type"]) in ("RIA", "IA"), cid
        assert "single_applicant_allowed" not in served(cid)["facts"], cid
    # ... and it stays a fact of a coordination and support action
    assert CALLS[155]["type"].startswith("HORIZON-CSA")
    assert served(155)["facts"]["single_applicant_allowed"]["value"] is True


def test_no_research_or_innovation_call_of_the_set_is_told_that_one_applicant_may_apply_from_a_general_sentence():
    checked = 0
    for cid, c in CALLS.items():
        if eligibility.action_kind(c["type"]) in ("RIA", "IA"):
            checked += 1
            f = served(cid)["facts"].get("single_applicant_allowed")
            assert not (f and f["scope"] == "general"), cid
    assert checked >= 15


def test_a_topic_that_asks_for_two_authorities_does_not_lower_the_minimum_of_three_entities_from_three_countries():
    for cid in (39, 42, 45, 55, 61, 62, 69):
        f = served(cid)["facts"]
        assert f["min_entities"]["value"] >= 3 and f["min_countries"]["value"] >= 3, cid
        assert f["min_entities"]["quote"] == eligibility.GENERAL_CONSORTIUM and f["min_entities"]["scope"] == "general"
        assert "The topic's own conditions add:" in f["min_entities"]["note"]
    for cid in (60, 64):
        f = served(cid)["facts"]
        assert f["min_entities"]["value"] >= 3 and f["min_countries"]["value"] >= 3, cid
    assert eligibility.summary_line(served(55)["facts"]).startswith("Consortium of at least 3 entities from 3 countries")


def test_the_general_consortium_sentence_is_in_the_annexes_we_hold():
    quotes = {f["quote"] for r in FX["rows"].values() for n, f in r["fields"].items()
              if n == "min_entities" and r["scope"] == "general" and f["quote"]}
    assert eligibility.GENERAL_CONSORTIUM in quotes, "the constant must be the annexes' sentence word for word"


def test_the_floor_leaves_other_actions_and_a_topic_that_says_no_consortium_alone():
    facts = {"min_entities": {"value": 2, "quote": "q", "note": None, "confidence": 1, "scope": "topic"}}
    assert eligibility.consortium_floor(facts, "CSA", True) == facts and eligibility.consortium_floor(facts, "PCP", True) == facts
    assert eligibility.consortium_floor(facts, "RIA", False) == facts, "only where the general annexes were read"
    no_consortium = {**facts, "consortium_required": {"value": False, "quote": "q", "note": None, "confidence": 1, "scope": "topic"}}
    assert eligibility.consortium_floor(no_consortium, "RIA", True) == no_consortium
    assert eligibility.consortium_floor({}, "IA", True)["min_entities"]["value"] == 3
    higher = {"min_entities": {"value": 5, "quote": "q", "note": None, "confidence": 1, "scope": "topic"}}
    assert eligibility.consortium_floor(higher, "RIA", True)["min_entities"]["value"] == 5


def test_a_coordination_and_support_call_keeps_its_own_minimum_and_a_general_consortium_rule_is_not_applied_to_it():
    assert served(43)["facts"]["min_entities"]["value"] == 2           # the topic's own number (CSA): not raised to three
    row = {"fields": {"consortium_required": {"value": True, "quote": eligibility.GENERAL_CONSORTIUM, "note": None, "confidence": 1, "verified": True}}}
    assert eligibility._served_fact(row["fields"]["consortium_required"], "general", "consortium_required", None, "CSA") is None
    assert eligibility._served_fact(row["fields"]["consortium_required"], "general", "consortium_required", None, "RIA")["value"] is True


def test_the_accelerators_rate_is_not_the_rate_of_a_pathfinder_challenge_or_an_equity_only_call():
    for cid in (128, 129, 130, 131):
        assert "funding_rate" not in served(cid)["facts"], cid
    accelerator = {"value": "70% of eligible costs for the Accelerator grant component", "note": None, "quote": "q", "confidence": 1, "verified": True}
    assert eligibility._served_fact(accelerator, "general", "funding_rate", None, "ACC")["value"].startswith("70%")
    assert eligibility._served_fact(accelerator, "general", "funding_rate", None, None) is None


# ======================================================================= B9, B2: the Ukraine flag

EDIP_CLOSED = {108, 109, 110, 111, 112, 115, 116, 117, 193}
CYBER = {20, 21, 22, 23, 28, 29, 144, 145, 146, 147, 148, 149, 150, 191, 192}
HORIZON_ASSOCIATED = {30, 31, 32, 34, 35, 36, 37}


def test_edip_calls_are_unknown_for_ukraine_and_the_evidence_gives_the_regulations_sentence():
    """V3-A (verify3-fixes B9): the nine flags were "closed" from Articles 9(1) and 2 alone; the call documents of all nine name Ukraine as a
    member of a SEAP, as a state that designates a procurement agent or as a recipient of additional quantities (stored text read on
    18 October 2026) and none says a Ukrainian entity may not apply. The Regulation limits the recipients; the flag says unknown."""
    for cid in EDIP_CLOSED:
        flag, reason, evidence = ukraine_flag(cid)
        assert (flag, reason) == (None, "programme_rule"), cid
        assert evidence.startswith("Recipients of EDIP funding must be established in the Union or in an associated country"), cid
        assert "Ukraine is not one" in evidence and "No sentence we hold says whether entities established in Ukraine may apply" in evidence, cid


def test_a_document_that_names_ukraine_as_a_member_of_a_seap_does_not_make_an_edip_call_open_or_closed():
    # call 114: "The SEAP must have at least 3 members from EU Member States, EDIP associated countries or Ukraine": a participant, not a recipient
    flag, reason, evidence = ukraine_flag(114)
    assert flag is None and reason == "programme_rule"
    assert "The call document also says" in evidence and "or Ukraine" in evidence and "Ukraine is not one" in evidence


def test_an_edf_call_is_unknown_and_its_evidence_is_the_sentence_of_the_call_documents():
    edf = [cid for cid, c in CALLS.items() if regime_of(c["programme"], c["topic"]) is EDF]
    assert len(edf) >= 15
    for cid in edf:
        flag, reason, evidence = ukraine_flag(cid)
        assert (flag, reason) == (None, "edf_association_unconfirmed"), cid
        assert "pending the signature of the association agreement to EDF" in evidence, cid
        assert "EU-Ukraine Association Agreement" in evidence and "Article 3(1)" in evidence
    assert len(ukraine.EDF_EVIDENCE) <= ukraine.EVIDENCE_MAX


def test_the_digital_europe_cyber_documents_list_the_eligible_countries_and_ukraine_is_not_on_the_list():
    for cid in CYBER:
        flag, reason, evidence = ukraine_flag(cid)
        assert (flag, reason) == (False, "call_document_closed_list"), cid
        assert "Norway, Iceland, Liechtenstein" in evidence and "Ukrain" not in evidence
    # a Digital Europe call whose document names associated countries is not decided by that
    assert all(ukraine_flag(cid)[0] is None for cid in (4, 5, 6))


def test_a_horizon_topic_limited_to_member_states_and_associated_countries_is_open_to_ukraine_which_the_annexes_list_as_associated():
    for cid in HORIZON_ASSOCIATED:
        flag, reason, evidence = ukraine_flag(cid)
        assert (flag, reason) == (True, "topic_text_associated"), cid
        assert "limited to legal entities established in Member States and Associated Countries" in evidence
        assert "list Ukraine among the countries associated to Horizon Europe" in evidence
    # the topics that list countries of their own and the associated countries ("Iceland and Norway, associated countries, OECD"): WP-99,
    # open as the verdict reads them (verdict.country_status: the countries associated to Horizon Europe, Ukraine among them); a list of
    # named countries without the associated ones (the Bridging topic 151) is not decided
    for cid in (33, 152):
        assert ukraine_flag(cid)[:2] == (True, "horizon_associated"), cid
    assert ukraine_flag(151)[0] is None
    assert regime_of(CALLS[30]["programme"], CALLS[30]["topic"]) is HORIZON


def test_the_evidence_of_a_bare_list_item_is_the_whole_sentence_it_stands_in():
    call = {"programme_code": "EDF", "topic_code": "EDF-EDIP-USI-2027-LS-IRA-CUXS", "eligibility_text": None}
    quote = "be established in one of the eligible countries, i.e.: − EU Member States (including OCTs) − non-EU countries: − Ukraine"
    flag, reason, evidence = ukraine.decide(call, {"eligible_countries": {"value": "x", "quote": quote, "scope": "call_document"}})
    assert (flag, reason) == (True, "call_document") and evidence.endswith("Ukraine") and len(evidence) > 25


# ======================================================================= B1: who may apply, by kind of action

EDIP_TOPICS = {
    "EDF-EDIP-P-2026-FNLC-CPA-AMEW": "common_procurement", "EDF-EDIP-P-2026-FNLC-CPA-CDS": "common_procurement",
    "EDF-EDIP-P-2027-FNLC-CPA-AMDS": "common_procurement", "EDF-EDIP-P-2027-FNLC-CPA-C5ISRS": "common_procurement",
    "EDF-EDIP-P-2027-FNLC-CPA-GNPS": "common_procurement", "EDF-EDIP-P-2026-2027-FNLC-SA-SEAP": "seap_support",
    "EDF-EDIP-P-2026-FNLC-CSA-PREP": "edpci_preparation", "EDF-EDIP-P-2026-LS-IRA-EC": "industrial_reinforcement",
    "EDF-EDIP-P-2027-LS-IRA-KEC": "industrial_reinforcement", "EDF-EDIP-P-2027-LS-IRA-PE": "industrial_reinforcement",
    "EDF-EDIP-USI-2027-LS-IRA-CUXS": "industrial_reinforcement", "EDF-EDIP-USI-2026-LS-IRA-MAB": "industrial_reinforcement",
}


@pytest.mark.parametrize("topic,action", list(EDIP_TOPICS.items()))
def test_the_kind_of_action_of_the_twelve_edip_calls(topic, action):
    assert action_of("EDF", topic) == action


def test_other_calls_have_no_kind_of_action():
    assert action_of("EDF", "EDF-2026-DA-AIR-SPS") is None and action_of("HORIZON", "HORIZON-CL3-2026-01-DRS-01") is None
    assert action_of("EDF", None) is None and action_of("EDIDP", "EDF-EDIP-P-2026-FNLC-CPA-AMEW") is None


def block_rules(topic: str) -> set[str]:
    block = rules_apply.build(CONTENT, "EDF", topic)
    assert block is not None and block["action"] == action_of("EDF", topic)
    return {r["rule"] for r in block["rules"]}


def test_the_rules_block_of_a_common_procurement_call_names_who_may_apply_and_the_other_edip_calls_do_not():
    assert "EDIP-CPA-APPLICANT" in block_rules("EDF-EDIP-P-2027-FNLC-CPA-AMDS")
    assert block_rules("EDF-EDIP-P-2027-FNLC-CPA-AMDS") >= {"EDIP-CPA-APPLICANT", "EDIP-ESTABLISH", "EDIP-EXEC-MGMT", "EDIP-CONTROL"}
    assert "EDIP-SEAP-APPLICANT" in block_rules("EDF-EDIP-P-2026-2027-FNLC-SA-SEAP")
    assert "EDIP-PREP-APPLICANT" in block_rules("EDF-EDIP-P-2026-FNLC-CSA-PREP")
    for topic in ("EDF-EDIP-P-2027-LS-IRA-KEC", "EDF-EDIP-P-2026-LS-IRA-EC", "EDF-EDIP-P-2027-LS-IRA-PE"):
        assert not block_rules(topic) & {"EDIP-CPA-APPLICANT", "EDIP-SEAP-APPLICANT", "EDIP-PREP-APPLICANT"}, topic
    assert not block_rules("EDF-EDIP-P-2027-FNLC-CPA-AMDS") & {"EDIP-SEAP-APPLICANT", "EDIP-PREP-APPLICANT"}


def test_the_applicant_rule_quotes_article_11_2_word_for_word_and_the_call_document_rules_say_they_are_not_the_journal():
    rule = next(r for r in CONTENT.programmes["EDIP"].rules if r.code == "EDIP-CPA-APPLICANT")
    assert rule.text_origin == "primary" and "Article 11(2)" in rule.source_ref
    assert ("Only the following legal entities shall be eligible for common procurement actions: (a) contracting authorities of Member States "
            "or associated countries; (b) international organisations; (c) SEAPs; (d) the EDA.") in rule.source_text
    for code in ("EDIP-SEAP-APPLICANT", "EDIP-PREP-APPLICANT"):
        r = next(r for r in CONTENT.programmes["EDIP"].rules if r.code == code)
        assert r.text_origin == "call_document" and r.source_url.endswith(".pdf") and "Call document" in r.source_text


def test_the_edip_control_rule_says_article_9_9_exempts_the_same_entities():
    rule = next(r for r in CONTENT.programmes["EDIP"].rules if r.code == "EDIP-CONTROL")
    assert "Article 9(9)" in rule.note and "Paragraphs 5 and 6 shall not apply to" in rule.source_text
    block = rules_apply.build(CONTENT, "EDF", "EDF-EDIP-P-2027-FNLC-CPA-AMDS")
    assert "Article 9(9)" in next(r for r in block["rules"] if r["rule"] == "EDIP-CONTROL")["caveat"]


def test_the_edf_rules_block_says_ukraine_is_conditional_on_the_association_agreement():
    block = rules_apply.build(CONTENT, "EDF", "EDF-2026-DA-AIR-SPS")
    caveats = {r["rule"]: r["caveat"] for r in block["rules"] if r["caveat"]}
    assert set(caveats) == {"EDF-ESTABLISH", "EDF-EXEC-MGMT"}
    assert all("conditional on the EU-Ukraine association agreement, which is not confirmed" in c for c in caveats.values())


# ======================================================================= B2, B4, B7: the seed

def rule(programme: str, code: str):
    return next(r for r in CONTENT.programmes[programme].rules if r.code == code)


def test_the_edf_rules_treat_ukraine_as_conditional_with_the_call_documents_sentence():
    est = rule("EDF", "EDF-ESTABLISH")
    assert est.condition == {"field": "country", "in": ["EU", "EEA_EFTA"]} and est.conditional_when == {"field": "country", "is": "UA"}
    assert "pending the signature of the association agreement to EDF" in est.texts["conditional"]
    assert "conditional on that agreement, not confirmed" in est.texts["conditional"]
    assert rule("EDF", "EDF-EXEC-MGMT").conditional_when == {"field": "executive_management_country", "is": "UA"}
    assert "Ukraine" not in rule("EDF", "EDF-ESTABLISH").texts["met"] and "Ukraine" not in rule("EDF", "EDF-EXEC-MGMT").texts["met"]


def test_the_safe_rules_make_a_canadian_company_conditional_under_the_provisionally_applied_agreement():
    for code in ("SAFE-ESTABLISH", "SAFE-EXEC-MGMT", "SAFE-ORIGIN-35"):
        r = rule("SAFE", code)
        assert "13 April 2026" in r.texts["conditional"] and "2026/1381" in r.texts["conditional"] and "OJ L 2026/445" in r.texts["conditional"], code
    assert "has been applied on a provisional basis from 13 April 2026" in rule("SAFE", "SAFE-ESTABLISH").source_text
    assert "Canadian legal entities must be established in Canada" in rule("SAFE", "SAFE-ESTABLISH").source_text


@pytest.mark.parametrize("programme,code", [("EDF", "EDF-LEGAL-ENTITY"), ("EDIP", "EDIP-LEGAL-ENTITY"), ("EDIP-USI", "USI-LEGAL-ENTITY")])
def test_a_sole_trader_is_conditional_with_the_wording_of_the_call_documents(programme, code):
    r = rule(programme, code)
    assert "not a natural person" not in r.title and "sole trader" not in r.title
    assert r.conditional_when == {"field": "legal_form", "in": ["no_legal_personality", "natural_person"]}
    assert "self-employed persons, i.e. sole traders, where the company does not have legal personality separate from that of the natural person" in r.texts["conditional"]


# ======================================================================= B8: the tracker

def test_the_tracker_no_longer_says_a_rule_is_missing_from_the_readiness_check_that_is_in_it():
    for e in TRACKER.values():
        assert "not yet part of the readiness check" not in e["what_changed"], e["code"]
    # The rule is named as the readiness check shows it (its title), never by its internal code (WP-59).
    assert f"rule “{rule('EDIP', 'EDIP-ORIGIN-35').title}”" in TRACKER["edip-origin-35"]["what_changed"]
    assert f"rule “{rule('EDIP-USI', 'USI-ORIGIN-35').title}”" in TRACKER["usi-origin-35"]["what_changed"]
    for e in TRACKER.values():
        for key in ("title", "what_changed", "affected"):
            assert not re.search(r"\b[A-Z]{2,}-[A-Z]{2,}-\d+\b", e[key]), (e["code"], key)
    assert {r.code for p in CONTENT.programmes.values() for r in p.rules} >= {"EDIP-ORIGIN-35", "USI-ORIGIN-35"}


def test_the_tracker_cites_the_right_article_and_does_not_widen_the_safe_paragraph():
    assert "Article 3(1)" in TRACKER["edf-ukraine-legal-basis"]["source_ref"] and "Article 1(1)" not in TRACKER["edf-ukraine-legal-basis"]["source_ref"]
    affected = TRACKER["safe-establishment"]["affected"]
    assert "every supplier" not in affected and "Article 16(12)" in affected


def test_the_uk_entry_rests_on_the_written_statement_of_the_uk_government():
    e = TRACKER["safe-uk-unconfirmed"]
    assert e["source_url"].endswith("/2025-12-01/hcws1114") and e["event_date"] == "2025-12-01" and e["status"] == "unconfirmed"
    assert e["source_quote"] == "However, we have not been able to conclude these negotiations with an agreement."
    assert "up to 35 %" in e["what_changed"] and "unconfirmed" in e["what_changed"]


def test_the_edf_ukraine_entry_quotes_the_call_documents_and_the_three_places_agree():
    e = TRACKER["edf-ukraine-in-force-unconfirmed"]
    assert e["source_quote"].startswith("Participation of entities established in Ukraine is pending the signature of the association agreement to EDF")
    assert e["source_quote"] in ukraine.EDF_PENDING or ukraine.EDF_PENDING in e["source_quote"]
    assert "10 of 10" in e["what_changed"] and "conditional" in e["what_changed"]
    # the flag, the readiness rule and the tracker use the same sentence
    assert ukraine.EDF_PENDING.split(" (see")[0] in rule("EDF", "EDF-ESTABLISH").texts["conditional"].replace("“", "").replace("”", "") or \
        "pending the signature of the association agreement to EDF" in rule("EDF", "EDF-ESTABLISH").texts["conditional"]


def test_the_applicant_rule_of_common_procurement_is_in_the_tracker_with_the_sentence_of_the_journal():
    e = TRACKER["edip-common-procurement-applicants"]
    assert e["status"] == "in_force" and "Article 11(2)" in e["source_ref"]
    assert e["source_quote"] == "Only the following legal entities shall be eligible for common procurement actions:"


def test_the_floor_leaves_a_topic_that_lets_a_single_applicant_apply_alone():
    facts = {"single_applicant_allowed": {"value": True, "quote": "q", "note": None, "confidence": 1, "scope": "topic"}}
    assert eligibility.consortium_floor(facts, "RIA", True) == facts


def test_the_edip_programme_card_says_that_not_every_call_is_open_to_a_company():
    summary = CONTENT.programmes["EDIP"].summary
    assert "common procurement actions are open only to contracting authorities" in summary and "Article 11(2)" in summary
