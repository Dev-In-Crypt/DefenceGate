"""WP-64 on a real Postgres: the Spanish defence supplier route and the new general rules go through the database (seed, read back,
the public API) unchanged, including the questions of the unasked requirements, the "consultant needed" texts and the roadmap note.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dgate import api
from dgate.readiness import api as readiness_api
from dgate.readiness import seed

pytestmark = pytest.mark.integration

CONTENT = seed.load_file()
ES_AUTO = {"country": "ES", "legal_form": "legal_person", "executive_management_country": "ES", "third_country_control": "no",
           "non_eu_component_cost_pct": 15, "restricted_third_country_component": False, "components_from_ua_or_eea_efta": False,
           "safe_role": "other_supplier", "applicant_kind": "company_or_research", "handles_classified": False,
           "product_regime": "none", "export_intent": "within_eu"}


@pytest.fixture()
def client(conn):
    readiness_api.reset_cache()
    seed.apply(conn, CONTENT)
    conn.commit()
    with TestClient(api.app) as c:
        yield c


def test_the_database_round_trip_keeps_the_new_content(conn):
    seed.apply(conn, CONTENT)
    conn.commit()
    back = seed.read_content(conn)
    assert set(back.programmes) == set(CONTENT.programmes)
    assert [r.code for r in back.programmes["ES-MOD"].rules] == [r.code for r in CONTENT.programmes["ES-MOD"].rules]
    assert back.requirements["REQ-RID"].extras["question"] == CONTENT.requirements["REQ-RID"].extras["question"]
    assert back.requirements["REQ-PECAL"].extras["roadmap_note"] == CONTENT.requirements["REQ-PECAL"].extras["roadmap_note"]
    hses = next(r for r in back.programmes["ES-MOD"].rules if r.code == "ES-HSES")
    assert hses.texts["consultant"].startswith("HSES path")
    # a second apply inserts nothing
    assert seed.apply(conn, CONTENT)["inserted"] == 0


def test_the_api_answers_a_spanish_automotive_supplier(client):
    r = client.post("/v1/readiness/assess", json={"profile": ES_AUTO, "statuses": {"REQ-ISO9001": "held"}})
    assert r.status_code == 200
    body = r.json()
    es = next(a for a in body["assessments"] if a["programme"] == "ES-MOD")
    assert es["verdict"] == "conditional"
    assert {"field": "REQ-RID", "question": "Does the company hold a current RID certificate (registration or renewal)?"} in es["missing"]
    assert {f["key"] for f in body["consultants"]} >= {"ES-PECAL-CONTRACT", "US-COMPONENTS"}
    pecal = next(s for s in body["roadmap"]["steps"] if s["code"] == "REQ-PECAL")
    assert "nine months" in pecal["note"]
    # marked done in the roadmap: the RID is sent and read
    again = client.post("/v1/readiness/assess", json={"profile": ES_AUTO, "statuses": {"REQ-ISO9001": "held", "REQ-RID": "held"}}).json()
    rid = next(x for a in again["assessments"] if a["programme"] == "ES-MOD" for x in a["rules"] if x["rule"] == "ES-RID")
    assert rid["outcome"] == "met" and rid["consultant"] is None
    # a Polish company does not see the Spanish route; a new answer of the wrong kind is refused
    pl = client.post("/v1/readiness/assess", json={"profile": {**ES_AUTO, "country": "PL", "executive_management_country": "PL"}}).json()
    assert "ES-MOD" not in [a["programme"] for a in pl["assessments"]]
    assert client.post("/v1/readiness/assess", json={"profile": {**ES_AUTO, "de_ausfuhrliste": "part_ii"}}).status_code == 422
    # the public rules carry the new fields and their questions
    fields = client.get("/v1/readiness/programmes").json()["fields"]
    assert fields["foreign_capital"]["question"].startswith("Does a foreign investor hold shares")
    assert client.get("/v1/requirements/REQ-RID").json()["issuers"][0]["country"] == "ES"
