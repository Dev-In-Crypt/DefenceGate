"""WP-102: the eligibility verdicts after the second check of 24 October 2026 (60 new pairs, 49 of 58 checkable correct before). The pairs
are the second regression set (web/lib/data/wp102-pairs.json, built by tests/wp102_golden.py); the browser (web/lib/wp102.check.ts) and
this module check the same file. Every rule read here is a sentence of the official text, quoted verbatim below."""

from __future__ import annotations

import pytest

from dgate import eligibility, verdict
from dgate.readiness import api, seed
from dgate.rule_readings import designated, eic, general_annexes, read_conditions
from tests import wp102_golden as golden

DATA = golden.load()


# ---------------------------------------------------------------- the second regression set

def test_the_set_holds_60_pairs_58_of_them_checkable_and_none_of_the_wp93_calls_profiles():
    assert len(DATA["pairs"]) == 60
    assert sum(1 for p in DATA["pairs"] if p["document"] == "uncheckable") == 2
    assert {p["document"] for p in DATA["pairs"]} == {"can", "can_if", "cannot", "uncheckable", "not_held"}


def test_every_checkable_pair_is_correct_now_and_the_score_before_is_recorded():
    ok, n, wrong = golden.score(DATA, DATA["expected"])
    assert (ok, n, wrong) == (58, 58, [])
    assert (DATA["before"]["correct"], DATA["before"]["checkable"]) == (49, 58)


def test_the_derived_facts_and_verdicts_are_what_the_code_gives_now():
    assert golden.after_facts(DATA) == DATA["after"]
    content = seed.load_file()
    for key, req in DATA["requests"].items():
        body = api.AssessIn(**req)
        payload = api.assess_payload(content, body.profile.to_engine(), body.statuses)
        assert [a["verdict"] for a in payload["assessments"]] == [a["verdict"] for a in DATA["assessments"][key]["assessments"]], key
    for key in DATA["requests"]:
        for cid in DATA["after"]:
            assert golden.expected(DATA, key, cid) == DATA["expected"][f"{key}|{cid}"], (key, cid)


def test_every_reading_of_the_set_carries_its_sentence():
    for cid, read in DATA["readings"].items():
        for name, f in read.items():
            assert len(f["quote"]) > 20 and f["from"], (cid, name)


# ---------------------------------------------------------------- the readings (excerpts of the stored texts, verbatim)

FCT05 = ("The following additional eligibility criteria apply: This topic requires the active involvement, as beneficiaries, of at least 3 "
         "Police Authorities[[In the context of this Destination, ‘Police Authorities’ means public authorities explicitly designated by national "
         "law, or other entities legally mandated by the competent national authority, for the prevention, detection and/or investigation of "
         "terrorist offences or other criminal offences, specifically excluding police academies, forensic institutes, training facilities as "
         "well as border and customs authorities.]] and at least 2 Civil Society Organisations (or Non-Governmental Organisations) from at least "
         "3 different EU Member States or Associated Countries. For these participants, applicants must")
SSRI01 = ("Participation of non-SME industries and Research and Technology Organisations (RTOs) is not excluded, but it must be limited to 15% "
          "of the proposed budget. At least 50% of the proposed budget must be allocated to SMEs.")
CSECCC = ("participation in this topic is limited to legal entities established in Member States and Associated Countries. In order to guarantee "
          "the protection of the strategic interests of the Union and its Member States, entities established in an eligible country listed "
          "above, but which are directly or indirectly controlled by a non-eligible country or by a non-eligible country entity, shall not "
          "participate in the action. described in Annex B of the Work Programme General Annexes.")
EUROHPC = ("participation is limited to legal entities established in Member States or Participating States of the EuroHPC JU [ At the moment "
           "of the adoption of the Amendment No 5, the Participating States of EuroHPC JU are Albania, Austria, Belgium, Bulgaria, Croatia, "
           "Cyprus, Czechia, Denmark, Estonia, Finland, France, Germany, Greece, Hungary, Iceland, Ireland, Israel, Italy, Latvia, Lithuania, "
           "Luxembourg, Malta, Moldova, Montenegro, Netherlands, North Macedonia, Norway, Poland, Portugal, Romania, Serbia, Slovakia, Slovenia, "
           "Spain, Sweden, Switzerland, Türkiye and United Kingdom ( Discover EuroHPC JU - The European High Performance Computing Joint "
           "Undertaking (EuroHPC JU) ) ]. In addition, legal entities which are established in associated countries to Horizon Europe that "
           "become a participant state to EuroHPC JU before the signature of the grant agreement will also become eligible. For the duly "
           "justified and exceptional reasons listed in the paragraph above, in order to guarantee the protection of the strategic interests "
           "of the Union and its Member States, entities established in an eligible country listed above, but which are directly or indirectly "
           "controlled by a non-eligible country or by a non-eligible country entity, may not participate in the action unless it can be "
           "demonstrated, by means of guarantees approved by the eligible country of establishment, that their participation to the action "
           "would not negatively impact the Union’s strategic, assets, interests, autonomy, or security.")
RAISE = ("The following additional eligibility criteria apply: The proposals submitted under the RAISE Doctoral Networks must fulfil all the "
         "admissibility and eligibility conditions of the MSCA Doctoral Networks call 2026 and pass all the thresholds for that call.")
PATHFINDER = ("The legal entities may for example be universities, research organisations, SMEs, startups, natural persons. In the case of single "
              "beneficiary projects, mid-caps and larger companies will not be permitted. Applications with elements")
COORDPREP = ("DIGITAL-ECCC-2027-DEPLOY-CYBER-11-COORDPREP – Coordinated \npreparedness testing and other preparedness actions \nThis action "
             "supports.\nTargeted stakeholders \nFor coordinated preparedness [Part 1] testing: \nThe action is targeted at public bodies that have "
             "been designated or entrusted by the \nrelevant Member State with responsibilities in the area of cybersecurity, in cluding \n"
             "cybersecurity competent authorities and CSIRTs designated under NIS2 Directive . \nOther relevant public or private partners may also "
             "participate in the consortium to \nsupport the implementation of the preparedness activities. \n3. Available budget\n")
ANNEX_H = ("by entities with a mandate from one or more of these procurers to act on their behalf in the procurement (e.g. central purchasing "
           "bodies). Other entities (e.g. end -users) that do not have a conflict of interest with the PCP/PPI, and whose participation in the "
           "action is well justified, may participate in ‘additional activities’ to pre pare, manage and follow -up the PCP/PPI and embed it into "
           "a wider set of demand -side activities. This includes")


def test_the_police_and_civil_society_beneficiaries_of_fct05_are_read_without_the_footnote():
    got = read_conditions(FCT05, "HORIZON-CL3-2026-01-FCT-05")["required_partners"]
    assert got["value"] == ("at least 3 Police Authorities and at least 2 Civil Society Organisations (or Non-Governmental Organisations) from at "
                            "least 3 different EU Member States or Associated Countries, as beneficiaries")
    assert "[[" not in got["quote"] and got["origin"] == "rule_reading"
    assert read_conditions(FCT05, "DIGITAL-ECCC-2027-X-Y") == {}, "a Horizon Europe topic's text only"


def test_the_budget_cap_of_non_sme_industries_is_read():
    got = read_conditions(SSRI01, "HORIZON-CL3-2027-01-SSRI-01")["non_sme_budget_cap"]
    assert got["value"] == 15 and got["quote"].startswith("Participation of non-SME industries")


def test_an_article_22_5_clause_without_guarantees_is_read_as_no_way_round_and_blocks_a_us_controlled_company():
    own = read_conditions(CSECCC, "HORIZON-CL3-2027-02-CS-ECCC-02")["ownership_control_restriction"]
    assert own["value"] is True and "no way round" in own["note"]
    us = verdict.check_profile({"country": "DE", "legal_form": "legal_person", "applicant_kind": "company_or_research", "org_kind": "company",
                                "headcount": "500_1999", "in_group": True, "group_headcount": "2000plus", "third_country_control": "other",
                                "control_country": "other_non_eu"})
    fact = {"value": True, "note": "Stated in this topic's own conditions.", "scope": "topic",
            "quote": "In order to guarantee the protection of the strategic interests of the Union and its Member States, entities established in an "
                     "eligible country listed above, but which are directly or indirectly controlled by a non-eligible country"}
    assert verdict.check({"ownership_control_restriction": fact}, us)["verdict"] == "no", "the verb 'to guarantee' is no route of guarantees"


def test_the_eurohpc_topic_reads_its_own_countries_and_its_guarantee_route():
    got = read_conditions(EUROHPC, "HORIZON-JU-EUROHPC-2026-NQKD-12-01")
    assert "approved by the eligible country" in got["ownership_control_restriction"]["note"]
    countries = got["eligible_countries"]
    assert countries["value"].startswith("Member States or Participating States of the EuroHPC JU: Albania, Austria")
    assert "participant state to EuroHPC JU" in countries["note"]
    ctx = {"programme": "HORIZON", "topic": "HORIZON-JU-EUROHPC-2026-NQKD-12-01"}
    assert verdict.country_status(countries, "IL", ctx)[0] == "yes"
    assert verdict.country_status(countries, "UA", ctx)[0] == "no", "not a Participating State today"


def test_raise_points_to_the_msca_doctoral_network_rule_and_the_rule_is_kept_with_its_source():
    got = read_conditions(RAISE, "HORIZON-RAISE-2026-01-03")
    assert got["consortium_required"]["value"] is True and got["min_entities"]["value"] == 3 and got["min_countries"]["value"] == 3
    assert got["consortium_required"]["quote"].startswith("The following additional eligibility criteria apply: The proposals submitted")
    assert "at least three independent legal entities" in got["consortium_required"]["note"] and "1.3.1" in got["consortium_required"]["note"]


def test_the_pathfinder_single_beneficiary_rule_is_read_for_every_challenge_topic():
    for topic in ("HORIZON-EIC-PATHFINDERCHALLENGES-01-01", "HORIZON-EIC-PATHFINDERCHALLENGES-01-02"):
        got = eic(PATHFINDER, topic)["single_beneficiary_excludes"]
        assert got["value"] == "mid-caps and larger companies" and got["quote"].endswith("will not be permitted.")
    assert "single_beneficiary_excludes" not in eic(PATHFINDER, "HORIZON-EIC-2026-ACCELERATOR-01")


def test_coordprep_is_for_designated_public_bodies_with_others_as_partners():
    got = designated(COORDPREP, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-COORDPREP")["designated_applicants"]
    assert got["value"].startswith("public bodies that have been designated or entrusted by the relevant Member State")
    assert "Other relevant public or private partners may also participate" in got["note"]


def test_annex_h_is_read_from_the_general_annexes_and_served_for_pcp_and_ppi_actions_only():
    got = general_annexes(ANNEX_H)["procurement_conflict"]
    assert got["value"] is True and "conflict of interest with the PCP/PPI" in got["quote"]
    stored = {**got, "verified": True}
    assert eligibility._served_fact(stored, "general", "procurement_conflict", "HORIZON-CL3-2026-01-SSRI-03", "PPI") is not None
    assert eligibility._served_fact(stored, "general", "procurement_conflict", "HORIZON-CL3-2026-01-FCT-05", "IA") is None


def test_the_conditions_text_is_read_when_the_call_is_served():
    src = eligibility.Source("general", "https://x.test/annexes.pdf", "General annexes")
    got = eligibility.assemble([src], {}, "HORIZON-CL3-2026-01-FCT-05", "IA", FCT05)
    assert got["state"] == "read" and got["facts"]["required_partners"]["scope"] == "topic"


def test_kinds_that_must_be_beneficiaries_are_required_partners_with_the_involvement_sentence():
    facts = {"entity_types": {"value": ["Training Centres", "practitioners"], "scope": "topic", "quote": "and at least 2 practitioners involved",
                              "note": "Stated in this topic's own conditions. Both are required to be involved as beneficiaries."},
             "consortium_required": {"value": True, "scope": "topic", "note": None,
                                     "quote": "This topic requires the active involvement, as beneficiaries, of: at least 2 Training Centres"}}
    got = eligibility.required_partners(facts)
    assert "entity_types" not in got and got["required_partners"]["value"] == "at least 2 Training Centres, as beneficiaries"


# ---------------------------------------------------------------- the verdict, piece by piece (the same cases as lib/wp102.check.ts)

def answers(**over):
    return {"country": "PL", "legal_form": "legal_person", "applicant_kind": "company_or_research", "third_country_control": "no",
            "executive_management_country": "PL", "org_kind": "company", "headcount": "lt50", "in_group": False, **over}


def fact(value, quote="q", note=None, scope="topic"):
    return {"value": value, "quote": quote, "note": note, "confidence": 1.0, "scope": scope}


SME_ONLY = {"sme_only": fact(True, note="A small mid-cap (up to 499 employees) may apply only for investment component only support.", scope="programme"),
            "eligible_countries": fact("EU Member States and countries associated to Horizon Europe", scope="programme")}


def test_a_research_organisation_of_300_staff_is_blocked_on_an_sme_only_call_and_a_small_one_is_a_check():
    big = verdict.call_fit({"state": "read", "facts": SME_ONLY, "programme": "HORIZON", "topic": "HORIZON-EIC-2026-ACCELERATOR-01"},
                           answers(org_kind="research", headcount="250_499"), None)
    assert verdict.fit_word(big) == "Blocked by: Organisation size"
    small = verdict.check(SME_ONLY, verdict.check_profile(answers(org_kind="research")))
    assert [x["verdict"] for x in small["lines"] if x["key"] == "sme"] == ["check"]


def test_the_form_without_a_staff_count_never_says_not_reserved_for_smes_on_a_call_for_smes_and_small_mid_caps():
    kinds = {"entity_types": fact(["SME company", "Small mid-cap company (up to 499 employees)"]), "sme_only": fact(False)}
    form = {"country": "BE", "orgType": "sme", "hasPartners": "", "controlledAbroad": "no"}
    line = next(x for x in verdict.check(kinds, form)["lines"] if x["key"] == "sme")
    assert line["verdict"] == "yes" and "not reserved" not in line["reason"]
    uni = next(x for x in verdict.check(kinds, {**form, "orgType": "university"})["lines"] if x["key"] == "sme")
    assert uni["verdict"] == "no"


@pytest.mark.parametrize("country, want", [("CH", "yes"), ("TR", "yes"), ("LI", "no"), ("GB", "check"), ("US", "check")])
def test_horizon_association_follows_the_commissions_list(country, want):
    ctx = {"programme": "HORIZON", "topic": "HORIZON-CL3-2027-02-CS-ECCC-01"}
    assert verdict.country_status(fact("Member States and Associated Countries"), country, ctx)[0] == want
    assert verdict.ASSOCIATION_SOURCES["HORIZON"]["no"] == "Liechtenstein does not intend to associate to Horizon Europe."


def test_control_from_an_eea_efta_state_is_a_check_where_only_some_of_them_are_eligible():
    facts = {"eligible_countries": fact("Member States and Associated Countries"),
             "ownership_control_restriction": fact(True, "controlled by a non-eligible country or by a non-eligible country entity, shall not participate")}
    p = verdict.check_profile(answers(country="NO", third_country_control="ua_eea_only", control_country="eea"))
    line = verdict.check(facts, p, {"programme": "HORIZON", "topic": "HORIZON-CL3-2027-02-CS-ECCC-01"})["lines"][-1]
    assert line["key"] == "control" and line["verdict"] == "check"


def test_non_sme_industries_cover_a_large_company_with_the_budget_cap_as_a_condition():
    facts = {"entity_types": fact(["SMEs", "end-user organisations", "non-SME industries"]), "non_sme_budget_cap": fact(15),
             "eligible_countries": fact("EU Member States")}
    lines = verdict.check(facts, verdict.check_profile(answers(headcount="2000plus")))["lines"]
    assert next(x for x in lines if x["key"] == "entity")["verdict"] == "yes"
    assert "15 % of the proposed budget" in next(x for x in lines if x["key"] == "cap")["reason"]
    assert not any(x["key"] == "cap" for x in verdict.check(facts, verdict.check_profile(answers()))["lines"]), "an SME is not capped"


def test_a_large_company_may_not_be_a_single_beneficiary_of_a_pathfinder_challenge():
    facts = {"single_beneficiary_excludes": fact("mid-caps and larger companies", scope="programme"), "eligible_countries": fact("Member States")}
    assert [x["key"] for x in verdict.check(facts, verdict.check_profile(answers(headcount="500_1999")))["lines"] if x["verdict"] == "check"] == ["single"]
    assert verdict.check(facts, verdict.check_profile(answers()))["verdict"] == "yes"


def test_a_ppi_says_a_potential_supplier_cannot_be_a_beneficiary():
    facts = {"procurement_conflict": fact(True, scope="general"), "eligible_countries": fact("EU Member States")}
    line = next(x for x in verdict.check(facts, verdict.check_profile(answers()))["lines"] if x["key"] == "procurement")
    assert line["verdict"] == "check" and "conflict of interest" in line["reason"]
    assert not any(x["key"] == "procurement" for x in verdict.check(facts, verdict.check_profile(answers(applicant_kind="contracting_authority")))["lines"])


def test_a_call_whose_establishment_rule_was_not_read_is_never_eligible():
    rapid = {"max_group_headcount": {"value": 1999, "note": "n", "quote": "", "confidence": 1.0, "scope": "call_document"}}
    r = verdict.call_fit({"state": "read", "facts": rapid, "programme": "NATIONAL", "topic": ""}, answers(country="ES"), None)
    assert verdict.shown_fit(r) == "check" and "was not read" in r["result"]["lines"][-1]["reason"]


def test_a_designated_body_call_with_a_partner_route_says_so_on_the_badge():
    facts = {"designated_applicants": fact("National Coordination Centres", note="Others may take part in a consortium with them: x"),
             "eligible_countries": fact("EU Member States; EEA countries (Norway)")}
    r = verdict.call_fit({"state": "read", "facts": facts, "programme": "DIGITAL", "topic": "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC"}, answers(), None)
    assert verdict.fit_word(r) == verdict.PARTNER_ONLY_WORD and verdict.shown_fit(r) == "check"


def test_a_company_profile_without_the_applicant_kind_answer_is_blocked_from_common_procurement():
    got = verdict.applicant_fit("EDF", "EDF-EDIP-P-2027-FNLC-CPA-GNPS", answers(applicant_kind=None))
    assert got == {"fit": "no", "because": ["Who may apply: contracting authorities, international organisations, SEAPs and the EDA"]}
    assert verdict.applicant_fit("EDF", "EDF-EDIP-P-2027-FNLC-CPA-GNPS", answers(applicant_kind=None, org_kind=None))["fit"] == "check"
