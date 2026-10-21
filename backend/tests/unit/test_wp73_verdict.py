"""WP-73 (frontend QA of 21 October 2026, MJ-3 and MJ-4): the verdict of a supply route follows the three-valued logic of its rules.

MJ-4: the Spanish MoD card said "Eligible" while its HSEM and NATO facility clearance rules said "Not met" and three answers were missing:
the verdict read only rules of obligation `mandatory`, and every ES-MOD rule but the RID is `conditional` (binding where it applies). MJ-3:
the supplier page sent the PIC, the export authorisation and the HSEM as "not held" without asking; it now sends them as `unknown`.
The profile is the audit's profile B: a Spanish electronics firm that needs classified work, supplier page only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dgate.readiness import api, engine
from dgate.readiness.seed import load_file

ROOT = Path(__file__).resolve().parents[3]
CONTENT = load_file()
FIXTURES = ROOT / "web" / "e2e" / "fixtures"

# what the supplier page sends for profile B (the wizard's answers empty): the page asked the certificates and registrations it shows
# ("not held" unless ticked) and nothing about the PIC, the export authorisation, REOCE or, unless answered, the HSEM ("unknown")
ASKED = {"REQ-NCAGE": "not_held", "REQ-ISO9001": "held", "REQ-EN9100": "not_held", "REQ-AQAP2110": "not_held",
         "REQ-AQAP2310": "not_held", "REQ-RID": "held", "REQ-PECAL": "not_held"}
UNASKED = {"REQ-PIC": "unknown", "REQ-EXPORT": "unknown", "REQ-REOCE": "unknown", "REQ-FSC-ES": "unknown"}
PROFILE_B = {"country": "ES", "handles_classified": True, "third_country_control": "no", "foreign_capital": False, "us_components": False,
             "pecal_certificate_wanted": False, "pecal_2310_target": False, "ncage_need_justified": True, "specific_defence_use": True,
             "homologation_mandatory": True, "stores_classified": False, "nato_classified_contract": True, "nsfcc_held": False,
             "nato_staff_cleared": False, "nato_icb_bid": False, "receives_eea_defence_products": False}


def mod(profile: dict, statuses: dict) -> dict:
    body = api.AssessIn.model_validate({"profile": profile, "statuses": statuses})
    payload = api.assess_payload(CONTENT, body.profile.to_engine(), body.statuses)
    return next(a for a in payload["assessments"] if a["programme"] == "ES-MOD")


def outcome(a: dict, rule: str) -> str:
    return next(r["outcome"] for r in a["rules"] if r["rule"] == rule)


def test_profile_b_is_never_eligible_with_a_clearance_not_met():
    a = mod(PROFILE_B, {**ASKED, **UNASKED})
    assert outcome(a, "ES-NSFCC") == "not_met"
    assert a["verdict"] == "blocked" and a["blocking"] == ["ES-NSFCC"]
    # the HSEM was not asked: it needs an answer, with its question, and is not "Not met"
    assert outcome(a, "ES-HSEM") == "unknown"
    assert {"field": "REQ-FSC-ES", "question": "Do you hold: HSEM facility security clearance (Spain)?"} in a["missing"]
    assert "homologated" in [m["field"] for m in a["missing"]]


def test_the_old_request_of_profile_b_is_blocked_by_both_clearances():
    # before WP-73 the page sent the HSEM as "not held": then both rules are not met, and the route is blocked, never "Eligible"
    a = mod(PROFILE_B, {**ASKED, **{k: "not_held" for k in UNASKED}})
    assert a["verdict"] == "blocked" and a["blocking"] == ["ES-HSEM", "ES-NSFCC"]


def test_missing_answers_on_a_conditional_rule_make_the_route_conditional():
    p = {**PROFILE_B, "nato_classified_contract": False}
    a = mod(p, {**ASKED, **UNASKED})
    assert (a["verdict"], a["incomplete"], a["blocking"]) == ("conditional", True, [])
    assert {"REQ-FSC-ES", "homologated"} <= {m["field"] for m in a["missing"]}


def test_every_answer_given_and_held_is_eligible():
    p = {**PROFILE_B, "nato_classified_contract": False, "homologated": True}
    a = mod(p, {**ASKED, **UNASKED, "REQ-NCAGE": "held", "REQ-FSC-ES": "held"})
    assert (a["verdict"], a["incomplete"], a["missing"]) == ("eligible", False, [])


def test_a_contract_requirement_not_met_is_a_condition_not_a_block():
    # PECAL wanted without ISO 9001 or EN 9100: the certificate cannot be applied for yet, which a contract may ask, not the route
    p = {**PROFILE_B, "nato_classified_contract": False, "homologated": True, "pecal_certificate_wanted": True,
         "pecal_system_9_months": True, "pecal_prior_contract": True}
    a = mod(p, {**ASKED, **UNASKED, "REQ-ISO9001": "not_held", "REQ-NCAGE": "held", "REQ-FSC-ES": "held"})
    assert outcome(a, "ES-PECAL-ISO") == "not_met"
    assert a["verdict"] == "conditional" and "ES-PECAL-ISO" in a["conditions"] and a["blocking"] == []


def test_a_recommendation_never_decides():
    p = {**PROFILE_B, "nato_classified_contract": False, "homologated": True, "receives_eea_defence_products": True}
    a = mod(p, {**ASKED, **UNASKED, "REQ-NCAGE": "held", "REQ-FSC-ES": "held"})
    assert outcome(a, "ES-CERTIFIED-RECIPIENT") == "unknown"     # recommended, its follow-up unanswered
    assert a["verdict"] == "eligible"


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("assess-*.json")), ids=lambda p: p.stem)
def test_no_card_of_the_fixtures_is_eligible_beside_a_binding_rule_that_is_not_met_or_open(path):
    body = json.loads(path.read_text(encoding="utf-8"))
    for a in body["assessments"]:
        open_ = [r["rule"] for r in a["rules"] if r["obligation"] != "recommended" and r["outcome"] in ("not_met", "unknown")]
        if open_:
            assert a["verdict"] != "eligible", (path.stem, a["programme"], open_)


def test_unknown_is_a_status_the_api_takes_and_the_roadmap_reads_as_not_held():
    with pytest.raises(ValidationError):
        api.AssessIn.model_validate({"profile": {"country": "ES"}, "statuses": {"REQ-PIC": "maybe"}})
    body = api.AssessIn.model_validate({"profile": {"country": "ES"}, "statuses": {"REQ-PIC": "unknown"}})
    payload = api.assess_payload(CONTENT, body.profile.to_engine(), body.statuses)
    edf = next(a for a in payload["assessments"] if a["programme"] == "EDF")
    pic = next(r for r in edf["rules"] if r["requirement"] == "REQ-PIC")
    assert pic["outcome"] == "unknown" and pic["asks"] == [{"field": "REQ-PIC", "question": "Do you hold: PIC (Participant Identification Code)?"}]
    step = next(s for s in payload["roadmap"]["steps"] if s["code"] == "REQ-PIC")
    assert step["status"] == "not_held"
    # unchanged for a request that does not mention it: a requirement not mentioned is still "not held"
    payload = api.assess_payload(CONTENT, body.profile.to_engine(), {})
    edf = next(a for a in payload["assessments"] if a["programme"] == "EDF")
    assert next(r for r in edf["rules"] if r["requirement"] == "REQ-PIC")["outcome"] == "to_obtain"


def test_rules_reviewed_is_the_latest_review_of_any_rule():
    latest = max(r.last_reviewed for p in CONTENT.programmes.values() for r in p.rules)
    assert CONTENT.reviewed == latest == "2026-10-20"
    assert engine.STATUS_UNKNOWN == "unknown"
