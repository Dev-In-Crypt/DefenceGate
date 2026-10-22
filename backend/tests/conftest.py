"""Shared fixtures.

Integration tests need a real Postgres. They are marked `integration`, are
excluded from the default gate, and skip themselves when DGATE_TEST_DSN is
unset, so the suite never silently points at a real database and never fails
for the wrong reason on a machine without Postgres.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"

# The suite makes hundreds of API calls from one address; the limiter has its own
# tests, which switch it back on.
os.environ.setdefault("DGATE_RATE_LIMIT", "0")
# Tests insert between two reads of one list: no response reuse, except in the tests of it.
os.environ.setdefault("DGATE_LIST_CACHE_SECONDS", "0")
# The nightly completeness control asks the portals for their day totals: never from tests.
os.environ.setdefault("DGATE_COMPLETENESS_CHECK", "0")

TABLES = """award, award_notice, compaction_pending, backfill_day, enrichment_job, enrichment, opportunity_version, opportunity_capability, opportunity,
            organisation_merge_candidate, organisation_alias, organisation,
            call, raw_ingest, ingest_run,
            app_user, app_login_token, app_auth_event, app_hit_daily, backup_status, control_check,
            suppression, data_request, list_snapshot, award_twin_set,
            call_eligibility, call_document_text, llm_usage, digest_issue,
            programme_requirement, requirement_issuer, requirement_prerequisite, requirement,
            readiness_programme,
            organisation_family_member, organisation_network, consortium_change, consortium_snapshot, participation, project_factsheet, project,
            resolution_review, resolution_gold, regulation_entry"""
# `programme` is deliberately not truncated: it is reference data the migration
# seeds once, and a test that started with no programmes would be testing a
# database that cannot exist.


@pytest.fixture(scope="session")
def dsn() -> str:
    value = os.environ.get("DGATE_TEST_DSN")
    if not value:
        pytest.skip("DGATE_TEST_DSN is not set; integration tests need a Postgres")
    return value


@pytest.fixture(scope="session")
def schema(dsn: str) -> str:
    """Apply every migration once per session, through the real runner."""
    from dgate.migrate import migrate

    migrate(dsn, MIGRATIONS)
    return dsn


@pytest.fixture()
def conn(schema: str, monkeypatch: pytest.MonkeyPatch):
    """A clean database per test, and the package pointed at it.

    Tests must be repeatable, so every test starts from a known-empty state.
    """
    import psycopg
    from psycopg.rows import dict_row

    from dgate import config

    monkeypatch.setenv("DGATE_DSN", schema)
    config.reset_cache()

    with psycopg.connect(schema, row_factory=dict_row) as c:
        # The archive refuses TRUNCATE (migration 0024); a test that starts from
        # empty tables says so out loud, for this transaction only.
        c.execute("SET LOCAL dgate.allow_truncate = 'on'")
        c.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
        c.commit()
        yield c
        c.rollback()
    config.reset_cache()
