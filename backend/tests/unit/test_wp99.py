"""WP-99 (persona round of 23 October 2026, D: funding and eligibility): the backend half.

D:/DEFENCEGATE TESTS/ux-oct23/SUMMARY.md section D and the problems of p05-fr-cyber, p08-ua-drones and p09-be-consultant.
"""

from __future__ import annotations

from dgate import rule_readings, ukraine, verdict, who_apply
from dgate.readiness.engine import FIELDS, Profile, assess
from dgate.readiness.seed import load_file

CONTENT = load_file()

# The shapes of the call documents stored in production (call_document_text, read on 24 October 2026): the code and the title are
# separated by an en dash or an em dash, sometimes with no space before it, and a table-of-contents line may wrap before its dot leaders.
PROD11 = """CALL FOR PROPOSALS
TABLE OF CONTENTS
DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME – Strengthening cybersecurity capacities of
European SMEs ................................................................. 11
DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC – Enhancing the NCC Network ............................... 28
DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME – Strengthening cybersecurity capacities of
European SMEs
Targeted stakeholders
Technology providers, SMEs, start-ups.
DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC – Enhancing the NCC Network
Objectives
This topic targets exclusively National Coordination Centres which have been recognised by the Commission as having the capacity to
manage funds to achieve the mission.
Targeted stakeholders
This call targets National Coordination Centres which have been recognized by the Commission as having the capacity to manage funds
and other private and public entities in consortium with NCCs, including academia and research entities.
DIGITAL-ECCC-2027-DEPLOY-CYBER-11-EULEG– Strengthening EU cybersecurity capacities
Objectives
Anybody.
3. Available budget
"""
PROD12 = """TABLE OF CONTENTS
DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH — National Cyber Hubs ................................... 7
DIGITAL-ECCC-2027-DEPLOY-CYBER-12- CBCH — Cross-Border Cyber Hubs ........................ 11
DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH — National Cyber Hubs
EU Grants: Call document (DEP): V1.0 – 01.12.2026 11
Targeted stakeholders
The targeted stakeholders under a) and b) above are public bodies acting as National Cyber Hubs, as identified by Member States.
DIGITAL-ECCC-2027-DEPLOY-CYBER-12- CBCH — Cross-Border Cyber Hubs
Targeted stakeholders
The target stakeholders under a) and b) above are Public bodies acting as National Cyber Hubs, as identified by Member States, linked to a call.
3. Available budget
6. Eligibility
For the topic DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH — National Cyber Hubs:
only entities designated at Member State level as National Cyber Hubs are allowed to apply for funding and the project should be mono-beneficiary.
"""


def test_the_production_headings_with_an_en_or_em_dash_are_found():
    ncc = rule_readings.designated(PROD11, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC")["designated_applicants"]
    assert ncc["value"] == "National Coordination Centres" and "in consortium with NCCs" in ncc["note"]
    cbch = rule_readings.designated(PROD12, "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-CBCH")["designated_applicants"]
    assert cbch["value"] == "Public bodies acting as National Cyber Hubs" and cbch["note"] is None
    # "CODE– Title" with no space before the dash, and the open topics read nothing
    assert "Anybody." in rule_readings.topic_section(PROD11, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-EULEG")
    assert rule_readings.designated(PROD11, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME") == {}
    assert rule_readings.designated(PROD11, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-EULEG") == {}


def test_a_table_of_contents_line_that_wraps_is_not_the_section():
    assert "Technology providers" in rule_readings.topic_section(PROD11, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME")


def test_the_strongest_phrase_wins_and_a_page_footer_is_not_part_of_the_quote():
    natch = rule_readings.designated(PROD12, "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH")["designated_applicants"]
    assert natch["value"] == "National Cyber Hubs" and natch["quote"].startswith("only entities designated")
    # without the eligibility paragraph the section's sentence is read, from its own words (no "EU Grants ... 11 Targeted stakeholders")
    hub = rule_readings.designated(PROD12.split("6. Eligibility")[0], "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH")["designated_applicants"]
    assert hub["quote"].startswith("The targeted stakeholders") and "EU Grants" not in hub["quote"]


def fact(value, scope="call_document", note=None, quote="q"):
    return {"value": value, "scope": scope, "note": note, "quote": quote, "confidence": 1.0}


def test_a_call_only_for_designated_bodies_is_badged_designated_and_one_with_a_consortium_route_is_not():
    hubs = {"designated_applicants": fact("National Cyber Hubs"), "entity_types": fact(["Legal entities (public or private bodies)"])}
    assert who_apply.decide(hubs)[0] == "designated"
    ncc = {"designated_applicants": fact("National Coordination Centres", note="Others may take part in a consortium with them: ..."),
           "entity_types": fact(["legal entities", "private bodies"])}
    assert who_apply.decide(ncc)[0] == "companies"
    general = {"designated_applicants": fact("National Cyber Hubs", scope="general")}
    assert who_apply.decide(general) == (None, None, None)


HORIZON = {"programme_code": "HORIZON", "topic_code": "HORIZON-CL3-2026-01-BM-01", "eligibility_text": None}


def test_a_horizon_call_open_to_the_associated_countries_is_open_to_ukraine_as_the_verdict_reads_it():
    flag, reason, evidence = ukraine.decide(HORIZON, {"eligible_countries": fact("EU Member States or Associated countries", scope="topic",
                                                                                  quote="EU Member States or Associated countries")})
    assert (flag, reason) == (True, "horizon_associated") and "list Ukraine among the countries associated" in evidence
    # the verdict of a Ukrainian company on the same fact says the same
    assert verdict.country_status(fact("EU Member States or Associated countries", scope="topic"), "UA", {"programme": "HORIZON", "topic": ""})[0] == "yes"
    eic = {**HORIZON, "topic_code": "HORIZON-EIC-2026-ACCELERATOR-01"}
    assert ukraine.decide(eic, {"eligible_countries": fact("EU Member States and countries associated to Horizon Europe", scope="programme")})[0] is True
    # the general annexes alone do not decide it, and a closed list of named countries is not open
    assert ukraine.decide(HORIZON, {"eligible_countries": fact("EU Member States; countries associated to Horizon Europe", scope="general")})[0] is None
    closed = fact("Member States, Iceland, Norway, Canada, Israel, Republic of Korea, New-Zealand, United Kingdom, Switzerland and Japan", scope="topic")
    assert ukraine.decide(HORIZON, {"eligible_countries": closed})[0] is None
    assert "horizon_associated" in ukraine.REASONS


UA_ANSWERS = {"country": "UA", "legal_form": "legal_person", "executive_management_country": "UA", "third_country_control": "ua_eea_only",
              "control_country": "ua", "ua_non_government_controlled_area": True, "org_kind": "company", "headcount": "50_249", "in_group": False}


def test_horizon_and_a_company_in_a_non_government_controlled_area_is_not_checked_and_says_so():
    facts = {"eligible_countries": fact("EU Member States or Associated countries", scope="topic")}
    r = verdict.fit_of(facts, UA_ANSWERS, {"programme": "HORIZON", "topic": "HORIZON-CL3-2026-01-BM-01"})
    line = next(x for x in r["result"]["lines"] if x["key"] == "territory")
    assert line["verdict"] == "check" and "not checked here" in line["reason"] and r["fit"] == "check"
    # not for a company outside those areas, and not for another programme
    assert all(x["key"] != "territory" for x in verdict.fit_of(facts, {**UA_ANSWERS, "ua_non_government_controlled_area": False},
                                                             {"programme": "HORIZON", "topic": ""})["result"]["lines"])
    assert all(x["key"] != "territory" for x in verdict.fit_of(facts, UA_ANSWERS, {"programme": "DIGITAL", "topic": ""})["result"]["lines"])


def assessment_of(profile: Profile) -> dict:
    a = assess(profile, {"REQ-PIC": "held"}, CONTENT.programmes["EDIP-USI"])
    return {"assessments": [{"programme": a.programme, "name": a.name, "verdict": a.verdict, "blocking": list(a.blocking),
                             "rules": [{"rule": r.rule, "title": r.title, "requirement": r.requirement, "outcome": r.outcome} for r in a.rules]}],
            "roadmap": {"steps": []}}


USI_CALL = {"state": "read", "facts": {}, "programme": "EDF", "topic": "EDF-EDIP-USI-2026-LS-IRA-MAB"}
USI_FACTS = {"eligible_countries": fact("EU Member States (including OCTs) and Ukraine")}


def test_no_ukrainian_partner_reads_not_without_a_ukrainian_partner_and_never_nothing_blocks_you():
    pl = Profile(country="PL", executive_management_country="PL", third_country_control="no", ua_partner=False)
    r = verdict.call_fit({**USI_CALL, "facts": USI_FACTS}, {"country": "PL", "ua_partner": False}, assessment_of(pl))
    assert verdict.shown_fit(r) == "check" and verdict.fit_word(r) == verdict.NO_UA_PARTNER
    unanswered = Profile(country="PL", executive_management_country="PL", third_country_control="no")
    r = verdict.call_fit({**USI_CALL, "facts": USI_FACTS}, {"country": "PL"}, assessment_of(unanswered))
    assert verdict.fit_word(r) != verdict.NO_UA_PARTNER


def test_a_company_in_a_non_government_controlled_area_is_blocked_by_the_fact_not_by_a_double_negative():
    occupied = Profile(country="UA", executive_management_country="UA", third_country_control="no", ua_non_government_controlled_area=True)
    r = verdict.call_fit({**USI_CALL, "facts": USI_FACTS}, {"country": "UA"}, assessment_of(occupied))
    assert r["fit"] == "no"
    assert verdict.fit_word(r).startswith("Blocked: Your company is established in a non-government controlled area of Ukraine")
    rule = next(x for x in assess(occupied, {}, CONTENT.programmes["EDIP-USI"]).rules if x.rule == "USI-TERRITORY")
    assert rule.reason.startswith("Your company is established in a non-government controlled area of Ukraine.")


def test_a_ukrainian_controlled_ukrainian_company_with_ukrainian_components_is_eligible_under_usi():
    p = Profile(country="UA", legal_form="legal_person", executive_management_country="UA", third_country_control="ua_eea_only",
                control_country="ua", ua_non_government_controlled_area=False, non_eu_component_cost_pct=20,
                restricted_third_country_component=False, components_from_ua=True, components_from_eea_efta=False,
                applicant_kind="company_or_research")
    a = assess(p, {"REQ-PIC": "held", "REQ-NCAGE": "held", "REQ-AQAP2110": "held"}, CONTENT.programmes["EDIP-USI"])
    assert a.verdict == "eligible", [(r.rule, r.outcome) for r in a.rules if r.outcome not in ("met", "not_applicable", "info")]


def test_the_controlling_country_is_asked_only_after_the_control_answer_that_leads_to_it():
    assert FIELDS["control_country"]["asked_after"][0] == "third_country_control"
    a = assess(Profile(country="PL", executive_management_country="PL"), {}, CONTENT.programmes["EDIP-USI"])
    assert "third_country_control" in a.missing and "control_country" not in a.missing
    a = assess(Profile(country="PL", executive_management_country="PL", third_country_control="ua_eea_only"), {}, CONTENT.programmes["EDIP-USI"])
    assert "control_country" in a.missing


def test_an_older_clients_joint_component_answer_still_works():
    fields = Profile(country="PL", components_from_ua_or_eea_efta=False).fields()
    assert (fields["components_from_ua"], fields["components_from_eea_efta"]) == (False, False)
    fields = Profile(country="PL", components_from_ua=True, components_from_eea_efta=False).fields()
    assert fields["components_from_ua_or_eea_efta"] is True
    fields = Profile(country="PL", components_from_ua=False, components_from_eea_efta=False).fields()
    assert fields["components_from_ua_or_eea_efta"] is False


def test_an_eic_step_call_and_the_answer_no_investor_is_a_no():
    facts = {"investor_precommitment": fact(True, scope="programme"), "eligible_countries": fact("EU Member States and Associated Countries", scope="programme")}
    ctx = {"programme": "HORIZON", "topic": "HORIZON-EIC-2026-DEFENCE-01"}
    fr = {"country": "FR", "org_kind": "company", "headcount": "lt50", "in_group": False}
    assert verdict.fit_of(facts, {**fr, "investor_precommitment": False}, ctx)["fit"] == "no"
    assert verdict.fit_of(facts, {**fr, "investor_precommitment": True}, ctx)["fit"] in ("yes", "check")
    assert verdict.fit_of(facts, fr, ctx)["fit"] == "check"
