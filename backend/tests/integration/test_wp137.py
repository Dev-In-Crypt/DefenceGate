"""WP-137 against Postgres: a EuroHPC JU call whose own conditions limit participation (Art. 22.5) and exclude entities controlled from
non-eligible countries keeps "Companies can take part", with the call's own sentences as the evidence instead of the general annexes'
"Any legal entity, regardless of its place of establishment"; the call page serves the limits; the readiness check of a company
controlled from elsewhere names the condition; the ops step reports what it writes and a second run changes nothing."""

from __future__ import annotations

import pytest

from dgate import verdict
from dgate.ops import wp137_who_apply
from tests.integration.test_wp31 import doc, put
from tests.integration.test_wp93 import client, row, stored  # noqa: F401  (the fixture `client`)
from tests.unit.test_wp132 import ANY_LEGAL
from tests.unit.test_wp137 import EUROHPC, TOPIC

pytestmark = pytest.mark.integration

ANNEXES = "https://ec.europa.eu/info/funding-tenders/opportunities/docs/2021-2027/horizon/wp-call/2026-2027/wp-15-general-annexes_horizon-2026-2027_en.pdf"


def test_the_calls_own_limits_are_the_evidence_and_are_served_with_the_answer(conn, client):  # noqa: F811
    hpc = put(conn, "hpc", topic=TOPIC, text=EUROHPC, documents=[doc(ANNEXES, "General Annexes")])
    plain = put(conn, "plain", topic="HORIZON-NATURE-2027-01-02", text="2. Eligible countries described in Annex B of the Work Programme "
                "General Annexes.", documents=[doc(ANNEXES, "General Annexes")])
    stored(conn, ANNEXES, "General annexes.")
    row(conn, ANNEXES, "general", ANNEXES, sme_only=(False, ANY_LEGAL, None),
        entity_types=(["Legal persons"], "A legal entity means any natural or legal person.", None))
    conn.execute("UPDATE call SET who_may_apply_doc = 'companies', who_may_apply_evidence = %s", (ANY_LEGAL,))   # as WP-132 wrote it
    conn.commit()

    report = wp137_who_apply.run(write=False)
    assert report[0].startswith("who may apply: 1 calls change;"), report
    assert report[1].startswith(f"  {hpc} {TOPIC}: companies -> companies; evidence 'Any legal entity")
    assert conn.execute("SELECT who_may_apply_evidence FROM call WHERE id = %s", (hpc,)).fetchone()["who_may_apply_evidence"] == ANY_LEGAL, \
        "a report writes nothing"
    conn.commit()
    written = wp137_who_apply.run(write=True)
    assert written[0].startswith("who may apply: 1 calls change (written)") and written[1:] == report[1:], "the write takes what the report named"
    rows = {r["id"]: r for r in conn.execute("SELECT id, who_may_apply_doc, who_may_apply_evidence FROM call").fetchall()}
    assert rows[hpc]["who_may_apply_doc"] == "companies"
    assert rows[hpc]["who_may_apply_evidence"].startswith("participation is limited to legal entities established in Member States or Participating States")
    assert rows[plain]["who_may_apply_evidence"] == ANY_LEGAL, "a call without an own limit keeps the annexes' sentence"
    conn.commit()           # end the read before the API's own connection reads (an open transaction holds its locks)
    assert wp137_who_apply.run(write=False)[0].startswith("who may apply: 0 calls change"), "a second run changes nothing"

    page = client.get(f"/v1/funding/{hpc}").json()
    assert page["whoMayApply"] == "companies"
    assert [x["kind"] for x in page["whoMayApplyLimits"]] == ["established", "control"]
    assert "guarantees approved by the eligible country" in page["whoMayApplyLimits"][1]["note"]
    assert client.get(f"/v1/funding/{plain}").json()["whoMayApplyLimits"] == []

    body = {"profile": {"country": "ES", "legal_form": "legal_person", "applicant_kind": "company_or_research", "org_kind": "company",
                        "headcount": "50_249", "in_group": False, "third_country_control": "other", "control_country": "cn"},
            "statuses": {}, "call": hpc}
    got = client.post("/v1/readiness/assess", json=body).json()["call"]["verdict"]
    assert got["fit"] == "check" and got["word"] == verdict.CONTROL_WORD
    body["profile"].update(country="US", third_country_control="no", control_country=None)
    assert client.post("/v1/readiness/assess", json=body).json()["call"]["verdict"]["word"] == "Blocked by: Country"


def test_an_edip_call_filed_under_the_edf_is_served_with_its_own_programme_name(conn, client):  # noqa: F811
    kec = put(conn, "kec", programme="EDF", topic="EDF-EDIP-P-2027-LS-IRA-KEC")
    usi = put(conn, "usi", programme="EDF", topic="EDF-EDIP-USI-2026-DA-UA")
    edf = put(conn, "edf", programme="EDF", topic="EDF-2026-DA-PROTMOB-DMM")
    items = {c["id"]: c for c in client.get("/v1/funding", params={"pageSize": 100, "status": "all"}).json()["items"]}
    assert (items[str(kec)]["programme"], items[str(kec)]["programmeName"]) == ("EDIP", "European Defence Industry Programme")
    assert (items[str(usi)]["programme"], items[str(usi)]["programmeName"]) == ("EDIP-USI", "EDIP Ukraine Support Instrument")
    assert items[str(edf)]["programmeName"] == "European Defence Fund"
    assert client.get(f"/v1/funding/{kec}").json()["programmeName"] == "European Defence Industry Programme", "the call page reads the same"
