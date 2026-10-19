"""WP-52 (UX audit of 19 October 2026, tenders backend): the parts that need no database.

T2/T3 the order a list runs in and the status conditions, T8 the status of a planned notice, T12 a remapped
version that moved a line, T16/T18 the freshness of a source by its rhythm and why a run is partial."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dgate import tenders
from dgate.api import EFFECTIVE_STATUS_SQL, effective_status
from dgate.funding import STALE_AFTER_HOURS_BY_FREQ, run_reason
from dgate.tenders import (
    MAX_OFFSET,
    ORDER_DEADLINE_ASC,
    ORDER_DEADLINE_DESC,
    ORDER_OPEN_DEADLINE,
    ORDER_PUBLISHED_DESC,
    TOTAL_CAP,
    status_conditions,
    tender_order,
    timeline,
)

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0091_tender_list_indexes_and_source_names.sql"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").replace("\r\n", "\n")


# ---------------------------------------------------------------- T2 / T3: the order and the filters

def test_every_order_a_list_runs_in_is_the_order_of_an_index():
    sql = _sql()
    assert "(deadline_at ASC NULLS LAST, id ASC)" in sql and ORDER_DEADLINE_ASC == "o.deadline_at ASC NULLS LAST, o.id ASC"
    assert "(deadline_at DESC NULLS LAST, published_at DESC NULLS LAST, id DESC)" in sql
    assert ORDER_DEADLINE_DESC == "o.deadline_at DESC NULLS LAST, o.published_at DESC NULLS LAST, o.id DESC"
    assert "(coalesce(published_at, notice_date)) DESC NULLS LAST, id DESC" in sql
    assert ORDER_PUBLISHED_DESC == "coalesce(o.published_at, o.notice_date) DESC NULLS LAST, o.id DESC"
    assert sql.count("WHERE is_defence AND NOT suppressed") == 3
    assert "ON opportunity (deadline_at)\n    WHERE status = 'open' AND is_defence AND NOT suppressed" in sql


def test_the_open_list_is_ordered_so_that_no_index_can_walk_the_closed_notices():
    """`opp_list_deadline_asc` would be walked from the oldest deadline through 350,000 closed notices."""
    assert tender_order(None, "open", "EFF") == ORDER_OPEN_DEADLINE
    assert tender_order("deadline-asc", "open", "EFF") == ORDER_OPEN_DEADLINE
    assert ORDER_OPEN_DEADLINE.startswith("(o.deadline_at IS NULL)")      # an expression: not an index's order


def test_closed_and_planned_run_newest_deadline_first_and_a_sort_asked_for_wins():
    assert tender_order(None, "closed", "EFF") == ORDER_DEADLINE_DESC
    assert tender_order(None, "planned", "EFF") == ORDER_DEADLINE_DESC
    assert tender_order("deadline-asc", "closed", "EFF") == ORDER_DEADLINE_ASC
    assert tender_order("published-desc", "open", "EFF") == ORDER_PUBLISHED_DESC
    assert tender_order(None, "all", "EFF") == ORDER_DEADLINE_ASC


def test_the_open_filter_carries_the_conditions_the_planner_can_use():
    got = status_conditions("open", "EFF")
    assert got[0] == "EFF = 'open'"
    assert "o.status = 'open'" in got and any("o.deadline_at >= now()" in c for c in got)
    assert status_conditions("all", "EFF") == []
    assert status_conditions("rest", "EFF") == ["EFF <> 'open'"]


def test_the_caps_are_the_documented_ones():
    assert MAX_OFFSET == 10_000 and TOTAL_CAP == 10_000
    assert tenders.SMALL_CAP < TOTAL_CAP and tenders.COUNT_BUDGET_MS < 5000     # the API's budget is 5 s


# ------------------------------------------------------------------------ T8: a planned notice is not closed

def test_a_planned_notice_is_planned_until_its_deadline_passes():
    ahead, behind = NOW + timedelta(days=8), NOW - timedelta(days=8)
    assert effective_status("forthcoming", ahead, date(2026, 10, 1), NOW) == "forthcoming"
    assert effective_status("forthcoming", None, date(2026, 10, 1), NOW) == "forthcoming"
    assert effective_status("forthcoming", behind, date(2026, 10, 1), NOW) == "expired"
    assert effective_status("awarded", ahead, date(2026, 10, 1), NOW) == "awarded"      # unchanged


def test_the_sql_says_the_same_and_closed_leaves_the_planned_out():
    assert "WHEN o.status = 'forthcoming' AND o.deadline_at < now() THEN 'expired'" in EFFECTIVE_STATUS_SQL
    assert status_conditions("closed", "EFF") == ["EFF NOT IN ('open', 'forthcoming')"]
    assert status_conditions("planned", "EFF")[0] == "EFF = 'forthcoming'"


# ---------------------------------------------------- T12: a remapped version corrects the line it contradicts

AT = datetime(2026, 9, 10, tzinfo=timezone.utc)


def _row(version, changed, kinds=(), **payload):
    return {"version": version, "observed_at": AT + timedelta(days=version), "changed_fields": changed,
            "payload": payload, "kinds": list(kinds)}


def _notice_235():
    """Notice 235 on production: opened, the feed stamp moved, awarded, then two bulk re-readings of the same
    payloads, the second of which reads it as cancelled and takes the publication date back."""
    return [
        _row(1, [], status="open", published_at="2026-08-31"),
        _row(2, ["published_at"], status="open", published_at="2026-09-11"),
        _row(3, ["published_at", "status"], status="awarded", published_at="2026-09-29"),
        _row(4, ["procedure_type"], ("remapped",), status="awarded", published_at="2026-09-29", procedure_type="open"),
        _row(5, ["legal_basis", "value_amount", "published_at", "status"], ("remapped",), status="cancelled",
             published_at="2026-08-31", procedure_type="open", legal_basis="x", value_amount=5),
    ]


def test_the_history_ends_where_the_notice_does():
    entries = timeline(_notice_235())
    assert [e["sequence"] for e in entries] == [1, 2]
    lines = {c["field"]: c for c in entries[1]["changes"]}
    assert lines["status"]["before"] == "Open" and lines["status"]["after"] == "Cancelled"     # not "Awarded"
    assert lines["published_at"]["after"] == "31 Aug 2026"        # the headline's date, not the feed stamp's 29 Sep


def test_a_remap_that_restores_the_old_value_removes_the_line_and_the_entry():
    rows = [
        _row(1, [], status="open", published_at="2026-08-31"),
        _row(2, ["status"], status="awarded", published_at="2026-08-31"),
        _row(3, ["status"], ("remapped",), status="open", published_at="2026-08-31"),
    ]
    assert [e["sequence"] for e in timeline(rows)] == [1]


def test_a_remap_of_a_field_no_line_shows_changes_nothing():
    rows = [
        _row(1, [], status="open", procedure_type="a"),
        _row(2, ["status"], status="awarded", procedure_type="a"),
        _row(3, ["procedure_type"], ("remapped",), status="awarded", procedure_type="b"),
    ]
    entries = timeline(rows)
    assert [c["field"] for c in entries[1]["changes"]] == ["status"] and entries[1]["changes"][0]["after"] == "Awarded"


def test_a_real_amendment_after_a_remap_is_measured_from_the_corrected_reading():
    rows = _notice_235() + [_row(6, ["deadline_at"], status="cancelled", published_at="2026-08-31",
                                 procedure_type="open", legal_basis="x", value_amount=5,
                                 deadline_at="2026-11-01")]
    entries = timeline(rows)
    assert [e["sequence"] for e in entries] == [1, 2, 3]
    assert [c["field"] for c in entries[2]["changes"]] == ["deadline_at"]


def test_every_body_of_the_snapshot_table_is_an_object():
    """A statement that edits a key of every row (`jsonb_set(body, '{total}', ...)`) must work on the rows that
    hold a list, the sitemap's slugs and the buyer aggregate."""
    from dgate.listcache import restored, stored

    rows = [{"slug": "1-x"}]
    assert stored(rows) == {"__list__": rows} and restored(stored(rows)) == rows
    page = {"items": [], "total": 3}
    assert stored(page) is page and restored(page) is page
    assert restored({"__list__": [], "total": 1}) == {"__list__": [], "total": 1}      # an object with other keys is not one


# ---------------------------------------------------- T16 / T18: a source is late by its own rhythm

def test_a_monthly_source_is_not_late_after_three_days():
    assert STALE_AFTER_HOURS_BY_FREQ["daily"] == 72
    assert STALE_AFTER_HOURS_BY_FREQ["monthly"] >= 31 * 24
    assert "one-off" not in STALE_AFTER_HOURS_BY_FREQ and "on demand" not in STALE_AFTER_HOURS_BY_FREQ


def test_a_partial_run_says_why_in_a_fixed_sentence():
    assert run_reason("success", 100, 10, None) == (None, None)
    assert run_reason("partial", 100, 10, "live feed stale: newest entry 2026-10-17T19:50:06+02:00, older than 36h")[0] == "stale_feed"
    kind, text = run_reason("partial", 284, 150, "1 factsheets could not be read")
    assert kind == "unreadable" and text.startswith("1 factsheets could not be read")
    assert run_reason("partial", 5, 400, "x")[0] == "below_minimum"
    assert run_reason("partial", 400, 400, "1 records quarantined: ? (UniqueViolation)")[0] == "quarantined"
    assert run_reason("partial", 400, 400, "unmapped TED notice types: brin-ecs (1)")[0] == "other"
    assert run_reason("failed", 0, 400, "psycopg.OperationalError: host=10.0.0.5")[0] == "failed"


def test_the_reason_never_repeats_the_error_text():
    for message in ("psycopg.OperationalError: could not connect to host=10.0.0.5 user=dgate",
                    "s3://bucket/key?X-Amz-Signature=abc"):
        for status in ("partial", "failed"):
            _, text = run_reason(status, 0, 400, message)
            assert text and "10.0.0.5" not in text and "Signature" not in text


# ---------------------------------------------------- T18: the names as the operators spell them

def test_the_migration_gives_the_sources_their_accents_back():
    sql = _sql()
    for name in ("Plataforma de Contratación del Sector Público", "Biuletyn Zamówień Publicznych (e-Zamówienia)",
                 "Bulletin officiel des annonces de marchés publics (BOAMP)", "Narodowe Centrum Badań i Rozwoju",
                 "Agence de l''innovation de défense (AID), appels à projets", "Datenservice Öffentlicher Einkauf",
                 "Atlas Przetargów"):
        assert name in sql
    # codes are what everything joins on: never touched
    assert not re.search(r"SET\s+code\b", sql)
