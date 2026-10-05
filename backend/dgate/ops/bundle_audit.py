"""Does every bundled index row still point at its own payload?

A bundled record is addressed by line: `<bundle>#<line>`. That is exact as long
as reader and writer agree on what ends a line, and for a while they did not --
`str.splitlines()` treats U+2028, U+2029, the vertical tab, the form feed and
the next-line control as line boundaries, while the writer ends a record with a
newline and `json.dumps(ensure_ascii=False)` leaves those characters inside the
text of a notice. A bundle holding one such notice reads one line too many, and
every record after it is off by one: the archive returns the wrong payload for
the right key, quietly.

The check is not "do the counts match" but "does the line hash to what the index
recorded when the payload was landed". That catches the off-by-one and anything
else that could put a record in the wrong place.

    python -m dgate.ops.bundle_audit --source ted              check
    python -m dgate.ops.bundle_audit --source ted --repair     check and repoint
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from .. import db
from ..config import settings
from ..rawstore import RawStore, build_store, record_key, split_record_key

log = logging.getLogger("bundle-audit")


@dataclass
class Report:
    bundles: int = 0
    rows: int = 0
    misplaced: int = 0
    repaired: int = 0
    unresolved: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"{self.bundles} bundles, {self.rows} rows, {self.misplaced} misplaced, "
                f"{self.repaired} repaired, {len(self.unresolved)} unresolved")


def hasher(source: str) -> Callable[[Any], str]:
    from .compact_raw import hasher as known

    return known(source)


def bundles_of(conn: Any, source: str) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT split_part(r.storage_key, '#', 1) AS bundle
             FROM raw_ingest r JOIN source s ON s.id = r.source_id
            WHERE s.code = %s AND r.storage_key LIKE '%%#%%'
         ORDER BY 1""",
        (source,),
    ).fetchall()
    return [row["bundle"] for row in rows]


def rows_by_bundle(source: str, limit: int | None = None) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Every bundled index row of a source, handed out one bundle at a time.

    One pass over the index instead of one query per bundle. The per-bundle query
    -- `storage_key LIKE '<bundle>#%'` -- has no index to use: the partial one
    covers only the plain keys, and a parameterised LIKE cannot use a pattern
    index anyway. Each of those queries was a sequential scan of nine million
    rows, and with two audits running at once they held both cores of the host
    for hours; the same audit had looked fast only because it ran alone.

    Ordered with COLLATE "C", on purpose. Under the database's own locale
    punctuation is ignored at the first comparison, so keys of different bundles
    can interleave; byte order is what guarantees every row of a bundle is
    contiguous, which is all the grouping relies on.

    Opens its own connection: a named cursor is closed by a commit, and the
    repair mode commits on the connection that is doing the repairing.
    """
    with db.connect(settings().dsn) as conn:
        with conn.cursor(name="bundle_audit") as cursor:
            cursor.itersize = 20_000
            cursor.execute(
                """SELECT r.id, r.storage_key, r.content_hash
                     FROM raw_ingest r JOIN source s ON s.id = r.source_id
                    WHERE s.code = %s AND r.storage_key LIKE '%%#%%'
                 ORDER BY r.storage_key COLLATE "C" """,
                (source,))
            current: str | None = None
            batch: list[dict[str, Any]] = []
            seen = 0
            for row in cursor:
                bundle = row["storage_key"].partition("#")[0]
                if bundle != current:
                    if batch:
                        yield current, batch  # type: ignore[misc]
                        seen += 1
                        if limit is not None and seen >= limit:
                            return
                    current, batch = bundle, []
                batch.append(row)
            if batch and (limit is None or seen < limit):
                yield current, batch  # type: ignore[misc]


def audit_bundle(conn: Any, store: RawStore, source: str, bundle: str, *,
                 repair: bool = False,
                 rows: list[dict[str, Any]] | None = None) -> tuple[int, int, int, list[str]]:
    """Check every row pointing into one bundle. Returns counts and unresolved keys.

    `rows` are the bundle's index rows when the caller already has them; without
    them the bundle is looked up, which is right for one bundle and wrong for all.
    """
    hash_of = hasher(source)
    if rows is None:
        rows = conn.execute(
            """SELECT id, storage_key, content_hash FROM raw_ingest
                WHERE storage_key LIKE %s ORDER BY id""",
            (bundle + "#%",),
        ).fetchall()
    if not rows:
        return 0, 0, 0, []

    lines = store._bundle_lines(bundle)
    import json

    hashes = [hash_of(json.loads(line)) for line in lines]
    by_hash: dict[str, int] = {}
    for line, digest in enumerate(hashes):
        by_hash.setdefault(digest, line)

    misplaced = repaired = 0
    unresolved: list[str] = []
    for row in rows:
        _, line = split_record_key(row["storage_key"])
        if line is not None and 0 <= line < len(hashes) and hashes[line] == row["content_hash"]:
            continue
        misplaced += 1
        correct = by_hash.get(row["content_hash"])
        if correct is None:
            unresolved.append(row["storage_key"])
            continue
        if repair:
            conn.execute("UPDATE raw_ingest SET storage_key = %s WHERE id = %s",
                         (record_key(bundle, correct), row["id"]))
            repaired += 1
    if repair and repaired:
        conn.commit()
    return len(rows), misplaced, repaired, unresolved


def audit(source: str, *, repair: bool = False, store: RawStore | None = None,
          limit: int | None = None) -> Report:
    store = store or build_store()
    report = Report()
    with db.connect(settings().dsn) as conn:
        for bundle, bundle_rows in rows_by_bundle(source, limit):
            rows, misplaced, repaired, unresolved = audit_bundle(
                conn, store, source, bundle, repair=repair, rows=bundle_rows)
            report.bundles += 1
            report.rows += rows
            report.misplaced += misplaced
            report.repaired += repaired
            report.unresolved += unresolved
            if misplaced:
                log.warning("%s: %s of %s rows misplaced, %s repaired, %s unresolved",
                            bundle, misplaced, rows, repaired, len(unresolved))
            if report.bundles % 200 == 0:
                log.info("%s", report)
    return report


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("botocore").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="dgate-bundle-audit")
    parser.add_argument("--source", required=True)
    parser.add_argument("--repair", action="store_true",
                        help="repoint rows whose payload is elsewhere in the same bundle")
    parser.add_argument("--limit", type=int, default=None, help="check only this many bundles")
    args = parser.parse_args(argv)
    report = audit(args.source, repair=args.repair, limit=args.limit)
    print(report)
    for key in report.unresolved[:20]:
        print(f"unresolved: {key}")
    return 1 if (report.misplaced - report.repaired) else 0


if __name__ == "__main__":
    sys.exit(main())
