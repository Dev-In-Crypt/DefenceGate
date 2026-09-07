"""Migration discovery and the append-only rule as written (plan task M0-06).

Applying migrations needs a database and is covered by the integration suite.
What is checked here is everything that can be wrong before Postgres is
involved: ordering, naming, duplicate versions, and that the archive guard is
actually present in the schema.
"""

import pytest

from dgate.migrate import MIGRATIONS_DIR, discover


def test_migrations_are_discovered_in_order():
    versions = [m.version for m in discover()]
    assert versions == sorted(versions)
    assert versions[0] == 1


def test_first_migration_is_the_phase1_core():
    first = discover()[0]
    assert first.name == "phase1_core"
    assert first.path.name == "0001_phase1_core.sql"


def test_bad_filename_is_rejected(tmp_path):
    (tmp_path / "schema.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(ValueError, match="NNNN_lower_snake_case"):
        discover(tmp_path)


def test_duplicate_version_is_rejected(tmp_path):
    (tmp_path / "0002_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0002_b.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate migration version"):
        discover(tmp_path)


def test_empty_directory_is_not_an_error(tmp_path):
    assert discover(tmp_path) == []


# ------------------------------------------------- the rules in the schema

def _core_sql() -> str:
    return (MIGRATIONS_DIR / "0001_phase1_core.sql").read_text(encoding="utf-8")


def test_archive_is_protected_by_a_trigger():
    """The rule that must not depend on anybody remembering it."""
    sql = _core_sql()
    assert "CREATE TRIGGER opportunity_version_append_only" in sql
    assert "BEFORE UPDATE OR DELETE ON opportunity_version" in sql


def test_guard_permits_only_valid_to_to_change():
    sql = _core_sql()
    guard = sql[sql.index("opportunity_version_guard"):]
    for column in ("payload", "raw_hash", "version", "changed_fields", "valid_from"):
        assert f"NEW.{column}" in guard, f"{column} must be guarded against update"
    assert "NEW.valid_to" not in guard, "closing a version with valid_to must stay legal"


def test_both_placsp_datasets_are_seeded_as_sources():
    sql = _core_sql()
    assert "'es_placsp'" in sql
    assert "'es_placsp_agg'" in sql


def test_status_native_column_exists():
    assert "status_native" in _core_sql()
