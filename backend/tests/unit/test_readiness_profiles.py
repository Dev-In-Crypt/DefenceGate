"""Regression set of the independent verifier's profiles (WP-33).

`fixtures/readiness_profiles.json` holds 26 company profiles: the 17 runs the verifier of the readiness layer
itemised in docs/verification/product/verify-readiness.md (its section 3, profiles 1 to 14 with the variants 1b and
11a to 11c) and nine more for the rules added in WP-33. Each carries the verdict per programme that the law gives.
This file states the legal reason for every verdict (REASONS) and fails if a profile has no reason or a verdict
differs. The profiles go through `ProfileIn`, so the API's own validation is part of the test.

Verdicts: eligible; obtain (only registrations that anybody can obtain are missing: PIC, NCAGE); conditional (a
derogation, a guarantee or an unanswered question is open); blocked (a rule that every applicant must meet is not met).
PIC held unless the profile says otherwise. A missing answer is never read as "no".
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from dgate.readiness.api import ProfileIn
from dgate.readiness.engine import assess
from dgate.readiness.seed import load_file

CONTENT = load_file()
PROFILES = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "readiness_profiles.json").read_text(encoding="utf-8"))
PROGRAMMES = [p for p in CONTENT.programmes.values() if p.kind != "general"]

REASONS = {
    "p01-ua-country-only": "EDIP Programme: Ukraine is not an associated country (Reg. 2025/2643 Art 2 'associated countries' = EEA EFTA members that apply it; Art 9(1)), so blocked whatever else is answered. "
                           "EDF, USI and SAFE cannot be decided: a question left unanswered is unknown, never 'no' (conditional). NATO: the NCAGE is a free registration to obtain.",
    "p02-ua-all-answered-10pct": "EDF: Reg. 2025/2653 Art 3 replaces Art 5 of 2021/697 so that Ukraine can be an associated country 'in accordance with the conditions laid down in the EU-Ukraine Association Agreement'; the EDF call documents of 2026 say participation of entities established in Ukraine is pending the signature of that agreement and no primary text says it applies (V2-B2), so conditional, not 'obtain'. "
                                 "USI: 'established in the Union or in Ukraine' (2025/2643 Art 26(1)); only the free PIC is missing, so 'obtain', not blocked. "
                                 "EDIP: blocked as for profile 1. SAFE: established in Ukraine (2025/1106 Art 16(3)), 10 % <= 35 % (Art 16(10)): eligible.",
    "p03-es-iso9001-only": "A Spanish legal person meets every establishment, management and control rule of EDF, EDIP and USI; the only gap is the free, immediate PIC: obtain. SAFE has no registration: eligible. NCAGE to obtain.",
    "p04-pl-sme-30pct-us-components": "30 % is not higher than 35 % under SAFE Art 16(10), EDIP Art 10(3) and USI Art 27(3), so all four are eligible. Dual-use goods moved inside the Union need an authorisation only for Annex IV items or where a Member State imposes one (Reg. 2021/821 Art 11), so the export step is not mandatory (D6).",
    "p05-de-controlled-from-third-country": "Control by a third country: EDF Art 9(4), EDIP Art 9(6), USI Art 26(6) and SAFE Art 16(5) allow a derogation for an entity established in the Union if guarantees or screening are in place: conditional in all four.",
    "p06-es-sole-trader": "A sole trader is a natural person. 'Legal entity' is defined in 2021/697 Art 2 and 2025/2643 Art 2 as a legal person or an entity without legal personality as in the Financial Regulation point (c); natural persons are point (b) of that Article, which the definition does not cite. "
                          "The EDF, EDIP and Ukraine Support Instrument call documents of 2026 say: 'Natural persons are NOT eligible (with the exception of self-employed persons, i.e. sole traders, where the company does not have legal personality separate from that of the natural person)', so conditional for EDF, EDIP and USI, not blocked (V2-B4). "
                          "SAFE Art 16 contains no such definition for contractors, so SAFE is not decided by legal form.",
    "p07-norwegian-company": "EDF Art 5(a): EEA EFTA members are associated countries. EDIP Art 2: only EEA EFTA members that apply the Regulation, so a check (conditional). USI Art 26(1): the Union or Ukraine only: blocked. SAFE Art 16(3): EEA EFTA State: eligible.",
    "p08-us-company": "Established outside the Union, an associated country, the EEA EFTA states and Ukraine: EDF Art 9(1), EDIP Art 9(1), USI Art 26(1) and SAFE Art 16(3) are not met. The SAFE agreements of Art 17 are not encoded.",
    "p09-de-management-in-us": "Executive management structures must be in the Union or an associated country (EDF Art 9(2), EDIP Art 9(1), USI Art 26(1)) or the Union, an EEA EFTA state or Ukraine (SAFE Art 16(3)).",
    "p10-de-controlled-by-ua-or-eea": "SAFE Art 16(3) does not count control by an EEA EFTA State or Ukraine. EDF Art 9(3) does not count control by an associated country: an EEA EFTA State is one, Ukraine only if its association agreement applies, which is not confirmed (V2-B2), and the answer cannot tell the two apart: conditional. "
                                 "EDIP Art 9(5) and USI Art 26(5) name only associated countries (EEA EFTA states that apply it) and, for USI, Ukraine: conditional for the same reason.",
    "p11-ua-non-government-controlled-area": "USI Art 26(1), second subparagraph: entities in non-government controlled areas of Ukraine are not eligible. EDIP: blocked (Ukraine is not associated). The texts of EDF and SAFE do not mention the area: SAFE eligible on its rules, EDF conditional only because Ukraine's association to the EDF is not confirmed (V2-B2).",
    "p12-fr-exactly-35pct": "'Not higher than 35 %': exactly 35 % passes (SAFE Art 16(10), EDIP Art 10(3), USI Art 27(3)). No Ukrainian or EEA EFTA component is reported, so the denominators of the three Articles agree.",
    "p13-fr-35-01pct": "35.01 % is higher than 35 %: SAFE Art 16(10), EDIP Art 10(3)-(4) and USI Art 27(3)-(4) are not met. EDF has no origin rule.",
    "p14-fr-restricted-component": "SAFE Art 16(10) second sentence, EDIP Art 10(3) and USI Art 27(3) second sentences: no component from a third country that contravenes the security and defence interests of the Union. A categorical ban; EDF has none.",
    "p15-ua-controlled-by-other-country": "EDF Art 9(4): the derogation is for an entity in the Union or an associated country; Ukraine is one only if its association agreement applies, which is not confirmed (V2-B2): conditional either way. USI Art 26(6) and SAFE Art 16(5): the derogation is for an entity established in the Union only: blocked. EDIP: blocked as for any Ukrainian company.",
    "p16-fr-60pct": "60 % > 35 %: EDIP Art 10(3)-(4) and USI Art 27(3)-(4) have the same limit as SAFE Art 16(10) (the verifier's defect D1: these were shown 'Eligible'). EDF has no origin rule.",
    "p17-greece-sent-as-EL": "'EL' is Greece in EU usage; it is read as GR and Greece is a Member State: eligible (D11: it was read as a country outside the EU).",
    "p18-es-entity-without-legal-personality": "An entity without legal personality is a legal entity only if it is of the kind in point (c) of the Financial Regulation (2021/697 Art 2; 2025/2643 Art 2): conditional. SAFE: not decided by legal form.",
    "p19-fr-20pct-plus-ukrainian-components": "EDIP Art 10(3) counts components from outside 'the Union and associated countries' and Ukraine is not associated; USI Art 27(3) counts those from outside 'the Union and Ukraine', so EEA EFTA components count. With such components the 20 % reported on SAFE's base may exceed 35 % on theirs: conditional, never eligible. SAFE Art 16(10) counts neither.",
    "p20-de-origin-flag-unanswered": "The question about components from Ukraine or an EEA EFTA state is unanswered: EDIP and USI cannot be decided (conditional). SAFE's base does not need it.",
    "p21-us-supplier-below-the-subcontractor-threshold": "SAFE Art 16(3) binds contractors and 'subcontractors involved in the common procurement', defined in Art 16(12) as critical-input providers with at least 15 % of the contract value and a need for classified access. A supplier below that is not bound (D5), so SAFE rules on establishment, management and control do not apply to it; EDF, EDIP and USI still block a US company.",
    "p22-us-subcontractor-involved": "A US company that meets Art 16(12) is a subcontractor involved: Art 16(3) applies and is not met (the 15 to 35 % relief of Art 16(4) is information, not encoded as a pass).",
    "p23-es-safe-role-unanswered": "Whether SAFE Art 16(3) binds the company depends on its role (Art 16(12)); unanswered is unknown (conditional), not 'contractor' and not 'supplier'.",
    "p24-pl-nothing-held": "A Polish legal person with clean answers lacks only the PIC (EDF, EDIP, USI) and the NCAGE (NATO): free registrations, so 'obtain' and not blocked (D3).",
    "p25-pl-controlled-and-no-pic": "Control by a third country needs guarantees (derogation) and the PIC is missing: conditional dominates; the PIC stays in the 'to obtain' list.",
    "p26-es-everything-held": "Every rule is met and both registrations are held: eligible.",
    "p27-ca-contractor-under-the-safe-agreement": "The agreement between the EU and Canada (Council Decision (EU) 2026/1381, OJ L 2026/445) has applied provisionally since 13 April 2026: Art 5(2) lets a Canadian legal entity established in Canada with executive management in Canada take part in SAFE procurement, so SAFE is conditional, not blocked (V2-B7). "
                                                  "EDF, EDIP and USI have no such agreement: blocked.",
    "p28-ca-management-in-the-us": "Art 5(2) of the SAFE agreement with Canada needs executive management in Canada, the Union, an EEA EFTA State or Ukraine: management in the United States is not met, so SAFE stays blocked.",
    "p29-ca-40pct-components": "Art 5(8) of the SAFE agreement with Canada lets components originating in Canada exceed 35 % and sets other limits that the single answer cannot separate: the origin rule is conditional, not blocked, for a Canadian entity.",
    "p30-ua-with-pic": "Everything is answered and held that can be: EDF stays conditional on the EU-Ukraine association agreement (V2-B2); the Ukraine Support Instrument and SAFE are met; EDIP is blocked (Ukraine is not an associated country of the Programme).",
    "p31-pl-company-edip-common-procurement": "Regulation (EU) 2025/2643 Art 11(2): 'Only the following legal entities shall be eligible for common procurement actions: contracting authorities of Member States or associated countries; international organisations; SEAPs; the EDA.' A company is none of them: EDIP is blocked for a call of this action (V2-B1).",
    "p32-pl-company-edip-industrial-reinforcement": "Art 11(2) concerns common procurement only; industrial reinforcement actions (Art 12) are open to legal entities in a consortium or a SEAP: no regression for the same company.",
    "p33-pl-ministry-edip-common-procurement": "A contracting authority of a Member State is the first kind of entity Art 11(2)(a) names.",
    "p34-no-ministry-edip-common-procurement": "Art 11(2)(a): contracting authorities of Member States or associated countries; Norway is an associated country only if it applies the Regulation (Art 2): conditional. USI is blocked (not the Union or Ukraine).",
    "p35-us-ministry-edip-common-procurement": "A contracting authority of a third country is not one of Art 11(2)(a), and the establishment rules of Art 9(1) are not met either.",
    "p36-pl-company-edip-support-to-seaps": "The call document of the call for support to SEAPs admits only an established SEAP ('Only single applications by a SEAP are allowed'): a company cannot apply (V2-B1, call document rule).",
    "p37-seap-edip-support-to-seaps": "A SEAP is the applicant the call document names.",
    "p38-pl-company-edip-project-preparation": "The call document admits a SEAP or a group of at least four Member States and associated countries: a company cannot apply.",
    "p39-pl-kind-unanswered-edip-common-procurement": "Who the applicant is has not been said: unknown, never 'not eligible' and never 'eligible' (conditional).",
    "p40-pl-company-no-call": "No call is being judged: the rules that belong to one kind of action are not asked, so the Polish company keeps the verdicts it had before V2-B1.",
}


def engine_profile(raw, action=None):
    profile = ProfileIn.model_validate(raw).to_engine()
    return dataclasses.replace(profile, action=action) if action else profile


def verdicts(entry):
    profile = engine_profile(entry["profile"], entry.get("action"))
    return {p.code: assess(profile, entry["statuses"], p).verdict for p in PROGRAMMES}


def test_there_are_40_profiles_and_every_one_has_a_stated_legal_reason():
    assert len(PROFILES) == 40
    assert {p["id"] for p in PROFILES} == set(REASONS)
    assert all(len(REASONS[i]) > 40 for i in REASONS)
    # the 17 runs the verifier itemised
    assert {p["verifier_profile"] for p in PROFILES} >= {"1", "1b", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11a", "11b", "11c", "12", "13", "14"}


@pytest.mark.parametrize("entry", PROFILES, ids=[p["id"] for p in PROFILES])
def test_each_profile_gets_the_verdicts_the_law_gives(entry):
    assert verdicts(entry) == entry["expected"], REASONS[entry["id"]]


def test_the_verifiers_wrong_eligible_verdicts_are_gone():
    # D1: 60 % of component cost from outside under EDIP and the Ukraine Support Instrument
    sixty = next(p for p in PROFILES if p["id"] == "p16-fr-60pct")
    assert verdicts(sixty)["EDIP"] == verdicts(sixty)["EDIP-USI"] == "blocked"
    # D2: a natural person
    # V2-B4: a sole trader is conditional where the call documents make the exception, not blocked (this was D2's over-correction)
    sole = next(p for p in PROFILES if p["id"] == "p06-es-sole-trader")
    assert set(verdicts(sole)[c] for c in ("EDF", "EDIP", "EDIP-USI")) == {"conditional"}
    # V2-B1: a company is not eligible for an EDIP call of common procurement, a SEAP-only call or the preparation call
    for pid in ("p31-pl-company-edip-common-procurement", "p36-pl-company-edip-support-to-seaps", "p38-pl-company-edip-project-preparation"):
        assert verdicts(next(p for p in PROFILES if p["id"] == pid))["EDIP"] == "blocked", pid
    # V2-B2: Ukraine is not treated as an associated country of the EDF
    ua = next(p for p in PROFILES if p["id"] == "p30-ua-with-pic")
    assert verdicts(ua)["EDF"] == "conditional"


def test_a_missing_pic_alone_is_obtain_and_never_blocked():
    # D3: 7 of the verifier's 100 funding verdicts, and NATO supply in 25 of 25 runs
    for pid in ("p02-ua-all-answered-10pct", "p03-es-iso9001-only", "p24-pl-nothing-held"):
        entry = next(p for p in PROFILES if p["id"] == pid)
        got = verdicts(entry)
        assert "blocked" not in {got["EDF"], got["EDIP-USI"], got["NATO-SUPPLY"]}, pid
    entry = next(p for p in PROFILES if p["id"] == "p24-pl-nothing-held")
    a = assess(engine_profile(entry["profile"]), {}, CONTENT.programmes["EDF"])
    assert a.to_obtain == ("EDF-PIC",) and a.blocking == () and a.verdict == "obtain"
