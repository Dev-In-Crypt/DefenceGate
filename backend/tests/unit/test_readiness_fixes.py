"""WP-33: one test group per defect of docs/verification/product/verify-readiness.md (D1 to D12).

The verdicts of whole profiles are in test_readiness_profiles.py; these tests pin the pieces: the rules that were
missing, the words they print, the issuer table, the roadmap prices. Each fails on the code before WP-33.
"""

from __future__ import annotations

import copy
import json
import re

import pydantic
import pytest

from dgate.readiness import seed
from dgate.readiness.api import COUNTRY_ALIASES, ISO_COUNTRIES, ProfileIn
from dgate.readiness.engine import Profile, assess
from dgate.readiness.seed import load_file

CONTENT = load_file()
RAW = json.loads(seed.SEED_PATH.read_text(encoding="utf-8"))
RULES = {r.code: r for p in CONTENT.programmes.values() for r in p.rules}
NATO = ("AL BE BG CA HR CZ DK EE FI FR DE GR HU IS IT LV LT LU ME NL MK NO PL PT RO SK SI ES SE TR GB US").split()
TIER2 = "AE AR AU AT BR CO GE IN ID IL JO JP KR MY MA NZ RS SG QA".split()


def clean(**kw):
    base = dict(country="FR", legal_form="legal_person", executive_management_country="FR", third_country_control="no",
                non_eu_component_cost_pct=10, restricted_third_country_component=False, components_from_ua_or_eea_efta=False,
                safe_role="contractor")
    base.update(kw)
    return Profile(**base)


def outcome(code, programme, profile, statuses=None):
    a = assess(profile, statuses or {}, CONTENT.programmes[programme])
    return next(r.outcome for r in a.rules if r.rule == code)


# --------------------------------------------------------------------------- D1: EDIP and USI have an origin rule

def test_d1_edip_and_usi_have_the_35_percent_and_the_categorical_rules_with_the_articles_own_wording():
    for code, programme, art in (("EDIP-ORIGIN-35", "EDIP", "Article 10"), ("USI-ORIGIN-35", "EDIP-USI", "Article 27")):
        rule = RULES[code]
        assert rule.programme == programme and rule.obligation == "mandatory" and rule.kind == "threshold"
        assert art in rule.source_ref and "35 %" in rule.source_text
        assert "estimated cost of the components of the end product" in rule.source_text
    assert "outside the Union and associated countries" in RULES["EDIP-ORIGIN-35"].source_text
    assert "outside the Union and Ukraine" in RULES["USI-ORIGIN-35"].source_text
    for code in ("EDIP-NO-RESTRICTED", "USI-NO-RESTRICTED"):
        assert RULES[code].kind == "categorical"
        assert "contravene the security and defence interests of the Union and its Member States" in RULES[code].source_text


def test_d1_the_edip_and_usi_denominators_differ_from_safes_and_a_possibly_wrong_pass_is_never_given():
    # Ukraine is outside under EDIP and inside under USI; an EEA EFTA state the other way round; SAFE has neither outside.
    for programme, code in (("EDIP", "EDIP-ORIGIN-35"), ("EDIP-USI", "USI-ORIGIN-35")):
        assert outcome(code, programme, clean(non_eu_component_cost_pct=35)) == "met"
        assert outcome(code, programme, clean(non_eu_component_cost_pct=35.01)) == "not_met"
        assert outcome(code, programme, clean(non_eu_component_cost_pct=20, components_from_ua_or_eea_efta=True)) == "conditional"
        assert outcome(code, programme, clean(non_eu_component_cost_pct=60, components_from_ua_or_eea_efta=True)) == "not_met"
        assert outcome(code, programme, clean(non_eu_component_cost_pct=20, components_from_ua_or_eea_efta=None)) == "unknown"
        assert outcome(code, programme, clean(non_eu_component_cost_pct=None, components_from_ua_or_eea_efta=False)) == "unknown"
    assert outcome("SAFE-ORIGIN-35", "SAFE", clean(non_eu_component_cost_pct=20, components_from_ua_or_eea_efta=True)) == "met"


def test_d1_the_edip_subcontractor_allowance_and_the_ukraine_involvement_are_information_lines():
    relief = RULES["EDIP-SUBCONTRACT-RELIEF"]
    assert relief.condition is None and relief.obligation == "conditional" and "Article 11(7)" in relief.source_ref
    assert "between 15 % and 35 %" in relief.source_text and "29 December 2025" in relief.texts["info"]
    ukraine = RULES["USI-INVOLVES-UA"]
    assert ukraine.condition is None and "Article 27(7)" in ukraine.source_ref
    assert "with the involvement of, at a minimum, Ukraine" in ukraine.source_text


# --------------------------------------------------------------------------- D2: legal entity

def test_d2_a_legal_entity_rule_for_edf_edip_and_usi_and_none_for_safe():
    for code, programme in (("EDF-LEGAL-ENTITY", "EDF"), ("EDIP-LEGAL-ENTITY", "EDIP"), ("USI-LEGAL-ENTITY", "EDIP-USI")):
        rule = RULES[code]
        assert rule.programme == programme and rule.obligation == "mandatory"
        assert "a legal person created and recognised as such" in rule.source_text
        assert "(b) natural persons" in rule.source_text and "(c) entities which do not have legal personality" in rule.source_text
        assert outcome(code, programme, clean(legal_form="legal_person")) == "met"
        # V2-B4: the call documents allow self-employed persons, i.e. sole traders, whose company has no separate legal personality
        assert outcome(code, programme, clean(legal_form="natural_person")) == "conditional"
        conditional = next(r for r in CONTENT.programmes[programme].rules if r.code == code).texts["conditional"]
        assert "sole traders" in conditional and "Natural persons are NOT eligible (with the exception of self-employed persons" in conditional
        assert outcome(code, programme, clean(legal_form="no_legal_personality")) == "conditional"
        assert outcome(code, programme, clean(legal_form=None)) == "unknown"
    assert not [r for r in CONTENT.programmes["SAFE"].rules if r.condition and "legal_form" in json.dumps(r.condition)]


# --------------------------------------------------------------------------- D4: NCAGE issuers

def test_d4_every_nato_member_and_tier_2_country_has_a_national_bureau_row_and_no_one_is_sent_to_nspa_wrongly():
    assert len(NATO) == 32 and len(set(NATO)) == 32
    for country in NATO + TIER2:
        rows = CONTENT.issuers_for("REQ-NCAGE", country)
        assert rows and rows[0].country == country, country
        assert "NSPA" not in rows[0].name, country
    # a country that is neither: NSPA, which the row says
    for country in ("CH", "CN", "BY", "XX"):
        (row,) = CONTENT.issuers_for("REQ-NCAGE", country)
        assert row.country == "*" and row.name.startswith("NSPA")
    # the rows carry the status the appendix allows: the routing rule is known, the bureau's name is not
    assert CONTENT.issuers_for("REQ-NCAGE", "IT")[0].status == "U" and CONTENT.issuers_for("REQ-NCAGE", "ES")[0].status == "V"


# --------------------------------------------------------------------------- D5: SAFE roles

def test_d5_the_safe_rules_bind_the_contractor_and_the_subcontractors_involved_not_every_supplier():
    for code in ("SAFE-ESTABLISH", "SAFE-EXEC-MGMT", "SAFE-CONTROL"):
        rule = RULES[code]
        assert rule.applies_when == {"field": "safe_role", "in": ["contractor", "subcontractor_involved"]}
        assert "‘subcontractors involved in the common procurement’ means any legal entity which provides critical inputs" in rule.source_text
        assert "at least 15 % of the value of the contract" in rule.source_text
        assert "not_applicable" in rule.texts and "does not bind you" in rule.texts["not_applicable"]
        assert "every subcontractor" not in json.dumps(rule.texts)
    far = clean(country="US", executive_management_country="US")
    for role, expected in (("contractor", "not_met"), ("subcontractor_involved", "not_met"), ("other_supplier", "not_applicable"), (None, "unknown")):
        assert outcome("SAFE-ESTABLISH", "SAFE", Profile(**{**far.fields(), "safe_role": role})) == expected
    # the origin rules concern the end product and stay for every role
    assert outcome("SAFE-ORIGIN-35", "SAFE", Profile(**{**clean().fields(), "safe_role": "other_supplier", "non_eu_component_cost_pct": 40})) == "not_met"


# --------------------------------------------------------------------------- D6: export regimes

def export_outcomes(regime, intent, country="PL"):
    p = Profile(country=country, product_regime=regime, export_intent=intent)
    a = assess(p, {}, CONTENT.programmes["GENERAL"])
    return {r.rule: r.outcome for r in a.rules if r.rule.startswith(("G-EXPORT", "G-REOCE"))}


def test_d6_dual_use_goods_moved_inside_the_union_need_no_export_step():
    got = export_outcomes("dual_use", "within_eu")
    assert got["G-EXPORT"] == "not_applicable" and got["G-EXPORT-INTRA-DU"] == "info" and got["G-EXPORT-MIL"] == "not_applicable"
    assert "Annex IV" in RULES["G-EXPORT-INTRA-DU"].texts["info"] and "Annex IV" in RULES["G-EXPORT-INTRA-DU"].source_text
    assert export_outcomes("dual_use", "outside_eu")["G-EXPORT"] == "not_met"
    assert export_outcomes("dual_use", "unsure")["G-EXPORT"] == "not_met"
    assert export_outcomes("dual_use", "none")["G-EXPORT"] == "not_applicable"


def test_d6_military_goods_are_under_the_directive_and_national_law_not_under_the_dual_use_regulation():
    for intent in ("within_eu", "outside_eu", "unsure"):
        got = export_outcomes("military", intent)
        assert got["G-EXPORT"] == "not_applicable" and got["G-EXPORT-MIL"] == "not_met", intent
    assert export_outcomes("military", "none")["G-EXPORT-MIL"] == "not_applicable"
    mil = RULES["G-EXPORT-MIL"]
    assert "The transfer of defence-related products between Member States shall be subject to prior authorisation." in mil.source_text
    assert "Member States’ legislation shall indicate in which case an export licence is required" in mil.source_text
    assert "dual-use" not in mil.source_text


def test_d6_the_spanish_registration_follows_the_licence_it_belongs_to():
    assert export_outcomes("dual_use", "within_eu", "ES")["G-REOCE"] == "not_applicable"
    assert export_outcomes("dual_use", "outside_eu", "ES")["G-REOCE"] == "not_met"
    assert export_outcomes("military", "within_eu", "ES")["G-REOCE"] == "not_met"
    assert export_outcomes("dual_use", "outside_eu", "PL")["G-REOCE"] == "not_applicable"


# --------------------------------------------------------------------------- D7, D9, D12: words

def test_d7_every_rule_with_a_condition_has_a_sentence_that_says_what_it_asks_and_is_not_addressed_to_the_company():
    for code, rule in RULES.items():
        if rule.condition is None:
            continue
        req = rule.texts["requires"]
        # a verdict sentence speaks to the company ("Your company is ...", "You report ..."); a requirement page must not
        assert not re.match(r"(?i)you\b|your\b", req), code
        assert len(req) > 40, code


def test_d7_the_loader_refuses_a_rule_with_a_condition_and_no_requires_sentence():
    raw = copy.deepcopy(RAW)
    next(x for x in raw["rules"] if x["code"] == "EDF-ESTABLISH")["texts"].pop("requires")
    with pytest.raises(seed.SeedError, match="texts.requires"):
        seed.parse(raw)


def test_d9_the_export_page_does_not_claim_a_category_service():
    text = CONTENT.requirements["REQ-EXPORT"].description
    assert "tells you whether a category needs a licence" not in text
    assert "It does not tell you whether a given category needs a licence" in text and "Spain, Germany and Poland" in text


def test_d12_the_subcontractor_relief_says_a_subcontractor_and_gives_the_date():
    info = RULES["SAFE-SUBCONTRACT-RELIEF"].texts["info"]
    assert "include a subcontractor" in info and "one subcontractor" not in info
    assert "28 May 2025" in info and "29 May 2025" in info and "at least one of two conditions" in info


# --------------------------------------------------------------------------- D11: country codes

def test_d11_el_and_uk_are_read_as_greece_and_the_united_kingdom_and_unknown_codes_are_refused():
    assert ProfileIn(country="EL").country == "GR" and ProfileIn(country="UK").country == "GB"
    assert ProfileIn(country="XX", executive_management_country="UK").executive_management_country == "GB"
    for bad in ("ZZ", "AA", "QQ", "EU", "es", "ESP", "1A"):
        with pytest.raises(pydantic.ValidationError):
            ProfileIn(country=bad)
    with pytest.raises(pydantic.ValidationError):
        ProfileIn(country="ES", executive_management_country="ZZ")
    assert len(ISO_COUNTRIES) == 250 and set(COUNTRY_ALIASES) == {"EL", "UK"}      # 249 ISO 3166-1 codes and XX
    from dgate.readiness.engine import EEA_EFTA, EU27
    assert EU27 | EEA_EFTA | {"UA", "GB", "US", "TR", "CH", "XX", "LI"} <= ISO_COUNTRIES


# --------------------------------------------------------------------------- D8: no rule claims more than its origin shows

def test_d8_a_rule_quoted_from_the_research_notes_is_never_described_as_re_read_by_us():
    # the web words depend on text_origin ('notes' or 'primary'); the seed must therefore state it for every line
    for code, rule in RULES.items():
        assert rule.text_origin in {"primary", "notes", "call_document"}, code
    for req in CONTENT.requirements.values():
        assert req.text_origin in {"primary", "notes"}, req.code
    notes_only = [c for c, r in RULES.items() if r.text_origin == "notes"] + [c for c, q in CONTENT.requirements.items() if q.text_origin == "notes"]
    assert len(notes_only) >= 14
