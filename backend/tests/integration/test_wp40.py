"""WP-40 on a real Postgres: who may apply to an EDIP call depends on its kind of action (V2-B1), through the API a visitor uses.

The call page's "Your readiness for this call" posts the saved profile with the call id; the rules block of the call comes with the
call detail. No language model and no network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dgate import api, stats
from dgate.readiness import api as readiness_api
from dgate.readiness.seed import apply as apply_rules
from dgate.readiness.seed import load_file as load_rules
from tests.integration.test_wp31 import put

pytestmark = pytest.mark.integration

PL = {"country": "PL", "legal_form": "legal_person", "executive_management_country": "PL", "third_country_control": "no",
      "non_eu_component_cost_pct": 10, "restricted_third_country_component": False, "components_from_ua_or_eea_efta": False,
      "safe_role": "contractor", "handles_classified": False, "product_regime": "none", "export_intent": "none"}
HELD = {"REQ-PIC": "held", "REQ-NCAGE": "held"}
CPA, IRA, SEAP, PREP = ("EDF-EDIP-P-2027-FNLC-CPA-AMDS", "EDF-EDIP-P-2027-LS-IRA-KEC",
                        "EDF-EDIP-P-2026-2027-FNLC-SA-SEAP", "EDF-EDIP-P-2026-FNLC-CSA-PREP")


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    readiness_api.reset_cache()
    yield
    stats.reset_cache()
    readiness_api.reset_cache()


@pytest.fixture()
def client(conn):
    apply_rules(conn, load_rules())
    conn.commit()
    with TestClient(api.app) as c:
        yield c


def edip_timing(client, call_id, **profile):
    body = client.post("/v1/readiness/assess", json={"profile": {**PL, **profile}, "statuses": HELD, "call": call_id}).json()
    (timing,) = [t for t in body["call"]["timings"] if t["programme"] == "EDIP"]
    return body["call"], timing


def test_a_company_is_not_eligible_for_an_edip_common_procurement_call_but_is_for_industrial_reinforcement(client, conn):
    cpa = put(conn, "cpa", programme="EDF", topic=CPA, days=60)
    ira = put(conn, "ira", programme="EDF", topic=IRA, days=60)

    call, t = edip_timing(client, cpa, applicant_kind="company_or_research")
    assert call["action"] == "common_procurement"
    assert t["verdict"] == "blocked" and t["realistic"] == "not_possible"
    assert [n["rule"] for n in t["notFixable"]] == ["EDIP-CPA-APPLICANT"]
    assert "contracting authorities of Member States or associated countries, international organisations, SEAPs and the EDA" in t["notFixable"][0]["reason"]

    call, t = edip_timing(client, ira, applicant_kind="company_or_research")
    assert call["action"] == "industrial_reinforcement" and t["verdict"] == "eligible" and t["realistic"] == "yes", "no regression for the other EDIP calls"


def test_a_contracting_authority_is_eligible_and_an_organisation_that_did_not_say_is_told_to_say(client, conn):
    cpa = put(conn, "cpa", programme="EDF", topic=CPA, days=60)
    _, t = edip_timing(client, cpa, applicant_kind="contracting_authority")
    assert t["verdict"] == "eligible" and t["realistic"] == "yes"
    _, t = edip_timing(client, cpa)                                    # no applicant_kind
    assert t["verdict"] == "conditional" and t["realistic"] == "depends", "unanswered is unknown, never 'not eligible' and never 'eligible'"


def test_the_calls_that_support_seaps_and_prepare_projects_of_common_interest_name_their_applicants(client, conn):
    seap = put(conn, "seap", programme="EDF", topic=SEAP, days=60)
    prep = put(conn, "prep", programme="EDF", topic=PREP, days=60)
    assert edip_timing(client, seap, applicant_kind="company_or_research")[1]["realistic"] == "not_possible"
    assert edip_timing(client, seap, applicant_kind="seap")[1]["realistic"] == "yes"
    assert edip_timing(client, prep, applicant_kind="company_or_research")[1]["realistic"] == "not_possible"
    assert edip_timing(client, prep, applicant_kind="contracting_authority")[1]["realistic"] == "depends"


def test_without_a_call_the_rule_of_one_kind_of_action_is_not_asked(client):
    body = client.post("/v1/readiness/assess", json={"profile": {**PL, "applicant_kind": "company_or_research"}, "statuses": HELD}).json()
    edip = next(a for a in body["assessments"] if a["programme"] == "EDIP")
    rule = next(r for r in edip["rules"] if r["rule"] == "EDIP-CPA-APPLICANT")
    assert rule["outcome"] == "not_applicable" and "checked when you open a call of that kind" in rule["reason"]
    assert edip["verdict"] == "eligible" and edip["missing"] == []


def test_the_api_does_not_take_the_context_of_a_call_from_the_visitor(client):
    refused = client.post("/v1/readiness/assess", json={"profile": {**PL, "action": "common_procurement"}, "statuses": {}})
    assert refused.status_code == 422
    assert client.post("/v1/readiness/assess", json={"profile": {**PL, "applicant_kind": "plumber"}, "statuses": {}}).status_code == 422
    fields = client.get("/v1/readiness/programmes").json()["fields"]
    assert fields["action"]["context"] is True and "context" not in fields["applicant_kind"]


def test_the_rules_block_of_the_call_detail_follows_the_kind_of_action_and_carries_the_caveats(client, conn):
    cpa = put(conn, "cpa", programme="EDF", topic=CPA)
    ira = put(conn, "ira", programme="EDF", topic=IRA)
    edf = put(conn, "edf", programme="EDF", topic="EDF-2026-DA-D")

    block = client.get(f"/v1/funding/{cpa}").json()["rulesApply"]
    assert block["action"] == "common_procurement" and "EDIP-CPA-APPLICANT" in [r["rule"] for r in block["rules"]]
    first = next(r for r in block["rules"] if r["rule"] == "EDIP-CPA-APPLICANT")
    assert "Only the following legal entities shall be eligible for common procurement actions" in first["source"]["text"]
    assert "Article 9(9)" in next(r for r in block["rules"] if r["rule"] == "EDIP-CONTROL")["caveat"]
    assert "EDIP-CPA-APPLICANT" not in [r["rule"] for r in client.get(f"/v1/funding/{ira}").json()["rulesApply"]["rules"]]

    caveats = {r["rule"]: r["caveat"] for r in client.get(f"/v1/funding/{edf}").json()["rulesApply"]["rules"] if r["caveat"]}
    assert set(caveats) == {"EDF-ESTABLISH", "EDF-EXEC-MGMT"} and all("not confirmed" in c for c in caveats.values())


def test_wp42_r1_the_ukraine_support_instrument_calls_do_not_say_you_can_apply_now_to_a_company_outside_ukraine(client, conn):
    usi = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-MAB", days=20)
    body = client.post("/v1/readiness/assess", json={"profile": PL, "statuses": HELD, "call": usi}).json()
    (t,) = body["call"]["timings"]
    assert t["programme"] == "EDIP-USI" and t["verdict"] == "conditional" and t["realistic"] == "depends"
    # WP-53 (T21): the profile can now say whether a Ukrainian partner takes part. Unsaid, the answer is missing; "no" leaves the condition open.
    assert t["openConditions"] == [] and "apply now" not in t["text"] and "answer is still needed" in t["text"]
    (t,) = client.post("/v1/readiness/assess", json={"profile": {**PL, "ua_partner": False}, "statuses": HELD, "call": usi}).json()["call"]["timings"]
    assert t["verdict"] == "conditional" and t["realistic"] == "depends"
    assert t["openConditions"] == ["The action involves Ukraine"] and "apply now" not in t["text"]
    assert "USI-INVOLVES-UA" in [r["rule"] for r in client.get(f"/v1/funding/{usi}").json()["rulesApply"]["rules"]]
    ua = {**PL, "country": "UA", "executive_management_country": "UA", "ua_non_government_controlled_area": False}
    (t,) = client.post("/v1/readiness/assess", json={"profile": ua, "statuses": HELD, "call": usi}).json()["call"]["timings"]
    assert t["verdict"] == "eligible" and t["realistic"] == "yes" and t["openConditions"] == []
