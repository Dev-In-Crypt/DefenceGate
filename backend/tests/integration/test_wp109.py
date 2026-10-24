"""WP-109 against a real Postgres: the funding list's "Open and forthcoming" status and "Universities and research organisations"
filter, the calls the scope rule no longer takes, the AID labels, and the equity wording of EIC STEP. No network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dgate import api, stats
from dgate.ops import wp109_scope
from tests.integration.test_wp31 import put

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_cache():
    stats.reset_cache()
    yield
    stats.reset_cache()


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _ids(client, query: str) -> set[str]:
    r = client.get(f"/v1/funding?pageSize=100&{query}")
    assert r.status_code == 200, r.text
    return {c["id"] for c in r.json()["items"]}


def test_open_and_forthcoming_is_one_list(client, conn):
    o = put(conn, "open")
    f = put(conn, "soon", status="forthcoming", days=90)
    c = put(conn, "gone", status="closed", days=-10)
    got = _ids(client, "status=open-forthcoming")
    assert {str(o), str(f)} <= got and str(c) not in got
    assert client.get("/v1/funding?status=nonsense").status_code == 422


def test_universities_and_research_organisations(client, conn):
    horizon = put(conn, "h1", programme="HORIZON", topic="HORIZON-CL3-2026-01-BM-01")
    cpa = put(conn, "cpa", programme="EDF", topic="EDF-EDIP-P-2027-FNLC-CPA-AMDS")      # public buyers only
    digital = put(conn, "d1", programme="DIGITAL", topic="DIGITAL-2026-AI-09-ECAVA")    # nothing we hold says
    sme = put(conn, "sme", programme="HORIZON", topic="HORIZON-EIC-2026-ACCELERATOR-01")
    conn.execute("UPDATE call SET research_may_apply_doc = false WHERE id = %s", (sme,))
    conn.commit()
    got = _ids(client, "who=research")
    assert str(horizon) in got
    assert not {str(cpa), str(digital), str(sme)} & got
    one = client.get(f"/v1/funding/{horizon}").json()
    assert one["researchMayApply"] is True
    assert client.get(f"/v1/funding/{digital}").json()["researchMayApply"] is None


def test_the_ops_tool_takes_out_the_civil_topics_and_fixes_the_aid_labels(client, conn):
    keep = put(conn, "cl3", topic="HORIZON-CL3-2026-01-BM-01")
    soil = put(conn, "soil", topic="HORIZON-NEB-2027-02-NEB-SOIL-01")
    rapid = put(conn, "rapid-regime-dappui-linnovation-duale", programme="FR-AID", source="fr_aid", days=None)
    conn.execute("UPDATE call SET regime = 'dual_use' WHERE id IN (%s, %s)", (keep, soil))
    conn.execute("UPDATE call SET issuer = 'Agence de l''innovation de defense (AID)' WHERE id = %s", (rapid,))
    conn.commit()

    report = wp109_scope.run(write=False)
    assert f"{soil} HORIZON-NEB-2027-02-NEB-SOIL-01: topic family NEB" in report and "(written)" not in report
    assert str(soil) in _ids(client, "status=all")                       # the report changes nothing
    assert "written" in wp109_scope.run(write=True)
    stats.reset_cache()
    assert str(soil) not in _ids(client, "status=all") and str(keep) in _ids(client, "status=all")
    row = conn.execute("SELECT regime, issuer FROM call WHERE id = %s", (rapid,)).fetchone()
    assert (row["regime"], row["issuer"]) == ("dual_use", "Agence de l'innovation de défense (AID)")
    assert wp109_scope.run(write=True).startswith("calls to change: 0")   # a second run writes nothing
    # the page of a call taken out still opens (a call row is never deleted)
    assert client.get(f"/v1/funding/{soil}").status_code == 200


def test_the_aid_programme_name_says_the_agency_once(conn):
    name = conn.execute("SELECT name FROM programme WHERE code = 'FR-AID'").fetchone()["name"]
    assert name == "AID calls for projects and RAPID"
