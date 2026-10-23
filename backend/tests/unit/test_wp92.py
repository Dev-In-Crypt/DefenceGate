"""WP-92: what a call funds, from the topic's own description, commercial sentences only; and who may apply
from the call's own eligibility facts first.

The filter fails closed: a sentence is kept only when it is recognised as saying what the call is for and has no
figure, no specification word and no named system. Scope, functional requirements and activity tables are never read.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dgate import topic_summary as ts
from dgate import who_apply
from dgate.sources import eu_portal

FIXTURES = json.loads((Path(__file__).parents[1] / "fixtures" / "eu_topic_descriptions.json").read_text(encoding="utf-8"))
TOPICS = {k: v for k, v in FIXTURES.items() if not k.startswith("_")}


# ------------------------------------------------------------------------- the sentence filter

KEPT = [
    "The aim is to strengthen the European defence technological and industrial base in the field of passive surveillance.",
    "Proposals are expected to foster cooperation between industry, research organisations and SMEs across Member States.",
    "The objective is to develop the next generation of ground combat capabilities in a cooperative way between Member States.",
    "Proposals should enable European industry to deliver interoperable solutions to the armed forces of several Member States.",
    "Participating SMEs are expected to gain access to new supply chains.",
    "Actions should support cooperation between Ukrainian and EU companies in ramping up manufacturing of defence products.",
    "The topic also aims to secure supply chains for critical raw materials used by the defence industry.",
    "This topic will support the common procurement of air defence products by consortia of Member States.",
    "It aims to reduce fragmentation of demand and to improve the security of supply of the European defence industry.",
    "Better uptake of innovative solutions by public buyers and end-users across Europe.",
    "New market opportunities for European SMEs in the civil security sector.",
    "The project is expected to strengthen the competitiveness of the EU security industry.",
    "The objective is to deploy trusted artificial intelligence testing facilities that support SMEs and start-ups in "
    "bringing products to market.",
    "Results are expected to support future joint procurement by Member States.",
    "The topic contributes to the CARD focus area on enhanced military mobility.",
    "Projects funded under the 2026 call should strengthen cooperation between EDF beneficiaries and NATO partners.",
]

DROPPED = [
    # figures with units, percentages, TRL levels
    ("The detection range should exceed 150 km against small targets.", "figure"),
    ("The resulting solutions should reach TRL 4 at the end of the project.", "figure"),
    ("The vehicle should reach a top speed of 90 km/h.", "figure"),
    ("Applicants should increase output by 30% within 24 months.", "figure"),
    ("Faster deployment of drones with a flight endurance of more than 2 hours.", "figure"),
    ("The system shall operate in the 2-4 GHz band to support interoperability.", "figure"),
    # specification words
    ("Sensor accuracy and latency must be improved over current systems.", "specification"),
    ("The design of the turret should allow modular integration.", "specification"),
    ("The research should explore ways of increasing the operational endurance of unmanned vessels.", "specification"),
    ("The project should aim for a payload capacity of at least one tonne.", "specification"),
    ("Ballistic protection of the hull must be considered.", "specification"),
    ("The vessel should be designed for operation in high sea states.", "specification"),
    ("The solution shall support European industry in the integration of new sensors.", "specification"),
    ("The demonstrator should improve the resolution and bandwidth of European radars.", "specification"),
    ("Industry should develop solutions that meet the requirements of the armed forces.", "specification"),
    ("The project should increase the altitude and speed of European high-altitude platforms.", "specification"),
    ("The aim is to develop a technology readiness roadmap for European industry.", "specification"),
    # named systems
    ("The project builds on the work of MGCS and Leopard upgrade programmes.", "named system"),
    ("Patriot and IRIS-T SLM batteries are eligible products.", "named system"),
    ("The action should support the integration of the Eurodrone into European fleets.", "named system"),
    ("Proposals should develop MALE RPAS capabilities for European armed forces.", "named system"),
    # not classified as purpose: dropped, never guessed
    ("The facilities should be open to companies from every Member State on fair terms.", "unclassified"),
    ("In addition, this action complements earlier investments.", "unclassified"),
    ("The challenge is open to all bidders on the same terms as before.", "unclassified"),
    # lead-ins, links, addresses, fragments
    ("Projects' results are expected to contribute to some or all of the following outcomes:", "fragment"),
    ("See https://example.europa.eu for details on the support available to SMEs.", "link"),
    ("Contact the helpdesk at info@example.eu for support to industry.", "link"),
    ("Supports SMEs.", "length"),
]


@pytest.mark.parametrize("sentence", KEPT)
def test_a_sentence_about_what_the_call_is_for_is_kept(sentence):
    assert ts.verdict(sentence) is None


@pytest.mark.parametrize("sentence,why", DROPPED)
def test_a_technical_named_or_unclassified_sentence_is_dropped(sentence, why):
    assert ts.verdict(sentence) == why


# ------------------------------------------------------------------------- sections

def test_only_objective_and_expected_outcome_are_read_never_scope_or_requirements():
    read = " ".join(ts.purpose_text(TOPICS["EDF-2026-RA-SENS-MSDT"]["description"]))
    assert "The objective of this topic" in read
    for elsewhere in ("demonstrator able to fuse", "2-4 GHz", "track at least 50", "waveform", "Mandatory",
                      "Reduced dependence"):
        assert elsewhere not in read
    horizon = " ".join(ts.purpose_text(TOPICS["HORIZON-CL3-2026-01-DRS-01"]["description"]))
    assert "first responders" in horizon and "toolbox" not in horizon


def test_a_heading_on_the_same_line_as_its_text_and_one_without_a_colon_are_both_read():
    assert ts.purpose_text(TOPICS["EDF-2026-DA-GROUND-FCV"]["description"])[0].startswith("The objective is to develop")
    assert ts.purpose_text(TOPICS["EDF-EDIP-USI-2026-SCS"]["description"])[0].startswith("The objective of this topic")
    scope = "".join(ts.purpose_text(TOPICS["EDF-2026-DA-GROUND-FCV"]["description"]))
    assert "prototyping of the platform" not in scope


def test_text_with_no_purpose_heading_gives_nothing_fail_closed():
    assert ts.funds_summary(TOPICS["EDF-2026-NO-HEADINGS"]) is None          # no heading: not classified
    assert ts.funds_summary(TOPICS["EDF-2026-LS-RA-CHALLENGE"]) is None      # an objective under Functional requirements
    assert ts.funds_summary({"description": ""}) is None
    assert ts.funds_summary({"description": 5}) is None
    assert ts.funds_summary({}) is None
    assert ts.funds_summary(None) is None


def test_the_summary_is_at_most_three_kept_sentences_in_the_order_of_the_text():
    got = ts.funds_summary(TOPICS["EDF-2026-RA-SENS-MSDT"])
    assert got == ("The aim is to strengthen the European defence technological and industrial base in the field of passive "
                   "surveillance. Proposals are expected to foster cooperation between industry, research organisations "
                   "and SMEs across Member States. The topic contributes to the CARD focus area on enhanced military "
                   "mobility.")
    for topic in TOPICS.values():
        summary = ts.funds_summary(topic)
        if summary:
            kept = [s for s, why in ts.sentences(topic["description"]) if why is None]
            assert summary == " ".join(kept[:3])


def test_bullets_become_sentences_and_a_lead_in_is_dropped():
    got = ts.funds_summary(TOPICS["HORIZON-CL3-2026-01-DRS-01"])
    assert got == ("Improved preparedness of first responders and civil protection authorities for large-scale disasters. "
                   "Better uptake of innovative solutions by public buyers and end-users across Europe. "
                   "New market opportunities for European SMEs in the civil security sector.")


def test_no_kept_sentence_of_any_fixture_carries_a_digit_other_than_a_year_or_a_specification_word():
    for topic in TOPICS.values():
        for s, why in ts.sentences(topic["description"]):
            if why is None:
                assert not ts._DIGIT.search(ts._YEAR.sub("", s)), s
                assert not ts._SPEC.search(s), s


# ------------------------------------------------------------------------- the connector

def test_the_connector_stores_the_summary_with_the_other_detail_fields():
    details = {**TOPICS["EDF-EDIP-USI-2026-SCS"], "conditions": "<p>described in section 6 of the call document.</p>"}
    fields = eu_portal.detail_fields(details, "EDF-EDIP-USI-2026-SCS")
    assert fields["funds_summary"].startswith("The objective of this topic is to increase the production capacity")
    assert "30%" not in fields["funds_summary"] and "reconfiguration" not in fields["funds_summary"]
    # the full description is not a field of the call
    assert all("description" not in k for k in fields) and "description" not in fields["conditions_raw"]
    assert eu_portal.detail_fields({"conditions": "<p>x</p>"}, "X")["funds_summary"] is None


def test_the_summary_is_a_call_detail_column():
    from dgate import db

    assert "funds_summary" in db.CALL_DETAIL_FIELDS


# ------------------------------------------------------------------------- who may apply, from the call's own facts

def fact(value, scope="call_document", quote="q"):
    return {"value": value, "note": None, "quote": quote, "confidence": 1.0, "scope": scope}


@pytest.mark.parametrize("facts,expected", [
    # only public buyers: Member State procurement agencies, ministries
    ({"entity_types": fact(["Member State procurement agencies", "Ministries of defence"])}, ("public", None)),
    ({"entity_types": fact(["Public authorities", "Contracting authorities of Member States"])}, ("public", None)),
    ({"entity_types": fact(["Public legal entities"])}, ("public", None)),
    # companies
    ({"entity_types": fact(["Any legal entity"])}, ("companies", None)),
    ({"entity_types": fact(["Public or private legal entities established in the EU"])}, ("companies", None)),
    ({"entity_types": fact(["Legal entities established in Member States"])}, ("companies", None)),
    ({"entity_types": fact(["Universities", "SMEs"])}, ("companies", None)),
    # SME-only: companies, and the flag
    ({"sme_only": fact(True), "entity_types": fact(["SMEs"])}, ("companies", True)),
    ({"sme_only": fact(True, scope="topic")}, ("companies", True)),
    # nothing the call's own facts settle: the programme rules decide
    ({"entity_types": fact(["Universities", "Research organisations"])}, (None, None)),
    ({"entity_types": fact(["Member States"])}, (None, None)),
    ({"entity_types": fact([])}, (None, None)),
    ({}, (None, None)),
    # a rule of the work programme's general annexes is not the call's own
    ({"entity_types": fact(["Public authorities"], scope="general")}, (None, None)),
    ({"sme_only": fact(True, scope="general")}, (None, None)),
    ({"sme_only": fact(False)}, (None, None)),
])
def test_who_may_apply_is_read_from_the_calls_own_facts_first(facts, expected):
    who, sme, _ = who_apply.decide(facts)
    assert (who, sme) == expected


def test_the_evidence_is_the_quote_it_rests_on():
    assert who_apply.decide({"entity_types": fact(["Ministries of defence"], quote="Only ministries may apply.")})[2] \
        == "Only ministries may apply."
