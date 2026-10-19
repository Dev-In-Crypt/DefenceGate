"""WP-53 through the API a visitor uses: the Ukrainian partner (T21) and "Not applicable to us" for the PIC (T4)."""

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
      "safe_role": "contractor", "handles_classified": False, "product_regime": "none", "export_intent": "none",
      "applicant_kind": "company_or_research"}


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


def usi(client, statuses, **profile):
    body = client.post("/v1/readiness/assess", json={"profile": {**PL, **profile}, "statuses": statuses})
    assert body.status_code == 200, body.text
    return next(a for a in body.json()["assessments"] if a["programme"] == "EDIP-USI")


def test_the_partner_answer_moves_the_ukraine_support_instrument_from_conditional_to_eligible(client):
    held = {"REQ-PIC": "held"}
    asked = usi(client, held)
    assert asked["verdict"] == "conditional" and [m["field"] for m in asked["missing"]] == ["ua_partner"]
    assert "Ukraine" in asked["missing"][0]["question"]
    assert usi(client, held, ua_partner=False)["verdict"] == "conditional"
    yes = usi(client, held, ua_partner=True)
    assert yes["verdict"] == "eligible" and yes["missing"] == [] and yes["conditions"] == []


def test_the_partner_field_is_in_the_catalogue_of_fields_and_a_non_boolean_is_refused(client):
    assert "ua_partner" in client.get("/v1/readiness/programmes").json()["fields"]
    assert client.post("/v1/readiness/assess", json={"profile": {**PL, "ua_partner": "maybe"}, "statuses": {}}).status_code == 422


def test_not_applicable_is_not_a_pic_the_company_holds(client):
    body = client.post("/v1/readiness/assess", json={"profile": PL, "statuses": {"REQ-PIC": "not_applicable"}}).json()
    for programme in ("EDF", "EDIP", "EDIP-USI"):
        a = next(x for x in body["assessments"] if x["programme"] == programme)
        rule = next(r for r in a["rules"] if r["rule"].endswith("-PIC"))
        assert rule["outcome"] == "not_applicable" and "You have a PIC" not in rule["reason"], programme
    assert "REQ-PIC" not in [s["code"] for s in body["roadmap"]["steps"]]


def timing(client, call_id, programme, **profile):
    body = client.post("/v1/readiness/assess", json={"profile": {**PL, **profile}, "statuses": {"REQ-PIC": "held"}, "call": call_id}).json()
    return next(t for t in body["call"]["timings"] if t["programme"] == programme)


def test_the_four_calls_open_to_a_company_can_say_you_can_apply_now_once_the_partner_is_named(client, conn):
    """Calls 118 and 113 (Ukraine Support Instrument) and 116 and 117 (EDIP industrial reinforcement) of 19 October 2026: with a company that
    meets every stated condition, the programme side was never better than 'depends' (0 of 9 calls could be a yes); with the Ukrainian
    partner named the Ukraine Support Instrument calls are 'yes'. The EDIP calls do not read the Ukrainian partner (the SEAP condition
    is in the call document and is answered in the browser)."""
    usi = [put(conn, "usi118", programme="EDF", topic="EDF-EDIP-USI-2026-LS-IRA-MAB", days=60),
           put(conn, "usi113", programme="EDF", topic="EDF-EDIP-USI-2027-LS-IRA-CUXS", days=60)]
    edip = [put(conn, "edip116", programme="EDF", topic="EDF-EDIP-P-2027-LS-IRA-KEC", days=60),
            put(conn, "edip117", programme="EDF", topic="EDF-EDIP-P-2027-LS-IRA-PE", days=60)]
    for call in usi:
        asked = timing(client, call, "EDIP-USI")
        assert asked["realistic"] == "depends" and asked["verdict"] == "conditional"
        assert timing(client, call, "EDIP-USI", ua_partner=False)["realistic"] == "depends"
        named = timing(client, call, "EDIP-USI", ua_partner=True)
        assert named["verdict"] == "eligible" and named["realistic"] == "yes", named
    for call in edip:
        assert timing(client, call, "EDIP")["realistic"] == "yes"
