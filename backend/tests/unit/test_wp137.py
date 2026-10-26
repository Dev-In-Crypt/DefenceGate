"""WP-137: who may apply, where the call's own conditions limit where an applicant is established or who may control it. The sentences
are the portal's own, as stored on production for the EuroHPC JU calls 138-143 and HORIZON-NATURE-2027-02-04 (154)
(D:/DEFENCEGATE TESTS/verify-oct25/ops-r10/15-extra8.jsonl)."""

from __future__ import annotations

from dgate import funding, rule_readings, verdict, who_apply
from tests.unit.test_wp132 import ANY_LEGAL, answers, fact

TOPIC = "HORIZON-JU-EUROHPC-2026-SPT-10-01"
EUROHPC = (
    "2. Eligible countries described in Annex B of the Work Programme General Annexes. The following exceptions apply: The eligibility "
    "conditions are those established in the EuroHPC JU Council Regulation (EU) 2021/1173 as last amended by Council Regulation 2026/150. In "
    "accordance with Article 22.5 of the HE Regulation, the Governing Board has decided that in order to achieve the expected outcomes, and "
    "safeguard the Union’s strategic assets, interests, autonomy, or security participation is limited to legal entities established in Member "
    "States or Participating States of the EuroHPC JU [ At the moment of the adoption of the Amendment No 5, the Participating States of "
    "EuroHPC JU are Albania, Austria, Belgium, Bulgaria, Croatia, Cyprus, Czechia, Denmark, Estonia, Finland, France, Germany, Greece, Hungary, "
    "Iceland, Ireland, Israel, Italy, Latvia, Lithuania, Luxembourg, Malta, Moldova, Montenegro, Netherlands, North Macedonia, Norway, Poland, "
    "Portugal, Romania, Serbia, Slovakia, Slovenia, Spain, Sweden, Switzerland and Türkiye. ]. In addition, legal entities which are established "
    "in associated countries to Horizon Europe that become a participant state to EuroHPC JU before the signature of the grant agreement will "
    "also become eligible. For the duly justified and exceptional reasons listed in the paragraph above, in order to guarantee the protection "
    "of the strategic interests of the Union and its Member States, entities established in an eligible country listed above, but which are "
    "directly or indirectly controlled by a non-eligible country or by a non-eligible country entity, may not participate in the action unless "
    "it can be demonstrated, by means of guarantees approved by the eligible country of establishment, that their participation to the action "
    "would not negatively impact the Union’s strategic, assets, interests, autonomy, or security. 3. Other Eligibility Conditions described in "
    "Annex B of the Work Programme General Annexes.")
CHINA = ("entities established in an eligible country but which are directly or indirectly controlled by China or by a legal entity established "
         "in China are not eligible to participate in the action.")
GENERAL = {"sme_only": fact(False, ANY_LEGAL, scope="general"),
           "entity_types": fact(["Natural persons who qualify as legal entities under applicable law", "Legal persons"], "A legal entity", scope="general")}


def eurohpc() -> dict:
    """The facts as eligibility.assemble serves them: the general annexes, then the readings of the topic's conditions (topic scope)."""
    read = {k: {**f, "scope": "topic"} for k, f in rule_readings.read_conditions(EUROHPC, TOPIC).items()}
    return {**GENERAL, **read}


def test_the_calls_own_limits_are_the_evidence_not_the_general_annexes():
    facts = eurohpc()
    assert set(facts) >= {"eligible_countries", "ownership_control_restriction"}
    who, sme, evidence = who_apply.decide(facts)
    assert (who, sme) == ("companies", None), "the kind of entity is not limited: companies may apply"
    assert evidence.startswith("participation is limited to legal entities established in Member States or Participating States of the EuroHPC JU")
    assert "regardless of its place of establishment" not in evidence
    assert [x["kind"] for x in who_apply.limits_of(facts)] == ["established", "control"]
    assert "guarantees approved by the eligible country" in who_apply.limits_of(facts)[1]["note"]


def test_a_china_control_restriction_is_a_limit_and_the_evidence():
    facts = {**GENERAL, "ownership_control_restriction": fact(True, CHINA)}
    assert who_apply.decide(facts) == ("companies", None, CHINA)
    assert who_apply.limits_of(facts) == [{"kind": "control", "quote": CHINA, "note": ""}]


def test_what_is_no_limit_of_the_call():
    # a count of some partners is not where an applicant must be established (Cluster 3, BM-01)
    border = {**GENERAL, "eligible_countries": fact("EU Member States or Associated countries", "This topic requires the active involvement, as "
                                                    "beneficiaries, of at least 2 Border or Coast Guard Authorities from at least 2 different EU Member States or "
                                                    "Associated countries.")}
    assert who_apply.limits_of(border) == []
    assert who_apply.decide(border) == ("companies", None, ANY_LEGAL), "without an own limit the annexes' sentence stays the evidence"
    # a rule of the general annexes is not the call's; a restriction stated false is none
    assert who_apply.limits_of({"ownership_control_restriction": fact(True, CHINA, scope="general")}) == []
    assert who_apply.limits_of({"ownership_control_restriction": fact(False, "No restriction applies.")}) == []
    # the call's own answer keeps its own evidence
    own = {**eurohpc(), "entity_types": fact(["legal entities"], "participation is limited to legal entities")}
    assert who_apply.decide(own) == ("companies", None, "participation is limited to legal entities")


def test_the_readiness_check_does_not_tell_a_restricted_company_nothing_blocks_it():
    facts, ctx = eurohpc(), {"programme": "HORIZON", "topic": TOPIC}
    word = lambda **p: verdict.fit_word(verdict.fit_of(facts, answers(**p), ctx))  # noqa: E731
    assert word(country="US") == "Blocked by: Country"
    controlled = word(country="ES", third_country_control="other", control_country="cn")
    assert controlled == verdict.CONTROL_WORD and "Nothing known blocks you" not in controlled
    assert word(country="ES", third_country_control="other", control_country="other_non_eu") == verdict.CONTROL_WORD
    assert word(country="ES").startswith("Nothing known blocks you"), "a company established in Spain and not controlled from elsewhere"
    china = {**GENERAL, "ownership_control_restriction": fact(True, CHINA)}
    assert verdict.fit_word(verdict.fit_of(china, answers(country="ES", third_country_control="other", control_country="cn"), ctx)).startswith("Blocked")


def test_an_edip_call_filed_under_the_edf_is_named_after_its_own_programme():
    """Round-8 data audit fund-8: the 9 EDIP / EDIP-USI calls (110-114, 116-118, 193) served programmeName "European Defence Fund"."""
    for topic, name in (("EDF-EDIP-P-2027-LS-IRA-KEC", "European Defence Industry Programme"),
                        ("EDF-EDIP-USI-2026-DA-UA", "EDIP Ukraine Support Instrument"), ("EDF-2026-DA-PROTMOB-DMM", "European Defence Fund")):
        assert funding.programme_name_of(funding.programme_of("EDF", topic), "European Defence Fund") == name, topic
    assert funding.programme_name_of("HORIZON", "Horizon Europe") == "Horizon Europe"
