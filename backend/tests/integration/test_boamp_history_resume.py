"""The French history against a real Postgres: a clean stop, a marker, a resume.

And the two columns this work package adds to what is stored: the CPV codes of
a legacy notice, and the link from a rectificatif to the notice it corrects.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from dgate import config, db, pipeline
from dgate.ops import link_ted
from dgate.rawstore import build_store
from dgate.sources import RateLimited, boamp

pytestmark = pytest.mark.integration

D1, D2, D3 = date(2026, 9, 18), date(2026, 9, 19), date(2026, 9, 20)


def _legacy(idweb: str, *, etat: str = "INITIAL", lie: list[str] | None = None,
            corrects: str | None = None, cpv: str = "35111100") -> dict:
    """A 2015-2020 notice of the defence regime, in the Boamp_v230 shape."""
    body: dict = {"OBJET": {"CPV": {"PRINCIPAL": cpv},
                            "CARACTERISTIQUES": {"VALEUR": {"@DEVISE": "EUR", "#text": "1120000"}}}}
    if corrects:
        body["RECTIF"] = {"ANNONCE_ANTERIEUR": {"REFERENCE": {"IDWEB": corrects}}}
    return {"idweb": idweb, "objet": f"Marche {idweb}", "nomacheteur": "Ministere des Armees",
            "dateparution": "2026-09-19", "datelimitereponse": "2026-10-15T12:00:00+00:00",
            "perimetre": "DIRECTIVE-81", "nature": "APPEL_OFFRE", "etat": etat,
            "annonce_lie": lie, "donnees": json.dumps(body)}


@pytest.fixture(autouse=True)
def fs_store(tmp_path, monkeypatch, conn):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    # backfill_stop is not in the shared TRUNCATE list; a hold left by another test
    # would make every history run here refuse to start.
    conn.execute("DELETE FROM backfill_stop")
    conn.commit()
    yield
    conn.execute("DELETE FROM backfill_stop")
    conn.commit()
    config.reset_cache()


def _search_by_day(days: dict[date, object]):
    """A `boamp.search` that answers per day; a value that is an exception is raised
    (after yielding what came before it, as a page that fails mid-day does)."""
    asked: list[date] = []

    def search(params, **kw):
        day = date.fromisoformat(params["where"][-11:-1])
        asked.append(day)
        outcome = days.get(day, [])
        if isinstance(outcome, Exception):
            def broken():
                yield _legacy("26-partial")
                raise outcome
            return broken()
        return iter(outcome)

    search.asked = asked
    return search


# ----------------------------------------------------------- stop and resume

def test_a_rate_limit_stops_the_history_cleanly_and_leaves_a_marker(conn, monkeypatch):
    search = _search_by_day({D1: [_legacy("26-h1")],
                             D2: RateLimited("fr_boamp: HTTP 429 at offset 0", 1200.0),
                             D3: [_legacy("26-h3")]})
    monkeypatch.setattr(boamp, "search", search)

    with pytest.raises(pipeline.HistoryStopped) as stopped:
        pipeline.run_history("fr_boamp", D1, D3)

    assert stopped.value.day == D2 and stopped.value.loaded == 1
    # the day before is done, the day in progress is not, the one after was not asked for
    assert db.backfill_days_done(conn, "fr_boamp") == {D1}
    assert search.asked == [D1, D2]
    # nothing of the interrupted day was kept: no index row, no opportunity
    ids = [r["native_id"] for r in conn.execute("SELECT native_id FROM raw_ingest").fetchall()]
    assert ids == ["26-h1"]
    # the marker says where, why and until when
    row = conn.execute("SELECT * FROM backfill_stop WHERE source_code = 'fr_boamp'").fetchone()
    assert row["day"] == D2 and "429" in row["reason"]
    waited = (row["resume_after"] - row["stopped_at"]).total_seconds()
    assert 1199 <= waited <= 1201                       # the source's 1,200 seconds, not our 900


def test_without_a_retry_after_the_run_stays_away_for_the_cooldown(conn, monkeypatch):
    monkeypatch.setattr(boamp, "search",
                        _search_by_day({D1: RateLimited("fr_boamp: HTTP 403", None)}))
    with pytest.raises(pipeline.HistoryStopped):
        pipeline.run_history("fr_boamp", D1, D1)
    row = conn.execute("SELECT * FROM backfill_stop").fetchone()
    assert (row["resume_after"] - row["stopped_at"]).total_seconds() >= db.BACKFILL_COOLDOWN_SECONDS - 1


def test_a_rerun_inside_the_hold_asks_the_source_for_nothing(conn, monkeypatch):
    first = _search_by_day({D1: RateLimited("fr_boamp: HTTP 429", 600.0)})
    monkeypatch.setattr(boamp, "search", first)
    with pytest.raises(pipeline.HistoryStopped):
        pipeline.run_history("fr_boamp", D1, D2)

    again = _search_by_day({D1: [_legacy("26-h1")]})
    monkeypatch.setattr(boamp, "search", again)
    with pytest.raises(pipeline.HistoryStopped) as held:
        pipeline.run_history("fr_boamp", D1, D2)
    assert again.asked == [] and held.value.loaded == 0
    assert held.value.resume_after > datetime.now(timezone.utc)


def test_after_the_hold_the_same_command_continues_where_it_stopped(conn, monkeypatch):
    monkeypatch.setattr(boamp, "search", _search_by_day(
        {D1: [_legacy("26-h1")], D2: RateLimited("fr_boamp: HTTP 429", 600.0)}))
    with pytest.raises(pipeline.HistoryStopped):
        pipeline.run_history("fr_boamp", D1, D3)

    # the hold lapses
    conn.execute("UPDATE backfill_stop SET resume_after = clock_timestamp() - interval '1 second'")
    conn.commit()
    resumed = _search_by_day({D1: [_legacy("26-h1")], D2: [_legacy("26-h2")], D3: [_legacy("26-h3")]})
    monkeypatch.setattr(boamp, "search", resumed)
    loaded = pipeline.run_history("fr_boamp", D1, D3)

    assert loaded == 2 and resumed.asked == [D2, D3]            # D1 was not asked for again
    assert db.backfill_days_done(conn, "fr_boamp") == {D1, D2, D3}
    assert sorted(r["native_id"] for r in conn.execute(
        "SELECT native_id FROM opportunity").fetchall()) == ["26-h1", "26-h2", "26-h3"]
    row = conn.execute("SELECT reason, resume_after FROM backfill_stop").fetchone()
    assert row["reason"].startswith("resumed and finished")
    assert db.backfill_resume_after(conn, "fr_boamp") is None


def test_the_command_line_exits_75_when_the_source_stops_it(conn, monkeypatch, caplog):
    """Not 0: a wrapper that reports success on a stopped load is how the French
    history went unnoticed for three weeks."""
    monkeypatch.setattr(boamp, "search",
                        _search_by_day({D1: RateLimited("fr_boamp: HTTP 429", 60.0)}))
    code = pipeline.main(["history", "--source", "fr_boamp", "--from", "2026-09-18",
                          "--to", "2026-09-18"])
    assert code == pipeline.EXIT_STOPPED == 75
    assert any("history stopped" in m for m in caplog.messages)


def test_another_failure_is_still_a_failure_and_leaves_no_marker(conn, monkeypatch):
    monkeypatch.setattr(boamp, "search", _search_by_day({D1: RuntimeError("disk full")}))
    with pytest.raises(RuntimeError, match="disk full"):
        pipeline.run_history("fr_boamp", D1, D1)
    assert conn.execute("SELECT count(*) n FROM backfill_stop").fetchone()["n"] == 0
    assert db.backfill_days_done(conn, "fr_boamp") == set()


# ------------------------------------------------------- what is stored

def test_the_cpv_and_value_of_a_legacy_notice_are_stored(conn, monkeypatch):
    monkeypatch.setattr(boamp, "search", _search_by_day({D1: [_legacy("26-h1", cpv="35121000")]}))
    pipeline.run_history("fr_boamp", D1, D1)
    row = conn.execute("SELECT cpv_codes, value_amount, value_currency, sig_cpv "
                       "FROM opportunity").fetchone()
    assert row["cpv_codes"] == ["35121000"]
    assert (float(row["value_amount"]), row["value_currency"]) == (1120000.0, "EUR")
    assert row["sig_cpv"] is True          # CPV division 35, military group


def test_a_rectificatif_is_stored_with_the_notice_it_corrects(conn, monkeypatch):
    parent = _legacy("26-100")
    fix = _legacy("26-101", etat="RECTIFICATIF", lie=["26-5", "26-100"], corrects="26-100")
    monkeypatch.setattr(boamp, "search", _search_by_day({D1: [parent, fix]}))
    pipeline.run_history("fr_boamp", D1, D1)

    rows = {r["native_id"]: r for r in conn.execute(
        "SELECT native_id, related_native_id FROM opportunity").fetchall()}
    assert rows["26-101"]["related_native_id"] == "26-100"
    assert rows["26-100"]["related_native_id"] is None
    payload = conn.execute(
        "SELECT payload FROM opportunity_version v JOIN opportunity o ON o.id = v.opportunity_id "
        "WHERE o.native_id = '26-101'").fetchone()["payload"]
    assert payload["related_native_id"] == "26-100"

    # the archived parent has no such key, so its hash did not move
    parent_payload = conn.execute(
        "SELECT payload FROM opportunity_version v JOIN opportunity o ON o.id = v.opportunity_id "
        "WHERE o.native_id = '26-100'").fetchone()["payload"]
    assert "related_native_id" not in parent_payload


def test_the_link_can_be_filled_for_rows_stored_before_it_existed(conn, monkeypatch):
    fix = _legacy("26-101", etat="RECTIFICATIF", corrects="26-100")
    monkeypatch.setattr(boamp, "search", _search_by_day({D1: [fix]}))
    pipeline.run_history("fr_boamp", D1, D1)
    conn.execute("UPDATE opportunity SET related_native_id = NULL")
    conn.commit()

    assert link_ted.backfill(conn, build_store(), "fr_boamp", dry_run=True,
                             column="related_native_id") == (1, 1)
    assert conn.execute("SELECT related_native_id FROM opportunity").fetchone()[
        "related_native_id"] is None
    assert link_ted.backfill(conn, build_store(), "fr_boamp", column="related_native_id") == (1, 1)
    assert conn.execute("SELECT related_native_id FROM opportunity").fetchone()[
        "related_native_id"] == "26-100"
    # and the TED link of the same rows is untouched
    assert conn.execute("SELECT ted_ref FROM opportunity").fetchone()["ted_ref"] is None


def test_an_unknown_link_column_is_refused(conn):
    with pytest.raises(ValueError, match="not a link column"):
        link_ted.backfill(conn, build_store(), "fr_boamp", column="status; DROP TABLE opportunity")


def test_the_migration_adds_the_column_and_its_index(conn):
    col = conn.execute(
        "SELECT data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'opportunity' AND column_name = 'related_native_id'").fetchone()
    assert col == {"data_type": "text", "is_nullable": "YES"}
    assert conn.execute(
        "SELECT 1 FROM pg_indexes WHERE indexname = 'opp_related_native_id'").fetchone()


def test_the_stop_marker_survives_a_second_stop_as_one_row(conn):
    first = db.record_backfill_stop(conn, "fr_boamp", D1, "HTTP 429", 60.0)
    second = db.record_backfill_stop(conn, "fr_boamp", D2, "HTTP 429 again", 7200.0)
    assert conn.execute("SELECT count(*) n FROM backfill_stop").fetchone()["n"] == 1
    assert second > first + timedelta(hours=1)
    assert conn.execute("SELECT day FROM backfill_stop").fetchone()["day"] == D2
