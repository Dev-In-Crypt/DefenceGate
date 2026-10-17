"""Where the eligibility rules of a call are written, mapped deterministically (WP-31)."""

from __future__ import annotations

import json
from pathlib import Path

from dgate import eligibility

CALLS = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "wp31_calls.json").read_text(encoding="utf-8"))
ANNEXES_2026 = ("https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/wp-call/2026-2027/"
                "wp-15-general-annexes_horizon-2026-2027_en.pdf")


def of(call_id: str):
    c = CALLS[call_id]
    return eligibility.sources_of({"documents": c["documents"]}, c["text"])


def test_a_horizon_topic_without_a_call_document_reads_the_general_annexes_and_its_own_text():
    sources = of("56")
    assert [s.scope for s in sources] == ["general", "topic"]
    assert sources[0].key == ANNEXES_2026
    topic = sources[1]
    assert topic.key.startswith("call-text:") and "at least 3 practitioners and 3 public procurers" in topic.text
    assert "Beneficiaries may provide financial support to third parties" in topic.text


def test_the_mapping_is_deterministic_and_the_key_follows_the_text():
    assert of("56") == of("56")
    assert of("56")[1].key != of("39")[1].key
    assert eligibility.topic_key("a") == eligibility.topic_key("a") != eligibility.topic_key("b")


def test_two_calls_of_the_same_work_programme_share_one_general_source():
    assert of("56")[0] == of("39")[0]


def test_the_eic_calls_read_the_eic_work_programme():
    general = of("25")[0]
    assert general.scope == "general" and "EIC-Work-Programme-2026.pdf" in general.key
    assert general.key.startswith("https://eic.ec.europa.eu/"), "the EIC work programme, not the Horizon annexes also listed"
    assert general.label == "EIC work programme"


def test_a_text_that_only_points_to_the_annexes_adds_no_topic_source():
    assert eligibility.topic_text(CALLS["139"]["text"]) is None
    assert all(s.scope != "topic" for s in of("139"))


def test_a_call_with_a_call_document_is_read_from_it_alone():
    cond = {"documents": [{"label": "Call document", "url": "https://example.test/fiche.pdf"},
                          {"label": "Annex A", "url": ANNEXES_2026}]}
    got = eligibility.sources_of(cond, CALLS["56"]["text"])
    assert [(s.scope, s.key) for s in got] == [("call_document", "https://example.test/fiche.pdf")]


def test_the_newest_general_annexes_are_chosen_when_several_are_listed():
    old = ANNEXES_2026.replace("2026-2027", "2023-2024").replace("wp-15", "wp-13")
    mid = ANNEXES_2026.replace("2026-2027", "2025").replace("wp-15", "wp-14")
    cond = {"documents": [{"label": "Annex A", "url": u} for u in (old, ANNEXES_2026, mid)]}
    assert eligibility.sources_of(cond, None)[0].key == ANNEXES_2026


def test_nothing_listed_means_nothing_to_read_and_never_a_guess_from_the_name():
    assert eligibility.sources_of({}, None) == []
    assert eligibility.sources_of(None, None) == []
    insecure = {"documents": [{"label": "Annex A", "url": ANNEXES_2026.replace("https://", "http://")}]}
    assert eligibility.sources_of(insecure, None) == []


def test_a_foreign_or_malformed_document_list_is_ignored():
    assert eligibility.sources_of({"documents": ["x", 3, {"label": None, "url": None}, {"url": 5}]}, None) == []


def test_the_note_of_a_general_or_topic_fact_says_which_it_is():
    fields = {"min_entities": {"value": 3, "note": None, "quote": "q", "confidence": 1, "verified": True},
              "sme_only": {"value": None, "note": None, "quote": None, "confidence": 0, "verified": False},
              "funding_rate": {"value": "100%", "note": "RIA only", "quote": "q", "confidence": 1, "verified": True}}
    general = eligibility.annotate_scope(fields, "general")
    assert general["min_entities"]["note"].startswith("General rule of the work programme annexes")
    assert general["funding_rate"]["note"].endswith("RIA only")
    assert general["sme_only"]["note"] is None, "an unstated fact gets no note"
    assert eligibility.annotate_scope(fields, "topic")["min_entities"]["note"] == "Stated in this topic's own conditions."
    assert eligibility.annotate_scope(fields, "call_document") == fields


def test_the_summary_line_is_built_from_verified_facts_only_and_marks_a_general_source():
    def f(v, scope="call_document"):
        return {"value": v, "scope": scope, "quote": "q", "note": None, "confidence": 1}

    assert eligibility.summary_line({}) is None
    line = eligibility.summary_line({"min_entities": f(3), "min_countries": f(3), "sme_only": f(True)})
    assert line == "Consortium of at least 3 entities from 3 countries; SMEs only."
    assert eligibility.summary_line({"min_entities": f(3, "general")}).endswith("the topic may add conditions.")


def test_the_topic_text_that_is_stored_and_sent_carries_no_e_mail_address():
    text = ("3. Other Eligible Conditions This topic requires at least three practitioners from three Member States; "
            "questions go to jane.doe@example.eu or the national contact point. 4. Financial and operational capacity")
    got = eligibility.topic_text(text)
    assert got is not None and "@" not in got and "practitioners" in got
