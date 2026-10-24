"""WP-35: the code checks on eligibility facts (V-B verifier, 17 October 2026).

The regression set is the 30 calls the verifier read against their documents: the facts stored for
them (prompt v3, the quotes are the documents' sentences) in `fixtures/wp35_verifier_calls.json`.
What the verifier judged wrong is expected to go, what it judged right is expected to stay."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dgate import cascade, eligibility
from dgate.eligibility import Source

FX = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "wp35_verifier_calls.json").read_text(encoding="utf-8"))
AT = datetime(2026, 10, 17, tzinfo=timezone.utc)
CALLS = {c["id"]: c for c in FX["calls"]}


def _held():
    """The rows as production holds them: one per document, keyed by url (read before rows were per topic)."""
    return {key: {"url": key, "extracted_at": AT, "fields": {
        name: {"value": f["v"], "note": f["n"], "quote": f["q"], "confidence": 0.9, "verified": True}
        for name, f in doc["facts"].items()}} for key, doc in FX["documents"].items()}


def _sources(call):
    out = []
    for key in call["documents"]:
        scope = FX["documents"][key]["scope"]
        out.append(Source(scope, key, scope, document=key if scope == "call_document" else None,
                          topic=call["topic"] if scope == "call_document" else None))
    return out


def served(call_id: int) -> dict:
    call = CALLS[call_id]
    return eligibility.assemble(_sources(call), _held(), call["topic"], eligibility.action_kind(call["type"]))


def before(call_id: int) -> dict[str, object]:
    """What was served before WP-35: every verified fact, the topic's own over the general one."""
    facts: dict[str, object] = {}
    docs = sorted((FX["documents"][k] for k in CALLS[call_id]["documents"]), key=lambda d: eligibility.SCOPES.index(d["scope"]))
    for doc in docs:
        for name, f in doc["facts"].items():
            facts[name] = f["v"]
    return facts


def after(call_id: int) -> dict[str, object]:
    return {n: f["value"] for n, f in served(call_id)["facts"].items()}


def test_wp93_a_topics_border_authorities_are_required_partners_and_the_annexes_list_of_who_may_apply_stays():
    for cid in (43, 69):
        got = served(cid)["facts"]
        assert got["required_partners"]["value"].startswith("at least 2 Border")
        assert got["entity_types"]["scope"] == "general" and "Legal" in str(got["entity_types"]["value"])


# What the verifier judged wrong and the checks must take away (call ids), and why.
GONE = {
    "cascade_funding": {138, 140, 59, 33, 36, 60, 69, 43,    # F1: general "where the topic allows"
                        144, 145},                           # F4: allowed for the NCC topic only
    "ownership_control_restriction": {138, 140, 59, 43,      # F2: general "topics may exclude"
                                      63, 69,                # a "No" built on the high-risk-supplier sentence
                                      19, 119},              # E3: high-risk suppliers, not a control restriction
    "single_applicant_allowed": {138, 140, 59, 33, 36,       # F3: RIA/IA consortium actions
                                 109, 110},                  # F5: only a SEAP may apply alone
    # V2-B6: "up to 70 % for the EIC Accelerator grant component" is the rate of a grant scheme, not of the equity-only defence call
    "funding_rate": {131},
}


def test_the_facts_the_verifier_found_wrong_are_gone_and_nothing_else_is_lost():
    lost = {}
    for cid in CALLS:
        b, a = before(cid), after(cid)
        for name in b:
            if name not in a:
                lost.setdefault(name, set()).add(cid)
    assert lost == GONE


@pytest.mark.parametrize("cid", [138, 140, 59, 33, 36, 60, 69, 43])
def test_a_general_annex_sentence_is_never_a_yes_for_cascade_funding(cid):
    got = served(cid)["facts"]
    assert "cascade_funding" not in got
    assert "financial support to third parties" not in (eligibility.summary_line(got) or "")


@pytest.mark.parametrize("cid", [138, 140, 59, 43])
def test_a_general_annex_sentence_is_never_a_yes_for_an_ownership_restriction(cid):
    got = served(cid)["facts"]
    assert "ownership_control_restriction" not in got
    assert "ownership control" not in (eligibility.summary_line(got) or "")


def test_a_topics_own_text_still_states_what_it_states():
    # call 63: the topic's own conditions say FSTP; call 33: its own text names the restriction.
    assert served(63)["facts"]["cascade_funding"]["scope"] == "topic"
    assert served(33)["facts"]["ownership_control_restriction"] == {
        **served(33)["facts"]["ownership_control_restriction"], "scope": "topic", "value": True}


@pytest.mark.parametrize("cid", [19, 119])
def test_a_high_risk_supplier_sentence_is_not_an_ownership_control_restriction(cid):
    assert "ownership_control_restriction" not in served(cid)["facts"]


@pytest.mark.parametrize("cid", [28, 191, 81, 96])
def test_a_real_control_restriction_stays(cid):
    assert served(cid)["facts"]["ownership_control_restriction"]["value"] is True


@pytest.mark.parametrize("cid", [144, 145])
def test_a_sentence_about_another_topic_is_not_a_fact_of_this_call(cid):
    s = served(cid)
    assert "cascade_funding" not in s["facts"]
    assert "NCC" in s["other_topic"]["cascade_funding"]
    # and the flag keeps its reason: the document allows it for other topics only.
    flag = cascade.decide({"topic_code": CALLS[cid]["topic"], "eligibility_text": None}, s["facts"], s["other_topic"])
    assert flag[:2] == (None, "call_document_other_topic")


def test_a_sentence_that_names_this_topic_is_not_turned_into_a_no():
    assert before(123)["cascade_funding"] is False          # the model's slip, against its own quote
    assert after(123)["cascade_funding"] is True


@pytest.mark.parametrize("cid", [138, 140, 59, 33, 36])
def test_a_consortium_action_does_not_also_allow_a_single_applicant(cid):
    got = served(cid)["facts"]
    # V2-B5: the sentence that lets a single applicant apply is about Coordination and support actions, so it is not served
    # for a research or innovation action in the first place (WP-35 settled the contradiction afterwards, with a note)
    assert got["consortium_required"]["value"] is True and "single_applicant_allowed" not in got


def test_the_same_sentence_gives_the_same_answer_on_two_calls():
    """EDIP CPA 109 and 110: 'Single applicants may apply only if they are a SEAP.'"""
    a, b = served(109)["facts"], served(110)["facts"]
    for got in (a, b):
        assert got["consortium_required"]["value"] is True and "single_applicant_allowed" not in got
        assert "SEAP" in got["consortium_required"]["note"]
    assert (a["min_entities"]["value"], a["consortium_required"]["value"]) == (b["min_entities"]["value"], b["consortium_required"]["value"])


def test_facts_the_verifier_judged_correct_are_served_unchanged():
    for cid in (96, 81, 85, 88, 101, 118, 78, 126, 131):
        b, a = before(cid), after(cid)
        assert {n: v for n, v in b.items() if n in a} == {n: v for n, v in a.items() if n in b}, cid
    assert after(78)["entity_types"] == before(78)["entity_types"]
    assert after(96)["eligible_countries"] == before(96)["eligible_countries"]


def test_an_unread_call_and_a_call_without_sources_keep_their_states():
    assert eligibility.assemble([], {}, None)["state"] == "no_source"
    got = eligibility.assemble(_sources(CALLS[96]), {}, CALLS[96]["topic"])
    assert got["state"] == "not_read" and got["facts"] == {}


# ------------------------------------------------------------------ the pieces

def fact(value, note=None, quote="q", scope="call_document", confidence=0.9):
    return {"value": value, "note": note, "quote": quote, "scope": scope, "confidence": confidence}


def test_topic_codes_are_found_and_standards_are_not():
    assert eligibility.topic_codes("allowed in DIGITAL-2026-BESTUSE-10-EHDS and HORIZON-CL3-2026-01-BM-03.") == [
        "DIGITAL-2026-BESTUSE-10-EHDS", "HORIZON-CL3-2026-01-BM-03"]
    assert eligibility.topic_codes("certified to ISO-9001-2015 and AQAP-2110-2022") == []


@pytest.mark.parametrize("quote,mine,other", [
    ("allowed in DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC", "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-REGCABH", True),
    ("allowed in DIGITAL-ECCC-2027-DEPLOY-CYBER-11-REGCABH", "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-REGCABH", False),
    ("allowed in BESTUSE-TECH-09-MDL", "DIGITAL-2025-BESTUSE-TECH-09-MDL", False),            # the short form
    ("allowed in BESTUSE-TECH-09-WALLET", "DIGITAL-2025-BESTUSE-TECH-09-MDL", True),
    ("topics of EDF-2026-DA", "EDF-2026-DA-SENS-CEW-STEP", False),                            # the call, not another topic
    ("the call DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC and DIGITAL-ECCC-2027-DEPLOY-CYBER-11-REGCABH",
     "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-REGCABH", False),                                     # names this one too
    ("the topic DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NCH", "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH", False),   # a document's abbreviation (call 191)
    ("see DIGITAL-2025-BESTUSE-08", "DIGITAL-2026-BESTUSE-10-EHDS", False),                    # the previous year's call (call 123)
    ("allowed in DIGITAL-2026-BESTUSE-10-NETWORKSICS", "DIGITAL-2026-BESTUSE-10-EHDS", True),
    ("a sentence with no code", "EDF-2026-DA-SENS-CEW-STEP", False),
    ("allowed in EDF-2026-DA-OTHER-ONE", None, False),                                        # topic unknown: no check
])
def test_names_other_topic(quote, mine, other):
    assert eligibility.names_other_topic(quote, mine) is other


def test_the_quote_check_refuses_a_quote_that_names_another_topic():
    text = "Financial support to third parties is allowed in topic DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC for grants."
    answer = {n: {"value": None, "confidence": 0.0, "quote": None, "note": None} for n in eligibility.FIELDS}
    answer["cascade_funding"] = {"value": True, "confidence": 0.95, "note": None, "quote": text}
    mine = eligibility.check_quotes(answer, text, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-REGCABH")["cascade_funding"]
    assert mine["verified"] is False and mine["other_topic"] is True and mine["confidence"] == eligibility.UNVERIFIED_CAP
    ncc = eligibility.check_quotes(answer, text, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC")["cascade_funding"]
    assert ncc["verified"] is True and "other_topic" not in ncc
    assert eligibility.check_quotes(answer, text)["cascade_funding"]["verified"] is True       # no topic given: as before


def test_the_model_is_told_which_topic_the_call_is():
    head = eligibility.topic_header(("HORIZON-CL3-2026-01-BM-03", "Reliability of  age\nassessment"))
    assert "HORIZON-CL3-2026-01-BM-03" in head and "Reliability of age assessment" in head and head.endswith("\n\n")
    assert eligibility.topic_header(None) == ""
    assert "this topic" in eligibility.SYSTEM and "high-risk" in eligibility.SYSTEM
    assert eligibility.PROMPT_VERSION == 4


def test_call_document_sources_are_keyed_per_topic_and_open_at_the_document():
    cond = {"documents": [{"label": "Call document", "url": "https://example.test/fiche.pdf"}]}
    [one] = eligibility.sources_of(cond, None, "EDF-2026-DA-X")
    assert one.key == "https://example.test/fiche.pdf#EDF-2026-DA-X" and one.url == "https://example.test/fiche.pdf"
    [plain] = eligibility.sources_of(cond, None)
    assert plain.key == plain.url == "https://example.test/fiche.pdf"


def test_the_topic_row_wins_over_the_older_document_row():
    cond = {"documents": [{"label": "Call document", "url": "https://example.test/fiche.pdf"}]}
    srcs = eligibility.sources_of(cond, None, "EDF-2026-DA-X")

    def row(url, n):
        return {url: {"url": url, "extracted_at": AT, "fields": {"min_entities": {
            "value": n, "note": None, "quote": "q", "confidence": 1.0, "verified": True}}}}
    legacy = row("https://example.test/fiche.pdf", 3)
    assert eligibility.assemble(srcs, legacy, "EDF-2026-DA-X")["facts"]["min_entities"]["value"] == 3
    both = {**legacy, **row("https://example.test/fiche.pdf#EDF-2026-DA-X", 5)}
    assert eligibility.assemble(srcs, both, "EDF-2026-DA-X")["facts"]["min_entities"]["value"] == 5


@pytest.mark.parametrize("quote,expected", [
    ("Entities that are assessed as high -risk suppliers of mobile network communication equipment (and any entities they own or control) are not eligible.", True),
    ("Entities must not be directly or indirectly controlled from a country that is not an eligible country.", False),
    ("high-risk suppliers are excluded; entities controlled by non-eligible third countries as well", False),
    (None, False),
])
def test_supplier_exclusion(quote, expected):
    assert eligibility.is_supplier_exclusion(quote) is expected


def test_reconcile_contradictions():
    # consortium and single applicant: the single-applicant fact goes, its note is kept
    got = eligibility.reconcile({"consortium_required": fact(True), "single_applicant_allowed": fact(True, "CSA only")})
    assert set(got) == {"consortium_required"} and "CSA only" in got["consortium_required"]["note"]
    # conditional single applicant and a consortium minimum: the others must form a consortium
    got = eligibility.reconcile({"consortium_required": fact(False), "min_entities": fact(3),
                                 "single_applicant_allowed": fact(True, "Only a SEAP may apply alone.")})
    assert got["consortium_required"]["value"] is True and "single_applicant_allowed" not in got
    # round 3 (call 114): only single applications: no consortium, the minimum is the SEAP's own membership
    got = eligibility.reconcile({"consortium_required": fact(True, "The SEAP must have at least 3 members.",
                                                             "Only single applications by a SEAP are allowed."),
                                 "min_entities": fact(3),
                                 "single_applicant_allowed": fact(True, "Only a SEAP may submit a single application.")})
    assert got["consortium_required"]["value"] is False and "single_applicant_allowed" in got
    assert "membership" in got["consortium_required"]["note"] and "check the call document" not in got["consortium_required"]["note"]
    # a plain single applicant with an optional consortium is consistent
    same = {"consortium_required": fact(False), "min_entities": fact(3), "single_applicant_allowed": fact(True)}
    assert eligibility.reconcile(same) == same
    # no consortium, a minimum of two, nobody may apply alone: the two disagree
    assert "consortium_required" not in eligibility.reconcile({"consortium_required": fact(False), "min_entities": fact(2)})
    # one entity is not a minimum that contradicts anything
    one = {"consortium_required": fact(False), "min_entities": fact(1)}
    assert eligibility.reconcile(one) == one
    assert eligibility.reconcile({}) == {}


def test_reconcile_does_not_change_its_input():
    src = {"consortium_required": fact(True), "single_applicant_allowed": fact(True)}
    eligibility.reconcile(src)
    assert "single_applicant_allowed" in src


def test_the_summary_line():
    # F8: one entity is not a consortium, one country is not "from 1 countries"
    assert eligibility.summary_line({"min_entities": fact(1), "min_countries": fact(1),
                                     "single_applicant_allowed": fact(True)}) == "A single applicant may apply."
    assert eligibility.summary_line({"min_entities": fact(1), "min_countries": fact(1)}) is None
    assert eligibility.summary_line({"min_entities": fact(3), "min_countries": fact(1)}) == "Consortium of at least 3 entities."
    assert eligibility.summary_line({"min_entities": fact(3), "min_countries": fact(3)}) == "Consortium of at least 3 entities from 3 countries."
    # F1: a general-annex Yes is not repeated, a call's own is
    general = {"cascade_funding": fact(True, scope="general"), "ownership_control_restriction": fact(True, scope="general")}
    assert eligibility.summary_line(general) is None
    own = {"cascade_funding": fact(True), "ownership_control_restriction": fact(True)}
    assert eligibility.summary_line(own) == "Ownership control restriction; financial support to third parties."
