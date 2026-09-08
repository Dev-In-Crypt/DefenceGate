"""Rebuild the serving layer from raw storage.

This module is the answer to one question: what is left if the database dies?

The pipeline lands every payload in object storage before it normalises
anything, so the database is a derived artefact. Losing it costs the time it
takes to replay, not the data. Nothing here talks to a source, so a replay
works when TED is down, when a national portal has removed the notice, and when
the source has changed its schema underneath us.

Two modes, and the difference matters on the worst day:

    from the index    reads `raw_ingest`, which is fast and ordered, and is the
                      right choice for replaying a parser fix
    from the store    enumerates the object store itself, which is the only
                      mode that survives losing the database, because
                      `raw_ingest` is a table inside it

    python -m dgate.reprocess --source ted --from 2026-09-01
    python -m dgate.reprocess --from-store          # after a total loss
    python -m dgate.reprocess --from-store --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date
from typing import Iterator

from . import db
from .config import settings
from .normalise import from_ezamowienia, from_ted, strip_personal_data
from .rawstore import RawStore, build_store
from .sources.ted import content_hash

log = logging.getLogger("reprocess")

# One mapper per source. A source missing from here cannot be replayed, and
# saying so loudly is better than silently skipping a third of the archive.
MAPPERS = {
    "ted": from_ted,
    "pl_ezam": from_ezamowienia,
}

# PLACSP stores the normalised record rather than the source XML, because the
# connector parses CODICE during fetching. Replaying it needs no mapper.
PASSTHROUGH_SOURCES = {"es_placsp", "es_placsp_agg"}


@dataclass
class ReplayResult:
    scanned: int = 0
    rebuilt: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (f"scanned {self.scanned}, rebuilt {self.rebuilt}, "
                f"unchanged {self.unchanged}, skipped {self.skipped}, "
                f"failed {self.failed}")


def _source_of(key: str) -> str:
    """`ted/2026/09/07/id.json` -> `ted`."""
    return key.split("/", 1)[0]


def _day_of(key: str) -> date | None:
    parts = key.split("/")
    if len(parts) < 4:
        return None
    try:
        return date(int(parts[1]), int(parts[2]), int(parts[3]))
    except (ValueError, IndexError):
        return None


def keys_from_store(
    store: RawStore, source: str | None = None,
    since: date | None = None, until: date | None = None,
) -> Iterator[str]:
    """Enumerate the object store, filtered by source and date."""
    for key in store.list(source or ""):
        day = _day_of(key)
        if since and (day is None or day < since):
            continue
        if until and (day is None or day > until):
            continue
        yield key


def keys_from_index(
    conn, source: str | None = None,
    since: date | None = None, until: date | None = None,
) -> Iterator[str]:
    """Read the keys out of `raw_ingest`, oldest first."""
    where, params = ["TRUE"], []
    if source:
        where.append("s.code = %s")
        params.append(source)
    if since:
        where.append("r.fetched_at >= %s")
        params.append(since)
    if until:
        where.append("r.fetched_at < %s + INTERVAL '1 day'")
        params.append(until)
    rows = conn.execute(
        f"""SELECT r.storage_key FROM raw_ingest r
              JOIN source s ON s.id = r.source_id
             WHERE {' AND '.join(where)}
             ORDER BY r.fetched_at""",
        params,
    ).fetchall()
    for row in rows:
        yield row["storage_key"]


def replay_key(conn, store: RawStore, key: str, result: ReplayResult,
               dry_run: bool = False) -> None:
    """Rebuild one record. Ordering is identical to a live run, minus the fetch."""
    from .pipeline import _finalise

    source_code = _source_of(key)
    result.scanned += 1

    if source_code not in MAPPERS and source_code not in PASSTHROUGH_SOURCES:
        log.warning("no mapper for source %s (key %s)", source_code, key)
        result.skipped += 1
        return

    try:
        payload = store.get(key)
    except Exception as exc:  # noqa: BLE001 - one unreadable object must not stop a rebuild
        log.error("cannot read %s: %s", key, exc)
        result.failed += 1
        return

    try:
        clean = strip_personal_data(payload)
        digest = content_hash(clean)
        if source_code in PASSTHROUGH_SOURCES:
            opportunity = db.opportunity_from_payload(clean)
        else:
            opportunity = MAPPERS[source_code](clean)
    except Exception as exc:  # noqa: BLE001
        log.error("cannot normalise %s: %s", key, exc)
        result.failed += 1
        return

    if dry_run:
        result.rebuilt += 1
        return

    src_id = db.source_id(conn, source_code)
    opportunity = _finalise(conn, opportunity, src_id)
    if not opportunity.is_defence:
        result.skipped += 1
        return

    _, action = db.upsert_opportunity(conn, opportunity, digest, src_id)
    if action == "unchanged":
        result.unchanged += 1
    else:
        result.rebuilt += 1


def reprocess(
    *, source: str | None = None, since: date | None = None, until: date | None = None,
    from_store: bool = False, dry_run: bool = False, dsn: str | None = None,
) -> ReplayResult:
    """Replay raw payloads through normalisation, classification and the archive.

    Idempotent by construction: the content hash decides, so replaying a day
    that is already in the database produces `unchanged` and writes no version.
    """
    store = build_store()
    result = ReplayResult()
    with db.connect(dsn or settings().dsn) as conn:
        keys = (keys_from_store(store, source, since, until) if from_store
                else keys_from_index(conn, source, since, until))
        for index, key in enumerate(keys, start=1):
            replay_key(conn, store, key, result, dry_run=dry_run)
            if index % 200 == 0:
                if not dry_run:
                    conn.commit()
                log.info("reprocess: %s", result)
    log.info("reprocess done: %s", result)
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="dgate-reprocess")
    parser.add_argument("--source", help="source code, e.g. ted")
    parser.add_argument("--from", dest="since", type=date.fromisoformat)
    parser.add_argument("--to", dest="until", type=date.fromisoformat)
    parser.add_argument("--from-store", action="store_true",
                        help="enumerate object storage instead of raw_ingest; "
                             "the mode that survives losing the database")
    parser.add_argument("--dry-run", action="store_true",
                        help="read and normalise, write nothing")
    args = parser.parse_args(argv)

    result = reprocess(source=args.source, since=args.since, until=args.until,
                       from_store=args.from_store, dry_run=args.dry_run)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
