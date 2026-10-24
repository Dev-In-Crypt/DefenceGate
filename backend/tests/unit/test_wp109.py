"""WP-109 (round 4 of 24 October 2026): funding call verdicts and funding lists. Pure: no database, no network.

The facts are what production served on 24 October for the calls named (GET /v1/funding/<id>, read-only), trimmed to the facts a test reads.
"""

from __future__ import annotations

import pytest

from dgate import funding, verdict, who_apply
from dgate.network_api import relevance
from dgate.sources import aid
from dgate.sources import eu_portal as portal


def _topic(identifier: str, title: str, *, programme: str = "HORIZON", division: str = "HORIZON.2.4", tags=None) -> dict:
    return {"type": 1, "identifier": identifier, "title": title, "frameworkProgramme": [{"abbreviation": programme}],
            "programmeDivision": [{"abbreviation": division}], "tags": tags or [], "status": {"abbreviation": "Open"}}


# ---------------------------------------------------------------- 6. the dual-use rule

@pytest.mark.parametrize("identifier,title", [
    ("HORIZON-NEB-2027-02-NEB-SOIL-01", "Reducing soil sealing through sustainable urban and territorial design"),       # 38
    ("HORIZON-RAISE-2026-01-03", "RAISE Doctoral Networks for AI in Science (RAISE pilot)"),                              # 77
    ("HORIZON-EIC-PATHFINDERCHALLENGES-01-02", "Biotechnology for Healthy Ageing"),                                       # 130
    ("HORIZON-JU-EUROHPC-2026-QEXP-14-01", "Quantum Experimental Pilot Lines for Quantum Technologies"),                  # 139
    ("HORIZON-NATURE-2027-02-04", "Innovative solutions to fight wildlife trafficking and to reduce invasive alien species"),  # 154
])
def test_clearly_civil_topics_of_a_dual_use_division_are_not_collected(identifier, title):
    record = _topic(identifier, title, division="HORIZON.3.1" if "EIC" in identifier else "HORIZON.2.4")
    assert portal.civil_subject(identifier, title)
    assert portal.regime(record) is None
    assert portal.in_scope(record) is False


@pytest.mark.parametrize("identifier,title,division", [
    ("HORIZON-CL3-2026-01-BM-01", "Advanced border surveillance and situational awareness", "HORIZON.2.3"),
    ("HORIZON-EIC-2026-ACCELERATOR-01", "EIC Accelerator 2026 - Short proposal", "HORIZON.3.1"),
    ("HORIZON-CL4-2027-05-DIGITAL-EMERGING-03", "Advanced integrated photonic devices", "HORIZON.2.4"),
    ("HORIZON-EIC-PATHFINDERCHALLENGES-01-03", "DeepRAP: Deep Reasoning, Abstraction & Planning", "HORIZON.3.1"),
])
def test_the_dual_use_topics_stay(identifier, title, division):
    assert portal.civil_subject(identifier, title) is None
    assert portal.regime(_topic(identifier, title, division=division)) == "dual_use"


def test_the_step_defence_seal_still_wins_over_a_civil_subject():
    assert portal.regime(_topic("HORIZON-NATURE-2027-02-04", "Wildlife", tags=["STEP-Defence"])) == "defence"


def test_rapid_is_dual_use_in_the_agencys_own_words_and_the_agency_keeps_its_accent():
    assert aid.regime_of("rapid-regime-dappui-linnovation-duale", "RAPID (Régime d’APpui à l’Innovation Duale)") == "dual_use"
    assert aid.regime_of("appel-projet-cyber-defense-factory", "Appel à projet pour la « Cyber Defense Factory »") == "defence"
    assert aid.ISSUER == "Agence de l'innovation de défense (AID)"


# ---------------------------------------------------------------- 2. the Cyber Defense Factory's verdict word

CDF = {"staff_nationality": {"value": "French", "note": "Only staff of French nationality may submit the application and contribute to the project.",
                             "quote": "", "confidence": 1.0, "scope": "call_document"}}
COMPANY = {"country": "UA", "applicant_kind": "company_or_research", "org_kind": "company", "headcount": "lt50", "in_group": False}


def test_the_nationality_condition_is_the_badge_word_not_nothing_known_blocks_you():
    r = verdict.call_fit({"state": "read", "facts": CDF, "programme": "NATIONAL", "topic": "appel-projet-cyber-defense-factory"}, COMPANY, None)
    assert verdict.shown_fit(r) == "check"
    assert verdict.fit_word(r) == "Only if your staff are French nationals"
    assert verdict.fit_word(r).startswith(verdict.NATIONALITY_PREFIX)


# ---------------------------------------------------------------- 3. call 39: the size line's sentence

SME_GENERAL = {"value": False, "note": "General rule of the work programme annexes; the topic or the type of action may add or change it.",
               "quote": "Any legal entity, regardless of its place of establishment, including legal entities from nonassociated third countries "
                        "or international organisations is eligible to participate (whether it is eligible for funding or not)",
               "confidence": 1.0, "scope": "general"}


def test_the_not_reserved_for_smes_line_drops_a_sentence_that_is_not_about_size():
    line = next(x for x in verdict.check({"sme_only": SME_GENERAL}, {"country": "BE", "orgType": "large", "controlledAbroad": "", "hasPartners": ""})["lines"]
                if x["key"] == "sme")
    assert line["quote"] is None
    about = {**SME_GENERAL, "quote": "Participation is not limited to SMEs."}
    line = next(x for x in verdict.check({"sme_only": about}, {"country": "BE", "orgType": "large", "controlledAbroad": "", "hasPartners": ""})["lines"]
                if x["key"] == "sme")
    assert line["quote"] == "Participation is not limited to SMEs."


CL3_CONTROL = {"value": True, "note": "Stated in this topic's own conditions. Entities established in an eligible country but directly or indirectly "
                                      "controlled by China, or by a legal entity established in China, are excluded.",
               "quote": "entities established in an eligible country but which are directly or indirectly controlled by China or by a legal entity "
                        "established in China are not eligible to participate in the action.", "confidence": 1.0, "scope": "topic"}


@pytest.mark.parametrize("controller,want", [("other_non_eu", "yes"), ("cn", "no"), ("", "check")])
def test_a_us_controlled_company_meets_a_china_only_restriction_once_it_says_who_controls_it(controller, want):
    p = {"country": "BE", "orgType": "large", "controlledAbroad": "yes", "hasPartners": "", "controller": controller}
    line = next(x for x in verdict.check({"ownership_control_restriction": CL3_CONTROL}, p)["lines"] if x["key"] == "control")
    assert line["verdict"] == want


# ---------------------------------------------------------------- 4. EIC STEP: an equity investment is not a grant

def test_an_equity_only_action_names_investments_not_grants():
    cond = {"expected_grants": 10, "min_contribution": 10_000_000, "max_contribution": 30_000_000, "deadline_model": "continuous"}
    rows = {r["label"]: r["value"] for r in funding.eligibility_rows("HORIZON", cond, {"type_of_action": "HORIZON-EIC-EQU HORIZON EIC Equity Only"})}
    assert rows == {"Expected number of investments": "10", "Investment per company": "EUR 10,000,000 to EUR 30,000,000", "Deadline model": "Continuous"}
    grant = {r["label"] for r in funding.eligibility_rows("HORIZON", cond, {"type_of_action": "HORIZON-RIA HORIZON Research and Innovation Actions"})}
    assert {"Expected number of grants", "Contribution per grant"} <= grant


# ---------------------------------------------------------------- 5. universities and research organisations

def _types(*kinds: str, scope: str = "call_document") -> dict:
    return {"entity_types": {"value": list(kinds), "quote": "q", "note": None, "confidence": 1.0, "scope": scope}}


def test_research_bodies_may_apply_where_the_call_says_legal_entities_or_names_them():
    assert who_apply.research_of(_types("Legal persons", "Natural persons who qualify as legal entities")) is True
    assert who_apply.research_of(_types("Universities", "Research and technology organisations")) is True
    assert who_apply.research_of(_types("SME company", "Small mid-cap company (up to 499 employees)", scope="topic")) is False   # 131
    assert who_apply.research_of(_types("Established SEAP")) is None                                                        # 114: public? unknown
    assert who_apply.research_of(_types("Member State procurement agencies", "Ministries of defence")) is False
    assert who_apply.research_of(_types("Legal persons", scope="general")) is None        # the work programme's general rule is not the call's
    assert who_apply.research_of({}) is None


# ---------------------------------------------------------------- 8. the Ukraine partners' order

def test_cluster_4_resilience_and_human_topics_and_eic_pathfinder_are_not_dual_use_in_the_partner_order():
    assert relevance("HORIZON", "HORIZON-CL4-2024-RESILIENCE-01") == 0        # QUEEN, BLOOM (p08: timber, geochemistry)
    assert relevance("HORIZON", "HORIZON-CL4-2023-HUMAN-01") == 0
    assert relevance("HORIZON", "HORIZON-EIC-2021-PATHFINDEROPEN-01") == 0
    assert relevance("HORIZON", "HORIZON-CL4-2022-SPACE-01-11") == 1
    assert relevance("HORIZON", "HORIZON-CL4-2021-DIGITAL-EMERGING-01-07") == 1
    assert relevance("HORIZON", "HORIZON-EIC-2023-ACCELERATOR-01") == 1
    assert relevance("HORIZON", "HORIZON-CL3-2022-BM-01") == 1
