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


def write_seeds(tmp_path, rows: list[str]):
    path = tmp_path / "seeds.csv"
    path.write_text("country,canonical_name,raw_name,category,seen\n" + "\n".join(rows) + "\n",
                    encoding="utf-8")
    return path


# ------------------------------------------------- re-read content (reversions)

def _placsp_state(status: str, published: str):
    from datetime import date

    from dgate.normalise import Opportunity

    return Opportunity(
        source_code="es_placsp", native_id="2026/ETSAE0906/00002554E",
        buyer_name_raw="Ministerio de Defensa", title_original="Suministro",
        country="ES", published_at=date.fromisoformat(published),
        status=status, status_native=status, cpv_codes=["35700000"], is_defence=True,
    )


def _upsert(conn, opp):
    src = db.source_id(conn, "es_placsp")
    digest = content_hash(db.opportunity_payload(opp))
    result = db.upsert_opportunity(conn, opp, digest, src)
    conn.commit()
    return result


def _versions(conn, oid):
    return conn.execute(
        """SELECT version, payload->>'status' AS status, valid_to
             FROM opportunity_version WHERE opportunity_id = %s ORDER BY version""",
        (oid,),
    ).fetchall()


def test_re_reading_old_content_does_not_flip_the_archive(conn):
    """The live defect, reproduced. One real change -- open on the 7th, awarded
    on the 8th -- read in both orders across four runs produced twelve versions
    alternating between the same two payloads, with "open" left current."""
    opened = _placsp_state("open", "2026-09-07")
    awarded = _placsp_state("awarded", "2026-09-08")
    oid, _ = _upsert(conn, opened)
    for _ in range(4):
        _upsert(conn, awarded)
        _upsert(conn, opened)
    rows = _versions(conn, oid)
    assert [r["status"] for r in rows] == ["open", "awarded"]
    current = conn.execute("SELECT status FROM opportunity WHERE id = %s", (oid,)).fetchone()
    assert current["status"] == "awarded"


def test_older_content_arriving_after_newer_never_becomes_current(conn):
    """Newest first is how the feed is served. The award must stay current."""
    oid, _ = _upsert(conn, _placsp_state("awarded", "2026-09-08"))
    _, action = _upsert(conn, _placsp_state("open", "2026-09-07"))
    assert action == "stale"
    assert [r["status"] for r in _versions(conn, oid)] == ["awarded"]


def test_a_genuinely_newer_change_is_still_archived(conn):
    oid, _ = _upsert(conn, _placsp_state("open", "2026-09-07"))
    _upsert(conn, _placsp_state("awarded", "2026-09-08"))
    _, action = _upsert(conn, _placsp_state("cancelled", "2026-09-09"))
    assert action == "changed"
    assert [r["status"] for r in _versions(conn, oid)] == ["open", "awarded", "cancelled"]


def test_a_flipped_history_is_repaired_by_appending_never_by_deleting(conn):
    """Rebuild the damaged history the way the old code wrote it, then repair."""
    from dgate.api import get_versions
    from dgate.ops.repair_reversions import run as repair

    awarded = _placsp_state("awarded", "2026-09-08")
    opened = _placsp_state("open", "2026-09-07")
    oid, _ = _upsert(conn, awarded)
    # append_version skips the change checks, so it reproduces the old writes.
    after = 1
    for opp in (opened, awarded, opened):
        digest = content_hash(db.opportunity_payload(opp))
        after = db.append_version(conn, oid, opp, digest, ["status", "published_at"],
                                  after=after)
    conn.commit()
    assert conn.execute("SELECT status FROM opportunity WHERE id=%s", (oid,)).fetchone()[
        "status"] == "open"

    from dgate.config import settings

    dsn = settings().test_dsn  # conn.info.dsn omits the password
    totals = repair(dsn=dsn)
    assert totals["corrected"] == 1

    rows = _versions(conn, oid)
    assert len(rows) == 5, "four damaged versions kept, one correction appended"
    assert rows[-1]["status"] == "awarded"
    assert conn.execute("SELECT status FROM opportunity WHERE id=%s", (oid,)).fetchone()[
        "status"] == "awarded"

    notes = {v["version"]: [n["kind"] for n in v["notes"]]
             for v in get_versions(oid, conn)["versions"]}
    assert notes[2] == ["out_of_order"]
    assert notes[3] == ["reread"] and notes[4] == ["reread"]
    assert notes[5] == ["correction"]

    # Running it again changes nothing -- including the notes. The first version
    # of the repair passed the two checks above and still marked the correction
    # `reread` on its second run.
    assert repair(dsn=dsn)["corrected"] == 0
    assert len(_versions(conn, oid)) == 5
    again = {v["version"]: sorted(n["kind"] for n in v["notes"])
             for v in get_versions(oid, conn)["versions"]}
    assert again == {1: [], 2: ["out_of_order"], 3: ["reread"], 4: ["reread"],
                     5: ["correction"]}


# --------------------------------------------------------- buyer seeding (M1-03)

def test_seeding_twice_creates_no_duplicates(conn, tmp_path):
    """M1-03's done-when. It failed before migration 0005: seeded aliases have
    no source, NULL is distinct from NULL in a unique constraint, and a second
    run turned 20 alias rows into 40."""
    seeds = write_seeds(tmp_path, [
        "PL,2 Regionalna Baza Logistyczna,2 Regionalna Baza Logistyczna,logistics_base,792",
        "PL,2 Regionalna Baza Logistyczna,2. Regionalna Baza Logistyczna,logistics_base,511",
    ])

    def counts():
        return conn.execute(
            """SELECT (SELECT count(*) FROM organisation_alias
                        WHERE normalised_name = '2 regionalna baza logistyczna') AS aliases,
                      (SELECT count(*) FROM organisation
                        WHERE canonical_name = '2 regionalna baza logistyczna') AS orgs"""
        ).fetchone()

    seed_buyers(seeds)
    conn.commit()
    first = counts()
    seed_buyers(seeds)
    seed_buyers(seeds)
    conn.commit()
    assert counts() == first
    # Both spellings normalise to the same name, so one alias and one organisation.
    assert (first["aliases"], first["orgs"]) == (1, 1)


def test_a_variant_spelling_resolves_to_a_defence_buyer(conn, tmp_path):
    seeds = write_seeds(tmp_path, [
        "PL,31 Wojskowy Oddzial Gospodarczy,31 Wojskowy Oddzial Gospodarczy,economic_unit,1430",
        "PL,31 Wojskowy Oddzial Gospodarczy,31 Wojskowy Oddzial Gospodarczy w Krakowie,economic_unit,4",
    ])
    seed_buyers(seeds)
    conn.commit()
    org = db.resolve_organisation(conn, "31 Wojskowy Oddzial Gospodarczy w Krakowie", "PL")
    assert db.is_defence_buyer(conn, org)


def test_an_organisation_ingestion_created_first_is_flagged_too(conn, tmp_path):
    """Ingestion may already have created an organisation under a variant
    spelling. Merging it would be a resolution decision without a method;
    flagging it means the buyer signal fires whichever one a notice hits."""
    src = db.source_id(conn, "pl_ezam")
    early = db.resolve_organisation(conn, "7 Wojskowy Oddzial Gospodarczy w Gdyni", "PL",
                                    src_id=src)
    conn.commit()
    seeds = write_seeds(tmp_path, [
        "PL,7 Wojskowy Oddzial Gospodarczy,7 Wojskowy Oddzial Gospodarczy,economic_unit,10",
        "PL,7 Wojskowy Oddzial Gospodarczy,7 Wojskowy Oddzial Gospodarczy w Gdyni,economic_unit,3",
    ])
    seed_buyers(seeds)
    conn.commit()
    assert db.is_defence_buyer(conn, early)


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


def test_reclassifying_after_the_buyer_list_grows(conn, tmp_path, monkeypatch):
    """The five days the buyer list was empty, and the pass that makes up for it.

    A notice archived on its CPV alone gains the buyer signal without a new
    version, because its content did not change. A notice from the same buyer
    that did not qualify then is archived now, from the payload stored at the
    time -- which is why every payload was kept, defence or not.
    """
    from datetime import date

    from dgate import config, reprocess
    from dgate.normalise import Opportunity
    from dgate.pipeline import seed_buyers
    from dgate.rawstore import FileRawStore, storage_key

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    try:
        buyer = "Jefatura de Asuntos Economicos del Mando de Apoyo Logistico"
        store = FileRawStore(tmp_path / "raw")
        src = db.source_id(conn, "es_placsp")

        def land(native_id, cpv):
            opp = Opportunity(source_code="es_placsp", native_id=native_id,
                              buyer_name_raw=buyer, title_original=native_id, country="ES",
                              published_at=date(2026, 9, 1), cpv_codes=[cpv])
            payload = db.opportunity_payload(opp)
            digest = content_hash(payload)
            key = store.put(storage_key("es_placsp", native_id, content_hash=digest), payload)
            db.record_raw(conn, src, native_id, digest, key)
            opp = _finalise(conn, opp, src)
            if opp.is_defence:
                db.upsert_opportunity(conn, opp, digest, src)
            conn.commit()

        land("EXP-MILITARY", "35300000")      # weapons: qualifies on CPV alone
        land("EXP-WORKS", "45000000")         # construction: needed the buyer list

        def row(native_id):
            return conn.execute(
                """SELECT is_defence, sig_buyer, current_version FROM opportunity
                    WHERE source_id = %s AND native_id = %s""", (src, native_id)).fetchone()

        assert row("EXP-MILITARY")["sig_buyer"] is False
        assert row("EXP-WORKS") is None

        seeds = write_seeds(tmp_path, [f"ES,{buyer},{buyer},army_economic_unit,33"])
        seed_buyers(seeds)
        conn.commit()
        result = reprocess.reprocess(source="es_placsp", workers=4)
        assert result.failed == 0

        military = row("EXP-MILITARY")
        assert military["sig_buyer"] is True and military["current_version"] == 1
        works = row("EXP-WORKS")
        assert works is not None and works["is_defence"] and works["sig_buyer"]
    finally:
        config.reset_cache()
