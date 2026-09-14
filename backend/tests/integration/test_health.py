"""The health endpoint must not report ok while nothing is being collected.

A green process with a dead connector is the failure this endpoint exists to
catch, so the cases that matter are the quiet ones: a source that has never
run, and a source whose last success is old.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from dgate import api, db

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _mark_finished(conn, code: str, *, status: str = "success", age_hours: int = 0) -> None:
    run_id = db.start_run(conn, code, expected_min=1)
    db.finish_run(conn, run_id, fetched=100, new=1, changed=0, status=status)
    conn.execute(
        "UPDATE ingest_run SET finished_at = now() - %s::interval, started_at = now() - %s::interval "
        "WHERE id = %s",
        (timedelta(hours=age_hours), timedelta(hours=age_hours), run_id),
    )
    conn.commit()


def test_never_run_source_is_not_reported_healthy(client, conn):
    """The empty database case: no failed runs, because there are no runs."""
    body = client.get("/v1/health").json()
    assert body["status"] == "degraded"
    assert set(body["unhealthy_sources"]) >= {"ted", "es_placsp", "es_placsp_agg", "pl_ezam"}
    assert all(s["status"] == "never_run" for s in body["sources"])


def _active_sources(conn) -> list[str]:
    """Read them from the database rather than hardcoding.

    Adding a source used to break these tests, which is backwards: a new
    connector must not require editing the health tests to stay green.
    """
    return [r["code"] for r in conn.execute(
        "SELECT code FROM source WHERE active ORDER BY code").fetchall()]


def test_all_sources_fresh_is_ok(client, conn):
    for code in _active_sources(conn):
        _mark_finished(conn, code)
    body = client.get("/v1/health").json()
    assert body["status"] == "ok", body["unhealthy_sources"]
    assert body["unhealthy_sources"] == []


def test_stale_success_is_degraded(client, conn):
    """Succeeding once, a week ago, is not health."""
    # ted gets only the old run: the endpoint reads the most recent run per
    # source, so a fresh one would simply hide the stale one.
    for code in _active_sources(conn):
        _mark_finished(conn, code, age_hours=24 * 7 if code == "ted" else 0)
    body = client.get("/v1/health").json()
    assert body["status"] == "degraded"
    assert body["unhealthy_sources"] == ["ted"]
    ted = next(s for s in body["sources"] if s["code"] == "ted")
    assert ted["health"] == "stale"


def test_partial_run_is_degraded(client, conn):
    for code in _active_sources(conn):
        _mark_finished(conn, code)
    run_id = db.start_run(conn, "ted", expected_min=100)
    db.finish_run(conn, run_id, fetched=2, new=0, changed=0)  # under floor
    conn.commit()
    body = client.get("/v1/health").json()
    assert body["status"] == "degraded"
    assert body["unhealthy_sources"] == ["ted"]


def test_archive_depth_is_reported(client, conn):
    body = client.get("/v1/health").json()
    assert "archive_versions" in body
    assert "archive_oldest_observation" in body


# ------------------------------------------------------- scope of the list

def _opp(conn, native_id, *, cpv, buyer, legal=False):
    from datetime import date

    from dgate.normalise import Opportunity
    from dgate.sources.ted import content_hash

    opp = Opportunity(source_code="pl_atlas", native_id=native_id, buyer_name_raw="B",
                      title_original=native_id, country="PL", published_at=date(2024, 5, 1),
                      is_defence=True, sig_cpv=cpv, sig_buyer=buyer, sig_legal_basis=legal)
    src = db.source_id(conn, "pl_atlas")
    db.upsert_opportunity(conn, opp, content_hash(db.opportunity_payload(opp)), src)
    conn.commit()


def test_the_default_list_is_the_core_defence_slice(client, conn):
    """Buyer-only matches became 90% of the slice. They are served on request."""
    _opp(conn, "RATIONS", cpv=True, buyer=False)
    _opp(conn, "UNIFORMS-AT-ARMY", cpv=True, buyer=True)
    _opp(conn, "EGGS-FOR-GARRISON", cpv=False, buyer=True)

    def ids(query=""):
        return sorted(o["native_id"] for o in client.get("/v1/opportunities" + query).json())

    assert ids() == ["RATIONS", "UNIFORMS-AT-ARMY"]
    assert ids("?scope=supply") == ["EGGS-FOR-GARRISON"]
    assert ids("?scope=all") == ["EGGS-FOR-GARRISON", "RATIONS", "UNIFORMS-AT-ARMY"]
    scopes = {o["native_id"]: o["scope"] for o in client.get("/v1/opportunities?scope=all").json()}
    assert scopes == {"RATIONS": "core", "UNIFORMS-AT-ARMY": "core", "EGGS-FOR-GARRISON": "supply"}


def test_an_unknown_scope_is_refused(client):
    assert client.get("/v1/opportunities?scope=everything").status_code == 422
