"""WP-64: the verified Spain, Germany and NATO/EU rules of docs/research/ANGLE1_RULES_ES_DE_2026-10-20.md in the readiness seed.

What is checked: every quote is verbatim from the research table, the rows built and the ones left out, the six corrections,
"unknown" (with the question) for what the questionnaire does not ask, the "consultant needed" flags, the PECAL
chicken-and-egg as a roadmap step and not a block, and the foreign-capital check of RD 679/2014 art. 13.3.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from dgate.readiness import api, engine, roadmap
from dgate.readiness.engine import Profile
from dgate.readiness.seed import SEED_PATH, load_file

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = (ROOT / "docs" / "research" / "ANGLE1_RULES_ES_DE_2026-10-20.md").read_text(encoding="utf-8")
RAW = json.loads(SEED_PATH.read_text(encoding="utf-8"))
CONTENT = load_file()

ES_ROUTE = {"ES-RID", "ES-NATO-DOE", "ES-PECAL-CONTRACT", "ES-AOC-CLAUSE", "ES-PECAL-CERT", "ES-PECAL-ISO", "ES-HSEM", "ES-HSES",
            "ES-HSEM-ISSUER", "ES-NSFCC", "ES-ONS-ROLE", "ES-NCAGE", "ES-CATALOG-CLAUSE", "ES-HOMOLOG", "ES-EXPORT-MIL",
            "ES-FOREIGN-CAPITAL", "ES-LGTC", "ES-CERTIFIED-RECIPIENT", "ES-MOD-EXPORT-ROLE", "Q-ISO9001-FILTER", "Q-EN9100-FILTER"}
GENERAL = {"DE-GHB-ADMISSION", "DE-GHB-COST", "DE-GHB-BID", "DE-VSNFD", "DE-SIBE", "DE-SUE", "DE-EXPORT-BAFA",
           "EU-CERTIFIED-RECIPIENT", "EU-DUALUSE-EXPERT"}
NATO = {"NATO-AQAP-ED"}

ES_AUTO = Profile(country="ES", legal_form="legal_person", executive_management_country="ES", third_country_control="no",
                  non_eu_component_cost_pct=15, restricted_third_country_component=False, components_from_ua_or_eea_efta=False,
                  safe_role="other_supplier", applicant_kind="company_or_research", handles_classified=False,
                  product_regime="none", export_intent="within_eu")


def research_ids() -> list[str]:
    return [line.strip("|").split(" | ")[0].strip().split(" ")[0] for line in RESEARCH.splitlines()
            if line.startswith("| ") and not line.startswith(("| id", "|---"))]


def rule(code: str, programme: str | None = None):
    found = [r for p in CONTENT.programmes.values() for r in p.rules if r.code == code and (programme is None or p.code == programme)]
    return found[0]


def answer(profile: Profile, statuses: dict[str, str]):
    return api.assess_payload(CONTENT, profile, statuses)


def result(payload, code: str):
    return next(r for a in [*payload["assessments"], *payload["general"]] for r in a["rules"] if r["rule"] == code)


# --------------------------------------------------------------------------- content

def test_the_research_table_has_33_rows_and_32_are_built_the_iatf_row_is_not():
    ids = research_ids()
    assert len(ids) == 33
    built = {r.code for p in CONTENT.programmes.values() for r in p.rules}
    # ES-REOCE is the upgrade of the existing G-REOCE (correction 2); the research says not to build Q-IATF16949
    assert set(ids) - built == {"ES-REOCE", "Q-IATF16949"}
    assert "G-REOCE" in built
    # IATF 16949 is named only as unverified, never as a requirement or a condition
    assert not [r for r in RAW["requirements"] if "IATF" in r["name"]]
    assert not [r for r in RAW["rules"] if "IATF" in json.dumps([r.get("applies_when"), r["condition"], r["title"]])]
    assert "UNVERIFIED: ISO 9001 or IATF 16949" in rule("Q-ISO9001-FILTER").note


def test_the_rules_are_grouped_in_the_spanish_route_and_the_general_rules():
    es = CONTENT.programmes["ES-MOD"]
    assert (es.name, es.kind) == ("Spanish defence supplier (MoD)", "route")
    assert {r.code for r in es.rules} == ES_ROUTE
    assert GENERAL <= {r.code for r in CONTENT.programmes["GENERAL"].rules}
    assert NATO <= {r.code for r in CONTENT.programmes["NATO-SUPPLY"].rules}
    for code in ES_ROUTE:
        assert "ES" in json.dumps(rule(code).applies_when), code       # a rule of the route is for companies in Spain


def test_every_new_quote_is_verbatim_from_the_research_table_with_source_and_date():
    new = [r for r in RAW["rules"] if r["code"] in ES_ROUTE | GENERAL | NATO]
    new += [r for r in RAW["requirements"] if r["code"] in ("REQ-RID", "REQ-PECAL", "REQ-HSES-ES")]
    assert len(new) == 34
    for r in new:
        assert r["source_url"].startswith("http") and r["verification_status"] in ("V", "S"), r["code"]
        assert r["last_reviewed"] in ("2026-10-20", "2026-10-17"), r["code"]
        for p in r["passages"]:
            assert p["text"] in RESEARCH, (r["code"], p["text"][:60])
    # the one rule the research rates S (the scope of "actividades relacionadas con la Defensa Nacional")
    assert rule("ES-FOREIGN-CAPITAL").status == "S"


def test_nothing_unconfirmed_is_seeded_as_a_fact():
    text = SEED_PATH.read_text(encoding="utf-8")
    assert "181.50" not in text and "181,50" not in text                     # RID fee: a regional guide only (item 1)
    for code in ("REQ-RID", "REQ-PECAL", "REQ-HSES-ES"):                     # no fee, time or validity (items 1-3)
        r = CONTENT.requirements[code]
        assert r.cost is None and r.days is None and "UNVERIFIED" in (r.description or ""), code
    assert "NSPA Source File" not in text                                    # item 5
    assert not re.search(r"renew\w* every (?:3|three) years", text.split('"code": "REQ-PECAL"')[1][:4000])   # item 2
    # item 11: a domestic sale to a Spanish prime is not said to need no licence
    na = rule("ES-EXPORT-MIL").texts["not_applicable"]
    assert "leaves Spain" in na and "domestic" not in na.lower()
    assert "UNVERIFIED" in rule("ES-EXPORT-MIL").note


def test_the_six_corrections():
    # 1. the HSEM issuer depends on whose information it is
    issuers = [i.name for i in CONTENT.issuers_for("REQ-FSC-ES", "ES")]
    assert issuers[0].startswith("Dirección General de Armamento y Material") and issuers[1].startswith("Oficina Nacional de Seguridad")
    g = rule("G-HSEM")
    assert "DGAM" in g.texts["not_met"] and "NATO, EU and ESA" in g.texts["not_met"] and g.text_origin == "primary"
    assert "FSCIS" not in CONTENT.requirements["REQ-FSC-ES"].source_text
    # 2. REOCE upgraded to Ley 53/2007 art. 12
    for r in (rule("G-REOCE"), CONTENT.requirements["REQ-REOCE"]):
        assert r.text_origin == "primary" and r.source_url == "https://www.boe.es/eli/es/l/2007/12/28/53/con"
        assert "Registro Especial de Operadores de Comercio Exterior de Material de Defensa y de Doble Uso" in r.source_text
    # 3. NATO-AQAP: verified for Spain through ES-PECAL-CONTRACT
    assert "ES-PECAL-CONTRACT" in rule("NATO-AQAP").note and rule("ES-PECAL-CONTRACT").status == "V"
    # 4. ISO 9001 / EN 9100 formal on the PECAL route
    assert "PA 4302" in CONTENT.requirements["REQ-ISO9001"].mandatory_for
    assert "PA 4302" in CONTENT.requirements["REQ-EN9100"].mandatory_for
    assert ("REQ-ISO9001", "before") in CONTENT.requirements["REQ-PECAL"].prerequisites
    # 5. NCAGE Spain: a justified need, not "an existing supply contract"
    (ncage,) = CONTENT.issuers_for("REQ-NCAGE", "ES")
    assert "existing supply contract" not in ncage.notes and "justified" in ncage.notes and "SAM" in ncage.notes
    # 6. AQAP 2310 edition as Spain lists it, and AQAP-2131
    assert "Versión 1" in CONTENT.requirements["REQ-AQAP2310"].description
    assert "AQAP-2131 Ed. C V1" in rule("NATO-AQAP-ED").texts["info"]


# --------------------------------------------------------------------------- engine

def test_a_requirement_the_questionnaire_does_not_ask_is_unknown_with_its_question():
    payload = answer(ES_AUTO, {"REQ-ISO9001": "held"})
    rid = result(payload, "ES-RID")
    assert rid["outcome"] == "unknown"
    assert rid["asks"] == [{"field": "REQ-RID", "question": "Does the company hold a current RID certificate (registration or renewal)?"}]
    es = next(a for a in payload["assessments"] if a["programme"] == "ES-MOD")
    assert es["verdict"] == "conditional" and es["incomplete"]
    # said: held is met, not held is a registration to obtain (not a block)
    assert result(answer(ES_AUTO, {"REQ-RID": "held"}), "ES-RID")["outcome"] == "met"
    held_not = answer(ES_AUTO, {"REQ-RID": "not_held"})
    assert result(held_not, "ES-RID")["outcome"] == "to_obtain"
    assert "REQ-RID" in [s["code"] for s in held_not["roadmap"]["steps"]]
    # the engine alone: the sentinel reads as unknown, a code that is not unasked still defaults to "not held"
    assert engine.evaluate({"status": "REQ-RID", "is": "held"}, {}, {"REQ-RID": engine.STATUS_UNKNOWN}) is None
    assert engine.evaluate({"status": "REQ-PIC", "is": "held"}, {}, engine.with_unasked({}, ["REQ-RID"])) is False
    assert engine.with_unasked({"REQ-RID": "held"}, ["REQ-RID", "REQ-PECAL"]) == {"REQ-RID": "held", "REQ-PECAL": "unknown"}


def test_an_unasked_registration_is_a_roadmap_step_to_mark_as_done():
    steps = {s["code"]: s for s in answer(ES_AUTO, {"REQ-ISO9001": "held"})["roadmap"]["steps"]}
    assert steps["REQ-RID"]["optional"] is False and steps["REQ-RID"]["blockingFor"] == ["ES-MOD"]
    assert steps["REQ-RID"]["cost"] is None and steps["REQ-RID"]["issuers"][0]["name"].startswith("Dirección General de Estrategia")


def test_a_company_outside_spain_does_not_see_the_spanish_route():
    pl = dataclasses.replace(ES_AUTO, country="PL", executive_management_country="PL")
    assert "ES-MOD" not in [a["programme"] for a in answer(pl, {})["assessments"]]
    assert "ES-MOD" in [a["programme"] for a in answer(ES_AUTO, {})["assessments"]]


def test_the_pecal_chicken_and_egg_is_a_roadmap_item_and_not_a_block():
    newcomer = dataclasses.replace(ES_AUTO, pecal_certificate_wanted=True, pecal_system_9_months=False, pecal_prior_contract=False)
    payload = answer(newcomer, {"REQ-RID": "held", "REQ-ISO9001": "held"})
    cert = result(payload, "ES-PECAL-CERT")
    assert cert["outcome"] == "conditional" and cert["obligation"] == "conditional"
    assert "does not stop you from bidding" in cert["reason"]
    es = next(a for a in payload["assessments"] if a["programme"] == "ES-MOD")
    assert es["verdict"] != "blocked" and "ES-PECAL-CERT" not in es["blocking"]
    # no RID and no ISO 9001: not met, and the roadmap orders RID and ISO 9001 before the PECAL step
    payload = answer(newcomer, {})
    assert result(payload, "ES-PECAL-CERT")["outcome"] == "not_met"
    steps = {s["code"]: s for s in payload["roadmap"]["steps"]}
    pecal = steps["REQ-PECAL"]
    assert "nine months" in pecal["note"] and "not a block before a first contract" in pecal["note"]
    assert steps["REQ-RID"]["order"] < pecal["order"] and steps["REQ-ISO9001"]["order"] < pecal["order"]
    assert pecal["blockingFor"] == [] and pecal["priceNote"]          # the state route: no vendor price
    # every condition of PA 4302 met: eligible to apply
    ready = dataclasses.replace(newcomer, pecal_system_9_months=True, pecal_prior_contract=True)
    assert result(answer(ready, {"REQ-RID": "held", "REQ-EN9100": "held"}), "ES-PECAL-CERT")["outcome"] == "met"
    # a company that did not say it wants the certificate: the step is still there, as a contract matter
    plain = {s["code"]: s for s in answer(ES_AUTO, {"REQ-ISO9001": "held"})["roadmap"]["steps"]}
    assert plain["REQ-PECAL"]["optional"] and plain["REQ-PECAL"]["when"] == "when a contract names it"


@pytest.mark.parametrize("control,capital,authorised,outcome", [
    ("no", None, None, "unknown"),
    ("no", False, None, "not_applicable"),
    ("no", True, None, "unknown"),
    ("no", True, True, "met"),
    ("no", True, False, "not_met"),
    ("other", None, False, "not_met"),
    ("ua_eea_only", None, None, "unknown"),
])
def test_foreign_capital_needs_the_council_of_ministers_authorisation(control, capital, authorised, outcome):
    p = dataclasses.replace(ES_AUTO, third_country_control=control, foreign_capital=capital, foreign_investor_authorised=authorised)
    r = result(answer(p, {}), "ES-FOREIGN-CAPITAL")
    assert r["outcome"] == outcome
    assert (r["consultant"] is not None) == (outcome not in ("met", "not_applicable"))
    if outcome == "not_met":
        assert "Council of Ministers" in r["reason"] and "RD 664/1999" in r["consultant"]
    if (control, capital) == ("no", None):
        assert [a["field"] for a in r["asks"]] == ["foreign_capital", "foreign_investor_authorised"]


def test_consultant_flags_for_export_classification_us_components_hses_and_prime_qualification():
    p = dataclasses.replace(ES_AUTO, product_regime="military", export_intent="outside_eu", es_defence_material_list="unsure",
                            handles_classified=True, stores_classified=True)
    payload = answer(p, {"REQ-FSC-ES": "held"})
    keys = [f["key"] for f in payload["consultants"]]
    assert {"ES-EXPORT-MIL", "ES-HSES", "ES-PECAL-CONTRACT", "US-COMPONENTS"} <= set(keys)
    mil = result(payload, "ES-EXPORT-MIL")
    assert mil["outcome"] == "conditional" and "Annex I of Real Decreto 679/2014" in mil["consultant"]
    assert "HSES path" in result(payload, "ES-HSES")["consultant"]
    assert "Prime qualification" in result(payload, "ES-PECAL-CONTRACT")["consultant"]
    us = next(f for f in payload["consultants"] if f["key"] == "US-COMPONENTS")
    assert us["rule"] is None and us["asks"][0]["field"] == "us_components" and "ITAR" in us["text"]
    # said yes: no question; said no: no flag
    assert next(f for f in answer(dataclasses.replace(p, us_components=True), {})["consultants"] if f["key"] == "US-COMPONENTS")["asks"] == []
    assert "US-COMPONENTS" not in [f["key"] for f in answer(dataclasses.replace(p, us_components=False), {})["consultants"]]
    # the item is said not to be in Annex I: the rule does not apply and carries no flag
    no = answer(dataclasses.replace(p, es_defence_material_list="no"), {})
    assert result(no, "ES-EXPORT-MIL")["outcome"] == "not_applicable" and result(no, "ES-EXPORT-MIL")["consultant"] is None
    # dual-use classification (EU) and the German list
    du = dataclasses.replace(ES_AUTO, country="DE", executive_management_country="DE", product_regime="dual_use",
                             export_intent="outside_eu", dualuse_annex_i="unsure", de_ausfuhrliste="unsure")
    out = answer(du, {})
    assert result(out, "EU-DUALUSE-EXPERT")["outcome"] == "conditional" and "2021/821" in result(out, "EU-DUALUSE-EXPERT")["consultant"]
    assert result(out, "DE-EXPORT-BAFA")["outcome"] == "conditional" and "Ausfuhrliste" in result(out, "DE-EXPORT-BAFA")["consultant"]


def test_the_german_rules():
    de = dataclasses.replace(ES_AUTO, country="DE", executive_management_country="DE", handles_classified=True,
                             de_vs_vertraulich=True, ghb_admitted=False)
    out = answer(de, {})
    adm = result(out, "DE-GHB-ADMISSION")
    assert adm["outcome"] == "conditional" and "cannot apply yourself" in adm["reason"]
    assert result(out, "DE-GHB-COST")["outcome"] == "info" and result(out, "DE-GHB-BID")["outcome"] == "info"
    assert result(out, "DE-SIBE")["outcome"] == "unknown"
    assert result(answer(dataclasses.replace(de, ghb_admitted=True, sibe_appointed=True), {}), "DE-SIBE")["outcome"] == "met"
    assert "79" in rule("DE-SUE").texts["info"] and "not a legal deadline" in rule("DE-SUE").texts["info"]
    # part I B goes out of the EU: a licence; inside the EU only part I A needs one
    b = dataclasses.replace(de, de_ausfuhrliste="part_i_b", export_intent="within_eu")
    assert result(answer(b, {}), "DE-EXPORT-BAFA")["outcome"] == "not_applicable"
    a = dataclasses.replace(de, de_ausfuhrliste="part_i_a", export_intent="within_eu")
    assert result(answer(a, {}), "DE-EXPORT-BAFA")["outcome"] == "not_met"
    assert result(answer(a, {"REQ-EXPORT": "held"}), "DE-EXPORT-BAFA")["outcome"] == "met"
    # Germany is now collected: the "other countries" line no longer applies to it
    assert result(out, "G-CLASSIFIED-OTHER")["outcome"] == "not_applicable"


def test_the_api_takes_the_new_answers_and_names_their_questions():
    body = api.AssessIn.model_validate({"profile": {"country": "ES", "us_components": True, "es_defence_material_list": "unsure",
                                                    "de_ausfuhrliste": "part_i_a"}, "statuses": {"REQ-RID": "held"}})
    assert body.profile.to_engine().us_components is True
    with pytest.raises(ValueError):
        api.AssessIn.model_validate({"profile": {"country": "ES", "es_defence_material_list": "maybe"}})
    for name in engine.SUPPLIER_FIELDS:
        assert name in api.ProfileIn.model_fields and engine.FIELDS[name]["label"].endswith("?"), name
    assert set(api.unasked(CONTENT)) == {"REQ-RID", "REQ-PECAL", "REQ-HSES-ES"}
    assert api.question(CONTENT, "REQ-PECAL").endswith("?") and api.question(CONTENT, "country") == engine.FIELDS["country"]["label"]


def test_the_roadmap_step_carries_the_seed_note():
    plan = roadmap.build_roadmap([], {}, CONTENT, "ES")
    assert plan["steps"] == []
    assert CONTENT.requirements["REQ-PECAL"].extras["roadmap_note"].startswith("The chicken-and-egg of PECAL")


def test_a_roadmap_step_says_where_its_text_and_figures_come_from():
    # WP-67: the supplier report prints a cost or a time only when the requirement's source is primary
    steps = {s["code"]: s for s in answer(ES_AUTO, {})["roadmap"]["steps"]}
    assert steps["REQ-RID"]["origin"] == "primary"
    assert steps["REQ-NCAGE"]["origin"] == "notes" and steps["REQ-NCAGE"]["cost"]["basis"] == "free"
    assert all(s["origin"] == CONTENT.requirements[c].text_origin for c, s in steps.items())
