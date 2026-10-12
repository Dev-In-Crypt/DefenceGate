"""Fill `opportunity.ted_ref` for records ingested before the column existed.

New records get the link at ingestion, through the normaliser. This replays the
archived raw payload of the older ones through the same normaliser and sets the
column; nothing is fetched and no version is written, because the link is
derived from what the source already said.

    python -m dgate.ops.link_ted                  # every source that states a link
    python -m dgate.ops.link_ted --source pl_ezam --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from .. import db
from ..config import settings
from ..normalise import Opportunity, from_atlas_pl, from_boamp, from_ezamowienia, from_tenderned
from ..rawstore import RawStore, build_store

log = logging.getLogger("link_ted")

# Sources whose own records can carry a TED reference. Spain's PLACSP parses
# during fetching and keeps no TED number, so it is not here.
MAPPERS: dict[str, Callable[[dict], Opportunity]] = {
    "nl_tenderned": from_tenderned,
    "pl_ezam": from_ezamowienia,
    "pl_atlas": from_atlas_pl,
    "fr_boamp": from_boamp,
}


LINK_COLUMNS = ("ted_ref", "related_native_id")


def backfill(conn, store: RawStore, source: str, *, dry_run: bool = False,
             column: str = "ted_ref") -> tuple[int, int]:
    """Returns (records read, links set).

    `column` is the link to fill: `ted_ref`, or `related_native_id` -- the notice
    a BOAMP rectificatif corrects, which the mapper reads from the same payloads.
    """
    if column not in LINK_COLUMNS:
        raise ValueError(f"not a link column: {column!r}")
    mapper = MAPPERS[source]
    src_id = db.source_id(conn, source)
    ids = [r["native_id"] for r in conn.execute(
        f"SELECT native_id FROM opportunity WHERE source_id = %s AND {column} IS NULL",
        (src_id,))]
    if not ids:
        return 0, 0
    # One scan for the latest raw key of every record, then read in key order so
    # a bundle is fetched once rather than once per record.
    keys = sorted(
        ((r["storage_key"], r["native_id"]) for r in conn.execute(
            "SELECT DISTINCT ON (native_id) native_id, storage_key FROM raw_ingest "
            "WHERE source_id = %s AND native_id = ANY(%s) ORDER BY native_id, id DESC",
            (src_id, ids))),
        key=lambda pair: pair[0],
    )
    read = linked = 0
    for key, native_id in keys:
        try:
            ref = getattr(mapper(store.get(key)), column)
        except Exception as exc:  # noqa: BLE001 - one unreadable record must not stop the rest
            log.warning("%s %s: %s", source, native_id, exc)
            continue
        read += 1
        if ref and not dry_run:
            conn.execute(
                f"UPDATE opportunity SET {column} = %s WHERE source_id = %s AND native_id = %s",
                (ref, src_id, native_id))
        linked += bool(ref)
    return read, linked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=sorted(MAPPERS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--related", action="store_true",
                        help="fill related_native_id (BOAMP rectificatifs) instead of ted_ref")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    store = build_store()
    column = "related_native_id" if args.related else "ted_ref"
    sources = [args.source] if args.source else (["fr_boamp"] if args.related else sorted(MAPPERS))
    with db.connect(settings().dsn) as conn:
        for source in sources:
            read, linked = backfill(conn, store, source, dry_run=args.dry_run, column=column)
            log.info("%s: read %s, %s set on %s%s", source, read, column, linked,
                     " (dry run)" if args.dry_run else "")
            conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
