"""Cascade funding (financial support to third parties) decided from the call text and the facts (WP-31)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dgate import cascade

CALLS = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "wp31_calls.json").read_text(encoding="utf-8"))


def fact(value, quote="", note=None, scope="call_document"):
    return {"cascade_funding": {"value": value, "quote": quote, "note": note, "confidence": 1.0, "scope": scope}}


# ---- the call text: the title of an annex is not a statement

def test_the_annex_title_every_horizon_call_lists_is_not_a_statement():
    # id 39 lists "Information on financial support to third parties (HE)" and says nothing else about it.
    assert "financial support to third parties" in CALLS["39"]["text"].lower()
    assert cascade.text_statement(CALLS["39"]["text"]) == (None, None)


def test_an_edf_guide_title_is_not_a_statement():
    text = "Rules for Legal Entity Guidelines on FSTP implementation - WP2026 EU Financial Regulation 2024/2509"
    assert cascade.text_statement(text) == (None, None)


def test_a_sentence_that_states_it_is_found_with_its_words():
    yes, sentence = cascade.text_statement(CALLS["56"]["text"])
    assert yes is True and sentence == "Beneficiaries may provide financial support to third parties."


@pytest.mark.parametrize("text,expected", [
    ("Beneficiaries must provide financial support to third parties.", True),
    ("Financial support to third parties is not allowed.", False),
    ("Beneficiaries may not provide financial support to third parties.", False),
    ("FSTP is allowed under this topic.", True),
    ("The cascade funding scheme is described in the guide.", None),   # no statement of yes or no
    ("", None),
    (None, None),
])
def test_sentences_with_and_without_a_yes_or_a_no(text, expected):
    assert cascade.text_statement(text)[0] is expected


def test_a_text_that_says_yes_and_no_is_not_decided():
    both = ("Financial support to third parties is allowed in topic A. "
            "Financial support to third parties is not allowed in topic B.")
    assert cascade.text_statement(both) == (None, None)


# ---- decide(): the order of the sources

def test_a_document_fact_decides_before_the_text():
    call = {"topic_code": "EDF-2026-DA-X", "eligibility_text": "Beneficiaries may provide financial support to third parties."}
    flag, reason, evidence = cascade.decide(call, fact(False, "Financial support to third parties is not allowed."))
    assert (flag, reason) == (False, "call_document") and "not allowed" in evidence


def test_no_fact_and_no_statement_is_not_determined_not_no():
    assert cascade.decide({"topic_code": "T", "eligibility_text": CALLS["39"]["text"]}, {}) == (None, "not_stated", None)


def test_the_text_decides_when_no_document_was_read():
    flag, reason, evidence = cascade.decide({"topic_code": "T", "eligibility_text": CALLS["56"]["text"]}, {})
    assert (flag, reason) == (True, "call_text") and evidence.startswith("Beneficiaries may provide")


def test_the_general_annexes_never_decide_it():
    out = cascade.decide({"topic_code": "T", "eligibility_text": ""}, fact(True, "FSTP may be allowed.", scope="general"))
    assert out == (None, "not_stated", None)


def test_the_topic_text_fact_decides():
    flag, reason, _ = cascade.decide({"topic_code": "T", "eligibility_text": ""},
                                     fact(True, "Beneficiaries may provide financial support to third parties.", scope="topic"))
    assert (flag, reason) == (True, "topic_text")


def test_a_document_that_names_the_topics_where_it_is_allowed():
    quote = "Financial support to third parties is allowed in topic DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC for grants under"
    mine = cascade.decide({"topic_code": "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC", "eligibility_text": ""}, fact(True, quote))
    other = cascade.decide({"topic_code": "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME", "eligibility_text": ""}, fact(True, quote))
    assert mine[:2] == (True, "call_document")
    assert other[:2] == (None, "call_document_other_topic"), "a topic the quote does not name is undecided, not 'no'"


def test_a_value_false_with_a_note_is_a_qualification_not_an_answer():
    # "not allowed for A, allowed for B" read as the lowest case: false with a note.
    f = fact(False, "For this topic, financial support to third parties is NOT allowed.", note="Allowed for COMPETITIONS.")
    assert cascade.decide({"topic_code": "T", "eligibility_text": ""}, f)[:2] == (None, "not_stated")


def test_a_value_true_limited_with_only_is_not_taken_for_every_call():
    f = fact(True, "Financial support to third parties is allowed.", note="Allowed for the NCC topic only.")
    assert cascade.decide({"topic_code": "T", "eligibility_text": ""}, f)[:2] == (None, "not_stated")


def test_the_evidence_is_capped():
    long = "Financial support to third parties is allowed " + "x" * 600
    assert len(cascade.decide({"topic_code": "T", "eligibility_text": ""}, fact(True, long))[2]) == cascade.EVIDENCE_MAX
