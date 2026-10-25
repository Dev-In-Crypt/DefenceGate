"""WP-132 (round-7 funding audit of 25 October 2026): the funding rules that need no database. The sentences are the portal's and the
call documents' own, as stored on production (D:/DEFENCEGATE TESTS/verify-oct25/r7-funding)."""

from __future__ import annotations

from dgate import eligibility, funding, verdict, who_apply
from dgate.sources import eu_portal


def fact(value, quote="q", note=None, scope="topic"):
    return {"value": value, "quote": quote, "note": note, "confidence": 1.0, "scope": scope}


# ------------------------------------------------------------------ 3. the minimum consortium

BORDER = ("The following additional eligibility criteria apply: This topic requires the active involvement, as beneficiaries, of at least 2 "
          "Border or Coast Guard Authorities from at least 2 different EU Member States or Associated countries. For these participants, "
          "applicants must fill in the table.")
POLICE = ("This topic requires the active involvement, as beneficiaries, of at least 3 Police Authorities[[In the context of this Destination, "
          "'Police Authorities' means public authorities.]] and at least 2 Civil Society Organisations (or Non-Governmental Organisations) from "
          "at least 3 different EU Member States or Associated Countries.")
FIRST_RESPONDERS = ("This topic requires the active involvement, as beneficiaries, of at least 3 first responders or authorities in charge of "
                    "disaster risk[[Authorities in charge of disaster risk: bodies with a formal mandate. They design, coordinate, or implement "
                    "measures.]] from at least 3 different EU Member States or Associated Countries.")
PRACTITIONERS = ("This topic requires the active involvement, as beneficiaries, of at least 2 practitioner organisations (first responders) and 2 "
                 "medical emergency authorities from at least 3 different EU Member States or Associated Countries.")
PATHFINDER = ("The EIC Pathfinder Challenges support collaborative or individual research and innovation from consortia or from single legal "
              "entities established in a Member State or an Associated Country. Consortia of two entities must be comprised of independent legal "
              "entities from two different Member States or Associated Countries. Consortia of three or more entities must include as beneficiaries "
              "at least three legal entities, independent from each other. In the case of single beneficiary projects, mid-caps and larger "
              "companies will not be permitted.")
DRS_01 = ("This topic requires the active involvement, as beneficiaries, of at least 3 organisations from at least 3 different EU Member States "
          "or Associated Countries as follows: (i) at least one civil society organisation (CSO).")


def test_a_count_of_some_partners_is_not_the_consortium_rule():
    """39, 42, 43, 45, 55 said "from 2 Member States" and 44, 46, 47, 51 "2 legal entities": the counts of the practitioners the topic
    requires, and the countries clause that belongs to them."""
    for text in (BORDER, POLICE, PRACTITIONERS, FIRST_RESPONDERS):
        assert eu_portal.consortium_rule(text) == (None, None), text[:60]


def test_a_call_that_takes_a_single_applicant_has_no_minimum_consortium():
    """EIC Pathfinder 128 and 129, closing 28 October: "3 legal entities" beside "a single legal entity may apply"."""
    assert eu_portal.consortium_rule(PATHFINDER) == (None, None)
    # a sentence that refuses single applicants is no such route
    assert eu_portal.consortium_rule("Single legal entities are not eligible. The consortium must include at least 3 legal entities.") == (3, None)


def test_the_consortium_sentence_is_still_read():
    assert eu_portal.consortium_rule(DRS_01) == (3, 3)


def test_the_minimum_consortium_row_comes_from_the_facts_with_where_they_were_read():
    pathfinder = {"min_entities": fact(1, scope="programme"), "single_applicant_allowed": fact(True, scope="programme"),
                  "consortium_required": fact(False, scope="programme")}
    assert who_apply.consortium_of(pathfinder) == "None: a single legal entity may apply (the EIC work programme)"
    fct03 = {"min_entities": fact(5), "min_countries": fact(3), "single_applicant_allowed": fact(False)}
    assert who_apply.consortium_of(fct03) == "At least 5 legal entities from at least 3 countries (the topic's conditions)"
    fct05 = {"min_entities": fact(3, scope="general"), "min_countries": fact(3)}
    assert who_apply.consortium_of(fct05) == ("At least 3 legal entities from at least 3 countries "
                                              "(the work programme's general annexes; the topic's conditions)")
    assert who_apply.consortium_of({"min_entities": fact(3, scope="call_document")}) == "At least 3 legal entities (the call document)"
    assert who_apply.consortium_of({"min_countries": fact(3)}) is None
    assert who_apply.consortium_of({}) is None


def test_the_terms_row_prefers_the_facts_and_names_the_topic_text_otherwise():
    rows = funding.eligibility_rows("HORIZON", {}, {"consortium_rule": "At least 5 legal entities from at least 3 countries (the topic's conditions)",
                                                     "min_consortium_size": 2, "min_member_states": 3})
    assert [r["value"] for r in rows if r["label"] == "Minimum consortium"] == [
        "At least 5 legal entities from at least 3 countries (the topic's conditions)"]
    rows = funding.eligibility_rows("HORIZON", {}, {"min_consortium_size": 3, "min_member_states": 3})
    assert [r["value"] for r in rows if r["label"] == "Minimum consortium"] == ["3 legal entities from 3 Member States (the topic's conditions)"]


# ------------------------------------------------------------------ 4. who may apply: the general annexes

ANY_LEGAL = ("Any legal entity, regardless of its place of establishment, including legal entities from nonassociated third countries or "
             "international organisations (including international European research organisations) is eligible to participate")


def test_a_horizon_call_whose_own_facts_say_nothing_takes_the_general_annexes_any_legal_entity():
    """20 Cluster 3 calls and HORIZON-CL4 155 were missing from "Open to companies"."""
    cl3 = {"sme_only": fact(False, ANY_LEGAL, scope="general"),
           "entity_types": fact(["Natural persons who qualify as legal entities under applicable law", "Legal persons"], "A legal entity", scope="general")}
    assert who_apply.decide(cl3) == ("companies", None, ANY_LEGAL)
    only_sme_general = {"sme_only": fact(False, ANY_LEGAL, scope="general")}             # FCT-03: no entity list at all
    assert who_apply.decide(only_sme_general)[0] == "companies"
    police = {**cl3, "entity_types": fact(["Police Authorities"], "at least 2 Police Authorities")}   # a list of required partners
    assert who_apply.decide(police)[0] == "companies"


def test_the_calls_own_facts_still_come_first():
    public = {"sme_only": fact(False, ANY_LEGAL, scope="general"),
              "entity_types": fact(["Contracting authorities", "Ministries"], "Only contracting authorities may apply.", scope="call_document")}
    assert who_apply.decide(public)[0] == "public"
    designated = {"sme_only": fact(False, ANY_LEGAL, scope="general"),
                  "designated_applicants": fact("National Cyber Hubs", "Only National Cyber Hubs may apply.", scope="call_document")}
    assert who_apply.decide(designated)[0] == "designated"
    assert who_apply.decide({}) == (None, None, None)
    # a general sentence that lets no company in decides nothing
    assert who_apply.decide({"entity_types": fact(["Universities"], "Universities.", scope="general")}) == (None, None, None)


# ------------------------------------------------------------------ 6. a quote that joins two lines of a list (KEC, EUR 282 m)

KEC_TEXT = ("Eligible participants (eligible countries) \nIn order to be eligible, the applicants (beneficiaries and affiliated entities) must: \n"
            "− be legal entities (public or private bodies) \n− be established in one of the eligible countries, i.e.: \n"
            "− EU Member States (including overseas countries and territories (OCTs)) \n− non-EU countries: \n"
            "− listed EEA countries and countries associated to the EDIP Programme \n(‘EDIP associated countries’; list of participating countries) \n"
            " Please check the list regularly, to get the latest status on \ncountries in the process of association.")
KEC_QUOTE = ("In order to be eligible, the applicants (beneficiaries and affiliated entities) must: − be established in one of the eligible "
             "countries, i.e.: − EU Member States (including overseas countries and territories (OCTs)) − non-EU countries: − listed EEA "
             "countries and countries associated to the EDIP Programme (‘EDIP associated countries’; list of participating countries)")


def test_a_quote_whose_parts_are_in_the_document_in_order_is_verified():
    hay = eligibility._norm(KEC_TEXT)
    assert eligibility.quote_found(KEC_QUOTE, hay)
    answer = {name: {"value": None, "quote": None, "note": None, "confidence": 0.0} for name in eligibility.FIELDS}
    answer["eligible_countries"] = {"value": "EU Member States, EEA and EDIP associated countries", "quote": KEC_QUOTE, "note": None, "confidence": 0.9}
    assert eligibility.check_quotes(answer, KEC_TEXT)["eligible_countries"]["verified"] is True


def test_parts_out_of_order_too_far_apart_or_made_up_are_not():
    hay = eligibility._norm(KEC_TEXT)
    swapped = ("be established in one of the eligible countries, i.e.: In order to be eligible, the applicants (beneficiaries and "
               "affiliated entities) must:")
    assert not eligibility.quote_found(swapped, hay)
    far = eligibility._norm("In order to be eligible, the applicants must " + "lorem ipsum dolor sit amet " * 20 + "be established in one of the eligible countries")
    assert not eligibility.quote_found("In order to be eligible, the applicants must be established in one of the eligible countries", far)
    assert not eligibility.quote_found("In order to be eligible, the applicants must hold a security clearance of the highest level", hay)


# ------------------------------------------------------------------ 7. a university on a call for companies (RAPID)

RAPID = {"max_group_headcount": {"value": 1999, "note": "The consolidated staff count, counted with the group, must be under 2000.", "quote": "",
                                 "confidence": 1.0, "scope": "call_document"}}


def answers(**over):
    return {"country": "PL", "legal_form": "legal_person", "applicant_kind": "company_or_research", "third_country_control": "no",
            "executive_management_country": "PL", "org_kind": "company", "headcount": "lt50", "in_group": False, **over}


def test_a_university_is_blocked_from_a_call_for_companies_with_a_group_staff_cap():
    """A Polish university got "Nothing known blocks you, 2 conditions to check" on RAPID."""
    line = next(x for x in verdict.check(RAPID, verdict.check_profile(answers(org_kind="university", headcount="2000plus")))["lines"]
                if x["key"] == "group")
    assert line["verdict"] == "no" and "A university is not a company" in line["reason"]
    research = next(x for x in verdict.check(RAPID, verdict.check_profile(answers(org_kind="research")))["lines"] if x["key"] == "group")
    assert research["verdict"] == "check" and "only if it is such a company" in research["reason"]
    company = next(x for x in verdict.check(RAPID, verdict.check_profile(answers()))["lines"] if x["key"] == "group")
    assert company["verdict"] == "yes"
    form = {"country": "FR", "orgType": "university", "hasPartners": "", "controlledAbroad": "no"}       # the call page's form
    assert next(x for x in verdict.check(RAPID, form)["lines"] if x["key"] == "group")["verdict"] == "no"


# ------------------------------------------------------------------ 1. a call the source stopped listing

def test_an_unlisted_call_has_its_own_status_after_the_closed_rule():
    sql = funding.EFFECTIVE_STATUS
    assert "'unlisted'" in sql and sql.index("THEN 'closed'") < sql.index("THEN 'unlisted'")
    assert f"c.unlisted_runs >= {funding.UNLISTED_AFTER_RUNS}" in funding.UNLISTED and funding.UNLISTED_AFTER_RUNS == 2
