"""WP-163: a restored dump ends with production's roles and grants after `migrate`.

Backups are `pg_dump --no-owner --no-privileges`, and roles are cluster objects a dump never
holds: a restore on a new server has every table, no GRANT and none of the service roles, and the
first `migrate` failed on the next pending migration's GRANT (`role "dgate_api" does not exist`,
drill of 31 Oct 2026). `migrate` now replays the applied migrations' role and privilege statements
before the pending ones (`migrate.reapply_privileges`).

The test builds that state for real: a scratch database migrated to the version before the last,
then the service roles renamed away, so the scratch database has no role of those names and no
grant to one, as after a restore on a new server. One `migrate` must end with exactly the grants
and role settings the migrations make (the session database is the reference), and the roles must
behave as on production. The original roles are renamed back afterwards, whatever happened.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from dgate import migrate
from dgate.ops.backup import with_database

pytestmark = pytest.mark.integration

ROLES = ("dgate_api", "dgate_worker", "dgate_app")
SCRATCH = "dgate_wp163_restore"
AWAY = "_wp163_away"

# The same query compares production with a restored copy (docs/RESTORE.md, "Verify").
PRIVILEGES = """
SELECT 'rel' AS kind, c.relname AS obj, a.grantee::regrole::text AS who, a.privilege_type AS priv
  FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a
 WHERE c.relnamespace = 'public'::regnamespace
UNION ALL
SELECT 'col', c.relname || '.' || t.attname, a.grantee::regrole::text, a.privilege_type
  FROM pg_attribute t JOIN pg_class c ON c.oid = t.attrelid CROSS JOIN LATERAL aclexplode(t.attacl) a
 WHERE c.relnamespace = 'public'::regnamespace
UNION ALL
SELECT 'schema', n.nspname, a.grantee::regrole::text, a.privilege_type
  FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a WHERE n.nspname = 'public'
UNION ALL
SELECT 'default:' || d.defaclobjtype::text, d.defaclnamespace::regnamespace::text, a.grantee::regrole::text,
       a.privilege_type
  FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a
"""
ROLE_SETTINGS = """
SELECT r.rolname, r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolconnlimit,
       (SELECT array_agg(c ORDER BY c) FROM pg_db_role_setting s, unnest(s.setconfig) c
         WHERE s.setrole = r.oid AND s.setdatabase = 0) AS settings
  FROM pg_roles r WHERE r.rolname = ANY(%s) ORDER BY 1
"""


def _privileges(c) -> set[tuple]:
    return {tuple(r) for r in c.execute(PRIVILEGES).fetchall() if r[2] in ROLES}


def _roles(c, names=ROLES) -> list[tuple]:
    return [tuple(r) for r in c.execute(ROLE_SETTINGS, (list(names),)).fetchall()]


def _as(dsn: str, role: str, password: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(netloc=f"{role}:{password}@{parts.hostname}:{parts.port}"))


@pytest.fixture()
def reference(schema):
    """Grants and role settings of the session database: every migration, as it ran."""
    with psycopg.connect(schema) as c:
        return _privileges(c), _roles(c)


@pytest.fixture()
def restored(schema, reference):
    """A database at the version before the last, on a cluster without the service roles."""
    admin = with_database(schema, "postgres")
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{SCRATCH}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{SCRATCH}"')
    target = with_database(schema, SCRATCH)
    with psycopg.connect(target) as c:
        for m in migrate.pending(c)[:-1]:
            migrate.apply(c, m)
    renamed = False
    try:
        with psycopg.connect(admin, autocommit=True) as c:
            for role in ROLES:
                c.execute(f"ALTER ROLE {role} RENAME TO {role}{AWAY}")
            renamed = True
        yield target
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{SCRATCH}" WITH (FORCE)')
            if renamed:
                for role in ROLES:
                    c.execute(f"DROP ROLE IF EXISTS {role}")
                    c.execute(f"ALTER ROLE {role}{AWAY} RENAME TO {role}")


def test_the_migrations_privilege_statements_are_found_in_order():
    found = migrate.privilege_statements(migrate.discover())
    assert found[0].startswith("DO $$") and "CREATE ROLE dgate_api" in found[0]
    assert "GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_api" in found
    # 0036 takes dgate_app's blanket SELECT back after 0027 gave it: the order is the meaning.
    assert (found.index("GRANT SELECT ON ALL TABLES IN SCHEMA public TO dgate_app")
            < found.index("REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM dgate_app"))
    assert not any("--" in s for s in found)
    assert migrate.privilege_statements([]) == []


def test_a_no_privileges_restore_ends_with_the_migrations_grants_and_roles(
        reference, restored, monkeypatch):
    expected, expected_roles = reference
    assert len(expected) > 200 and {r[2] for r in expected} == set(ROLES)
    with psycopg.connect(restored) as c:
        assert _privileges(c) == set() and _roles(c) == []          # as after the restore

    monkeypatch.setenv("DGATE_API_PASSWORD", "api-test-password-1")
    monkeypatch.setenv("DGATE_WORKER_PASSWORD", "worker-test-password-1")
    monkeypatch.setenv("DGATE_APP_PASSWORD", "app-test-password-1")
    applied = migrate.migrate(restored)                 # the deploy's step, nothing else
    assert [m.version for m in applied] == [migrate.discover()[-1].version]

    with psycopg.connect(restored) as c:
        assert _privileges(c) == expected
        assert _roles(c) == expected_roles
        migrate.reapply_privileges(c)                   # a second run changes nothing
        assert _privileges(c) == expected

    # As on production: the API role reads and cannot write, the worker writes.
    with psycopg.connect(_as(restored, "dgate_api", "api-test-password-1")) as c:
        assert c.execute("SHOW statement_timeout").fetchone()[0] == "5s"
        assert c.execute("SELECT count(*) FROM source").fetchone()[0] > 0
        c.commit()
        c.execute("SET TRANSACTION READ WRITE")         # past the read-only default: the grant refuses
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE source SET update_freq = update_freq")
    with psycopg.connect(_as(restored, "dgate_worker", "worker-test-password-1")) as c:
        assert c.execute("UPDATE source SET update_freq = update_freq").rowcount > 0
        assert c.execute("SELECT count(*) FROM app_user").fetchone()[0] == 0   # pg_dump reads it
        c.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):   # 0060 took DELETE back
            c.execute("DELETE FROM project")
        c.rollback()
