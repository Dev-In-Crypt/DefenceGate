"""WP-71 against a real Postgres: the backend fixes of the QA audit of 21 October 2026."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient

from dgate import api, db
from dgate.normalise import EMAIL_PLACEHOLDER, Call, Opportunity
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def client(conn):
    with TestClient(api.app) as c:
        yield c


def _opp(native_id: str = "N1", **kw) -> Opportunity:
    base = dict(source_code="es_placsp", native_id=native_id, buyer_name_raw="Ministerio de Defensa",
                title_original="Suministro", country="ES", status="open", published_at=date(2026, 9, 1))
    base.update(kw)
    return Opportunity(**base)


def _upsert(conn, opp: Opportunity) -> tuple[int, str]:
    src = db.source_id(conn, opp.source_code)
    got = db.upsert_opportunity(conn, opp, content_hash(db.opportunity_payload(opp)), src)
    conn.commit()
    return got


# ------------------------------------------------------------------ H2: /v1/calls/{id}

def _call(conn, native_id: str, source: str, programme: str) -> int:
    call = Call(programme_code=programme, native_id=native_id, title=f"Call {native_id}",
                topic_code=f"{programme}-{native_id}", deadline_at=NOW + timedelta(days=20), status="open",
                regime="defence", eligibility_text="Ask jan.nowak@ncbr.gov.pl for the rules.",
                conditions_raw={"contact": "Write to a.b@bdns.es", "budget": "1 M"})
    db.upsert_call(conn, call, f"hash-{native_id}", db.source_id(conn, source))
    conn.commit()
    return conn.execute("SELECT id FROM call WHERE native_id = %s", (native_id,)).fetchone()["id"]


def test_a_call_serves_its_source_text_only_under_the_licence_gate_and_redacted(client, conn):
    bdns = _call(conn, "B1", "es_bdns", "ES-BDNS")
    portal = _call(conn, "P1", "eu_portal", "HORIZON")
    held = {r["code"]: r["commercial_ok"] for r in conn.execute(
        "SELECT code, commercial_ok FROM source WHERE code IN ('es_bdns', 'eu_portal')").fetchall()}
    try:
        _the_gate(client, conn, bdns, portal)
    finally:                     # `source` is not emptied between tests
        conn.rollback()
        for code, ok in held.items():
            conn.execute("UPDATE source SET commercial_ok = %s WHERE code = %s", (ok, code))
        conn.commit()


def _the_gate(client, conn, bdns: int, portal: int) -> None:
    conn.execute("UPDATE source SET commercial_ok = TRUE WHERE code IN ('es_bdns', 'eu_portal')")
    conn.commit()
    body = client.get(f"/v1/calls/{bdns}").json()
    assert body["eligibility_text"] is None and body["conditions"] is None      # not on the list
    body = client.get(f"/v1/calls/{portal}").json()
    assert body["eligibility_text"] == f"Ask {EMAIL_PLACEHOLDER} for the rules."
    assert body["conditions"] == {"contact": f"Write to {EMAIL_PLACEHOLDER}", "budget": "1 M"}
    conn.execute("UPDATE source SET commercial_ok = NULL WHERE code = 'eu_portal'")   # unknown is not a yes
    conn.commit()
    body = client.get(f"/v1/calls/{portal}").json()
    assert body["eligibility_text"] is None and body["conditions"] is None


def test_a_call_deadline_filter_includes_the_whole_stated_day(client, conn):
    _call(conn, "D1", "eu_portal", "HORIZON")
    conn.execute("UPDATE call SET deadline_at = %s WHERE native_id = 'D1'",
                 (datetime(2030, 3, 5, 17, 0, tzinfo=timezone.utc),))
    conn.commit()
    got = client.get("/v1/calls", params={"status": "all", "deadline_before": "2030-03-05",
                                          "deadline_after": "2030-03-05"}).json()
    assert [c["native_id"] for c in got] == ["D1"]


# ------------------------------------------------------------------ M1: health

def _run(conn, code: str, status: str, *, error: str | None = None, hours: float = 0, finish: bool = True):
    run_id = db.start_run(conn, code, expected_min=None)
    if finish:
        db.finish_run(conn, run_id, fetched=10, new=0, changed=0, status=status, error=error)
    conn.execute("UPDATE ingest_run SET started_at = now() - %s::interval WHERE id = %s",
                 (timedelta(hours=hours), run_id))
    conn.commit()


def _sources(conn) -> list[str]:
    return [r["code"] for r in conn.execute("SELECT code FROM source WHERE active ORDER BY code").fetchall()]


def test_a_run_in_progress_does_not_make_health_degraded(client, conn):
    for code in _sources(conn):
        _run(conn, code, "success", hours=1)
    _run(conn, "es_placsp_agg", "running", finish=False)
    body = client.get("/v1/health").json()
    assert body["status"] == "ok", body["unhealthy_sources"]
    line = next(s for s in body["sources"] if s["code"] == "es_placsp_agg")
    assert line["health"] == "healthy" and "running_since" in line and line["status"] == "success"


def test_a_partial_run_with_a_stated_reason_is_a_warning_and_under_its_floor_unhealthy(client, conn):
    for code in _sources(conn):
        _run(conn, code, "success", hours=1)
    _run(conn, "fr_boamp", "partial", error="2026-10-20: landed 10 of 40 (-30)")
    rid = db.start_run(conn, "ted", expected_min=100)
    db.finish_run(conn, rid, fetched=2, new=0, changed=0)          # under its floor
    body = client.get("/v1/health").json()
    assert body["warning_sources"] == ["fr_boamp"]
    assert body["unhealthy_sources"] == ["ted"] and body["status"] == "degraded"


def test_a_run_nobody_finished_is_unhealthy(client, conn):
    for code in _sources(conn):
        _run(conn, code, "success", hours=1)
    _run(conn, "ted", "running", finish=False, hours=db.STALE_RUN_HOURS + 1)
    assert client.get("/v1/health").json()["unhealthy_sources"] == ["ted"]


# ------------------------------------------------------------------ M3: same-day instants

def test_an_older_entry_of_the_same_day_is_stale_not_current(conn):
    award = _opp(status="awarded", source_updated_at=datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc))
    _upsert(conn, award)
    call = _opp(status="open", title_original="Suministro (call)",
                source_updated_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc))
    assert _upsert(conn, call)[1] == "stale"
    assert conn.execute("SELECT status FROM opportunity").fetchone()["status"] == "awarded"


# ------------------------------------------------------------------ M4: the archive guard

def test_a_closed_version_cannot_be_reopened_or_moved_and_one_version_is_open(conn):
    opp_id, _ = _upsert(conn, _opp())
    _upsert(conn, _opp(status="awarded", published_at=date(2026, 9, 2)))
    first = conn.execute("SELECT id FROM opportunity_version WHERE opportunity_id = %s AND version = 1",
                         (opp_id,)).fetchone()["id"]
    for sql in ("UPDATE opportunity_version SET valid_to = NULL WHERE id = %s",
                "UPDATE opportunity_version SET valid_to = valid_to + interval '1 day' WHERE id = %s"):
        with pytest.raises(psycopg.errors.RaiseException, match="closed version stays closed"):
            conn.execute(sql, (first,))
        conn.rollback()
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("""INSERT INTO opportunity_version (opportunity_id, version, payload, raw_hash, changed_fields)
                        VALUES (%s, 9, '{}', 'x', '{}')""", (opp_id,))
    conn.rollback()


# ------------------------------------------------------------------ the 12 October TED repair path

def test_a_version_written_from_an_old_payload_carries_no_address(conn):
    """ops.repair_ted builds its record from the stored payload of the version before, which predated
    the sweep; append_version wrote its description with the addresses still in it (~113 versions)."""
    from dgate.ops import repair_ted

    opp = _opp(source_code="ted", native_id="1-2026", description="Contact: log.zampub@ron.mil.pl")
    src = db.source_id(conn, "ted")
    # an archive written before the sweep: the first version holds the address
    conn.execute("ALTER TABLE opportunity_version DISABLE TRIGGER opportunity_version_append_only")
    opp_id, _ = db.upsert_opportunity(conn, replace(opp), "h1", src)
    conn.execute("UPDATE opportunity_version SET payload = jsonb_set(payload, '{description}', %s::jsonb)",
                 ('"Contact: log.zampub@ron.mil.pl"',))
    conn.execute("ALTER TABLE opportunity_version ENABLE TRIGGER opportunity_version_append_only")
    conn.commit()
    row = repair_ted._state(conn, src, ["1-2026"])["1-2026"]
    change = repair_ted.plan_change(row["v_payload"], row, replace(opp, status="awarded"), ["status"])
    repair_ted.apply_change(conn, row["id"], row["v_version"], "h2", change, "raw")
    conn.commit()
    latest = conn.execute("SELECT payload FROM opportunity_version WHERE opportunity_id = %s AND version = 2",
                          (opp_id,)).fetchone()["payload"]
    assert latest["description"] == f"Contact: {EMAIL_PLACEHOLDER}" and latest["status"] == "awarded"


def test_the_restrip_dry_run_finds_the_archived_address_and_writes_nothing(conn, tmp_path):
    from dgate.ops import restrip

    opp_id, _ = _upsert(conn, _opp(source_code="ted", native_id="2-2026"))
    conn.execute("ALTER TABLE opportunity_version DISABLE TRIGGER opportunity_version_append_only")
    conn.execute("UPDATE opportunity_version SET payload = jsonb_set(payload, '{description}', %s::jsonb)",
                 ('"x@mil.fi"',))
    conn.execute("ALTER TABLE opportunity_version ENABLE TRIGGER opportunity_version_append_only")
    conn.commit()
    counts, plan = restrip.plan_archive(conn)
    assert counts["to_redact"] == 1 and counts["to_redact_ted"] == 1
    sql = restrip.break_glass_sql(plan)
    assert "x@mil.fi" not in sql
    assert conn.execute("SELECT payload->>'description' AS d FROM opportunity_version").fetchone()["d"] == "x@mil.fi"
    # the prepared statement, run as the owner would, redacts exactly that row
    conn.execute(sql.replace("BEGIN;", "").replace("COMMIT;", ""))
    assert conn.execute("SELECT payload->>'description' AS d FROM opportunity_version").fetchone()["d"] \
        == EMAIL_PLACEHOLDER
    assert conn.execute("SELECT tgenabled FROM pg_trigger WHERE tgname = 'opportunity_version_append_only'"
                        ).fetchone()["tgenabled"] == "O"
    conn.rollback()


# ------------------------------------------------------------------ M8: the error shape

def test_a_hand_raised_refusal_answers_in_the_contracts_shape(client):
    r = client.get("/v1/opportunities", params={"country": ",".join(["DE"] * 30)})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list) and set(detail[0]) == {"loc", "msg", "type"}
    assert "at most" in detail[0]["msg"]
    assert client.get("/v1/opportunities/99999999").status_code == 404      # other statuses unchanged
