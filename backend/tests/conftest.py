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

TABLES = """opportunity_version, opportunity_capability, opportunity,
            organisation_alias, organisation, raw_ingest, ingest_run"""


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
        c.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
        c.commit()
        yield c
        c.rollback()
    config.reset_cache()
