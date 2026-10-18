"""The readiness content (WP-29): every rule has its source, nothing is invented, the file validates.

These tests read the real `seeds/requirements.json`. What they cannot check is that the verbatim
passages are in the sources: `tests/verify_quotes.py` does that against the Official Journal texts and
the technical appendix, by hand, when the seed changes.
"""

from __future__ import annotations

import copy
import json
import re

import pytest

from dgate.readiness import seed
from dgate.readiness.engine import Profile, assess

EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)*\.[A-Z]{2,}", re.I)
RAW = json.loads(seed.SEED_PATH.read_text(encoding="utf-8"))
CONTENT = seed.parse(copy.deepcopy(RAW))


def rules(code: str):
    return [r for p in CONTENT.programmes.values() for r in p.rules if r.code == code]


def test_the_catalogue_has_no_requirement_without_a_source_url_or_a_review_date():
    assert len(CONTENT.requirements) == 12
    for r in CONTENT.requirements.values():
        assert r.source_url.startswith("http"), r.code
        assert r.source_text and r.source_text.startswith("["), r.code
        assert r.status in {"V", "S", "U"} and r.last_reviewed >= "2026-09-07", r.code


def test_every_rule_has_a_source_url_a_reference_a_verbatim_text_and_a_status():
    count = 0
    for p in CONTENT.programmes.values():
        for r in p.rules:
            count += 1
            assert r.source_url.startswith("http"), r.code
            assert r.source_ref and r.source_text.startswith("["), r.code
            assert r.text_origin in {"primary", "notes", "call_document"} and r.status in {"V", "S", "U"}, r.code
    assert count >= 30


def test_the_requirements_of_the_appendix_table_are_all_there_plus_the_two_prerequisites():
    wanted = {"REQ-NCAGE", "REQ-PIC", "REQ-EDF-ELIG", "REQ-SAFE-35", "REQ-EDIP-ELIG", "REQ-AQAP2110",
              "REQ-AQAP2310", "REQ-EXPORT", "REQ-REOCE", "REQ-FSC-ES", "REQ-ISO9001", "REQ-EN9100"}
    assert set(CONTENT.requirements) == wanted


def test_safe_article_16_10_is_two_rules_a_threshold_and_a_categorical_exclusion():
    (threshold,) = rules("SAFE-ORIGIN-35")
    (exclusion,) = rules("SAFE-NO-RESTRICTED")
    assert (threshold.kind, exclusion.kind) == ("threshold", "categorical")
    assert threshold.programme == exclusion.programme == "SAFE"
    assert threshold.obligation == exclusion.obligation == "mandatory"
    assert threshold.condition == {"threshold": {"field": "non_eu_component_cost_pct", "lte": 35}}
    assert exclusion.condition == {"field": "restricted_third_country_component", "is": False}
    assert "Article 16(10)" in threshold.source_ref and "Article 16(10)" in exclusion.source_ref


def test_the_35_percent_is_measured_on_component_cost_not_on_contract_value():
    (threshold,) = rules("SAFE-ORIGIN-35")
    assert threshold.denominator == "the estimated cost of the components of the end product"
    assert "estimated cost of the components of the end product" in threshold.source_text
    assert "estimated cost of the components of the end product" in threshold.texts["met"]
    assert "component_cost" in threshold.condition["threshold"]["field"]
    assert "contract" not in threshold.condition["threshold"]["field"]
    assert "not against the contract value" in threshold.note
    # the one place the contract value does appear is the separate 15-35 % subcontractor allowance
    (relief,) = rules("SAFE-SUBCONTRACT-RELIEF")
    assert relief.obligation == "conditional" and relief.condition is None
    assert "value of the contract" in relief.source_text and "not the 35 % component cost threshold" in relief.texts["info"]


def test_aqap_is_never_an_eligibility_condition_of_edf_edip_or_safe():
    aqap = [r for p in CONTENT.programmes.values() for r in p.rules if r.requirement in {"REQ-AQAP2110", "REQ-AQAP2310"}]
    assert {r.programme for r in aqap} == {"EDF", "EDIP", "EDIP-USI", "SAFE", "NATO-SUPPLY"}
    for r in aqap:
        assert r.obligation == "conditional" and r.condition is None and r.kind == "contract", r.code
        assert "contract" in r.texts["info"], r.code
    for programme in ("EDF", "EDIP", "EDIP-USI", "SAFE", "NATO-SUPPLY"):
        a = assess(Profile(country="ES", legal_form="legal_person", executive_management_country="ES", third_country_control="no",
                           non_eu_component_cost_pct=10, restricted_third_country_component=False,
                           components_from_ua_or_eea_efta=False, safe_role="contractor"),
                   {"REQ-PIC": "held", "REQ-NCAGE": "held"}, CONTENT.programmes[programme])
        # holding no AQAP never blocks; the Ukraine Support Instrument is conditional for a Spanish company for another reason (WP-42 R1)
        assert a.verdict == ("conditional" if programme == "EDIP-USI" else "eligible"), programme
        assert a.blocking == () and a.to_obtain == (), programme


def test_pic_is_mandatory_for_edf_and_edip_and_not_for_safe():
    for programme in ("EDF", "EDIP", "EDIP-USI"):
        (pic,) = [r for r in CONTENT.programmes[programme].rules if r.requirement == "REQ-PIC"]
        assert pic.obligation == "mandatory"
    assert not [r for r in CONTENT.programmes["SAFE"].rules if r.requirement == "REQ-PIC"]


def test_costs_are_vendor_ranges_labelled_with_their_currency_and_nothing_is_converted():
    aqap = CONTENT.requirements["REQ-AQAP2110"]
    assert (aqap.cost.min, aqap.cost.max, aqap.cost.currency, aqap.cost.basis) == (17000, 48000, "USD", "vendor_range")
    assert aqap.cost.alt == {"min": 15700, "max": 44200, "currency": "EUR", "text": aqap.cost.alt["text"]}
    assert (aqap.days.min, aqap.days.max) == (90, 240)
    (iso_held,) = aqap.variants
    assert iso_held.when_held == "REQ-ISO9001"
    assert (iso_held.cost.min, iso_held.cost.max, iso_held.cost.currency) == (17000, 25000, "USD")
    assert (iso_held.days.min, iso_held.days.max) == (90, 120)
    assert "30-40 %" in aqap.extras["without_prerequisite"]["text"]
    for r in CONTENT.requirements.values():
        if r.cost and r.cost.basis == "vendor_range":
            assert r.cost.currency and "vendor" in r.cost.text
    # where the sources are silent the field is empty
    for code in ("REQ-AQAP2310", "REQ-ISO9001", "REQ-EN9100", "REQ-EXPORT", "REQ-REOCE", "REQ-FSC-ES"):
        assert CONTENT.requirements[code].cost is None and CONTENT.requirements[code].days is None, code
    ncage = CONTENT.requirements["REQ-NCAGE"]
    assert ncage.cost.basis == "free" and (ncage.days.min, ncage.days.max) == (5, 20)
    assert CONTENT.requirements["REQ-PIC"].cost.basis == "free" and CONTENT.requirements["REQ-PIC"].days.max == 0


def test_every_covered_country_has_the_ncage_and_pic_issuer_rows():
    for country in ("ES", "UA", "DE", "PL", "NL", "FR", "RO", "CZ", "LT", "LV", "EE", "PT", "IT", "SE", "FI", "GR", "BE"):
        for code in ("REQ-NCAGE", "REQ-PIC"):
            assert CONTENT.issuers_for(code, country), (country, code)


def test_what_the_appendix_marks_unverified_is_marked_unverified_here():
    ua = [i for i in CONTENT.issuers_for("REQ-NCAGE", "UA")]
    assert ua and "UNVERIFIED" in ua[0].notes
    (hsem,) = CONTENT.issuers_for("REQ-FSC-ES", "ES")
    assert "UNVERIFIED" in hsem.notes and "processing times" in hsem.notes
    de = CONTENT.issuers_for("REQ-NCAGE", "DE")[0]
    assert de.status == "U" and de.notes.startswith("UNVERIFIED")
    (other,) = rules("G-CLASSIFIED-OTHER")
    assert other.status == "U" and other.texts["info"].startswith("UNVERIFIED")
    # an issuer for a country the appendix did not cover is "not collected", never invented
    assert CONTENT.issuers_for("REQ-EXPORT", "FR") == []
    assert CONTENT.issuers_for("REQ-AQAP2110", "FR") == []


def test_no_esg_requirement_is_encoded_because_none_was_confirmed():
    text = json.dumps(RAW).lower()
    assert "esg" not in text.replace("message", "")
    assert not [r for r in CONTENT.requirements.values() if r.category == "integrity"]


def test_the_seed_contains_no_e_mail_address_and_no_personal_data():
    assert EMAIL.findall(seed.SEED_PATH.read_text(encoding="utf-8")) == []


def test_an_eligibility_rule_that_is_assessed_not_obtained_lists_the_rules_it_stands_for():
    def codes(requirement):
        return [r.code for r in CONTENT.rules_of(requirement)]
    assert codes("REQ-EDF-ELIG") == ["EDF-LEGAL-ENTITY", "EDF-ESTABLISH", "EDF-EXEC-MGMT", "EDF-CONTROL"]
    assert codes("REQ-EDIP-ELIG") == [
        "EDIP-LEGAL-ENTITY", "EDIP-ESTABLISH", "EDIP-EXEC-MGMT", "EDIP-CONTROL", "EDIP-ORIGIN-35", "EDIP-NO-RESTRICTED",
        "EDIP-SUBCONTRACT-RELIEF", "USI-LEGAL-ENTITY", "USI-ESTABLISH", "USI-EXEC-MGMT", "USI-TERRITORY", "USI-CONTROL",
        "USI-ORIGIN-35", "USI-NO-RESTRICTED", "USI-INVOLVES-UA"]
    assert codes("REQ-SAFE-35") == ["SAFE-ORIGIN-35", "SAFE-NO-RESTRICTED"]
    assert CONTENT.rules_of("REQ-NOPE") == []


def test_aqap_2120_is_flagged_as_stale_guidance():
    assert "AQAP 2120 no longer exists" in CONTENT.requirements["REQ-AQAP2110"].description


def test_the_check_command_validates_without_a_database(capsys):
    assert seed.main(["--check"]) == 0
    assert "seed ok: 6 programmes, 12 requirements" in capsys.readouterr().out


# --------------------------------------------------------------------- the loader refuses a broken file

def broken(mutate):
    raw = copy.deepcopy(RAW)
    mutate(raw)
    with pytest.raises(seed.SeedError):
        seed.parse(raw)


def test_a_requirement_without_a_source_url_is_refused():
    broken(lambda r: r["requirements"][0].update(source_url=""))


def test_a_rule_without_a_verbatim_passage_is_refused():
    broken(lambda r: r["rules"][0].update(passages=[]))


def test_a_rule_with_a_wrong_expression_is_refused():
    broken(lambda r: r["rules"][0].update(condition={"field": "no_such_field", "is": 1}))


def test_a_rule_pointing_to_an_unknown_requirement_or_programme_is_refused():
    broken(lambda r: r["rules"][3].update(requirement="REQ-NOPE"))
    broken(lambda r: r["rules"][0].update(programmes=["NOPE"]))


def test_a_rule_without_the_texts_its_outcomes_need_is_refused():
    broken(lambda r: r["rules"][0].update(texts={"met": "x"}))                          # no not_met
    broken(lambda r: r["rules"][2]["texts"].pop("conditional"))                          # EDF-CONTROL
    broken(lambda r: next(x for x in r["rules"] if x["code"] == "USI-TERRITORY")["texts"].pop("not_applicable"))
    broken(lambda r: next(x for x in r["rules"] if x["code"] == "EDF-AQAP").update(texts={}))


def test_a_requirement_that_lists_a_rule_that_does_not_exist_is_refused():
    broken(lambda r: r["requirements"][2]["extras"].update(rules=["EDF-NOPE"]))


def test_a_duplicate_rule_or_requirement_is_refused():
    broken(lambda r: r["rules"].append(copy.deepcopy(r["rules"][0])))
    broken(lambda r: r["requirements"].append(copy.deepcopy(r["requirements"][0])))


def test_a_cost_that_is_not_a_range_or_has_no_currency_is_refused():
    broken(lambda r: r["requirements"][7]["cost"].update(min=60000))
    broken(lambda r: r["requirements"][7]["cost"].update(currency=None))
    broken(lambda r: r["requirements"][7]["cost"].update(basis="guess"))
    broken(lambda r: r["requirements"][0]["days"].update(min=30, max=3))


def test_a_bad_status_date_issuer_or_prerequisite_is_refused():
    broken(lambda r: r["requirements"][0].update(verification_status="X"))
    broken(lambda r: r["requirements"][0].update(last_reviewed="yesterday"))
    broken(lambda r: r["issuers"][0].update(country="Spain"))
    broken(lambda r: r["issuers"][0].update(requirement="REQ-NOPE"))
    broken(lambda r: r["prerequisites"].append({"requirement": "REQ-PIC", "prerequisite": "REQ-PIC", "relation": "before"}))
    broken(lambda r: r["prerequisites"][0].update(relation="after"))
    broken(lambda r: r["requirements"][7]["variants"][0].update(when_held="REQ-NOPE"))
