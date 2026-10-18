"""The readiness rules engine (WP-29): the language of a rule, the three-valued logic, the verdicts.

Every branch of the evaluator is exercised here (the brief asks for 100 % branch coverage of it;
`python -m coverage run --branch` over this file and `test_readiness_seed.py` is how it is measured).
"""

from __future__ import annotations

import dataclasses

import pytest

from dgate.readiness import engine
from dgate.readiness.content import Content, Programme, Rule
from dgate.readiness.engine import ExprError, Profile, assess, evaluate, fields_in, validate_expr

CODES = {"REQ-PIC", "REQ-NCAGE"}


def ev(expr, statuses=None, **fields):
    base = dict.fromkeys(engine.FIELDS)
    base.update(fields)
    return evaluate(expr, base, statuses or {})


# --------------------------------------------------------------------- the three-valued logic

def test_all_is_false_if_one_is_false_unknown_if_one_is_unknown_and_none_is_false():
    t, f, u = {"field": "handles_classified", "is": True}, {"field": "handles_classified", "is": False}, {"field": "export_intent", "is": "none"}
    assert ev({"all": [t, t]}, handles_classified=True) is True
    assert ev({"all": [t, f]}, handles_classified=True) is False
    assert ev({"all": [t, u]}, handles_classified=True) is None
    assert ev({"all": [f, u]}, handles_classified=True) is False        # a certain "no" beats a missing answer


def test_any_is_true_if_one_is_true_unknown_if_one_is_unknown_and_none_is_true():
    t, f, u = {"field": "handles_classified", "is": True}, {"field": "handles_classified", "is": False}, {"field": "export_intent", "is": "none"}
    assert ev({"any": [t, f]}, handles_classified=True) is True
    assert ev({"any": [f, f]}, handles_classified=True) is False
    assert ev({"any": [f, u]}, handles_classified=True) is None
    assert ev({"any": [t, u]}, handles_classified=True) is True


def test_not_flips_true_and_false_and_keeps_unknown():
    expr = {"not": {"field": "handles_classified", "is": True}}
    assert ev(expr, handles_classified=True) is False
    assert ev(expr, handles_classified=False) is True
    assert ev(expr) is None


def test_a_missing_answer_is_unknown_never_no():
    assert ev({"field": "country", "is": "ES"}) is None
    assert ev({"field": "country", "in": ["EU"]}) is None
    assert ev({"threshold": {"field": "non_eu_component_cost_pct", "lte": 35}}) is None


def test_is_compares_values_and_booleans_exactly():
    assert ev({"field": "country", "is": "ES"}, country="ES") is True
    assert ev({"field": "country", "is": "ES"}, country="PL") is False
    assert ev({"field": "handles_classified", "is": True}, handles_classified=True) is True
    assert ev({"field": "handles_classified", "is": False}, handles_classified=True) is False
    assert ev({"field": "handles_classified", "is": True}, handles_classified=1) is False   # 1 is not True


def test_in_expands_the_country_groups_for_country_fields_only():
    expr = {"field": "country", "in": ["EU", "EEA_EFTA", "UA"]}
    for code in ("ES", "NO", "UA"):
        assert ev(expr, country=code) is True
    for code in ("GB", "XX", "CH", "TR", "US"):
        assert ev(expr, country=code) is False
    assert ev({"field": "country", "in": ["ES", "PL"]}, country="PL") is True        # a plain code
    # a group name is a group only on a country field
    assert ev({"field": "product_regime", "in": ["military", "dual_use"]}, product_regime="military") is True
    assert ev({"field": "product_regime", "in": ["military"]}, product_regime="dual_use") is False


def test_the_eu_group_is_the_27_member_states():
    assert len(engine.EU27) == 27
    assert "GB" not in engine.EU27 and "NO" not in engine.EU27 and "UA" not in engine.EU27
    assert engine.EEA_EFTA == {"IS", "LI", "NO"}


def test_threshold_boundaries_for_all_four_operators():
    def t(op, value, limit):
        return ev({"threshold": {"field": "non_eu_component_cost_pct", op: limit}}, non_eu_component_cost_pct=value)
    assert t("lte", 35, 35) is True and t("lte", 35.01, 35) is False
    assert t("lt", 35, 35) is False and t("lt", 34.99, 35) is True
    assert t("gte", 35, 35) is True and t("gte", 34.99, 35) is False
    assert t("gt", 35, 35) is False and t("gt", 35.01, 35) is True
    assert t("lte", 0, 35) is True


def test_a_status_is_compared_and_a_requirement_not_mentioned_is_not_held():
    held = {"status": "REQ-PIC", "in": ["held", "not_applicable"]}
    assert ev(held, {"REQ-PIC": "held"}) is True
    assert ev(held, {"REQ-PIC": "not_applicable"}) is True
    assert ev(held, {"REQ-PIC": "in_progress"}) is False
    assert ev(held, {}) is False                                   # nothing said: not held
    assert ev({"status": "REQ-PIC", "is": "not_held"}, {}) is True


# --------------------------------------------------------------------- validation

@pytest.mark.parametrize("bad", [
    None, {}, [], "x", {"all": []}, {"all": "x"}, {"all": [{"field": "country", "is": "ES"}], "extra": 1},
    {"any": []}, {"not": {}}, {"not": {"field": "country", "is": "ES"}, "x": 1}, {"unknown": 1},
    {"field": "nope", "is": 1}, {"field": "country"}, {"field": "country", "is": "ES", "in": ["EU"]},
    {"field": "country", "eq": "ES"}, {"field": "country", "in": []}, {"field": "country", "in": "EU"},
    {"field": "country", "is": 5}, {"field": "country", "is": "ESP"}, {"field": "third_country_control", "is": "maybe"},
    {"field": "handles_classified", "is": "yes"}, {"field": "non_eu_component_cost_pct", "is": 3},
    {"status": "REQ-NOPE", "is": "held"}, {"status": "REQ-PIC", "is": "kept"}, {"status": "REQ-PIC"},
    {"threshold": 5}, {"threshold": {"field": "country", "lte": 3}}, {"threshold": {"field": "non_eu_component_cost_pct"}},
    {"threshold": {"field": "non_eu_component_cost_pct", "lte": 3, "gte": 1}},
    {"threshold": {"field": "non_eu_component_cost_pct", "lte": "35"}},
    {"threshold": {"field": "non_eu_component_cost_pct", "lte": True}},
    {"threshold": {"field": "non_eu_component_cost_pct", "lte": 3}, "x": 1},
    {"threshold": {"field": "non_eu_component_cost_pct", "lte": 3, "extra": 1}},
])
def test_a_malformed_expression_is_refused_when_the_seed_is_loaded(bad):
    with pytest.raises(ExprError):
        validate_expr(bad, CODES)


@pytest.mark.parametrize("good", [
    {"all": [{"field": "country", "in": ["EU", "UA"]}, {"not": {"field": "handles_classified", "is": True}}]},
    {"any": [{"status": "REQ-PIC", "is": "held"}, {"status": "REQ-NCAGE", "in": ["held", "in_progress"]}]},
    {"threshold": {"field": "non_eu_component_cost_pct", "lte": 35}},
    {"field": "third_country_control", "in": ["no", "ua_eea_only"]},
    {"field": "ua_non_government_controlled_area", "is": False},
])
def test_a_well_formed_expression_passes(good):
    validate_expr(good, CODES)


def test_fields_in_lists_what_an_expression_reads_once_each_in_order():
    expr = {"all": [{"field": "country", "is": "ES"}, {"not": {"field": "handles_classified", "is": True}},
                    {"threshold": {"field": "non_eu_component_cost_pct", "lte": 1}}, {"field": "country", "in": ["EU"]},
                    {"status": "REQ-PIC", "is": "held"}]}
    assert fields_in(expr) == ["country", "handles_classified", "non_eu_component_cost_pct"]
    assert fields_in(None) == []


# --------------------------------------------------------------------- rules and verdicts

def _rule(code="R", *, obligation="mandatory", condition=None, applies_when=None, conditional_when=None,
          texts=None, requirement=None, kind="establishment") -> Rule:
    return Rule(programme="P", code=code, title=f"Rule {code}", obligation=obligation, kind=kind,
                requirement=requirement, applies_when=applies_when, condition=condition,
                conditional_when=conditional_when,
                texts=texts or {"met": "m", "not_met": "n", "conditional": "c", "unknown": "u", "not_applicable": "na", "info": "i"},
                note=None, denominator=None, source_url="https://example.test", source_ref="ref",
                source_text="[ref] quote", text_origin="primary", status="V", last_reviewed="2026-10-17")


def _programme(*rules) -> Programme:
    return Programme(code="P", name="Programme", summary="s", kind="programme", legal_basis=None,
                     source_url="https://example.test", call_programme=None, last_reviewed="2026-10-17",
                     rules=tuple(rules))


ES = {"field": "country", "is": "ES"}
PL = {"field": "country", "is": "PL"}
NO = {"field": "country", "in": ["EEA_EFTA"]}


def outcome(rule, **profile):
    result = assess(Profile(country="ES", **profile), {}, _programme(rule)).rules[0]
    return result.outcome, result.reason


def test_a_rule_outcome_for_each_branch():
    assert outcome(_rule(condition=ES)) == ("met", "m")
    assert outcome(_rule(condition=PL)) == ("not_met", "n")
    assert outcome(_rule(condition=PL, conditional_when=ES)) == ("conditional", "c")
    assert outcome(_rule(condition=PL, conditional_when=PL)) == ("not_met", "n")
    assert outcome(_rule(condition={"field": "handles_classified", "is": True})) == ("unknown", "u")
    assert outcome(_rule(condition=PL, conditional_when={"field": "handles_classified", "is": True})) == ("unknown", "u")
    assert outcome(_rule(condition=None)) == ("info", "i")


def test_applies_when_makes_a_rule_not_applicable_or_unknown():
    assert outcome(_rule(condition=ES, applies_when=PL)) == ("not_applicable", "na")
    assert outcome(_rule(condition=ES, applies_when=ES)) == ("met", "m")
    assert outcome(_rule(condition=ES, applies_when={"field": "handles_classified", "is": True})) == ("unknown", "u")


def test_a_missing_text_falls_back_to_a_plain_sentence():
    rule = _rule(condition={"field": "handles_classified", "is": True}, texts={"met": "m", "not_met": "n"})
    assert assess(Profile(country="ES"), {}, _programme(rule)).rules[0].reason == engine.GENERIC["unknown"]
    rule = _rule(condition=ES, applies_when=PL, texts={"met": "m", "not_met": "n"})
    assert assess(Profile(country="ES"), {}, _programme(rule)).rules[0].reason == engine.GENERIC["not_applicable"]
    rule = _rule(condition=PL, texts={"met": "m"})
    assert assess(Profile(country="ES"), {}, _programme(rule)).rules[0].reason == ""


def test_the_asks_of_an_unknown_rule_are_the_missing_fields_only():
    rule = _rule(condition={"all": [ES, {"field": "handles_classified", "is": True}, {"field": "export_intent", "is": "none"}]})
    result = assess(Profile(country="ES", export_intent="none"), {}, _programme(rule)).rules[0]
    assert result.outcome == "unknown" and result.asks == ("handles_classified",)


def test_verdicts():
    def verdict(*rules, **profile):
        a = assess(Profile(country="ES", **profile), {}, _programme(*rules))
        return a.verdict, a.incomplete
    assert verdict(_rule("A", condition=ES)) == ("eligible", False)
    assert verdict(_rule("A", condition=ES), _rule("B", condition=PL)) == ("blocked", False)
    assert verdict(_rule("A", condition=PL, conditional_when=ES)) == ("conditional", False)
    assert verdict(_rule("A", condition={"field": "handles_classified", "is": True})) == ("conditional", True)
    # blocked beats conditional and unknown, and an unknown beside a block is still incomplete
    assert verdict(_rule("A", condition=PL), _rule("B", condition={"field": "handles_classified", "is": True})) == ("blocked", True)
    # a rule that is not mandatory never changes the verdict
    assert verdict(_rule("A", condition=PL, obligation="conditional")) == ("eligible", False)
    assert verdict(_rule("A", condition=PL, obligation="recommended")) == ("eligible", False)
    assert verdict(_rule("A", condition=None)) == ("eligible", False)


HELD = {"status": "REQ-PIC", "in": ["held", "not_applicable"]}


def test_a_missing_registration_is_something_to_obtain_not_a_block():
    # D3: only a mandatory rule of kind "registration" (the PIC, the NCAGE) gets this outcome
    reg = _rule("PIC", condition=HELD, kind="registration", requirement="REQ-PIC")
    a = assess(Profile(country="ES"), {}, _programme(reg))
    assert (a.verdict, a.blocking, a.to_obtain, a.incomplete) == ("obtain", (), ("PIC",), False)
    assert a.rules[0].outcome == "to_obtain" and a.rules[0].reason == "n"      # the text of "not met" says what to obtain
    assert a.summary["to_obtain"] == 1 and a.summary["not_met"] == 0
    assert assess(Profile(country="ES"), {"REQ-PIC": "held"}, _programme(reg)).verdict == "eligible"
    assert assess(Profile(country="ES"), {"REQ-PIC": "in_progress"}, _programme(reg)).verdict == "obtain"
    # any other kind that is not met is still a block
    assert assess(Profile(country="ES"), {}, _programme(_rule("X", condition=HELD, kind="export"))).verdict == "blocked"


def test_what_beats_what_between_blocked_conditional_obtain_and_eligible():
    reg = _rule("PIC", condition=HELD, kind="registration")
    guarantee = _rule("G", condition=PL, conditional_when=ES)
    block = _rule("B", condition=PL)
    unknown = _rule("U", condition={"field": "handles_classified", "is": True})
    def verdict(*rules):
        a = assess(Profile(country="ES"), {}, _programme(*rules))
        return a.verdict, a.to_obtain
    assert verdict(reg, guarantee) == ("conditional", ("PIC",))        # the to-do stays listed
    assert verdict(reg, unknown) == ("conditional", ("PIC",))
    assert verdict(reg, block) == ("blocked", ("PIC",))
    assert verdict(_rule("PIC", condition=HELD, kind="registration", obligation="conditional")) == ("eligible", ())   # not mandatory


def test_the_questions_of_a_rule_whose_applicability_is_unknown_include_those_of_its_condition():
    rule = _rule(applies_when={"field": "safe_role", "in": ["contractor"]}, condition={"field": "third_country_control", "is": "no"})
    result = assess(Profile(country="ES"), {}, _programme(rule)).rules[0]
    assert result.outcome == "unknown" and result.asks == ("safe_role", "third_country_control")


def test_assessment_carries_blocking_conditions_missing_summary_and_the_plans_explanation():
    rules = (_rule("A", condition=PL), _rule("B", condition=PL, conditional_when=ES),
             _rule("C", condition={"field": "handles_classified", "is": True}),
             _rule("D", condition={"field": "handles_classified", "is": False}))
    a = assess(Profile(country="ES"), {}, _programme(*rules))
    assert a.blocking == ("A",) and a.conditions == ("B",) and a.missing == ("handles_classified",)
    assert a.summary["not_met"] == 1 and a.summary["conditional"] == 1 and a.summary["unknown"] == 2
    assert [e["rule"] for e in a.explanation] == ["A", "B", "C", "D"]
    assert set(a.explanation[0]) == {"rule", "outcome", "reason", "source_url"}


def test_rules_are_assessed_in_their_position_order_and_the_same_input_gives_the_same_output():
    r1 = dataclasses.replace(_rule("B", condition=ES), position=2)
    r2 = dataclasses.replace(_rule("A", condition=ES), position=1)
    p = _programme(r1, r2)
    first = assess(Profile(country="ES"), {}, p)
    assert [r.rule for r in first.rules] == ["A", "B"]
    assert first == assess(Profile(country="ES"), {}, p)


def test_a_programme_can_be_named_by_code_with_the_content_and_not_without():
    p = _programme(_rule("A", condition=ES))
    content = Content(programmes={"P": p}, requirements={})
    assert assess(Profile(country="ES"), {}, "P", content).programme == "P"
    with pytest.raises(ValueError):
        assess(Profile(country="ES"), {}, "P")


def test_the_profile_exposes_exactly_the_fields_the_rules_may_read():
    assert set(Profile(country="ES").fields()) == set(engine.FIELDS)
    assert Profile(country="ES").fields()["product_regime"] == "unknown"
