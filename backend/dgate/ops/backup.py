"""Database backups.

Two independent guarantees, and it is worth being clear about which does what.

The raw payload store is the *primary* one: the database is derived from it,
and `dgate.reprocess --from-store` rebuilds the whole serving layer without
touching a source. That protects against losing the database and against a bad
parser, and it works when the sources are down or have deleted the notice.

A dump is the *fast* one. Replaying two hundred thousand payloads takes hours;
restoring a dump takes minutes, and it also carries what a replay cannot
reconstruct: the observation timeline. A version row records *when* we saw a
change, and no amount of replaying tells you that after the fact.

So both exist, and neither is redundant.

    python -m dgate.ops.backup                    write a dump
    python -m dgate.ops.backup --list             what is on disk
    python -m dgate.ops.backup --verify           restore the newest into a
                                                  scratch database and count
"""

from __future__ import annotations

import argparse
import gzip
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from ..config import settings

log = logging.getLogger("backup")

STAMP = "%Y%m%dT%H%M%SZ"


@dataclass
class Backup:
    path: Path
    taken_at: datetime
    bytes: int

    @property
    def megabytes(self) -> float:
        return self.bytes / 1_000_000


def backup_dir() -> Path:
    return Path(os.environ.get("DGATE_BACKUP_DIR", "./backups"))


def _pg_env(dsn: str) -> dict[str, str]:
    """Pass the password through the environment, never on the command line."""
    parsed = urlparse(dsn)
    env = dict(os.environ)
    if parsed.password:
        env["PGPASSWORD"] = parsed.password
    return env


def with_database(dsn: str, database: str) -> str:
    """Point a DSN at a different database, by parsing rather than replacing.

    `dsn.replace("/dgate", "/postgres")` looks equivalent and is not: in
    `postgresql://dgate:dgate@host/dgate` the first match is inside the
    username, so the result connects as the wrong user to the wrong database.
    """
    parsed = urlparse(dsn)
    return urlunparse(parsed._replace(path=f"/{database}"))


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(
            f"{tool} is not on PATH. Install the PostgreSQL client tools, or run "
            f"this inside the postgres container.")
    return path


def create(dsn: str | None = None, directory: Path | None = None) -> Backup:
    """Write one compressed dump. Never overwrites: the name carries the time."""
    dsn = dsn or settings().dsn
    directory = directory or backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    taken_at = datetime.now(timezone.utc)
    target = directory / f"dgate-{taken_at.strftime(STAMP)}.sql.gz"
    partial = target.with_suffix(".gz.partial")

    # Dump to a .partial name and rename on success, so a crash mid-dump cannot
    # leave a truncated file that looks like a usable backup.
    with subprocess.Popen(
        [_require("pg_dump"), "--no-owner", "--no-privileges", dsn],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_pg_env(dsn),
    ) as proc:
        with gzip.open(partial, "wb") as out:
            assert proc.stdout is not None
            shutil.copyfileobj(proc.stdout, out)
        stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.returncode != 0:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump failed ({proc.returncode}): {stderr.strip()[:400]}")

    partial.rename(target)
    result = Backup(target, taken_at, target.stat().st_size)
    log.info("backup written: %s (%.1f MB)", target.name, result.megabytes)
    return result


def listing(directory: Path | None = None) -> list[Backup]:
    directory = directory or backup_dir()
    if not directory.exists():
        return []
    out: list[Backup] = []
    for path in sorted(directory.glob("dgate-*.sql.gz")):
        try:
            stamp = datetime.strptime(path.name[len("dgate-"):-len(".sql.gz")], STAMP)
        except ValueError:
            continue
        out.append(Backup(path, stamp.replace(tzinfo=timezone.utc), path.stat().st_size))
    return sorted(out, key=lambda b: b.taken_at)


def prune(keep_days: int = 30, directory: Path | None = None) -> list[Path]:
    """Delete dumps older than the retention window, always keeping the newest.

    Keeping the newest unconditionally matters: a month of downtime must not
    end with an empty backup directory.
    """
    backups = listing(directory)
    if not backups:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    removed = []
    for backup in backups[:-1]:
        if backup.taken_at < cutoff:
            backup.path.unlink()
            removed.append(backup.path)
            log.info("pruned %s", backup.path.name)
    return removed


def verify(backup: Backup | None = None, dsn: str | None = None) -> dict[str, int]:
    """Restore the newest dump into a scratch database and count what arrived.

    An unverified backup is a belief, not a backup. This is what turns it into
    a fact, and it is why the scratch database is dropped afterwards rather
    than kept: the point is the restore working today, not the copy.
    """
    import psycopg
    from psycopg.rows import dict_row

    backup = backup or (listing()[-1] if listing() else None)
    if backup is None:
        raise RuntimeError("no backup to verify")

    dsn = dsn or settings().dsn
    scratch = f"dgate_verify_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    admin_dsn = with_database(dsn, "postgres")

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{scratch}"')
        conn.execute(f'CREATE DATABASE "{scratch}"')
    try:
        target_dsn = with_database(dsn, scratch)
        # Stream the decompressed bytes through a pipe rather than handing psql
        # the file object: subprocess takes the underlying descriptor, which
        # still points at the compressed file, so psql would be fed gzip.
        with subprocess.Popen(
            [_require("psql"), "--quiet", "-v", "ON_ERROR_STOP=1", target_dsn],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            env=_pg_env(dsn),
        ) as proc:
            assert proc.stdin is not None
            try:
                with gzip.open(backup.path, "rb") as src:
                    shutil.copyfileobj(src, proc.stdin)
                proc.stdin.close()
            except BrokenPipeError:
                # psql gave up early. Its own message is the useful one, so let
                # the stderr read below surface it instead of this.
                pass
            stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        if proc.returncode != 0:
            raise RuntimeError(f"restore failed: {stderr.strip()[:400]}")

        counts: dict[str, int] = {}
        with psycopg.connect(target_dsn, row_factory=dict_row) as conn:
            for table in ("opportunity", "opportunity_version", "raw_ingest",
                          "organisation", "organisation_alias", "ingest_run"):
                counts[table] = conn.execute(f"SELECT count(*) n FROM {table}").fetchone()["n"]
        log.info("verified %s: %s", backup.path.name, counts)
        return counts
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch}"')


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="dgate-backup")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--verify", action="store_true",
                        help="restore the newest dump into a scratch database")
    parser.add_argument("--keep-days", type=int, default=30)
    args = parser.parse_args(argv)

    if args.list:
        for backup in listing():
            print(f"{backup.path.name}  {backup.megabytes:8.1f} MB  {backup.taken_at:%Y-%m-%d %H:%M}Z")
        return 0

    if args.verify:
        counts = verify()
        print(" ".join(f"{k}={v}" for k, v in counts.items()))
        return 0

    result = create()
    prune(args.keep_days)
    print(f"{result.path} ({result.megabytes:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
