"""WP-99 (persona round of 23 October 2026, D: funding and eligibility), against a real Postgres. No network and no model."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dgate import api, stats
from dgate.readiness import api as readiness_api
from tests.integration import test_wp32 as wp32
from tests.integration.test_wp91 import projects  # noqa: F401  (the fixture of the Ukraine partners)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    readiness_api.reset_cache()
    yield
    stats.reset_cache()
    readiness_api.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def test_the_ukraine_partners_table_can_be_narrowed_by_a_keyword(client, projects):  # noqa: F811
    every = client.get("/v1/analytics/ukraine-partners?since=2021").json()
    assert {c["organisation"]["name"] for c in every["coordinators"]} == {"AIR FRAME SAS", "CIVIL UNIVERSITY"} and every["q"] is None
    maps = client.get("/v1/analytics/ukraine-partners", params={"since": 2021, "q": "maps"}).json()
    assert [c["organisation"]["name"] for c in maps["coordinators"]] == ["CIVIL UNIVERSITY"] and maps["q"] == ["maps"]
    assert maps["totals"]["projects"] == 1, "only the project whose title has the word"
    assert client.get("/v1/analytics/ukraine-partners", params={"since": 2021, "q": "sensing border"}).json()["coordinators"][0][
        "organisation"]["name"] == "AIR FRAME SAS"
    assert client.get("/v1/analytics/ukraine-partners", params={"since": 2021, "q": "radar"}).json()["coordinators"] == []


def test_a_digital_europe_cyber_call_gets_partners_from_earlier_cybersecurity_projects(conn, client):
    cs = [wp32.project(conn, f"cs{i}", edf=False, topic=f"HORIZON-CL3-2022-CS-01-0{i}", year=2023, title=f"Cyber range {i}") for i in range(2)]
    other = wp32.project(conn, "bm", edf=False, topic="HORIZON-CL3-2022-BM-01-01", year=2023, title="Border sensing")
    orgs = [wp32.org(conn, n, cc) for n, cc in (("Thales SIX", "FR"), ("Naval Group", "FR"), ("HarfangLab", "FR"),
                                               ("Cyber GmbH", "DE"), ("Secure SL", "ES"), ("Border Corp", "PL"))]
    for o in orgs[:5]:
        for p in cs:
            wp32.join(conn, p, o)
    wp32.join(conn, other, orgs[5])
    conn.commit()
    _, slug = wp32.call(conn, "ncc", "DIGITAL-ECCC-2027-DEPLOY-CYBER-11-NCC", programme="DIGITAL")
    body = wp32.partners(client, slug)
    assert body["area"]["kind"] == "cyber" and "Horizon Europe cybersecurity calls" in body["area"]["rule"]
    names = {p["name"] for p in body["partners"]}
    assert {"Thales SIX", "Naval Group", "HarfangLab"} <= names and "Border Corp" not in names
    assert client.get(f"/v1/funding/{slug}").json()["partnerArea"].startswith("earlier EU cybersecurity projects")
    # a Digital Europe call of another subject still has none, and says so
    _, ai = wp32.call(conn, "ai", "DIGITAL-2026-AI-09-DS-HEALTH-TOOL", programme="DIGITAL")
    assert wp32.partners(client, ai)["area"] is None


def test_a_call_only_for_designated_bodies_is_served_as_designated(conn, client):
    _, slug = wp32.call(conn, "hub", "DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH", programme="DIGITAL")
    conn.execute("UPDATE call SET who_may_apply_doc = 'designated' WHERE topic_code = 'DIGITAL-ECCC-2027-DEPLOY-CYBER-12-NATCH'")
    conn.commit()
    assert client.get(f"/v1/funding/{slug}").json()["whoMayApply"] == "designated"
    listed = client.get("/v1/funding", params={"status": "all", "who": "companies"}).json()
    assert all(c["whoMayApply"] == "companies" for c in listed["items"]), "the filter keeps its two values"
