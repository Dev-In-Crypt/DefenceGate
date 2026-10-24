"""WP-107 (round 3, 24 Oct 2026): the roadmap follows the result and the answers.

p09: one roadmap for an SME, a US-controlled group of 2,000+ and a university; p01: NATO clearance questions after "no classified work";
p09: "5 to 20 days" beside an immediate PIC; LEAR missing; ISO 9001 cost.
"""

from __future__ import annotations

from dgate.readiness import roadmap
from dgate.readiness.api import assess_all, assess_payload
from dgate.readiness.engine import Profile
from dgate.readiness.seed import load_file

CONTENT = load_file()


def plan_of(profile: Profile, statuses: dict[str, str] | None = None, context: dict | None = None) -> dict:
    return assess_payload(CONTENT, profile, statuses or {}, None, context)["roadmap"]


def co(country: str, **kw) -> Profile:
    base = dict(country=country, legal_form="legal_person", executive_management_country=country, third_country_control="no",
                non_eu_component_cost_pct=10, restricted_third_country_component=False, components_from_ua=False,
                components_from_eea_efta=False, safe_role="contractor", handles_classified=False, product_regime="military",
                export_intent="none")
    base.update(kw)
    return Profile(**base)


def codes(plan: dict) -> list[str]:
    return [s["code"] for s in plan["steps"]]


def test_software_firm_and_university_get_no_aqap_step():
    product = plan_of(co("BE"))
    assert "REQ-AQAP2110" in codes(product) and product["leftOut"] == []
    for ctx in ({"offering": "software_services"}, {"org_kind": "university"}, {"org_kind": "research"}):
        plan = plan_of(co("BE"), context=ctx)
        assert "REQ-AQAP2110" not in codes(plan) and "REQ-AQAP2310" not in codes(plan)
        # ISO 9001 came only as the step before AQAP 2110
        assert "REQ-ISO9001" not in codes(plan)
        assert [x["code"] for x in plan["leftOut"]] == ["REQ-AQAP2110"]
        assert "only a supply contract that names it" in plan["leftOut"][0]["text"]
        # the totals no longer count the AQAP vendor range
        assert plan["totalsWithOptional"]["cost"] == []


def test_aqap_range_says_when_it_does_not_fit_the_company_size():
    def note(headcount):
        step = next(s for s in plan_of(co("PL"), context={"headcount": headcount})["steps"] if s["code"] == "REQ-AQAP2110")
        return step["sizeNote"]
    assert note("lt50") is None and note("50_249") is None and note(None) is None
    assert "30 to 80 employees" in note("2000plus") and "2,000 or more" in note("2000plus")
    assert note("250_499") is not None


def test_control_and_component_rules_are_listed_to_settle():
    clean = plan_of(co("BE"))
    assert clean["settle"] == []
    group = plan_of(co("BE", third_country_control="other", control_country="other_non_eu", non_eu_component_cost_pct=60))
    rules = {x["rule"] for x in group["settle"]}
    assert {"EDF-CONTROL", "EDIP-CONTROL", "SAFE-CONTROL"} <= rules
    assert {"EDIP-ORIGIN-35", "SAFE-ORIGIN-35"} <= rules
    assert all(x["reason"] and x["programmeName"] for x in group["settle"])


def test_total_time_names_the_step_that_sets_it():
    plan = plan_of(co("BE"))
    assert plan["totals"]["days"] == {"min": 5, "max": 20}
    assert plan["longest"] == "REQ-NCAGE"
    # with AQAP 2110 (3-8 months) the total that includes it is set by AQAP's track
    assert plan["longestWithOptional"] == "REQ-AQAP2110"
    # a plan of steps that need no time names none
    held = plan_of(co("BE"), {"REQ-NCAGE": "held", "REQ-ISO9001": "held", "REQ-AQAP2110": "held"})
    assert held["totals"]["days"]["max"] == 0 and held["longest"] is None


def test_pic_step_names_validation_and_lear_and_iso9001_says_why_no_cost():
    steps = {s["code"]: s for s in plan_of(co("BE"))["steps"]}
    assert "LEAR" in steps["REQ-PIC"]["note"] and "Central Validation Service" in steps["REQ-PIC"]["note"]
    assert steps["REQ-ISO9001"]["cost"] is None
    assert "No source we hold states the cost" in steps["REQ-ISO9001"]["note"]


def test_german_aqap_issuer_is_unverified_like_the_country_route():
    # p03: the route says "Not covered yet for Germany"; the roadmap named "Bundeswehr" (a secondary source). No primary source was found,
    # so the row is unverified and the page says so (web: issuerFor), while Germany keeps its state-route price note
    step = next(s for s in plan_of(co("DE"))["steps"] if s["code"] == "REQ-AQAP2110")
    assert [i["status"] for i in step["issuers"]] == ["U"]
    assert step["priceNote"] is not None


def test_no_nato_clearance_question_without_classified_work():
    es = co("ES")
    assessments, general = assess_all(CONTENT, es, {}, [CONTENT.programmes["ES-MOD"]])
    nsfcc = next(r for r in assessments[0].rules if r.rule == "ES-NSFCC")
    assert nsfcc.outcome == "not_applicable" and nsfcc.asks == ()
    plan = roadmap.build_roadmap([*assessments, *general], {}, CONTENT, "ES")
    assert "REQ-FSC-ES" not in codes(plan)
    # with classified NATO work the rule still asks
    yes = co("ES", handles_classified=True, nato_classified_contract=True)
    a, _ = assess_all(CONTENT, yes, {}, [CONTENT.programmes["ES-MOD"]])
    assert next(r for r in a[0].rules if r.rule == "ES-NSFCC").outcome == "unknown"
