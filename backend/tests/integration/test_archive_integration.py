"""The archive behaviour, against a real Postgres.

This is the test that matters most. If versioning is wrong, the moat is
imaginary.

Ported from the original standalone script (plan task M0-08): no hardcoded
paths, no import-time connection, one clean database per test, and the checks
expressed as individual test functions so a failure names itself.
"""

from __future__ import annotations

import pytest

from dgate import db
from dgate.normalise import from_ted, strip_personal_data
from dgate.pipeline import _finalise, seed_buyers
from dgate.sources.ted import content_hash

pytestmark = pytest.mark.integration

NOTICE = {
    "notice-identifier": ["00512345-2026"],
    "notice-title": {"spa": "Suministro de equipos de comunicaciones tacticas"},
    "buyer-name": {"spa": ["Ministerio de Defensa"]},
    "buyer-country": ["ESP"],
    "official-language": ["spa"],
    "dispatch-date": ["2026-08-14+02:00"],
    "deadline-receipt-tender-date-lot": ["2026-10-02+02:00"],
    "deadline-receipt-tender-time-lot": ["12:00:00+02:00"],
    "classification-cpv": ["35700000"],
    "estimated-value-lot": ["4200000"],
    "estimated-value-cur-lot": ["EUR"],
    "legal-basis": ["32009L0081"],
    "buyer-email": ["contacto@example.es"],
    "buyer-person": ["Juan Perez"],
}


def ingest(conn, notice: dict) -> tuple[int, str]:
    """Land, normalise, classify, archive. The pipeline's ordering rule."""
    src = db.source_id(conn, "ted")
    clean = strip_personal_data(notice)
    h = content_hash(clean)
    opp = _finalise(conn, from_ted(clean), src)
    result = db.upsert_opportunity(conn, opp, h, src)
    conn.commit()
    return result


@pytest.fixture()
def seeded(conn):
    seed_buyers()
    return conn


@pytest.fixture()
def amended(seeded):
    """One notice ingested, then re-ingested with a later deadline and value."""
    oid, _ = ingest(seeded, NOTICE)
    changed = dict(NOTICE)
    changed["deadline-receipt-tender-date-lot"] = ["2026-10-16+02:00"]
    changed["estimated-value-lot"] = ["4600000"]
    ingest(seeded, changed)
    return seeded, oid


# ------------------------------------------------------------- versioning

def test_first_ingest_creates_version_1(seeded):
    oid, action = ingest(seeded, NOTICE)
    assert action == "new"
    row = seeded.execute(
        "SELECT version FROM opportunity_version WHERE opportunity_id=%s", (oid,)
    ).fetchone()
    assert row["version"] == 1


def test_reingesting_unchanged_notice_creates_no_new_version(seeded):
    oid, _ = ingest(seeded, NOTICE)
    oid2, action = ingest(seeded, NOTICE)
    assert action == "unchanged"
    assert oid == oid2, "the same notice must not create a second opportunity"
    count = seeded.execute(
        "SELECT count(*) n FROM opportunity_version WHERE opportunity_id=%s", (oid,)
    ).fetchone()["n"]
    assert count == 1


def test_amended_notice_creates_a_second_version(amended):
    conn, oid = amended
    versions = conn.execute(
        "SELECT version FROM opportunity_version WHERE opportunity_id=%s ORDER BY version",
        (oid,),
    ).fetchall()
    assert [v["version"] for v in versions] == [1, 2]


def test_changed_fields_names_what_changed_and_nothing_else(amended):
    conn, oid = amended
    row = conn.execute(
        "SELECT changed_fields FROM opportunity_version WHERE opportunity_id=%s AND version=2",
        (oid,),
    ).fetchone()
    changed = set(row["changed_fields"])
    assert "deadline_at" in changed
    assert "value_amount" in changed
    assert "title_original" not in changed


def test_previous_version_is_closed_and_current_is_open(amended):
    conn, oid = amended
    rows = conn.execute(
        "SELECT version, valid_to FROM opportunity_version WHERE opportunity_id=%s ORDER BY version",
        (oid,),
    ).fetchall()
    assert rows[0]["valid_to"] is not None, "the superseded version must be closed"
    assert rows[1]["valid_to"] is None, "the current version must stay open"


def test_serving_row_reflects_the_latest_version(amended):
    conn, oid = amended
    row = conn.execute("SELECT * FROM opportunity WHERE id=%s", (oid,)).fetchone()
    assert float(row["value_amount"]) == 4600000.0
    assert row["current_version"] == 2


def test_deadline_is_stored_with_its_offset(seeded):
    """A naive datetime would be read in the server's timezone (plan task M0-04)."""
    oid, _ = ingest(seeded, NOTICE)
    row = seeded.execute(
        "SELECT deadline_at AT TIME ZONE 'UTC' AS utc FROM opportunity WHERE id=%s", (oid,)
    ).fetchone()
    assert row["utc"].hour == 10, "12:00+02:00 must land at 10:00 UTC, not 12:00"


# ---------------------------------------------------------- classification

def test_classified_as_defence_with_separate_signals(seeded):
    oid, _ = ingest(seeded, NOTICE)
    row = seeded.execute("SELECT * FROM opportunity WHERE id=%s", (oid,)).fetchone()
    assert row["is_defence"] is True
    assert row["sig_legal_basis"] is True
    assert row["sig_buyer"] is True, "the seeded buyer list must have matched"
    assert row["sig_cpv"] is True


def test_status_defaults_to_open_and_is_persisted(seeded):
    oid, _ = ingest(seeded, NOTICE)
    row = seeded.execute("SELECT status FROM opportunity WHERE id=%s", (oid,)).fetchone()
    assert row["status"] == "open"


# ---------------------------------------------------------- personal data

def test_no_personal_data_in_the_serving_row(seeded):
    oid, _ = ingest(seeded, NOTICE)
    row = seeded.execute("SELECT * FROM opportunity WHERE id=%s", (oid,)).fetchone()
    blob = " ".join(str(v) for v in row.values())
    assert "Juan Perez" not in blob
    assert "contacto@" not in blob


def test_no_personal_data_in_archive_payloads(amended):
    conn, oid = amended
    rows = conn.execute(
        "SELECT payload::text t FROM opportunity_version WHERE opportunity_id=%s", (oid,)
    ).fetchall()
    assert rows, "the archive must not be empty"
    for r in rows:
        assert "Juan Perez" not in r["t"]
        assert "contacto@" not in r["t"]


# ------------------------------------------------------ entity resolution

def test_buyer_resolves_to_one_canonical_organisation(seeded):
    ingest(seeded, NOTICE)
    row = seeded.execute(
        """SELECT o.id, o.is_defence_buyer, count(a.id) aliases
             FROM organisation o
             LEFT JOIN organisation_alias a ON a.organisation_id = o.id
            WHERE o.canonical_name = 'ministerio de defensa' AND o.country = 'ES'
            GROUP BY o.id, o.is_defence_buyer"""
    ).fetchone()
    assert row is not None, "the buyer must have been resolved"
    assert row["is_defence_buyer"] is True
    assert row["aliases"] >= 1, "every resolution must leave an alias behind"


def test_buyer_org_id_is_persisted_on_the_opportunity(seeded):
    """Regression: resolution used to be computed and then silently discarded."""
    oid, _ = ingest(seeded, NOTICE)
    row = seeded.execute(
        "SELECT buyer_org_id FROM opportunity WHERE id=%s", (oid,)
    ).fetchone()
    assert row["buyer_org_id"] is not None


# ------------------------------------------------------------ operations

def test_run_below_its_floor_is_partial_not_success(conn):
    run_id = db.start_run(conn, "ted", expected_min=100)
    db.finish_run(conn, run_id, fetched=3, new=1, changed=0)
    row = conn.execute(
        "SELECT status, error_message FROM ingest_run WHERE id=%s", (run_id,)
    ).fetchone()
    assert row["status"] == "partial"
    assert "floor" in (row["error_message"] or "")


def test_run_above_its_floor_is_success(conn):
    run_id = db.start_run(conn, "ted", expected_min=2)
    db.finish_run(conn, run_id, fetched=10, new=10, changed=0)
    row = conn.execute("SELECT status FROM ingest_run WHERE id=%s", (run_id,)).fetchone()
    assert row["status"] == "success"


def test_both_placsp_datasets_are_registered_as_sources(conn):
    codes = {r["code"] for r in conn.execute("SELECT code FROM source").fetchall()}
    assert {"ted", "es_placsp", "es_placsp_agg"} <= codes


def test_raw_ingest_records_the_payload_before_normalisation(seeded):
    src = db.source_id(seeded, "ted")
    db.record_raw(seeded, src, "00512345-2026", "deadbeef", "ted/2026/09/07/x.json")
    seeded.commit()
    row = seeded.execute(
        "SELECT native_id, storage_key FROM raw_ingest WHERE content_hash='deadbeef'"
    ).fetchone()
    assert row["storage_key"].endswith("x.json")


# ------------------------------------------------- append-only enforcement

def test_archive_rows_cannot_be_deleted(seeded):
    """The rule the whole moat rests on, enforced by the database itself."""
    import psycopg

    oid, _ = ingest(seeded, NOTICE)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        seeded.execute("DELETE FROM opportunity_version WHERE opportunity_id=%s", (oid,))
    seeded.rollback()


def test_archive_payloads_cannot_be_rewritten(seeded):
    import psycopg

    oid, _ = ingest(seeded, NOTICE)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        seeded.execute(
            "UPDATE opportunity_version SET payload='{}'::jsonb WHERE opportunity_id=%s",
            (oid,),
        )
    seeded.rollback()


def test_closing_a_version_with_valid_to_stays_legal(seeded):
    """Versioning itself must not be blocked by the guard."""
    oid, _ = ingest(seeded, NOTICE)
    seeded.execute(
        "UPDATE opportunity_version SET valid_to = now() WHERE opportunity_id=%s", (oid,)
    )
    seeded.commit()
    row = seeded.execute(
        "SELECT valid_to FROM opportunity_version WHERE opportunity_id=%s", (oid,)
    ).fetchone()
    assert row["valid_to"] is not None


def test_migrations_are_recorded(conn):
    rows = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version").fetchall()
    assert rows, "the runner must record what it applied"
    assert rows[0]["version"] == 1


def test_a_zero_floor_with_nothing_fetched_is_success(conn):
    """TED publishes nothing at weekends, so the Monday run legitimately finds
    nothing. A floor of zero must mean "nothing expected", not "no floor"."""
    run_id = db.start_run(conn, "ted", expected_min=0)
    db.finish_run(conn, run_id, fetched=0, new=0, changed=0)
    row = conn.execute("SELECT status FROM ingest_run WHERE id=%s", (run_id,)).fetchone()
    assert row["status"] == "success"


def test_a_source_with_no_measured_floor_is_not_judged(conn):
    """None means the volumes have not been measured yet. Guessing a floor
    would produce alerts nobody can act on."""
    run_id = db.start_run(conn, "ted", expected_min=None)
    db.finish_run(conn, run_id, fetched=1, new=1, changed=0)
    row = conn.execute("SELECT status FROM ingest_run WHERE id=%s", (run_id,)).fetchone()
    assert row["status"] == "success"


# ------------------------------------------- rebuild after losing everything

def test_the_archive_can_be_rebuilt_from_raw_storage_alone(seeded, tmp_path, monkeypatch):
    """The guarantee the raw store exists for.

    `raw_ingest` indexes the payloads, but it is a table inside the database.
    When the database is gone, the index goes with it, so the rebuild has to
    enumerate the object store itself.
    """
    from dgate import config, reprocess
    from dgate.rawstore import FileRawStore, storage_key

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path))
    config.reset_cache()
    try:
        store = FileRawStore(tmp_path)
        clean = strip_personal_data(NOTICE)
        store.put(storage_key("ted", "00512345-2026"), clean)

        oid, action = ingest(seeded, NOTICE)
        assert action == "new"
        before = seeded.execute(
            "SELECT native_id, value_amount FROM opportunity ORDER BY native_id").fetchall()

        # The disaster: serving layer and index both gone.
        seeded.execute("""TRUNCATE opportunity_version, opportunity_capability,
                          opportunity, raw_ingest RESTART IDENTITY CASCADE""")
        seeded.commit()
        assert seeded.execute("SELECT count(*) n FROM opportunity").fetchone()["n"] == 0

        result = reprocess.reprocess(from_store=True)
        assert result.failed == 0 and result.rebuilt == 1

        after = seeded.execute(
            "SELECT native_id, value_amount FROM opportunity ORDER BY native_id").fetchall()
        assert [dict(r) for r in after] == [dict(r) for r in before]
    finally:
        config.reset_cache()


def test_replaying_twice_writes_no_second_version(seeded, tmp_path, monkeypatch):
    """Replay is idempotent: the content hash decides, so a replay of a day
    already in the database must not inflate the archive with duplicates."""
    from dgate import config, reprocess
    from dgate.rawstore import FileRawStore, storage_key

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path))
    config.reset_cache()
    try:
        FileRawStore(tmp_path).put(storage_key("ted", "00512345-2026"),
                                   strip_personal_data(NOTICE))
        reprocess.reprocess(from_store=True)
        first = reprocess.reprocess(from_store=True)
        assert first.rebuilt == 0 and first.unchanged == 1
        versions = seeded.execute("SELECT count(*) n FROM opportunity_version").fetchone()["n"]
        assert versions == 1
    finally:
        config.reset_cache()


def test_the_version_timeline_has_no_gap_between_versions(amended):
    """valid_to of one version is valid_from of the next, to the microsecond.

    The archive's claim is that it can say what a notice said at any past
    instant. An instant that falls in a gap between two versions has no answer,
    so the intervals have to meet rather than merely follow one another.
    """
    conn, opp_id = amended
    rows = conn.execute(
        """SELECT version, valid_from, valid_to FROM opportunity_version
            WHERE opportunity_id = %s ORDER BY version""",
        (opp_id,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["valid_to"] == rows[1]["valid_from"]
    assert rows[1]["valid_to"] is None


def test_observation_times_are_wall_clock_not_transaction_start(conn):
    """Two versions written in one transaction must not share an instant.

    now() is transaction-scoped in Postgres, so under it every row an ingest
    wrote carried the moment the transaction opened -- thousands of notices all
    claiming to have been observed at an instant when none of them had been.
    This is the archive's core claim, so it gets its own test.
    """
    before = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
    seen = []
    for _ in range(3):
        seen.append(conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"])
    frozen = conn.execute("SELECT now() AS t").fetchone()["t"]

    assert len(set(seen)) == 3, "clock_timestamp() should advance within a transaction"
    assert all(t >= before for t in seen)
    assert frozen <= before, "now() should be the transaction start, which is the bug"


def test_ingest_run_records_a_real_duration(conn):
    """finished_at must come from the wall clock, not the transaction's start.

    Under now() a forty-minute PLACSP run closed three seconds after it opened,
    which made every duration in the operational history a fiction and would
    have hidden a source slowing down until it stopped finishing at all.
    """
    run_id = db.start_run(conn, "ted", expected_min=0)
    conn.execute("SELECT pg_sleep(0.05)")
    db.finish_run(conn, run_id, fetched=1, new=1, changed=0)
    row = conn.execute(
        "SELECT started_at, finished_at FROM ingest_run WHERE id = %s", (run_id,)
    ).fetchone()
    assert row["finished_at"] > row["started_at"]


def test_an_interrupted_run_is_closed_at_start_up(conn):
    """A killed process leaves its run `running`, and nothing else reaps it.

    Coverage is read from the latest run per source, so one such row makes that
    source look degraded for ever and turns every later alert into noise.
    """
    run_id = db.start_run(conn, "ted", expected_min=0)
    assert conn.execute(
        "SELECT status FROM ingest_run WHERE id = %s", (run_id,)
    ).fetchone()["status"] == "running"

    closed = db.close_interrupted_runs(conn)
    assert run_id in closed

    row = conn.execute(
        "SELECT status, finished_at, error_message FROM ingest_run WHERE id = %s",
        (run_id,),
    ).fetchone()
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    assert "interrupted" in row["error_message"]


def test_closing_interrupted_runs_leaves_finished_runs_alone(conn):
    run_id = db.start_run(conn, "ted", expected_min=0)
    db.finish_run(conn, run_id, fetched=5, new=5, changed=0)
    db.close_interrupted_runs(conn)
    row = conn.execute(
        "SELECT status, records_fetched FROM ingest_run WHERE id = %s", (run_id,)
    ).fetchone()
    assert row["status"] == "success"
    assert row["records_fetched"] == 5


def test_progress_is_visible_while_a_run_is_still_going(conn):
    """A long run reporting zero records is indistinguishable from a stuck one."""
    run_id = db.start_run(conn, "ted", expected_min=0)
    db.record_progress(conn, run_id, fetched=400, new=12, changed=3)
    row = conn.execute(
        """SELECT status, records_fetched, records_new, records_changed
             FROM ingest_run WHERE id = %s""", (run_id,)
    ).fetchone()
    assert row["status"] == "running"
    assert (row["records_fetched"], row["records_new"], row["records_changed"]) == (400, 12, 3)
