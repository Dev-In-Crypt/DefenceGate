"""WP-93: the funding eligibility answers after the production check of 23 October 2026 (43 of 60 pairs correct, almost every error a
false "can"). The 60 verified pairs are the regression set (web/lib/data/wp93-pairs.json); the browser (web/lib/wp93.check.ts) and
this module check the same file, so the two implementations of the verdict give one answer."""

from __future__ import annotations

import json

import pytest

from dgate import eligibility, verdict
from dgate.readiness import api, seed
from dgate.rule_readings import designated, eic, read_aid_page, read_document, topic_section
from tests import wp93_golden as golden

DATA = golden.load()


# ---------------------------------------------------------------- the regression set

def test_the_set_holds_the_60_checkable_pairs_and_leaves_out_the_uncheckable_one():
    assert len(DATA["pairs"]) == 60
    assert [p["n"] for p in DATA["pairs"]].count(7) == 0          # A row 7 (RAPID for a Spanish company): uncheckable
    assert {p["document"] for p in DATA["pairs"]} == {"can", "can_if", "cannot"}


def test_the_derived_facts_are_what_the_code_serves_now():
    assert golden.after_facts(DATA) == DATA["after"]


def test_the_programme_verdicts_are_what_the_engine_gives_now():
    content = seed.load_file()
    for key, req in DATA["requests"].items():
        body = api.AssessIn(**req)
        payload = api.assess_payload(content, body.profile.to_engine(), body.statuses)
        assert [a["programme"] for a in payload["assessments"]] == [a["programme"] for a in DATA["assessments"][key]["assessments"]], key
        assert [a["verdict"] for a in payload["assessments"]] == [a["verdict"] for a in DATA["assessments"][key]["assessments"]], key


def test_the_api_verdict_of_every_call_and_profile_is_the_expected_one_the_browser_checks_too():
    for key in DATA["requests"]:
        for cid in DATA["after"]:
            assert golden.expected(DATA, key, cid) == DATA["expected"][f"{key}|{cid}"], (key, cid)


def score(after: bool = True) -> list[str]:
    wrong = []
    for p in DATA["pairs"]:
        got = DATA["expected"][f"{p['profile']}|{p['call']}"]
        words = " ".join([*(f"{x['reason']}" for x in got["lines"]), *got["conditions"]])
        shown = got["shown"]
        ok = ((p["document"] == "cannot" and shown == "no") or (p["document"] == "can_if" and shown == "check")
              or (p["document"] == "can" and shown in ("yes", "check"))) and (not p["mention"] or p["mention"] in words
                                                                             or p["mention"] in got["word"])
        if not ok:
            wrong.append(f"{p['n']} {p['profile']}/{p['call']} {p['document']}: {got['word']}")
    return wrong


def test_every_verified_pair_is_correct():
    assert score() == []


# ---------------------------------------------------------------- the readings (excerpts of the documents, verbatim)

EIC_ACCELERATOR = """
    To be an eligible applicant to EIC Accelerator, you must apply as one of the following
    eligible entities:

         a single company classified as a SME, and established within a Member State or
             an Associated Country (see Annex 2); or

         a single company classified as a small mid-cap (up to 499 employees)
             established in a Member State or an Associated Country, but only for
             "investment component only" support or for "blended finance" in exceptional
             cases for rapid scale up purposes; or
"""
EIC_STEP = """
              The pre-commitment represents at least 20% of the total target funding
                 round you are aiming to raise. Moreover, the portion of the pre-commitment
"""
DEP11 = """
2. Objectives -- Scope -- Outcomes and deliverables -- KPIs to measure
DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME - Strengthening
cybersecurity capacities of European SMEs
Targeted stakeholders
SMEs, start-ups, research and academia public sector, NIS 2 Directive entities, Other
industry actors and related stakeholders (including providers of AI-assisted
functionalities)
DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC - Enhancing the NCC Network
This topic targets exclusively National Coordination Centres which have been
recognised by the Commission as having the capacity to manage funds.

Targeted stakeholders

This call targets National Coordination Centres which have been recognized by the
Commission as having the capacity to manage funds and other private and public entities in
consortium with NCCs, including academia and research entities.
3. Available budget
"""
DEP12 = """
     DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NCH -- National Cyber Hubs ................................... 7
DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NCH -- National Cyber Hubs
Expected Outcomes
World-class National Cyber Hubs across the Union.
DIGITAL-ECCC-2027-DEPLOY-CYBER-12- CBCH -- Cross-Border Cyber Hubs
Targeted stakeholders
The target stakeholders under a) and b) above are Public bodies acting as National
Cyber Hubs, as identified by Member States, linked to a "call for expression of interest".
3. Available budget
DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NCH --           EUR 2.000.000
6. Eligibility
For the topic DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NCH -- National Cyber Hubs:
only entities designated at Member State level as National Cyber Hubs are allowed to
apply for funding and the project should be mono-beneficiary.
"""


def test_the_eic_accelerator_is_reserved_for_smes_with_the_small_mid_cap_route_in_the_note():
    got = eic(EIC_ACCELERATOR, "HORIZON-EIC-2026-ACCELERATOR-01")["sme_only"]
    assert got["value"] is True and got["verified"] and got["origin"] == "rule_reading"
    assert got["quote"].startswith("a single company classified as a SME")
    assert "investment component only" in got["note"]
    assert eligibility._norm(got["quote"]) in eligibility._norm(EIC_ACCELERATOR)          # the quote is the document's
    assert eic(EIC_ACCELERATOR, "HORIZON-EIC-2026-PATHFINDEROPEN-01") == {}


def test_both_step_calls_need_the_investor_pre_commitment_and_the_accelerator_does_not():
    for topic in ("HORIZON-EIC-2026-STEP", "HORIZON-EIC-2026-DEFENCE-01"):
        assert eic(EIC_STEP, topic)["investor_precommitment"]["value"] is True
    assert "investor_precommitment" not in eic(EIC_STEP, "HORIZON-EIC-2026-ACCELERATOR-01")
    assert eic(EIC_STEP, "DIGITAL-ECCC-2027-STEP-X") == {}


def test_designated_applicants_are_read_per_topic_with_the_consortium_route_where_there_is_one():
    ncc = designated(DEP11, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC")["designated_applicants"]
    assert ncc["value"] == "National Coordination Centres"
    assert "in consortium with NCCs" in ncc["note"]
    assert designated(DEP11, "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-AI4SME") == {}, "an open list of target groups is no rule on applicants"
    cbch = designated(DEP12, "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-CBCH")["designated_applicants"]
    assert cbch["value"] == "Public bodies acting as National Cyber Hubs" and cbch["note"] is None
    nch = designated(DEP12, "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH")["designated_applicants"]  # the document writes NCH
    assert nch["value"] == "National Cyber Hubs" and nch["quote"].startswith("only entities designated")
    assert "Cross-Border" not in topic_section(DEP12, "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH")
    assert "EUR" not in topic_section(DEP12, "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-CBCH")
    assert read_document(DEP12, None) == {} and read_document("", "DIGITAL-X-Y-Z") == {}


# The production report of 23 October 2026 gave `designated_applicants` to every topic of the ECCC documents: a heading or a "For the
# topic" sentence with the call's own code (a prefix of every topic's), or another year's code, was taken for each topic. Two topics,
# one designated and one open, with those traps and no blank lines (as pypdf may give the text).
MULTI = """Call: DIGITAL-ECCC-2027-DEPLOY-CYBER-13 -- Cybersecurity capacities
DIGITAL-ECCC-2027-DEPLOY-CYBER-13 -- Cybersecurity capacities and operational preparedness
This call targets exclusively National Coordination Centres which have been recognised by the Commission.
DIGITAL-ECCC-2027-DEPLOY-CYBER-13-OPEN - Open tools for companies
Targeted stakeholders
Technology providers, SMEs, start-ups, research and academia, public sector.
DIGITAL-ECCC-2027-DEPLOY-CYBER-13-NCH - National Cyber Hubs
Targeted stakeholders
The targeted stakeholders under a) above are public bodies acting as National Cyber Hubs, as identified by Member States.
3. Available budget
6. Eligibility
For the topic DIGITAL-ECCC-2027-DEPLOY-CYBER-13: only entities designated at Member State level as National Cyber Hubs are allowed to apply.
For the topic DIGITAL-ECCC-2026-DEPLOY-CYBER-09-OPEN: only entities designated at Member State level as National Cyber Hubs are allowed to apply.
"""


def test_a_designated_phrase_is_read_from_the_topics_own_section_only():
    hub = designated(MULTI, "DIGITAL-ECCC-2027-DEPLOY-CYBER-13-NATCH")["designated_applicants"]
    assert hub["value"] == "public bodies acting as National Cyber Hubs"
    assert designated(MULTI, "DIGITAL-ECCC-2027-DEPLOY-CYBER-13-OPEN") == {}, "an open topic of the same document"
    assert topic_section(MULTI, "DIGITAL-ECCC-2027-DEPLOY-CYBER-13-OPEN").strip().endswith("public sector.")
    # the real documents too: the open topics of DEP-11 read nothing
    for topic in ("AI4SME", "DUALUSE"):
        assert designated(DEP11, f"DIGITAL-ECCC-2027-DEPLOY-CYBER-11-{topic}") == {}


def test_the_aid_pages_give_the_group_staff_limit_and_the_staff_nationality():
    rapid = read_aid_page("Il s'adresse aux PME et ETI dont l'effectif consolidé de moins de 2000 salariés est établi en France.")
    assert rapid["max_group_headcount"]["value"] == 1999
    cdf = read_aid_page("Tout organisme de recherche, start-up, PME ou ETI. Seuls des personnels de nationalité française peuvent "
                        "déposer un dossier et contribuer au projet - Le déposant peut porter le projet seul")
    assert cdf["staff_nationality"]["value"] == "French"
    assert cdf["staff_nationality"]["quote"].endswith("contribuer au projet")
    assert read_aid_page("Aucune condition.") == {} and read_aid_page(None) == {}


def test_an_aid_page_rule_is_served_without_its_words():
    got = eligibility.page_rules({"rules_read": read_aid_page("effectif consolidé de moins de 2000 salariés"), "rules_read_at": "2026-10-01T00:00:00+00:00"})
    assert got["state"] == "read" and got["facts"]["max_group_headcount"] == {
        "value": 1999, "note": "The consolidated staff count, counted with the group, must be under 2000.", "quote": "", "confidence": 1.0, "scope": "call_document"}
    assert eligibility.page_rules({}) is None and eligibility.page_rules(None) is None


# ---------------------------------------------------------------- the serving fixes

def fact(value, quote="q", note=None, scope="topic"):
    return {"value": value, "quote": quote, "note": note, "confidence": 1.0, "scope": scope}


def test_border_guard_authorities_are_required_partners_not_who_may_apply():
    q = ("This topic requires the active involvement, as beneficiaries, of at least 2 Border or Coast Guard Authorities from at least 2 "
         "different EU Member States or Associated countries.")
    got = eligibility.required_partners({"entity_types": fact(["Border or Coast Guard Authorities"], q)})
    assert "entity_types" not in got
    assert got["required_partners"]["value"].startswith("at least 2 Border or Coast Guard Authorities from at least 2 different")
    practitioners = eligibility.required_partners({"entity_types": fact(["law enforcement"], "x", "These are required practitioner portfolios.")})
    assert practitioners["required_partners"]["value"] == "practitioners as beneficiaries, of these kinds: law enforcement"
    plain = {"entity_types": fact(["Legal entities"], "Any legal entity may apply.")}
    assert eligibility.required_partners(plain) == plain
    general = {"entity_types": fact(["Border authorities"], q, scope="general")}
    assert eligibility.required_partners(general) == general


def test_the_eic_work_programme_read_for_the_topic_is_the_schemes_own_text():
    url = "https://eic.ec.europa.eu/system/files/EIC-Work-Programme-2026.pdf"
    src = eligibility.Source("general", eligibility.document_key(url, "HORIZON-EIC-2026-ACCELERATOR-01"), "EIC work programme",
                             document=url, topic="HORIZON-EIC-2026-ACCELERATOR-01")
    row = {"extracted_at": "2026-10-20", "fields": {
        "sme_only": {**eic(EIC_ACCELERATOR, "HORIZON-EIC-2026-ACCELERATOR-01")["sme_only"]},
        "eligible_countries": {"value": "EU Member States", "quote": "q", "confidence": 1.0, "verified": True,
                               "note": eligibility.SCOPE_NOTES["general"]}}}
    got = eligibility.assemble([src], {src.key: row}, "HORIZON-EIC-2026-ACCELERATOR-01")
    assert got["facts"]["sme_only"]["scope"] == "programme" and got["facts"]["sme_only"]["value"] is True
    assert got["facts"]["eligible_countries"]["scope"] == "programme" and got["facts"]["eligible_countries"]["note"] is None
    # a row read for the whole document (before rows were kept per topic) stays a general rule
    old = eligibility.assemble([src], {url: row}, "HORIZON-EIC-2026-ACCELERATOR-01")
    assert old["facts"]["sme_only"]["scope"] == "general"


def test_the_badge_reads_the_programme_scope_as_the_calls_own():
    from dgate import who_apply

    assert who_apply.decide({"sme_only": fact(True, scope="programme")})[:2] == ("companies", True)


# ---------------------------------------------------------------- the verdict, piece by piece (the same cases as lib/wp93.check.ts)

def answers(**over):
    return {"country": "PL", "legal_form": "legal_person", "applicant_kind": "company_or_research", "third_country_control": "no",
            "executive_management_country": "PL", "org_kind": "company", "headcount": "lt50", "in_group": False, **over}


ECCC = {"eligible_countries": fact("EU Member States (including OCTs); EEA countries (Norway, Iceland, Liechtenstein)", scope="call_document"),
        "ownership_control_restriction": fact(True, "must not be directly or indirectly controlled from a country that is not an eligible country", scope="call_document")}


@pytest.mark.parametrize("country, want", [("PL", "yes"), ("NO", "yes"), ("UA", "no"), ("US", "no"), ("XX", "no")])
def test_a_closed_list_of_countries_excludes_a_country_outside_it(country, want):
    assert verdict.country_status(ECCC["eligible_countries"], country)[0] == want


def test_a_list_of_member_states_alone_or_a_general_rule_is_never_closed():
    assert verdict.country_status(fact("Legal entities established in EU Member States"), "UA")[0] == "check"
    assert verdict.country_status(fact("EU Member States; EEA countries (Norway)", scope="general"), "UA")[0] == "check"


@pytest.mark.parametrize("country, ctx, want", [
    ("NO", {"programme": "HORIZON", "topic": "HORIZON-CL3-2026-01-BM-01"}, "yes"),
    ("UA", {"programme": "HORIZON", "topic": "HORIZON-CL3-2026-01-BM-01"}, "yes"),
    ("UA", {"programme": "EDF", "topic": "EDF-EDIP-P-2027-LS-IRA-PE"}, "no"),
    ("NO", {"programme": "EDF", "topic": "EDF-EDIP-P-2027-LS-IRA-PE"}, "yes"),
    # WP-102: associated to the entire programme from 2025 (the Commission's list of participating countries, V4.2); was "check" before
    ("CH", {"programme": "HORIZON", "topic": "HORIZON-CL3-2026-01-BM-01"}, "yes"),
    ("LI", {"programme": "HORIZON", "topic": "HORIZON-CL3-2026-01-BM-01"}, "no"),
    ("GB", {"programme": "HORIZON", "topic": "HORIZON-CL3-2026-01-BM-01"}, "check"),     # associated to parts of the programme only
    ("NO", None, "check"),
])
def test_associated_countries_are_read_per_programme(country, ctx, want):
    assert verdict.country_status(fact("EU Member States or Associated countries"), country, ctx)[0] == want


@pytest.mark.parametrize("controller, want", [("cn", "no"), ("other_non_eu", "yes"), ("ru_by", "yes"), ("", "check")])
def test_a_china_only_control_clause_blocks_china_controlled_companies_only(controller, want):
    facts = {"ownership_control_restriction": fact(True, "entities established in an eligible country but which are directly or indirectly "
                                                         "controlled by China or by a legal entity established in China are not eligible")}
    got = verdict.check(facts, verdict.check_profile(answers(third_country_control="other", control_country=controller)))
    assert got["lines"][0]["verdict"] == want


def test_china_controlled_entities_that_cannot_submit_guarantees_are_out_and_others_keep_the_guarantee_route():
    facts = {"ownership_control_restriction": fact(True, "controlled by a non-eligible country may not participate",
                                                   "Participation may be allowed if guarantees are positively assessed. Entities controlled by China cannot submit guarantees.")}
    assert verdict.check(facts, verdict.check_profile(answers(third_country_control="other", control_country="cn")))["verdict"] == "no"
    assert verdict.check(facts, verdict.check_profile(answers(third_country_control="other", control_country="other_non_eu")))["verdict"] == "check"


def test_control_from_an_eligible_country_meets_the_restriction():
    p = verdict.check_profile(answers(country="NO", third_country_control="ua_eea_only", control_country="eea"))
    assert verdict.check(ECCC, p)["lines"][-1]["verdict"] == "yes"
    p = verdict.check_profile(answers(country="NO", third_country_control="ua_eea_only"))
    assert verdict.check(ECCC, p)["lines"][-1]["verdict"] == "check", "which country controls it is not said"


@pytest.mark.parametrize("over, want", [
    ({"headcount": "lt50", "in_group": False}, "yes"),
    ({"headcount": "lt50", "in_group": None}, "check"),                       # the group is not answered: never "yes"
    ({"headcount": "lt50", "in_group": True, "group_headcount": "2000plus"}, "no"),
    ({"headcount": "250_499", "in_group": False}, "check"),                    # a small mid-cap: investment component only
    ({"headcount": "2000plus", "in_group": False}, "no"),
    ({"org_kind": "university", "headcount": "500_1999"}, "no"),
    ({"org_kind": "research"}, "check"),
    ({"headcount": None}, "check"),
])
def test_the_accelerator_is_for_smes_counted_with_their_group(over, want):
    facts = {"sme_only": fact(True, note="A small mid-cap (up to 499 employees) may apply only for investment component only support.", scope="programme")}
    line = verdict.check(facts, verdict.check_profile(answers(**over)))["lines"][0]
    assert line["verdict"] == ("check" if want == "yes" else want)     # the small mid-cap note is a condition for an SME too
    if want == "yes":
        assert "under 250" in line["reason"]


def test_the_step_pre_commitment_is_asked_and_its_answer_decides():
    facts = {"investor_precommitment": fact(True)}
    assert [verdict.check(facts, verdict.check_profile(answers(investor_precommitment=v)))["verdict"] for v in (True, False, None)] == ["yes", "no", "check"]


def test_a_designated_body_call_is_a_no_for_a_company_and_a_check_with_a_consortium_route():
    p = verdict.check_profile(answers())
    assert verdict.check({"designated_applicants": fact("National Cyber Hubs")}, p)["verdict"] == "no"
    assert verdict.check({"designated_applicants": fact("National Coordination Centres", note="Others may take part in a consortium with them: x")}, p)["verdict"] == "check"
    assert verdict.check({"designated_applicants": fact("National Cyber Hubs")}, verdict.check_profile(answers(applicant_kind="contracting_authority")))["verdict"] == "check"


def test_a_call_whose_rules_were_not_read_is_unknown_never_possible():
    r = verdict.call_fit({"state": "no_source", "facts": {}, "programme": "NATIONAL", "topic": ""}, answers(), None)
    assert (r["fit"], verdict.fit_word(r)) == ("unknown", "Rules not read")


# ---------------------------------------------------------------- the request

def test_the_new_answers_are_taken_by_the_api_and_none_reaches_the_engine():
    body = api.AssessIn(profile=answers(control_country="cn", third_country_control="other", investor_precommitment=True,
                                        seap_partner=False, group_headcount="2000plus", in_group=True))
    eng = body.profile.to_engine()
    assert not any(hasattr(eng, f) for f in api.VERDICT_ONLY)
    with pytest.raises(ValueError):
        api.AssessIn(profile=answers(control_country="mars"))


def test_the_fixture_file_is_valid_json_with_the_requests_the_browser_sends():
    assert set(DATA["requests"]) == set(DATA["profiles"])
    json.dumps(DATA)
