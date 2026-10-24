"""WP-102 against Postgres: the rules read from a topic's conditions text are served with the call (the badge and the call page), the
general annexes' PCP/PPI rule is applied by the ops tool and served for PPI actions only, and the assessment API's verdict of a call
reads them."""

from __future__ import annotations

import pytest

from dgate import eligibility
from tests.integration.test_wp31 import doc, put
from tests.integration.test_wp93 import client, facts_of, row, stored  # noqa: F401  (the fixture `client`)
from tests.unit.test_wp102 import ANNEX_H, CSECCC, FCT05

pytestmark = pytest.mark.integration

ANNEXES = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/wp-call/2026-2027/wp-15-general-annexes_horizon-2026-2027_en.pdf"


def test_the_conditions_text_of_a_topic_is_read_when_the_call_is_served(conn, client):  # noqa: F811
    fct = put(conn, "fct05", topic="HORIZON-CL3-2026-01-FCT-05", text=f"3. Other Eligible Conditions {FCT05}", documents=[doc(ANNEXES, "General Annexes")])
    eccc = put(conn, "eccc02", topic="HORIZON-CL3-2027-02-CS-ECCC-02", text=f"2. Eligible countries {CSECCC}", documents=[doc(ANNEXES, "General Annexes")])
    stored(conn, ANNEXES, "General annexes.")
    row(conn, ANNEXES, "general", ANNEXES, eligible_countries=("EU Member States; countries associated to Horizon Europe", "q", eligibility.SCOPE_NOTES["general"]))
    got = facts_of(client, fct)["facts"]["required_partners"]
    assert got["value"].startswith("at least 3 Police Authorities and at least 2 Civil Society Organisations") and got["scope"] == "topic"
    own = facts_of(client, eccc)["facts"]["ownership_control_restriction"]
    assert own["value"] is True and "no way round" in own["note"]
    page = client.get(f"/v1/funding/{eccc}").json()
    assert page["documentEligibility"]["facts"]["ownership_control_restriction"]["note"] == own["note"], "the call page reads the same"
    body = {"profile": {"country": "DE", "legal_form": "legal_person", "applicant_kind": "company_or_research", "org_kind": "company",
                        "headcount": "500_1999", "in_group": True, "group_headcount": "2000plus", "third_country_control": "other",
                        "control_country": "other_non_eu"}, "statuses": {}, "call": eccc}
    verdict = client.post("/v1/readiness/assess", json=body).json()["call"]["verdict"]
    assert verdict["fit"] == "no" and verdict["word"] == "Blocked by: Ownership control"


def test_the_ops_tool_reads_annex_h_from_the_general_annexes_and_it_is_served_for_ppi_only(conn, client):  # noqa: F811
    from dgate.ops import rule_readings

    ppi = put(conn, "ssri03", topic="HORIZON-CL3-2026-01-SSRI-03", documents=[doc(ANNEXES, "General Annexes")])
    ia = put(conn, "fct05b", topic="HORIZON-CL3-2026-01-FCT-05", documents=[doc(ANNEXES, "General Annexes")])
    conn.execute("UPDATE call SET type_of_action = 'HORIZON-PPI HORIZON Public Procurement of Innovative Solutions' WHERE id = %s", (ppi,))
    conn.execute("UPDATE call SET type_of_action = 'HORIZON-IA HORIZON Innovation Actions' WHERE id = %s", (ia,))
    stored(conn, ANNEXES, ANNEX_H)
    row(conn, ANNEXES, "general", ANNEXES, eligible_countries=("EU Member States", "q", eligibility.SCOPE_NOTES["general"]))
    assert "procurement_conflict" not in facts_of(client, ppi)["facts"]
    report = rule_readings.run(write=False)
    assert any(c.startswith(f"{ANNEXES}: procurement_conflict") for c in report.changed), report.changed
    rule_readings.run(write=True)
    assert facts_of(client, ppi)["facts"]["procurement_conflict"]["value"] is True
    assert "procurement_conflict" not in facts_of(client, ia)["facts"], "Annex H is a rule of PCP and PPI actions"
    assert not any(c.startswith(ANNEXES) for c in rule_readings.run(write=True).changed), "a second run writes nothing"
