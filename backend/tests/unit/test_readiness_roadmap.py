"""Readiness scenarios (WP-29): a Ukrainian manufacturer with nothing and a Spanish manufacturer with
ISO 9001, run through the engine and the roadmap on the real seed. The expected verdicts and steps are
written out here; a change to a rule that changes one of them has to change this file on purpose.

The roadmap totals are compared with the ranges the technical appendix states (Part IV, AQAP):
  full AQAP 2110 cycle, 30-80 employees: USD 17,000-48,000 (about EUR 15,700-44,200), 3-8 months;
  small firm with ISO 9001 already: USD 17,000-25,000, 3-4 months.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from dgate.readiness import roadmap
from dgate.readiness.api import assess_all
from dgate.readiness.engine import Profile, assess
from dgate.readiness.seed import load_file

CONTENT = load_file()
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)

UA = Profile(country="UA", legal_form="legal_person", executive_management_country="UA", third_country_control="no",
             ua_non_government_controlled_area=False, non_eu_component_cost_pct=20,
             restricted_third_country_component=False, components_from_ua_or_eea_efta=False, safe_role="contractor",
             handles_classified=False, product_regime="dual_use", export_intent="outside_eu")
ES = Profile(country="ES", legal_form="legal_person", executive_management_country="ES", third_country_control="no",
             non_eu_component_cost_pct=10, restricted_third_country_component=False, components_from_ua_or_eea_efta=False,
             safe_role="contractor", handles_classified=True, product_regime="military", export_intent="outside_eu")
# Poland: a commercial route for AQAP (Spain's and Germany's is the state's own), so the vendor ranges apply
PL = Profile(country="PL", legal_form="legal_person", executive_management_country="PL", third_country_control="no",
             non_eu_component_cost_pct=10, restricted_third_country_component=False, components_from_ua_or_eea_efta=False,
             safe_role="contractor", handles_classified=False, product_regime="military", export_intent="outside_eu")


def co(country, **kw):
    """A clean legal person established and managed in `country`; `kw` overrides single answers."""
    base = dict(country=country, legal_form="legal_person", executive_management_country=country, third_country_control="no",
                ua_non_government_controlled_area=False if country == "UA" else None, non_eu_component_cost_pct=10,
                restricted_third_country_component=False, components_from_ua_or_eea_efta=False, safe_role="contractor")
    base.update(kw)
    return Profile(**base)


def run(profile, statuses):
    programmes = [p for p in CONTENT.programmes.values() if p.kind != "general"]
    # as the API answers (WP-64): unasked requirements read as unknown, a route that concerns nobody here is left out
    assessments, general = assess_all(CONTENT, profile, statuses, programmes)
    plan = roadmap.build_roadmap([*assessments, *general], statuses, CONTENT, profile.country)
    return {a.programme: a for a in assessments}, {a.programme: a for a in general}, plan


def outcomes(a):
    return {r.rule: r.outcome for r in a.rules}


# --------------------------------------------------------------------- a Ukrainian manufacturer with nothing

def test_ua_manufacturer_with_nothing_verdicts():
    by, general, _ = run(UA, {})
    # EDF: Regulation (EU) 2025/2653 lets Ukraine be an associated country "in accordance with the conditions laid down in the
    # EU-Ukraine Association Agreement"; the EDF call documents say that participation is pending the signature of the
    # agreement and no primary text says it applies (V2-B2), so the establishment rules are conditional, and the PIC
    # (a free registration to obtain first, D3) stays on the list.
    assert by["EDF"].verdict == "conditional" and by["EDF"].blocking == () and by["EDF"].to_obtain == ("EDF-PIC",)
    assert outcomes(by["EDF"])["EDF-ESTABLISH"] == outcomes(by["EDF"])["EDF-EXEC-MGMT"] == "conditional"
    assert by["EDF"].conditions == ("EDF-ESTABLISH", "EDF-EXEC-MGMT")
    # EDIP the Programme: Ukraine is not an associated country there (EEA EFTA members only)
    assert by["EDIP"].verdict == "blocked"
    assert by["EDIP"].blocking == ("EDIP-ESTABLISH", "EDIP-EXEC-MGMT") and by["EDIP"].to_obtain == ("EDIP-PIC",)
    # the Ukraine Support Instrument is the route for a Ukrainian company: only the PIC is missing
    assert by["EDIP-USI"].verdict == "obtain" and by["EDIP-USI"].to_obtain == ("USI-PIC",)
    assert outcomes(by["EDIP-USI"])["USI-TERRITORY"] == "met"
    # SAFE: established in Ukraine, 20 % of component cost from outside: eligible
    assert by["SAFE"].verdict == "eligible" and not by["SAFE"].incomplete
    assert by["NATO-SUPPLY"].verdict == "obtain" and by["NATO-SUPPLY"].to_obtain == ("NATO-NCAGE",)
    assert outcomes(general["GENERAL"]) == {
        "G-REGIME": "not_applicable", "G-EXPORT": "not_met", "G-EXPORT-INTRA-DU": "not_applicable",
        "G-EXPORT-MIL": "not_applicable", "G-REOCE": "not_applicable",
        "G-HSEM": "not_applicable", "G-CLASSIFIED-OTHER": "not_applicable",
        # WP-64: the German rules are for German companies; whether a dual-use item exported outside the EU is a listed one is
        # a classification the profile does not answer yet, so the "consultant needed" rule asks it
        "DE-GHB-ADMISSION": "not_applicable", "DE-GHB-COST": "not_applicable", "DE-GHB-BID": "not_applicable",
        "DE-VSNFD": "not_applicable", "DE-SIBE": "not_applicable", "DE-SUE": "not_applicable", "DE-EXPORT-BAFA": "not_applicable",
        "EU-CERTIFIED-RECIPIENT": "not_applicable", "EU-DUALUSE-EXPERT": "unknown"}


def test_ua_manufacturer_with_nothing_roadmap():
    _, _, plan = run(UA, {})
    codes = [s["code"] for s in plan["steps"]]
    assert codes == ["REQ-PIC", "REQ-NCAGE", "REQ-EXPORT", "REQ-ISO9001", "REQ-AQAP2110"]
    steps = {s["code"]: s for s in plan["steps"]}
    assert steps["REQ-PIC"]["blockingFor"] == ["EDF", "EDIP", "EDIP-USI"]
    assert steps["REQ-NCAGE"]["blockingFor"] == ["NATO-SUPPLY"]
    assert steps["REQ-EXPORT"]["blockingFor"] == [] and not steps["REQ-EXPORT"]["optional"]
    assert steps["REQ-AQAP2110"]["optional"] and steps["REQ-AQAP2110"]["when"] == "when a contract names it"
    assert steps["REQ-ISO9001"]["optional"]
    # the issuer is the one for the profile's country, else the one for every country, else "not collected"
    assert steps["REQ-NCAGE"]["issuers"][0]["name"].startswith("National Codification Bureau of Ukraine")
    assert steps["REQ-PIC"]["issuers"][0]["country"] == "*"
    assert steps["REQ-AQAP2110"]["issuers"][0]["name"].startswith("Commercial and partner certification bodies")
    assert steps["REQ-EXPORT"]["issuers"] == [] and "has not been collected" in steps["REQ-EXPORT"]["issuerNote"]
    # REOCE is Spanish: a Ukrainian exporter is not sent to it because the licence lists it as a prerequisite
    assert "REQ-REOCE" not in codes
    assert [p["code"] for p in steps["REQ-EXPORT"]["prerequisites"]] == []
    # the ISO 9001 step is a prerequisite of AQAP 2110; no cost or time is stated for it
    assert [(p["code"], p["status"]) for p in steps["REQ-AQAP2110"]["prerequisites"]] == [("REQ-ISO9001", "not_held")]
    assert steps["REQ-ISO9001"]["cost"] is None and steps["REQ-ISO9001"]["days"] is None
    # the full-cycle range of the source, with the vendor label, and the source's note about starting from zero
    assert (steps["REQ-AQAP2110"]["cost"]["min"], steps["REQ-AQAP2110"]["cost"]["max"],
            steps["REQ-AQAP2110"]["cost"]["currency"]) == (17000, 48000, "USD")
    assert steps["REQ-AQAP2110"]["cost"]["label"] == "vendor range, not a benchmark"
    assert steps["REQ-AQAP2110"]["variantUsed"] is None and "30-40 %" in steps["REQ-AQAP2110"]["branchNote"]
    # parallel tracks: the PIC, the NCAGE, the licence, and the ISO 9001 to AQAP 2110 chain
    assert plan["tracks"] == [["REQ-PIC"], ["REQ-NCAGE"], ["REQ-EXPORT"], ["REQ-ISO9001", "REQ-AQAP2110"]]
    assert steps["REQ-PIC"]["parallelWith"] == [2, 3, 4, 5]
    # totals of what is required: nothing costs money; the NCAGE takes 5 to 20 days; the licence is not stated
    required = plan["totals"]
    assert required["cost"] == [] and required["freeSteps"] == ["REQ-PIC", "REQ-NCAGE"]
    assert required["days"] == {"min": 5, "max": 20}
    assert plan["unknownCost"] == ["REQ-EXPORT"] and plan["unknownDuration"] == ["REQ-EXPORT"]
    # D10: ISO 9001 has no stated cost or time either, and the total that includes it must say so
    assert plan["unknownCostWithOptional"] == ["REQ-EXPORT", "REQ-ISO9001"]
    assert plan["unknownDurationWithOptional"] == ["REQ-EXPORT", "REQ-ISO9001"]
    # D10: the source's "+30-40 % and 1-2 months without ISO 9001" is shown, never added to a total
    assert [n["code"] for n in plan["notAdded"]] == ["REQ-AQAP2110"] and "30-40 %" in plan["notAdded"][0]["text"]


def test_ua_roadmap_total_with_aqap_equals_the_appendix_full_cycle_range():
    _, _, plan = run(UA, {})
    total = plan["totalsWithOptional"]
    assert total["cost"] == [{"currency": "USD", "min": 17000, "max": 48000, "steps": ["REQ-AQAP2110"]}]
    assert total["days"] == {"min": 90, "max": 240}              # appendix: 3-8 months at 30 days a month


# --------------------------------------------------------------------- a Spanish manufacturer with ISO 9001

STATUS_ES = {"REQ-ISO9001": "held"}


def test_es_manufacturer_with_iso_9001_verdicts():
    by, general, _ = run(ES, STATUS_ES)
    assert (by["EDF"].verdict, by["EDF"].to_obtain) == ("obtain", ("EDF-PIC",))
    assert (by["EDIP"].verdict, by["EDIP"].to_obtain) == ("obtain", ("EDIP-PIC",))
    # WP-42 R1: the PIC is still the only thing to obtain, but the action also needs a Ukrainian applicant or partner: conditional, not "obtain"
    assert (by["EDIP-USI"].verdict, by["EDIP-USI"].to_obtain, by["EDIP-USI"].missing) == ("conditional", ("USI-PIC",), ("ua_partner",))
    assert not by["EDF"].blocking and not by["EDIP"].blocking and not by["EDIP-USI"].blocking
    assert outcomes(by["EDIP-USI"])["USI-TERRITORY"] == "not_applicable"
    assert by["SAFE"].verdict == "eligible"
    assert outcomes(general["GENERAL"])["G-REOCE"] == "not_met" and outcomes(general["GENERAL"])["G-HSEM"] == "not_met"
    # D6: a military product is under the military regime, not Regulation 2021/821
    assert outcomes(general["GENERAL"])["G-EXPORT"] == "not_applicable" and outcomes(general["GENERAL"])["G-EXPORT-MIL"] == "not_met"
    assert outcomes(general["GENERAL"])["G-CLASSIFIED-OTHER"] == "not_applicable"


def test_es_manufacturer_with_iso_9001_roadmap():
    _, _, plan = run(ES, STATUS_ES)
    # WP-64: the RID (the questionnaire does not ask whether it is held, so it is a step to mark as done) and, after it, the
    # PECAL certificate as an optional step (a contract matter, not a block before a first contract)
    assert [s["code"] for s in plan["steps"]] == ["REQ-PIC", "REQ-NCAGE", "REQ-FSC-ES", "REQ-REOCE", "REQ-RID", "REQ-EXPORT",
                                                  "REQ-AQAP2110", "REQ-PECAL"]
    steps = {s["code"]: s for s in plan["steps"]}
    assert "REQ-ISO9001" not in steps                                    # held: not a step
    aqap = steps["REQ-AQAP2110"]
    # D10: in Spain the AQAP route is the state's own (PECAL), so the vendor price ranges say nothing about it
    assert aqap["cost"] is None and aqap["days"] is None and aqap["variantUsed"] is None and aqap["branchNote"] is None
    assert "state issues this itself" in aqap["priceNote"]
    assert aqap["prerequisites"] == [{"code": "REQ-ISO9001", "name": "ISO 9001 quality management certificate",
                                      "relation": "before", "status": "held", "step": None}]
    assert steps["REQ-NCAGE"]["issuers"][0]["name"].startswith("Unidad de Catalogación")
    assert steps["REQ-REOCE"]["issuers"][0]["country"] == "ES" and steps["REQ-EXPORT"]["issuers"][0]["country"] == "ES"
    # WP-64, correction 1 (Ministry of Defence SEGINFOEMP page): the DGAM for MoD classified contracts, the ONS for NATO, EU and ESA
    assert [i["name"].split(" (")[0].split(",")[0] for i in steps["REQ-FSC-ES"]["issuers"]] == [
        "Dirección General de Armamento y Material", "Oficina Nacional de Seguridad"]
    # REOCE comes before the licence, or with it: ordered, and in the same track
    assert steps["REQ-REOCE"]["order"] < steps["REQ-EXPORT"]["order"]
    assert [p["code"] for p in steps["REQ-EXPORT"]["prerequisites"]] == ["REQ-REOCE"]
    assert ["REQ-REOCE", "REQ-EXPORT"] in plan["tracks"]
    assert plan["totals"]["days"] == {"min": 5, "max": 20}
    assert sorted(plan["unknownCost"]) == ["REQ-EXPORT", "REQ-FSC-ES", "REQ-REOCE", "REQ-RID"]
    assert "REQ-AQAP2110" in plan["unknownCostWithOptional"] and plan["notAdded"] == []
    assert plan["totalsWithOptional"]["cost"] == []             # no price is invented for the state route
    assert plan["totalsWithOptional"]["days"] == {"min": 5, "max": 20}


def test_pl_manufacturer_with_iso_9001_roadmap_uses_the_small_firm_range_of_the_appendix():
    """Poland has commercial certification bodies, so the vendor ranges apply (the Spanish route is the state's)."""
    _, _, plan = run(PL, STATUS_ES)
    steps = {s["code"]: s for s in plan["steps"]}
    aqap = steps["REQ-AQAP2110"]
    assert aqap["variantUsed"] == "REQ-ISO9001" and "ISO 9001" in aqap["branchNote"] and aqap["priceNote"] is None
    assert (aqap["cost"]["min"], aqap["cost"]["max"], aqap["cost"]["currency"]) == (17000, 25000, "USD")
    assert (aqap["days"]["min"], aqap["days"]["max"]) == (90, 120)
    # the AQAP total is inside the appendix's small-firm-with-ISO range and inside its full-cycle range
    total = plan["totalsWithOptional"]
    assert total["cost"] == [{"currency": "USD", "min": 17000, "max": 25000, "steps": ["REQ-AQAP2110"]}]
    assert total["days"] == {"min": 90, "max": 120}
    assert 17000 <= total["cost"][0]["min"] and total["cost"][0]["max"] <= 48000
    assert plan["notAdded"] == []                                # ISO 9001 is held: nothing is left out


def test_a_state_route_issuer_removes_the_price_and_germany_is_one_too():
    de = co("DE", handles_classified=False, product_regime="none", export_intent="none")
    _, _, plan = run(de, {})
    aqap = next(s for s in plan["steps"] if s["code"] == "REQ-AQAP2110")
    assert aqap["cost"] is None and aqap["priceNote"] and "REQ-AQAP2110" in plan["unknownCostWithOptional"]


def test_a_requirement_in_progress_is_still_a_step_and_not_applicable_or_held_are_not():
    _, _, plan = run(UA, {"REQ-PIC": "in_progress", "REQ-NCAGE": "held", "REQ-EXPORT": "not_applicable"})
    steps = {s["code"]: s for s in plan["steps"]}
    assert steps["REQ-PIC"]["status"] == "in_progress"
    assert "REQ-NCAGE" not in steps and "REQ-EXPORT" not in steps


def test_marking_everything_done_leaves_an_empty_roadmap_and_eligible_cards():
    held = {"REQ-PIC": "held", "REQ-NCAGE": "held", "REQ-EXPORT": "held", "REQ-AQAP2110": "held"}
    by, _, plan = run(UA, held)
    assert [s["code"] for s in plan["steps"]] == []
    assert plan["totals"] == {"cost": [], "freeSteps": [], "days": {"min": 0, "max": 0}}
    # the Ukrainian company stays conditional for the EDF whatever it holds: the association agreement is not confirmed (V2-B2)
    assert by["EDF"].verdict == "conditional" and by["EDIP-USI"].verdict == "eligible" and by["EDIP"].verdict == "blocked"
    assert by["NATO-SUPPLY"].verdict == "eligible" and by["EDF"].to_obtain == ()


def test_iso_held_with_aqap_2110_in_progress_uses_the_iso_range():
    _, _, plan = run(PL, {"REQ-ISO9001": "held", "REQ-AQAP2110": "in_progress"})
    aqap = [s for s in plan["steps"] if s["code"] == "REQ-AQAP2110"][0]
    assert aqap["status"] == "in_progress" and aqap["cost"]["max"] == 25000


def test_a_prerequisite_that_is_optional_becomes_required_when_something_required_depends_on_it():
    from dataclasses import replace

    from dgate.readiness.content import Programme, Rule

    def rule(code, obligation, requirement, condition):
        return Rule(programme="T", code=code, title=code, obligation=obligation, kind="registration", requirement=requirement,
                    applies_when=None, condition=condition, conditional_when=None,
                    texts={"met": "m", "not_met": "n", "unknown": "u", "info": "i"}, note=None, denominator=None,
                    source_url="https://example.test", source_ref="r", source_text="[r] t", text_origin="primary",
                    status="V", last_reviewed="2026-10-17")
    test = Programme(code="T", name="T", summary="s", kind="programme", legal_basis=None, source_url="https://example.test",
                     call_programme=None, last_reviewed="2026-10-17", rules=(
        rule("NEEDS-AQAP", "mandatory", "REQ-AQAP2110", {"status": "REQ-AQAP2110", "in": ["held"]}),
        rule("MAYBE-ISO", "conditional", "REQ-ISO9001", None)))
    content = replace(CONTENT, programmes={**CONTENT.programmes, "T": test})
    a = assess(UA, {}, test)
    plan = roadmap.build_roadmap([a], {}, content, "UA")
    steps = {s["code"]: s for s in plan["steps"]}
    assert not steps["REQ-AQAP2110"]["optional"] and not steps["REQ-ISO9001"]["optional"]
    assert steps["REQ-AQAP2110"]["blockingFor"] == ["T"] and steps["REQ-ISO9001"]["blockingFor"] == []
    assert [s["code"] for s in plan["steps"]] == ["REQ-ISO9001", "REQ-AQAP2110"]
    assert plan["totals"]["days"] == {"min": 90, "max": 240}              # the ISO 9001 step first, then the cycle


# --------------------------------------------------------------------- the cross-layer question

def timing(profile, statuses, programme, days_left):
    a = assess(profile, statuses, CONTENT.programmes[programme])
    plan = roadmap.build_roadmap([a], statuses, CONTENT, profile.country)
    deadline = None if days_left is None else NOW + timedelta(days=days_left)
    return roadmap.call_timing(a, plan, deadline, NOW)


def test_call_timing_yes_when_the_slowest_path_fits():
    t = timing(PL, {}, "EDF", 42)
    assert t["realistic"] == "yes" and t["steps"] == ["REQ-PIC"] and t["fastestPathDays"] == {"min": 0, "max": 0}
    assert t["daysLeft"] == 42.0
    # U8: a PIC is issued at once, so the sentence must not say "up to 0 days".
    assert "0 days" not in t["text"] and t["text"].startswith("The missing steps need no time;")


def test_call_timing_when_nothing_is_missing_you_can_apply_now():
    t = timing(PL, {"REQ-PIC": "held"}, "EDF", 3)
    assert t["realistic"] == "yes" and t["text"].startswith("No blocking rule is open")


def test_call_timing_is_not_a_yes_while_a_condition_is_open_even_if_the_steps_fit():
    # V2-B2: the Ukrainian company's PIC takes no time, but the EU-Ukraine association agreement is not confirmed
    t = timing(UA, {}, "EDF", 42)
    assert t["realistic"] == "depends" and t["steps"] == ["REQ-PIC"] and "not a plain yes" in t["text"]
    t = timing(UA, {"REQ-PIC": "held"}, "EDF", 3)
    assert t["realistic"] == "depends" and t["verdict"] == "conditional"


def test_call_timing_maybe_and_no_for_a_certificate_that_takes_weeks():
    # NCAGE: 5 to 20 days
    assert timing(UA, {}, "NATO-SUPPLY", 10)["realistic"] == "maybe"
    assert timing(UA, {}, "NATO-SUPPLY", 30)["realistic"] == "yes"
    t = timing(UA, {}, "NATO-SUPPLY", 2)
    assert t["realistic"] == "no" and t["fastestPathDays"] == {"min": 5, "max": 20}
    assert "at least 5 days" in t["text"]


def test_call_timing_not_possible_when_a_rule_no_certificate_fixes_is_open():
    t = timing(UA, {}, "EDIP", 100)
    assert t["realistic"] == "not_possible"
    assert {n["rule"] for n in t["notFixable"]} == {"EDIP-ESTABLISH", "EDIP-EXEC-MGMT"}
    assert "EDIP-PIC" not in {n["rule"] for n in t["notFixable"]}
    assert t["steps"] == ["REQ-PIC"]


def test_call_timing_depends_when_only_a_guarantee_or_an_answer_is_missing():
    controlled = Profile(country="ES", executive_management_country="ES", third_country_control="other")
    t = timing(controlled, {"REQ-PIC": "held"}, "EDF", 30)
    assert t["verdict"] == "conditional" and t["realistic"] == "depends" and t["steps"] == []


def test_wp42_r1_a_company_outside_ukraine_is_never_told_it_can_apply_now_to_a_ukraine_support_instrument_call():
    # calls 118 and 113 (18 October 2026): the call document needs a Ukrainian applicant or partner; the answers of the profile cannot say.
    # WP-53 (T21): without the answer about a Ukrainian partner the answer is missing; with "no" the condition is open; with "yes" it is met
    t = timing(PL, {"REQ-PIC": "held"}, "EDIP-USI", 20)
    assert t["verdict"] == "conditional" and t["realistic"] == "depends"
    assert "you can apply now" not in t["text"] and t["text"] == "No certificate is missing, but a guarantee or an answer is still needed."
    t = timing(replace(PL, ua_partner=False), {"REQ-PIC": "held"}, "EDIP-USI", 20)
    assert t["verdict"] == "conditional" and t["realistic"] == "depends"
    assert "you can apply now" not in t["text"] and t["openConditions"] == ["The action involves Ukraine"]
    assert t["text"] == "No certificate is missing, but a condition is still open: The action involves Ukraine."
    # with the PIC still to obtain the steps fit, and the same condition keeps it from a plain yes, by name
    t = timing(replace(PL, ua_partner=False), {}, "EDIP-USI", 20)
    assert t["realistic"] == "depends" and "(The action involves Ukraine)" in t["text"] and "not a plain yes" in t["text"]
    # a Ukrainian partner named, a PL company holding its PIC may apply now
    t = timing(replace(PL, ua_partner=True), {"REQ-PIC": "held"}, "EDIP-USI", 20)
    assert t["verdict"] == "eligible" and t["realistic"] == "yes" and t["openConditions"] == []
    # the Ukrainian company that holds its PIC is the one that may apply now
    t = timing(UA, {"REQ-PIC": "held"}, "EDIP-USI", 20)
    assert t["verdict"] == "eligible" and t["realistic"] == "yes" and t["openConditions"] == []
    assert t["text"].startswith("No blocking rule is open")


def test_call_timing_after_the_deadline_is_closed_whatever_the_rules_say():
    t = timing(UA, {}, "EDF", -3)
    assert t["realistic"] == "closed" and t["text"] == "The deadline has passed." and t["daysLeft"] == -3.0
    assert timing(UA, {}, "EDIP", -1)["realistic"] == "closed"


def test_call_timing_without_a_deadline_is_unknown():
    assert timing(UA, {}, "EDF", None)["realistic"] == "unknown"


# --------------------------------------------------------------------- the real-world checks of the rules

@pytest.mark.parametrize("country,expected", [
    ("ES", "eligible"), ("PL", "eligible"), ("NO", "eligible"),
    ("UA", "conditional"),           # Ukraine's association to the EDF is not confirmed (V2-B2)
    ("GB", "blocked"), ("XX", "blocked"), ("CH", "blocked"), ("TR", "blocked"), ("US", "blocked"),
])
def test_edf_establishment_by_country(country, expected):
    p = co(country)
    assert assess(p, {"REQ-PIC": "held"}, CONTENT.programmes["EDF"]).verdict == expected


@pytest.mark.parametrize("country,expected", [
    ("ES", "eligible"), ("NO", "conditional"), ("UA", "blocked"), ("GB", "blocked")])
def test_edip_programme_establishment_by_country(country, expected):
    p = co(country)
    assert assess(p, {"REQ-PIC": "held"}, CONTENT.programmes["EDIP"]).verdict == expected


@pytest.mark.parametrize("country,expected", [
    ("ES", "conditional"), ("UA", "eligible"), ("NO", "blocked"), ("GB", "blocked")])     # WP-42 R1: a Ukrainian applicant or partner is needed
def test_edip_ukraine_support_instrument_establishment_by_country(country, expected):
    p = co(country, ua_non_government_controlled_area=False)
    assert assess(p, {"REQ-PIC": "held"}, CONTENT.programmes["EDIP-USI"]).verdict == expected


def test_usi_excludes_a_company_in_a_non_government_controlled_area_of_ukraine():
    p = co("UA", ua_non_government_controlled_area=True)
    a = assess(p, {"REQ-PIC": "held"}, CONTENT.programmes["EDIP-USI"])
    assert a.verdict == "blocked" and a.blocking == ("USI-TERRITORY",)


def test_control_by_a_third_country_is_conditional_where_the_regulation_has_a_derogation_and_blocked_where_it_has_none():
    def verdict(country, programme):
        p = co(country, third_country_control="other", ua_non_government_controlled_area=False, non_eu_component_cost_pct=0)
        return assess(p, {"REQ-PIC": "held"}, CONTENT.programmes[programme]).verdict
    assert verdict("ES", "EDF") == verdict("ES", "EDIP") == verdict("ES", "EDIP-USI") == verdict("ES", "SAFE") == "conditional"
    # the Ukraine Support Instrument and SAFE give the exception to an entity established in the Union only
    assert verdict("UA", "EDIP-USI") == "blocked" and verdict("UA", "SAFE") == "blocked"
    assert verdict("UA", "EDF") == "conditional"          # EDF Article 9(4): any entity in the Union or an associated country (and Ukraine's association is not confirmed)


def test_control_from_ukraine_or_an_eea_efta_state_does_not_count_under_safe_but_needs_a_check_under_edf_edip_and_usi():
    p = co("ES", third_country_control="ua_eea_only", ua_non_government_controlled_area=False, non_eu_component_cost_pct=0)
    assert assess(p, {"REQ-PIC": "held"}, CONTENT.programmes["SAFE"]).verdict == "eligible"
    # EDF: an EEA EFTA state is an associated country, Ukraine only if its association agreement applies (not confirmed, V2-B2).
    # EDIP: Ukraine is a non-associated country; an EEA EFTA state is associated only if it applies the Regulation.
    # The answer cannot tell the two apart, so it is a condition to check, not a pass and not a block.
    for programme in ("EDF", "EDIP", "EDIP-USI"):
        assert assess(p, {"REQ-PIC": "held"}, CONTENT.programmes[programme]).verdict == "conditional", programme


def test_safe_threshold_and_exclusion_are_separate_rules():
    def safe(pct, restricted):
        p = co("PL", non_eu_component_cost_pct=pct, restricted_third_country_component=restricted)
        a = assess(p, {}, CONTENT.programmes["SAFE"])
        return a.verdict, a.blocking, a.incomplete
    assert safe(35, False) == ("eligible", (), False)                       # not higher than 35 %
    assert safe(35.5, False) == ("blocked", ("SAFE-ORIGIN-35",), False)
    assert safe(0, True) == ("blocked", ("SAFE-NO-RESTRICTED",), False)     # the 35 % allowance does not cover it
    assert safe(80, True) == ("blocked", ("SAFE-ORIGIN-35", "SAFE-NO-RESTRICTED"), False)
    assert safe(None, None) == ("conditional", (), True)                    # unanswered is not "no"


def test_unanswered_questions_are_listed_with_the_question_to_ask():
    a = assess(Profile(country="ES"), {}, CONTENT.programmes["SAFE"])
    assert a.incomplete and a.verdict == "conditional"
    assert set(a.missing) == {"safe_role", "executive_management_country", "third_country_control",
                              "non_eu_component_cost_pct", "restricted_third_country_component"}
