"""WP-53: readiness correctness in the rule engine (T4: "Not applicable to us" is not "Met"; T21: the partner question).

The web mirror of the same decisions is in web/lib/*.check.ts. Each test here fails on the engine before WP-53.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from dgate.readiness import engine, roadmap
from dgate.readiness.api import ProfileIn
from dgate.readiness.engine import Profile, assess
from dgate.readiness.seed import load_file

CONTENT = load_file()
RULES = {r.code: r for p in CONTENT.programmes.values() for r in p.rules}


def company(country="PL", **kw):
    base = dict(country=country, legal_form="legal_person", executive_management_country=country, third_country_control="no",
                non_eu_component_cost_pct=10, restricted_third_country_component=False, components_from_ua_or_eea_efta=False,
                safe_role="contractor", handles_classified=False, product_regime="none", export_intent="none")
    base.update(kw)
    return Profile(**base)


def rules_of(programme, profile, statuses):
    a = assess(profile, statuses, CONTENT.programmes[programme])
    return a, {r.rule: r for r in a.rules}


# --------------------------------------------------------------------------- T4

@pytest.mark.parametrize("programme,code", [("EDF", "EDF-PIC"), ("EDIP", "EDIP-PIC"), ("EDIP-USI", "USI-PIC")])
def test_t4_not_applicable_is_not_a_pic_the_company_holds(programme, code):
    held = rules_of(programme, company(), {"REQ-PIC": "held"})[1][code]
    na = rules_of(programme, company(), {"REQ-PIC": "not_applicable"})[1][code]
    assert held.outcome == "met" and held.reason == "You have a PIC."
    assert na.outcome == "not_applicable", "a different state: left out, never counted as met"
    assert "You have a PIC" not in na.reason and "Not applicable to us" in na.reason and "not counted as met" in na.reason
    assert RULES[code].texts["met"] == "You have a PIC."


def test_t4_the_summary_does_not_count_it_as_met_and_the_verdict_does_not_ask_for_the_pic():
    held, _ = rules_of("EDF", company(), {"REQ-PIC": "held"})
    na, _ = rules_of("EDF", company(), {"REQ-PIC": "not_applicable"})
    assert na.summary["met"] == held.summary["met"] - 1 and na.summary["not_applicable"] == held.summary["not_applicable"] + 1
    assert na.to_obtain == () and na.verdict == "eligible"
    not_held, _ = rules_of("EDF", company(), {"REQ-PIC": "not_held"})
    assert not_held.verdict == "obtain" and not_held.to_obtain == ("EDF-PIC",)


def test_t4_the_roadmap_has_no_pic_step_for_not_applicable_or_held_and_one_for_the_rest():
    p = company()
    programmes = [x for x in CONTENT.programmes.values() if x.kind != "general"]
    for status, step in (("not_applicable", False), ("held", False), ("in_progress", True), ("not_held", True)):
        statuses = {"REQ-PIC": status}
        plan = roadmap.build_roadmap([assess(p, statuses, x) for x in programmes], statuses, CONTENT, p.country)
        assert ("REQ-PIC" in [s["code"] for s in plan["steps"]]) is step, status


def test_t4_the_same_holds_for_every_rule_that_reads_a_status():
    # the NCAGE code of NATO supply and the export authorisation of the general rules read statuses the same way
    _, rules = rules_of("NATO-SUPPLY", company(), {"REQ-NCAGE": "not_applicable"})
    assert rules["NATO-NCAGE"].outcome == "not_applicable" and rules["NATO-NCAGE"].reason == engine.DECLARED_NOT_APPLICABLE
    dual = company(product_regime="dual_use", export_intent="outside_eu")
    _, rules = rules_of("GENERAL", dual, {"REQ-EXPORT": "not_applicable"})
    assert rules["G-EXPORT"].outcome == "not_applicable" and rules["G-EXPORT"].reason == engine.DECLARED_NOT_APPLICABLE
    _, rules = rules_of("GENERAL", dual, {"REQ-EXPORT": "held"})
    assert rules["G-EXPORT"].outcome == "met"


def test_t4_a_rule_that_does_not_apply_for_its_own_reason_keeps_its_own_words():
    # a product that is not dual-use: the export rule does not apply, and the reason is the rule's, not "you answered"
    _, rules = rules_of("GENERAL", company(product_regime="none", export_intent="none"), {"REQ-EXPORT": "not_applicable"})
    assert rules["G-EXPORT"].outcome == "not_applicable" and rules["G-EXPORT"].reason != engine.DECLARED_NOT_APPLICABLE


def test_t4_no_seed_expression_counts_not_applicable_as_held():
    # the data says what the engine does: a status condition asks for "held" only
    for rule in RULES.values():
        for expr in (rule.condition, rule.conditional_when, rule.applies_when):
            assert "not_applicable" not in repr(expr), rule.code
    for code in ("EDF-PIC", "EDIP-PIC", "USI-PIC", "NATO-NCAGE", "G-EXPORT", "G-REOCE", "G-HSEM", "G-EXPORT-MIL"):
        assert RULES[code].condition == {"status": RULES[code].requirement, "is": "held"}, code


# --------------------------------------------------------------------------- T21

def test_t21_the_profile_takes_the_partner_answer_and_unanswered_is_unknown_not_no():
    assert ProfileIn(country="PL").to_engine().ua_partner is None
    assert ProfileIn(country="PL", ua_partner=True).to_engine().ua_partner is True
    assert "ua_partner" in engine.FIELDS and engine.FIELDS["ua_partner"]["label"].startswith("Does your planned consortium include")
    with pytest.raises(ValueError):
        ProfileIn(country="PL", ua_partner="maybe")


def test_t21_the_three_answers_give_three_outcomes_for_a_company_outside_ukraine():
    held = {"REQ-PIC": "held"}
    out = {}
    for answer in (None, False, True):
        a, rules = rules_of("EDIP-USI", company(ua_partner=answer), held)
        out[answer] = (rules["USI-INVOLVES-UA"].outcome, a.verdict, a.missing)
    assert out[None] == ("unknown", "conditional", ("ua_partner",))
    assert out[False] == ("conditional", "conditional", ())
    assert out[True] == ("met", "eligible", ())


def test_t21_a_ukrainian_company_needs_no_answer_and_the_answer_does_not_hurt_it():
    held = {"REQ-PIC": "held"}
    for answer in (None, False, True):
        a, rules = rules_of("EDIP-USI", company("UA", ua_non_government_controlled_area=False, ua_partner=answer), held)
        assert rules["USI-INVOLVES-UA"].outcome == "met" and a.verdict == "eligible" and a.missing == (), answer


def test_t21_the_partner_never_fixes_another_rule():
    # a Polish company controlled from outside stays short on the control rule whatever partner it names
    a, rules = rules_of("EDIP-USI", company(third_country_control="other", ua_partner=True), {"REQ-PIC": "held"})
    assert rules["USI-INVOLVES-UA"].outcome == "met" and rules["USI-CONTROL"].outcome != "met" and a.verdict != "eligible"
    # and the EDIP Programme has no rule that reads the partner
    assert all("ua_partner" not in engine.fields_in(r.condition) for r in CONTENT.programmes["EDIP"].rules)
    assert replace(company(), ua_partner=True).ua_partner is True
