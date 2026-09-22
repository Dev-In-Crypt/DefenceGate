"""Compact one-object-per-notice payloads into bundles, then delete the originals.

The first 4.8 million notices of the TED history were written one object each.
Object storage bills per object written and per gigabyte kept: those objects
cost about 22 dollars to write and hold about 55 GB. Rewritten as gzipped
bundles of JSON lines they are about a thousand objects and a seventh of the
size, which puts the whole store inside the free tier.

This is the one place ingested payloads are deleted, so the order is the whole
design, and each step has to hold before the next begins:

  1. read every payload of a chunk and check it against the content hash the
     index recorded when it was landed -- a payload that no longer matches is
     a problem to stop for, not to paper over;
  2. write the bundle, read it back, and check every line against the same
     hashes -- a bundle is trusted because it was verified, not because the
     write returned;
  3. repoint every index row at `<bundle>#<line>` and journal the originals in
     `compaction_pending`, in one transaction;
  4. only then delete the originals, and clear them from the journal.

A crash anywhere leaves either the originals (steps 1-3: nothing repointed) or
a journal saying exactly what is left to delete (after 3). The next run drains
the journal first. Resumable by construction: a row that points into a bundle
is no longer a candidate.

    python -m dgate.ops.compact_raw --source ted
    python -m dgate.ops.compact_raw --source ted --max-chunks 2   # a rehearsal
    python -m dgate.ops.compact_raw --source ted --dry-run        # read and verify only
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from .. import db
from ..config import settings
from ..rawstore import BUNDLE_EXTENSION, RawStore, build_store, record_key, split_record_key

log = logging.getLogger("compact")

# Five thousand notices is about 55 MB held in memory before the write and a
# bundle of roughly 8 MB: small enough to be safe on a 4 GB host, large enough
# that 4.8 million notices become under a thousand objects.
DEFAULT_CHUNK = 5000

# How each source computed the content hash it recorded. Compaction refuses a
# source it cannot verify: deleting a payload whose copy was never checked is
# the one mistake this tool exists not to make.
_HASHERS: dict[str, Callable[[Any], str]] = {}


def hasher(source: str) -> Callable[[Any], str]:
    if not _HASHERS:
        from ..sources import ted

        _HASHERS["ted"] = ted.content_hash
    if source not in _HASHERS:
        raise ValueError(f"no content hash known for {source!r}; refusing to compact it")
    return _HASHERS[source]


@dataclass
class Progress:
    chunks: int = 0
    objects: int = 0
    deleted: int = 0
    bundles: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"{self.chunks} chunks, {self.objects} objects into "
                f"{len(self.bundles)} bundles, {self.deleted} originals deleted")


def compact_bundle_key(first_key: str, first_id: int) -> str:
    """Where a chunk's bundle goes: beside its first original, named by row id.

    Named `compact-<id>` and never `bundle-<n>`, because `bundle-0000` for a
    storage day can already exist -- the history writes one per publication
    day -- and overwriting an existing bundle would destroy the records in it.
    The first row id is unique, so two chunks can never share a name.
    """
    prefix = first_key.rsplit("/", 1)[0]
    return f"{prefix}/compact-{first_id:010d}{BUNDLE_EXTENSION}"


def next_chunk(conn: Any, source: str, after_id: int, size: int) -> list[dict[str, Any]]:
    """The next rows still pointing at one-object-per-notice keys, in id order."""
    return conn.execute(
        """SELECT r.id, r.storage_key, r.content_hash
             FROM raw_ingest r JOIN source s ON s.id = r.source_id
            WHERE s.code = %s AND r.id > %s AND r.storage_key NOT LIKE '%%#%%'
         ORDER BY r.id
            LIMIT %s""",
        (source, after_id, size),
    ).fetchall()


def drain_pending(conn: Any, store: RawStore) -> int:
    """Finish deletions a previous run journaled but did not complete."""
    rows = conn.execute("SELECT storage_key FROM compaction_pending").fetchall()
    keys = [row["storage_key"] for row in rows]
    if not keys:
        return 0
    still_used = _still_referenced(conn, keys)
    safe = [k for k in keys if k not in still_used]
    store.delete_many(safe)
    conn.execute("DELETE FROM compaction_pending WHERE storage_key = ANY(%s)", (safe,))
    conn.commit()
    log.info("drained %s journaled deletions (%s skipped: still referenced)",
             len(safe), len(still_used))
    return len(safe)


def _still_referenced(conn: Any, keys: list[str]) -> set[str]:
    rows = conn.execute(
        """SELECT DISTINCT storage_key FROM raw_ingest
            WHERE storage_key NOT LIKE '%%#%%' AND storage_key = ANY(%s)""",
        (keys,),
    ).fetchall()
    return {row["storage_key"] for row in rows}


def compact_chunk(conn: Any, store: RawStore, source: str, rows: list[dict[str, Any]], *,
                  workers: int = 32, dry_run: bool = False, delete: bool = True) -> tuple[str, int]:
    """Steps 1 to 4 for one chunk. Returns the bundle key and originals deleted."""
    hash_of = hasher(source)

    # One line per distinct key: a key seen by two rows holds one payload, and
    # every row pointing at it is repointed to the same line.
    order: list[str] = []
    expected: dict[str, str] = {}
    for row in rows:
        key = row["storage_key"]
        if split_record_key(key)[1] is not None:
            continue
        if key not in expected:
            order.append(key)
            expected[key] = row["content_hash"]
        elif expected[key] != row["content_hash"]:
            raise RuntimeError(f"{key} is recorded under two content hashes; stopping")

    # 1. read and verify every original.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        payloads = list(pool.map(store.get, order))
    for key, payload in zip(order, payloads, strict=True):
        if hash_of(payload) != expected[key]:
            raise RuntimeError(f"{key} no longer matches the hash it was landed with; stopping")

    bundle = compact_bundle_key(order[0], rows[0]["id"])
    if dry_run:
        log.info("dry run: %s objects verified, would write %s", len(order), bundle)
        return bundle, 0

    # 2. write the bundle and verify it line by line.
    store.put_records(bundle, payloads)
    store._bundle_cache = None                      # read back from the store, not memory
    lines = store._bundle_lines(bundle)
    if len(lines) != len(order):
        raise RuntimeError(f"{bundle} holds {len(lines)} lines, not {len(order)}; stopping")
    for line, key in enumerate(order):
        if hash_of(store.get(record_key(bundle, line))) != expected[key]:
            raise RuntimeError(f"{bundle}#{line} does not match {key}; stopping")

    # 3. repoint and journal, in one transaction: committed together or not at all.
    #
    # By row id, in one statement. Repointing by key -- one UPDATE per key,
    # WHERE storage_key = $1 -- ran at a fifth of a second each on 22 September
    # 2026: the planner cannot prove a parameter satisfies the partial index's
    # NOT LIKE predicate, so every one was a scan of nine million rows, and 4.8
    # million of them would have taken eleven days. A row pointing at the same
    # key from outside this chunk is still caught: step 4 refuses to delete an
    # object anything references.
    line_of = {key: line for line, key in enumerate(order)}
    ids = [row["id"] for row in rows if row["storage_key"] in line_of]
    new_keys = [record_key(bundle, line_of[row["storage_key"]])
                for row in rows if row["storage_key"] in line_of]
    conn.execute(
        """UPDATE raw_ingest r SET storage_key = u.new_key
             FROM unnest(%s::bigint[], %s::text[]) AS u(id, new_key)
            WHERE r.id = u.id""",
        (ids, new_keys))
    conn.execute(
        """INSERT INTO compaction_pending (storage_key, bundle)
           SELECT k, %s FROM unnest(%s::text[]) AS k
           ON CONFLICT (storage_key) DO NOTHING""",
        (bundle, order))
    conn.commit()

    if not delete:
        return bundle, 0

    # 4. delete what nothing points at any more, then clear the journal.
    still_used = _still_referenced(conn, order)
    if still_used:
        raise RuntimeError(f"{len(still_used)} originals still referenced after repointing")
    deleted = store.delete_many(order)
    conn.execute("DELETE FROM compaction_pending WHERE storage_key = ANY(%s)", (order,))
    conn.commit()
    return bundle, deleted


def compact(source: str, *, chunk: int = DEFAULT_CHUNK, max_chunks: int | None = None,
            workers: int = 32, dry_run: bool = False, delete: bool = True,
            store: RawStore | None = None) -> Progress:
    hasher(source)                                   # refuse early, before touching anything
    store = store or build_store()
    progress = Progress()
    with db.connect(settings().dsn) as conn:
        if not dry_run:
            drain_pending(conn, store)
        after = 0
        while max_chunks is None or progress.chunks < max_chunks:
            rows = next_chunk(conn, source, after, chunk)
            if not rows:
                break
            bundle, deleted = compact_chunk(conn, store, source, rows, workers=workers,
                                            dry_run=dry_run, delete=delete)
            after = rows[-1]["id"]
            progress.chunks += 1
            progress.objects += len(rows)
            progress.deleted += deleted
            progress.bundles.append(bundle)
            log.info("%s: chunk %s -> %s (%s objects, %s deleted); %s",
                     source, progress.chunks, bundle.rsplit("/", 1)[-1], len(rows),
                     deleted, progress)
    return progress


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("botocore").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="dgate-compact")
    parser.add_argument("--source", required=True)
    parser.add_argument("--chunk", type=int, default=DEFAULT_CHUNK)
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--dry-run", action="store_true",
                        help="read and verify, write and delete nothing")
    parser.add_argument("--keep-originals", action="store_true",
                        help="bundle and repoint, but do not delete")
    args = parser.parse_args(argv)
    progress = compact(args.source, chunk=args.chunk, max_chunks=args.max_chunks,
                       workers=args.workers, dry_run=args.dry_run,
                       delete=not args.keep_originals)
    print(progress)
    return 0


if __name__ == "__main__":
    sys.exit(main())

