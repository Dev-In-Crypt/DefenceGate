"""Migration runner.

Plain SQL files applied in numeric order and recorded in ``schema_migrations``.
No ORM, no migration framework: the schema rules that matter here (append-only
archive, coverage floors, personal-data boundaries) are easier to audit when
the SQL is the SQL.

Rules:
  - a file is applied exactly once and never edited afterwards; corrections go
    into a new file
  - each file runs inside one transaction, so a failure leaves nothing half
    applied
  - applying is idempotent: running the runner twice applies nothing twice

    python -m dgate.migrate           apply everything pending
    python -m dgate.migrate --status  show applied and pending
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import settings

log = logging.getLogger("migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")

BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INT PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover(directory: Path | None = None) -> list[Migration]:
    """All migrations, ordered. Rejects duplicate versions and stray names."""
    directory = directory or MIGRATIONS_DIR
    found: dict[int, Migration] = {}
    for path in sorted(directory.glob("*.sql")):
        m = _NAME.match(path.name)
        if not m:
            raise ValueError(
                f"migration filename must be NNNN_lower_snake_case.sql: {path.name}")
        version = int(m.group(1))
        if version in found:
            raise ValueError(
                f"duplicate migration version {version}: "
                f"{found[version].path.name} and {path.name}")
        found[version] = Migration(version, m.group(2), path)
    return [found[v] for v in sorted(found)]


def applied_versions(conn) -> set[int]:
    conn.execute(BOOTSTRAP)
    conn.commit()
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] if isinstance(r, dict) else r[0] for r in rows}


def pending(conn, directory: Path | None = None) -> list[Migration]:
    done = applied_versions(conn)
    return [m for m in discover(directory) if m.version not in done]


def apply(conn, migration: Migration) -> None:
    """One migration, one transaction."""
    log.info("applying %04d_%s", migration.version, migration.name)
    try:
        conn.execute(migration.sql())
        conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
            (migration.version, migration.name),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# Top-level statement splitting: comments dropped, strings, quoted names and dollar bodies kept whole.
_TOKENS = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|(\$(?:[A-Za-z_]\w*)?\$).*?\1|;",
                     re.S)
_PRIVILEGE = re.compile(r"(?:GRANT|REVOKE|ALTER\s+DEFAULT\s+PRIVILEGES|ALTER\s+ROLE)\b", re.I)
_ROLE_BLOCK = re.compile(r"DO\b.*\bCREATE\s+ROLE\b", re.I | re.S)


def _statements(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    pos = 0
    for m in _TOKENS.finditer(text):
        buf.append(text[pos:m.start()])
        pos = m.end()
        token = m.group()
        if token == ";":
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(" " if token.startswith(("--", "/*")) else token)
    out.append("".join(buf + [text[pos:]]).strip())
    return [s for s in out if s]


def privilege_statements(migrations: list[Migration]) -> list[str]:
    """Every role and privilege statement of these migrations, in the order they ran:
    the role-creating DO blocks, ALTER ROLE, GRANT, REVOKE, ALTER DEFAULT PRIVILEGES."""
    return [s for m in migrations for s in _statements(m.sql())
            if _PRIVILEGE.match(s) or _ROLE_BLOCK.match(s)]


def reapply_privileges(conn, directory: Path | None = None) -> int:
    """Bring the service roles and their grants back to what the applied migrations made (WP-163).

    Backups are dumped with --no-privileges (roles are cluster objects, not in a dump), so a
    restored database has no dgate_api / dgate_worker / dgate_app roles on a new server and no
    grants on any table. Replaying the applied migrations' own privilege statements, in order, in
    one transaction, rebuilds exactly that state; on a database that has it already it changes
    nothing. `migrate` runs it before the pending migrations (their GRANTs need the roles), so a
    restore ends with `migrate` like any deploy.
    """
    done = applied_versions(conn)
    todo = privilege_statements([m for m in discover(directory) if m.version in done])
    try:
        for statement in todo:
            conn.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(todo)


def set_role_passwords(conn) -> list[str]:
    """Give the service roles of migration 0024 a login, from the environment.

    The passwords are never in SQL or in the repository: the operator sets
    DGATE_API_PASSWORD, DGATE_WORKER_PASSWORD and DGATE_APP_PASSWORD, and this runs after every
    migrate so a rotated value takes effect on the next deploy. A role whose
    variable is unset is left as it was.
    """
    import os

    from psycopg import sql

    done: list[str] = []
    for role, variable in (("dgate_api", "DGATE_API_PASSWORD"),
                           ("dgate_worker", "DGATE_WORKER_PASSWORD"),
                           ("dgate_app", "DGATE_APP_PASSWORD")):
        password = os.environ.get(variable)
        if not password:
            continue
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        if not exists:
            continue
        conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)))
        done.append(role)
    return done


def migrate(dsn: str | None = None, directory: Path | None = None) -> list[Migration]:
    """Apply everything pending. Returns what was applied."""
    from . import db

    with db.connect(dsn or settings().dsn) as conn:
        log.info("roles and grants: %d statements re-applied", reapply_privileges(conn, directory))
        todo = pending(conn, directory)
        for migration in todo:
            apply(conn, migration)
        for role in set_role_passwords(conn):
            log.info("login set for role %s", role)
    if not todo:
        log.info("database is up to date")
    return todo


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="dgate-migrate")
    parser.add_argument("--status", action="store_true", help="show state, apply nothing")
    parser.add_argument("--dsn", default=None)
    args = parser.parse_args(argv)

    from . import db

    if args.status:
        with db.connect(args.dsn or settings().dsn) as conn:
            done = applied_versions(conn)
            for m in discover():
                mark = "applied" if m.version in done else "PENDING"
                print(f"{m.version:04d}_{m.name:<28} {mark}")
        return 0

    applied = migrate(args.dsn)
    for m in applied:
        print(f"applied {m.version:04d}_{m.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
