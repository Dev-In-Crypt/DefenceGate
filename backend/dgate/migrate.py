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


def migrate(dsn: str | None = None, directory: Path | None = None) -> list[Migration]:
    """Apply everything pending. Returns what was applied."""
    from . import db

    with db.connect(dsn or settings().dsn) as conn:
        todo = pending(conn, directory)
        for migration in todo:
            apply(conn, migration)
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
