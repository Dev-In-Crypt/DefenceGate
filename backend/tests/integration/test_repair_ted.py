"""The TED repair and the daily run's coverage check, against a real Postgres.

What is asserted is what must hold for an append-only archive: a correction is a
new version annotated `remapped`, the archive trigger is never touched, a second
run writes nothing, and a remapped version is not shown as the source's amendment.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dgate import api, config, db, pipeline
from dgate.normalise import from_ted, strip_personal_data
from dgate.ops import repair_ted
from dgate.rawstore import build_store, storage_key
from dgate.sources import ted
from tests.integration.test_accounts import H, client, sent, sign_in  # noqa: F401

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ted_live_notices_2026_10.json"
LIVE = {n["publication-number"]: n for n in json.loads(FIXTURE.read_text(encoding="utf-8"))}
REQUESTED_LATER = ("publication-date", "deadline-receipt-request", "deadline-receipt-request-time-lot",
                   "procedure-type", "total-value", "total-value-cur", "result-value-notice",
                   "result-value-cur-notice", "winner-selection-status", "procedure-identifier")


@pytest.fixture
def fs_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield tmp_path / "raw"
    config.reset_cache()


@pytest.fixture
def no_floor(monkeypatch):
    """The coverage floor is for real feeds; these runs hold a handful of notices."""
    monkeypatch.setenv("DGATE_FLOOR_TED", "0")
    config.reset_cache()
    yield
    config.reset_cache()


@pytest.fixture(autouse=True)
def clean_markers(conn):
    conn.execute("DELETE FROM ted_repair_marker")
    conn.commit()


def seed_old(conn, pub: str, *, status="open") -> int:
    """A notice as it was stored before the correction: the payload landed without
    the later-requested fields, the row mapped by the old rules (open, dispatch
    date, numeric subtype, the deadline from the date field alone), and the signals
    set by classification."""
    raw = {k: v for k, v in strip_personal_data(LIVE[pub]).items() if k not in REQUESTED_LATER}
    digest = ted.content_hash(raw)
    src = db.source_id(conn, "ted")
    key = build_store().put(storage_key("ted", pub, content_hash=digest), raw)
    db.record_raw(conn, src, pub, digest, key)
    new = from_ted(raw)
    old = replace(new, status=status, status_native=None, procedure_type=new.notice_subtype,
                  notice_subtype=None, lot_count=None, value_kind=None,
                  procedure_identifier=None, is_defence=True, sig_cpv=True)
    opp_id, action = db.upsert_opportunity(conn, old, digest, src)
    assert action == "new"
    conn.commit()
    return opp_id


def versions(conn, opp_id: int) -> list[dict]:
    return conn.execute(
        """SELECT v.version, v.changed_fields, v.raw_hash, v.valid_to, v.payload,
                  array_remove(array_agg(n.kind), NULL) AS kinds
             FROM opportunity_version v
             LEFT JOIN opportunity_version_note n ON n.opportunity_version_id = v.id
            WHERE v.opportunity_id = %s GROUP BY v.id ORDER BY v.version""",
        (opp_id,)).fetchall()


def row(conn, opp_id: int) -> dict:
    return conn.execute("SELECT * FROM opportunity WHERE id = %s", (opp_id,)).fetchone()


# ---------------------------------------------------------------- --from-raw

def test_a_dry_run_writes_nothing(conn, fs_store):
    oid = seed_old(conn, "534116-2026")
    result = repair_ted.run("raw", write=False)
    assert result.versions == 1
    assert row(conn, oid)["status"] == "open"
    assert len(versions(conn, oid)) == 1
    assert conn.execute("SELECT count(*) AS n FROM ted_repair_marker").fetchone()["n"] == 0


def test_from_raw_appends_a_remapped_version_and_a_second_run_writes_nothing(conn, fs_store):
    oid = seed_old(conn, "534116-2026")
    other = seed_old(conn, "536788-2026")

    first = repair_ted.run("raw", write=True)
    assert (first.examined, first.versions, first.failed) == (2, 2, 0)

    got = versions(conn, oid)
    assert [v["version"] for v in got] == [1, 2]
    assert got[1]["changed_fields"] == ["status"]
    assert got[1]["kinds"] == ["remapped"]
    assert got[0]["valid_to"] is not None and got[1]["valid_to"] is None
    served = row(conn, oid)
    assert (served["status"], served["status_native"], served["current_version"]) == (
        "awarded", "can-standard", 2)
    assert served["notice_subtype"] == "31"
    assert served["is_defence"] is True and served["sig_cpv"] is True, "signals are carried"
    assert row(conn, other)["status"] == "awarded"

    again = repair_ted.run("raw", write=True)
    assert again.examined == 0, "every notice is marked done"
    conn.execute("DELETE FROM ted_repair_marker")
    conn.commit()
    compared = repair_ted.run("raw", write=True)
    assert (compared.examined, compared.versions, compared.direct) == (2, 0, 0), \
        "with the markers gone it is still idempotent: the states already agree"
    assert len(versions(conn, oid)) == 2


def test_from_raw_leaves_what_the_payload_cannot_say(conn, fs_store):
    oid = seed_old(conn, "534116-2026")
    before = row(conn, oid)
    repair_ted.run("raw", write=True)
    after = row(conn, oid)
    for column in ("published_at", "procedure_type", "value_amount", "deadline_at", "country"):
        assert after[column] == before[column], column


def test_an_unchanged_live_notice_gets_attributes_and_no_version(conn, fs_store):
    # A cn-standard that is open and whose versioned fields already agree: only
    # the attribute columns are filled, which is not a version.
    oid = seed_old(conn, "554343-2026")
    result = repair_ted.run("raw", write=True)
    assert result.versions == 0
    assert len(versions(conn, oid)) == 1
    served = row(conn, oid)
    assert served["notice_subtype"] == "18" and served["status_native"] == "cn-standard"
    assert served["lot_count"] == 2


def test_the_archive_guard_is_still_there_after_a_repair(conn, fs_store):
    oid = seed_old(conn, "534116-2026")
    repair_ted.run("raw", write=True)
    enabled = conn.execute(
        """SELECT tgenabled FROM pg_trigger
            WHERE tgrelid = 'opportunity_version'::regclass AND NOT tgisinternal""").fetchall()
    assert enabled and all(t["tgenabled"] == "O" for t in enabled)
    with pytest.raises(Exception, match="append-only|not permitted|only"):
        conn.execute("UPDATE opportunity_version SET payload = '{}' WHERE opportunity_id = %s",
                     (oid,))
    conn.rollback()


# ---------------------------------------------------------------- --refetch

def _serve(monkeypatch, notices: list[dict]) -> list[str]:
    queries: list[str] = []

    def fake_search(query, *args, **kwargs):
        queries.append(query)
        return iter(notices)

    monkeypatch.setattr(ted, "search", fake_search)
    return queries


def test_refetch_corrects_every_field_lands_the_payload_and_is_idempotent(
        conn, fs_store, monkeypatch):
    oid = seed_old(conn, "93334-2024")
    queries = _serve(monkeypatch, [LIVE["93334-2024"]])
    result = repair_ted.run_refetch(conn, ["93334-2024"], write=True, client=object(), pause=0)

    assert queries == ["publication-number IN (93334-2024)"]
    assert (result.examined, result.versions, result.requests) == (1, 1, 1)
    got = versions(conn, oid)
    assert got[1]["kinds"] == ["remapped"]
    assert set(got[1]["changed_fields"]) == {"procedure_type", "published_at", "deadline_at"}
    served = row(conn, oid)
    assert served["procedure_type"] == "restricted"
    assert served["published_at"] == date(2024, 2, 14)
    assert served["deadline_at"] == datetime(2024, 3, 22, 7, 0, tzinfo=timezone.utc)
    assert (served["value_kind"], served["lot_count"]) == ("estimated", 1)
    assert served["procedure_identifier"] == "c3c8137c-d92b-4f7f-8175-36decaf1451d"

    # The new payload is in the raw index, under the hash the next daily run computes.
    digest = ted.content_hash(strip_personal_data(LIVE["93334-2024"]))
    assert conn.execute("SELECT count(*) AS n FROM raw_ingest WHERE content_hash = %s",
                        (digest,)).fetchone()["n"] == 1
    assert got[1]["raw_hash"] == digest

    # A daily run that meets the same payload finds nothing to do.
    src = db.source_id(conn, "ted")
    _, action = db.upsert_opportunity(conn, from_ted(strip_personal_data(LIVE["93334-2024"])),
                                      digest, src)
    assert action == "unchanged"

    # And a second refetch, markers or not, writes nothing.
    conn.execute("DELETE FROM ted_repair_marker")
    conn.commit()
    again = repair_ted.run_refetch(conn, ["93334-2024"], write=True, client=object(), pause=0)
    assert (again.versions, again.direct, again.unchanged) == (0, 0, 1)
    assert len(versions(conn, oid)) == 2


def test_refetch_reports_a_number_the_source_no_longer_has(conn, fs_store, monkeypatch):
    seed_old(conn, "93334-2024")
    _serve(monkeypatch, [])
    result = repair_ted.run_refetch(conn, ["93334-2024"], write=True, client=object(), pause=0)
    assert (result.missing, result.versions) == (1, 0)
    assert conn.execute("SELECT count(*) AS n FROM ted_repair_marker").fetchone()["n"] == 0


def test_refetch_stops_on_a_refusal_and_keeps_what_it_did(conn, fs_store, monkeypatch):
    import httpx

    seed_old(conn, "93334-2024")
    second = seed_old(conn, "534116-2026")
    calls = {"n": 0}

    def fake_search(query, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return iter([LIVE["93334-2024"]])
        response = httpx.Response(429, request=httpx.Request("POST", ted.TED_SEARCH_URL))
        raise httpx.HTTPStatusError("rate limited", request=response.request, response=response)

    monkeypatch.setattr(ted, "search", fake_search)
    result = repair_ted.run_refetch(conn, ["93334-2024", "534116-2026"], write=True,
                                    batch=1, client=object(), pause=0)
    assert result.stopped == "HTTP 429 from TED"
    assert result.versions == 1
    assert row(conn, second)["status"] == "open"
    done = {r["native_id"] for r in conn.execute("SELECT native_id FROM ted_repair_marker")}
    assert done == {"93334-2024"}, "the second notice is left for the rerun"


# --------------------------------------------- what a client reads from it

def test_a_remapped_version_is_not_an_amendment(conn, fs_store):
    oid = seed_old(conn, "534116-2026")
    repair_ted.run("raw", write=True)
    with TestClient(api.app) as c:
        body = c.get(f"/v1/opportunities/{oid}/versions").json()
    assert body["version_count"] == 2
    assert body["amended"] is False
    assert body["versions"][1]["notes"][0]["kind"] == "remapped"


def test_a_real_amendment_after_a_remap_is_still_an_amendment(conn, fs_store):
    oid = seed_old(conn, "554343-2026")
    repair_ted.run("raw", write=True)
    src = db.source_id(conn, "ted")
    moved = replace(from_ted(strip_personal_data(LIVE["554343-2026"])), is_defence=True,
                    deadline_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert db.upsert_opportunity(conn, moved, "later-hash", src) == (oid, "changed")
    conn.commit()
    with TestClient(api.app) as c:
        assert c.get(f"/v1/opportunities/{oid}/versions").json()["amended"] is True


def test_the_dashboard_does_not_report_a_remap_as_a_change(client, sent, conn, fs_store):  # noqa: F811
    oid = seed_old(conn, "534116-2026")
    session, _ = sign_in(client, sent)
    client.put(f"/v1/account/shortlist/tender/{oid}", headers=H(session),
               json={"status": "watching"})
    client.get("/v1/account/dashboard", headers=H(session))      # sets the baseline
    repair_ted.run("raw", write=True)
    board = client.get("/v1/account/dashboard", headers=H(session)).json()
    assert board["changes"] == []


# ------------------------------------------------- the daily run's coverage

def _notice(number: str, notice_type: str | None) -> dict:
    n = {"publication-number": [number], "notice-title": {"eng": "Supply"},
         "buyer-name": {"eng": ["Ministry of Defence"]}, "buyer-country": ["DEU"],
         "official-language": ["eng"], "dispatch-date": ["2026-10-09+02:00"],
         "publication-date": ["2026-10-12+02:00"], "classification-cpv": ["35700000"],
         "legal-basis": ["32009L0081"]}
    if notice_type:
        n["notice-type"] = notice_type
    return n


def test_a_daily_run_with_an_unmapped_notice_type_is_partial_and_names_it(
        conn, fs_store, no_floor, monkeypatch):
    notices = [_notice("1-2026", "cn-standard"), _notice("2-2026", "brand-new-type"),
               _notice("3-2026", "brand-new-type"), _notice("4-2026", None)]
    monkeypatch.setattr(ted, "fetch_window", lambda days_back=2: iter(notices))
    pipeline.run_ted(days=2)

    run = conn.execute("SELECT status, error_message FROM ingest_run ORDER BY id DESC").fetchone()
    assert run["status"] == "partial"
    assert "brand-new-type (2)" in run["error_message"] and "(none) (1)" in run["error_message"]
    rows = {r["native_id"]: r["status"] for r in conn.execute(
        "SELECT native_id, status FROM opportunity")}
    assert rows == {"1-2026": "open", "2-2026": "unknown", "3-2026": "unknown",
                    "4-2026": "unknown"}, "an unmapped type is stored unknown, never open"


def test_a_daily_run_of_known_types_is_a_success(conn, fs_store, no_floor, monkeypatch):
    notices = [_notice("1-2026", "cn-standard"), _notice("2-2026", "can-standard"),
               _notice("3-2026", "pin-only")]
    monkeypatch.setattr(ted, "fetch_window", lambda days_back=2: iter(notices))
    pipeline.run_ted(days=2)
    run = conn.execute("SELECT status, error_message FROM ingest_run ORDER BY id DESC").fetchone()
    assert run["status"] == "success", run["error_message"]
    rows = {r["native_id"]: (r["status"], r["published_at"]) for r in conn.execute(
        "SELECT native_id, status, published_at FROM opportunity")}
    assert rows == {"1-2026": ("open", date(2026, 10, 12)),
                    "2-2026": ("awarded", date(2026, 10, 12)),
                    "3-2026": ("forthcoming", date(2026, 10, 12))}


def test_whole_days_are_landed_and_classification_decides_and_a_rerun_changes_nothing(
        conn, fs_store, no_floor, monkeypatch):
    """Today and yesterday are asked for in full, so a notice the defence query
    did not return is still seen the morning it is published."""
    today = date.today()
    only_in_the_day = _notice("2-2026", "cn-standard")
    civil = {**_notice("3-2026", "cn-standard"), "classification-cpv": ["30200000"],
             "legal-basis": ["32014L0024"]}
    answers = {
        ted.defence_query(today - timedelta(days=2), today): [_notice("1-2026", "cn-standard")],
        ted.day_query(today): [only_in_the_day, civil],
        ted.day_query(today - timedelta(days=1)): [_notice("1-2026", "cn-standard")],
    }
    asked: list[str] = []

    def fake_search(query, *args, **kwargs):
        asked.append(query)
        return iter(answers[query])

    monkeypatch.setattr(ted, "search", fake_search)

    def state():
        return (conn.execute("SELECT native_id, current_version FROM opportunity "
                             "ORDER BY native_id").fetchall(),
                conn.execute("SELECT count(*) AS n FROM opportunity_version").fetchone()["n"])

    pipeline.run_ted(days=2)
    rows, n_versions = state()
    assert [r["native_id"] for r in rows] == ["1-2026", "2-2026"], "the civil one is not kept"
    assert asked == list(answers)
    run = conn.execute("SELECT status, records_fetched FROM ingest_run").fetchone()
    assert run["status"] == "success"
    assert run["records_fetched"] == 1, "the floor counts the defence query only"
    landed = {r["native_id"] for r in conn.execute("SELECT native_id FROM raw_ingest")}
    assert landed == {"1-2026", "2-2026", "3-2026"}, "everything fetched is landed"

    pipeline.run_ted(days=2)
    assert state() == (rows, n_versions), "a second run adds no version and moves no row"


def test_a_status_correction_arrives_as_a_version_through_the_daily_path(conn, fs_store):
    src = db.source_id(conn, "ted")
    raw = _notice("9-2026", "can-standard")
    first = {k: v for k, v in raw.items() if k != "notice-type"}
    opp = replace(from_ted(first), is_defence=True, status="open")
    oid, action = db.upsert_opportunity(conn, opp, ted.content_hash(first), src)
    assert action == "new"
    corrected = replace(from_ted(raw), is_defence=True)
    assert corrected.status == "awarded"
    assert db.upsert_opportunity(conn, corrected, ted.content_hash(raw), src) == (oid, "changed")
    assert db.upsert_opportunity(conn, corrected, ted.content_hash(raw), src) == (oid, "unchanged")
    assert [v["changed_fields"] for v in versions(conn, oid)][1] == ["status"]
