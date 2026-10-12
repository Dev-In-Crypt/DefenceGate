"""The hardening against a real Postgres: what the API refuses, what it no longer
says, what the service roles cannot do, and what the archive refuses.

The findings behind each test are in docs/SECURITY_REVIEW_2026-10-12.md.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, migrate, pipeline
from dgate.normalise import Opportunity

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _opp(native_id: str = "1-2026", **kw) -> Opportunity:
    base = dict(source_code="ted", native_id=native_id, buyer_name_raw="Ministry of Defence",
                title_original="Supply of ammunition", country="PL",
                published_at=date(2026, 10, 1), cpv_codes=["35300000"], is_defence=True,
                sig_cpv=True)
    return Opportunity(**{**base, **kw})


def _store(conn, opp: Opportunity, digest: str = "h1") -> int:
    opp_id, _ = db.upsert_opportunity(conn, opp, digest, db.source_id(conn, opp.source_code))
    conn.commit()
    return opp_id


# ------------------------------------------------------------ refused input

@pytest.mark.parametrize("query", [
    "limit=-1", "limit=0", "limit=201", "offset=-1", "offset=10001",
    "offset=99999999999999999999", "cpv=" + ",".join(["35"] * 21),
    "cpv=123456789", "country=" + ",".join(["PL"] * 21), "value_min=-1",
])
def test_a_request_outside_the_limits_is_a_422_never_a_query_or_a_500(client, query):
    assert client.get(f"/v1/opportunities?{query}").status_code == 422


def test_funding_refuses_what_it_should_and_serves_the_rest(client):
    assert client.get("/v1/funding?page=99999999999999999999").status_code == 422
    assert client.get("/v1/funding?page=1001").status_code == 422
    assert client.get("/v1/funding?q=" + "a" * 101).status_code == 422
    assert client.get("/v1/funding?currency=EURO").status_code == 422
    assert client.get("/v1/funding?q=%00").status_code == 200       # NUL is dropped, not a 500
    assert client.get("/v1/funding?programme=" + ",".join(["EDF"] * 21)).status_code == 422


def test_an_identifier_out_of_range_or_not_ascii_is_a_404_or_422_not_a_500(client):
    assert client.get("/v1/opportunities/99999999999999999999").status_code == 422
    assert client.get("/v1/opportunities/0").status_code == 422
    assert client.get("/v1/funding/%D9%A3-x").status_code == 404     # an Arabic-Indic digit


def test_the_resolve_oracle_bounds_what_it_echoes(client):
    assert client.get("/v1/organisations/resolve",
                      params={"name": "x" * 201, "country": "PL"}).status_code == 422
    assert client.get("/v1/organisations/resolve",
                      params={"name": "Agencja", "country": "POL"}).status_code == 422


# ---------------------------------------------------------- what is not said

def test_the_documentation_and_the_schema_are_not_published(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_every_response_carries_the_headers_a_json_api_wants(client):
    r = client.get("/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert r.headers["referrer-policy"] == "no-referrer"
    assert client.get("/v1/opportunities?limit=0").headers["cache-control"] == "no-store"


def test_health_says_what_is_wrong_never_why(client, conn):
    src = db.source_id(conn, "ted")
    run_id = db.start_run(conn, "ted", None)
    db.finish_run(conn, run_id, fetched=0, new=0, changed=0, status="failed",
                  error="HTTPStatusError: https://secret-endpoint.example/bucket?token=abc")
    body = client.get("/v1/health").text
    assert "secret-endpoint" not in body and "error_message" not in body
    assert src and client.get("/v1/health").json()["status"] == "degraded"


def test_a_version_snapshot_has_no_notice_text_and_no_address(client, conn):
    opp = _opp(title_original="Supply, contact name@agency.example",
               description="Full notice text. Phone and mail: officer@agency.example")
    opp_id = _store(conn, opp)
    body = client.get(f"/v1/opportunities/{opp_id}/versions").json()
    snapshot = body["versions"][0]["snapshot"]
    assert "description" not in snapshot and "buyer_org_id" not in snapshot
    assert "agency.example" not in client.get(f"/v1/opportunities/{opp_id}/versions").text
    assert "[email removed]" in snapshot["title_original"]


def test_a_stored_title_with_an_address_is_redacted_when_listed(client, conn):
    _store(conn, _opp(title_original="Works, ask old@person.example", status="open",
                      deadline_at=None))
    served = client.get("/v1/opportunities?scope=all").text
    assert "person.example" not in served


def test_the_rate_limit_answers_429_with_a_wait_and_leaves_the_probe_alone(
        client, monkeypatch):
    monkeypatch.setenv("DGATE_RATE_LIMIT", "1")
    config.reset_cache()
    try:
        codes = [client.get("/v1/health").status_code for _ in range(135)]
        assert 429 in codes and codes[0] == 200
        limited = client.get("/v1/health")
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
    finally:
        monkeypatch.setenv("DGATE_RATE_LIMIT", "0")
        config.reset_cache()
        api.app.middleware_stack = None          # the next test builds a fresh stack


# ------------------------------------------------------ the data boundary

def test_a_future_publication_date_is_not_kept_so_later_versions_are_not_dropped(conn):
    opp_id = _store(conn, _opp(published_at=date.today() + timedelta(days=60)), "a")
    assert conn.execute("SELECT published_at FROM opportunity WHERE id = %s",
                        (opp_id,)).fetchone()["published_at"] is None
    changed, action = db.upsert_opportunity(
        conn, _opp(published_at=date(2026, 10, 2), title_original="Supply (amended)"), "b",
        db.source_id(conn, "ted"))
    assert action == "changed"


def test_a_connector_built_spanish_record_is_swept_before_it_lands(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    opp = Opportunity(source_code="es_placsp", native_id="X1", buyer_name_raw="Ayuntamiento",
                      title_original="Suministro, contacto jefe@ayto.example",
                      country="ES", published_at=date(2026, 10, 1), cpv_codes=["35300000"],
                      is_defence=True, sig_cpv=True, description="correo: otro@ayto.example")
    pipeline._ingest_placsp([opp], "es_placsp")
    row = conn.execute("SELECT title_original FROM opportunity").fetchone()
    assert "ayto.example" not in row["title_original"]
    payload = conn.execute("SELECT payload::text p FROM opportunity_version").fetchone()["p"]
    assert "ayto.example" not in payload
    config.reset_cache()


# ------------------------------------------------- roles and the archive

def _as(dsn: str, role: str, password: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(netloc=f"{role}:{password}@{parts.hostname}:{parts.port}"))


@pytest.fixture()
def service_roles(conn, schema, monkeypatch):
    monkeypatch.setenv("DGATE_API_PASSWORD", "api-test-password-1")
    monkeypatch.setenv("DGATE_WORKER_PASSWORD", "worker-test-password-1")
    with db.connect(schema) as admin:
        assert migrate.set_role_passwords(admin) == ["dgate_api", "dgate_worker"]
    return {"api": _as(schema, "dgate_api", "api-test-password-1"),
            "worker": _as(schema, "dgate_worker", "worker-test-password-1")}


def test_the_api_role_reads_and_cannot_write_or_wipe(conn, service_roles):
    _store(conn, _opp())
    with psycopg.connect(service_roles["api"], autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM opportunity").fetchone()[0] == 1
        assert c.execute("SHOW statement_timeout").fetchone()[0] == "5s"
        assert c.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
                         ).fetchone()[0] is False
        for statement in ("UPDATE opportunity SET status = 'x'", "DELETE FROM source",
                          "TRUNCATE opportunity_version",
                          "ALTER TABLE opportunity DISABLE TRIGGER ALL",
                          "CREATE TABLE t (a int)"):
            with pytest.raises(psycopg.Error):
                c.execute(statement)


def test_the_api_role_stops_a_runaway_query_in_five_seconds(conn, service_roles):
    with psycopg.connect(service_roles["api"], autocommit=True) as c:
        with pytest.raises(psycopg.errors.QueryCanceled):
            c.execute("SELECT pg_sleep(30)")


def test_the_worker_role_writes_rows_and_cannot_change_the_schema_or_the_archive(
        conn, service_roles):
    with psycopg.connect(service_roles["worker"], autocommit=True) as c:
        c.execute("SELECT count(*) FROM opportunity").fetchone()
        c.execute("UPDATE source SET update_freq = update_freq WHERE code = 'ted'")
        for statement in ("TRUNCATE opportunity_version", "TRUNCATE opportunity CASCADE",
                          "ALTER TABLE opportunity ADD COLUMN x int",
                          "ALTER TABLE opportunity_version DISABLE TRIGGER ALL",
                          "DROP TABLE call", "CREATE ROLE intruder LOGIN"):
            with pytest.raises(psycopg.Error):
                c.execute(statement)


def test_the_archive_refuses_a_truncate_that_does_not_say_it_means_it(conn):
    _store(conn, _opp())
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("TRUNCATE opportunity_version CASCADE")
    conn.rollback()
    assert conn.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"] == 1


def test_a_version_cannot_close_before_it_opened(conn):
    opp_id = _store(conn, _opp())
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("UPDATE opportunity_version SET valid_to = valid_from - interval '1 day' "
                     "WHERE opportunity_id = %s", (opp_id,))
    conn.rollback()
