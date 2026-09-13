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
from typing import Any, Iterable, Iterator

from . import db
from .config import settings
from .normalise import from_atlas_pl, from_ezamowienia, from_ted, strip_personal_data
from .rawstore import RawStore, build_store
from .sources.ted import content_hash

log = logging.getLogger("reprocess")

# One mapper per source. A source missing from here cannot be replayed, and
# saying so loudly is better than silently skipping a third of the archive.
MAPPERS = {
    "ted": from_ted,
    "pl_ezam": from_ezamowienia,
    "pl_atlas": from_atlas_pl,
}

# Marks a payload replay_key has not been handed and must read itself.
_UNREAD = object()

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
    """Enumerate the object store, filtered by source and date, oldest first.

    Ordered by when each object was written, which is when we observed it. A
    notice can have several payloads in one day -- PLACSP publishes one entry
    per modification -- and replaying them out of order would number the
    versions wrongly and attribute the wrong changed_fields to each. Key order
    cannot supply it, because what separates those payloads is a content hash.
    """
    found = []
    for key, written in store.listing(source or ""):
        day = _day_of(key)
        if since and (day is None or day < since):
            continue
        if until and (day is None or day > until):
            continue
        found.append((written, key))
    for _, key in sorted(found):
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
               dry_run: bool = False, payload: Any = _UNREAD) -> None:
    """Rebuild one record. Ordering is identical to a live run, minus the fetch."""
    from .pipeline import _finalise

    source_code = _source_of(key)
    result.scanned += 1

    if source_code not in MAPPERS and source_code not in PASSTHROUGH_SOURCES:
        log.warning("no mapper for source %s (key %s)", source_code, key)
        result.skipped += 1
        return

    if payload is _UNREAD:
        try:
            payload = store.get(key)
        except Exception as exc:  # noqa: BLE001 - one unreadable object must not stop a rebuild
            log.error("cannot read %s: %s", key, exc)
            result.failed += 1
            return
    if isinstance(payload, Exception):
        log.error("cannot read %s: %s", key, payload)
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

    opp_id, action = db.upsert_opportunity(conn, opportunity, digest, src_id)
    if action in ("unchanged", "stale"):
        # The notice's content has not changed, but what we conclude from it
        # can: a buyer added to the list makes an archived notice a buyer match
        # without any new version. Signals are derived, not source content, so
        # they are refreshed in place rather than versioned.
        db.refresh_classification(conn, opp_id, opportunity)
    # A replay into a populated database re-reads content that is already
    # archived, most of it older than the current version. Both are expected.
    if action in ("unchanged", "stale"):
        result.unchanged += 1
    else:
        result.rebuilt += 1


def _read_all(store: RawStore, keys: list[str], workers: int) -> list[Any]:
    """Fetch payloads concurrently, in the order given; a failure is returned, not raised."""
    def read(key: str) -> Any:
        try:
            return store.get(key)
        except Exception as exc:  # noqa: BLE001 - reported per key by replay_key
            return exc

    if workers <= 1:
        return [read(k) for k in keys]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="replay") as pool:
        return list(pool.map(read, keys))


class StoreUnavailable(RuntimeError):
    """The object store stopped answering, as opposed to one object being unreadable."""


def _read_batch(store: RawStore, keys: list[str], workers: int,
                attempts: int, pause: float) -> list[Any]:
    """Read a batch, waiting out an outage rather than recording one.

    One unreadable object must not stop a replay, and still does not. But a batch
    in which every single read fails is not a batch of bad objects, it is a store
    that is not there -- and the replay used to treat it as the former. On
    13 September 2026 the network dropped 7,800 keys into a reclassification,
    and the run carried on through 147,000 more, marking every one failed in
    seconds each, having read none of them.

    Now such a batch is retried with growing pauses, and if the store never comes
    back the run stops loudly, leaving everything after it unread rather than
    wrongly counted.
    """
    import time

    payloads = _read_all(store, keys, workers)
    for attempt in range(1, attempts + 1):
        if not keys or not all(isinstance(p, Exception) for p in payloads):
            return payloads
        wait = min(pause * (2 ** (attempt - 1)), 300.0)
        log.warning("every read in a batch of %s failed (%s); store looks unavailable, "
                    "attempt %s of %s, waiting %.0fs",
                    len(keys), payloads[0], attempt, attempts, wait)
        time.sleep(wait)
        payloads = _read_all(store, keys, workers)
    if keys and all(isinstance(p, Exception) for p in payloads):
        raise StoreUnavailable(f"object store unreachable after {attempts} retries: "
                               f"{payloads[0]}")
    return payloads


def reprocess(
    *, source: str | None = None, since: date | None = None, until: date | None = None,
    from_store: bool = False, dry_run: bool = False, dsn: str | None = None,
    keys: Iterable[str] | None = None, workers: int = 1, batch: int = 200,
    outage_attempts: int = 8, outage_pause: float = 15.0,
) -> ReplayResult:
    """Replay raw payloads through normalisation, classification and the archive.

    Idempotent: content already archived at any version is unchanged, and content
    older than the current version is stale, so a replay into a populated
    database writes versions only for what is genuinely new. Before
    13 September 2026 only the latest version was compared, and a replay into a
    populated database would have re-archived history as change.

    `workers` reads payloads concurrently. Each is an object-storage round trip,
    about half a second from here, so a sequential replay of PLACSP's 136,000
    payloads would take nineteen hours. Records are still archived one at a
    time, in key order, because version order depends on it.
    """
    store = build_store()
    result = ReplayResult()
    with db.connect(dsn or settings().dsn) as conn:
        if keys is None:
            keys = (keys_from_store(store, source, since, until) if from_store
                    else keys_from_index(conn, source, since, until))
        chunk: list[str] = []

        def flush() -> None:
            payloads = _read_batch(store, chunk, workers, outage_attempts, outage_pause)
            for key, payload in zip(chunk, payloads, strict=True):
                replay_key(conn, store, key, result, dry_run=dry_run, payload=payload)
            if not dry_run:
                conn.commit()
            log.info("reprocess: %s", result)
            chunk.clear()

        for key in keys:
            chunk.append(key)
            if len(chunk) >= batch:
                flush()
        if chunk:
            flush()
    log.info("reprocess done: %s", result)
    return result


def defence_buyer_names(conn, country: str) -> set[str]:
    """Normalised names that resolve to a flagged defence buyer in one country."""
    rows = conn.execute(
        """SELECT a.normalised_name AS n FROM organisation_alias a
             JOIN organisation o ON o.id = a.organisation_id
            WHERE o.is_defence_buyer AND o.country = %s
           UNION
           SELECT lower(canonical_name) FROM organisation
            WHERE is_defence_buyer AND country = %s""",
        (country, country),
    ).fetchall()
    return {r["n"] for r in rows}


def atlas_buyer_keys(conn) -> list[str]:
    """Raw keys of Atlas rows whose buyer is on the defence list.

    The Atlas backfill landed 1.4 million payloads, and replaying all of them to
    find the buyer matches would read every one from object storage. The local
    Parquet files already carry the buyer, so candidates are found there and
    only their payloads are read.
    """
    from pathlib import Path

    from .normalise import normalise_org_name
    from .sources import atlas_pl

    wanted = defence_buyer_names(conn, "PL")
    ids: list[str] = []
    for filename in atlas_pl.YEAR_FILES.values():
        path = Path(settings().atlas_dir) / filename
        if not path.exists():
            log.warning("%s not present; its buyer matches cannot be replayed", path)
            continue
        for row in atlas_pl.read_rows(path, batch_size=50_000, columns=["id", "buyer"]):
            if normalise_org_name(row.get("buyer") or "") in wanted:
                ids.append(str(row["id"]))
    log.info("atlas: %s rows from listed defence buyers", len(ids))
    rows = conn.execute(
        """SELECT r.storage_key FROM raw_ingest r JOIN source s ON s.id = r.source_id
            WHERE s.code = 'pl_atlas' AND r.native_id = ANY(%s)
            ORDER BY r.fetched_at""",
        (ids,),
    ).fetchall()
    return [r["storage_key"] for r in rows]


def reclassify_buyers(workers: int = 64, dsn: str | None = None) -> dict[str, ReplayResult]:
    """Re-run classification wherever the defence buyer list can change it.

    Every stored payload of the live sources, which are small enough to replay
    whole, and of the Atlas backfill only the rows from listed buyers.
    """
    from .pipeline import seed_buyers

    seed_buyers()
    results: dict[str, ReplayResult] = {}
    for code in ("ted", "pl_ezam", "es_placsp", "es_placsp_agg"):
        log.info("reclassify: %s", code)
        results[code] = reprocess(source=code, workers=workers, dsn=dsn)
    with db.connect(dsn or settings().dsn) as conn:
        keys = atlas_buyer_keys(conn)
    log.info("reclassify: pl_atlas, %s candidate payloads", len(keys))
    results["pl_atlas"] = reprocess(keys=keys, workers=workers, dsn=dsn)
    return results


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
    parser.add_argument("--workers", type=int, default=1,
                        help="payloads read from storage at once")
    parser.add_argument("--reclassify-buyers", action="store_true",
                        help="re-run classification wherever the buyer list can change it")
    args = parser.parse_args(argv)

    if args.reclassify_buyers:
        results = reclassify_buyers(workers=max(args.workers, 1))
        for code, res in results.items():
            print(f"{code}: {res}")
        return 0 if all(r.failed == 0 for r in results.values()) else 1

    result = reprocess(source=args.source, since=args.since, until=args.until,
                       from_store=args.from_store, dry_run=args.dry_run,
                       workers=args.workers)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
