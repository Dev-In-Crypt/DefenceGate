"""Operate on the raw payload store.

The store is the thing the archive cannot be rebuilt without, so it needs the
three operations an operator actually reaches for at three in the morning:
prove it works, see what is in it, and move it somewhere safer.

    python -m dgate.ops.rawstore_cli --check          write, read back, delete
    python -m dgate.ops.rawstore_cli --count
    python -m dgate.ops.rawstore_cli --copy-from ./raw    filesystem -> configured store
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from ..rawstore import FileRawStore, build_store

log = logging.getLogger("rawstore")


def check() -> str:
    """Write a probe object, read it back, delete it. Reports what it did.

    Configuration that looks right and credentials that are not accepted look
    identical until something writes. This is the difference.
    """
    store = build_store()
    key = f"_check/{datetime.now(timezone.utc):%Y%m%dT%H%M%S}Z.json"
    payload = {"probe": True, "written_at": datetime.now(timezone.utc).isoformat()}

    store.put(key, payload)
    if not store.exists(key):
        raise RuntimeError(f"wrote {key} but the store says it is not there")
    got = store.get(key)
    if got != payload:
        raise RuntimeError(f"read back something else: {got!r}")

    deleted = store.delete(key)
    where = settings().s3_endpoint or settings().s3_bucket \
        if settings().raw_backend == "s3" else str(settings().raw_dir)
    return (f"{settings().raw_backend} store at {where}: "
            f"wrote, read and {'deleted' if deleted else 'could not delete'} {key}")


def count() -> dict[str, int]:
    """How many objects per source. The cheapest sanity check there is."""
    per_source: Counter[str] = Counter()
    for key in build_store().list():
        per_source[key.split("/", 1)[0]] += 1
    return dict(sorted(per_source.items()))


def copy_from(directory: Path, dry_run: bool = False) -> int:
    """Copy a filesystem store into the configured one.

    For the move from `fs` to `s3`: the payloads already collected are the
    archive's only insurance, and leaving them behind on the old disk would
    quietly undo the point of moving.
    """
    source = FileRawStore(directory)
    target = build_store()
    copied = 0
    for key in source.list():
        if target.exists(key):
            continue
        if not dry_run:
            target.put(key, source.get(key))
        copied += 1
        if copied % 200 == 0:
            log.info("copied %s objects", copied)
    return copied


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="dgate-rawstore")
    parser.add_argument("--check", action="store_true",
                        help="write a probe object, read it back, delete it")
    parser.add_argument("--count", action="store_true", help="objects per source")
    parser.add_argument("--create-bucket", action="store_true",
                        help="create the configured bucket if it does not exist")
    parser.add_argument("--copy-from", type=Path, metavar="DIR",
                        help="copy a filesystem store into the configured one")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.create_bucket:
        store = build_store()
        if not hasattr(store, "ensure_bucket"):
            print(f"the {settings().raw_backend} backend has no buckets")
            return 64
        created = store.ensure_bucket()
        print(f"bucket {settings().s3_bucket}: {'created' if created else 'already there'}")
        return 0
    if args.check:
        print(check())
        return 0
    if args.count:
        totals = count()
        for source, number in totals.items():
            print(f"{source:16} {number}")
        print(f"{'total':16} {sum(totals.values())}")
        return 0
    if args.copy_from:
        copied = copy_from(args.copy_from, dry_run=args.dry_run)
        print(f"{'would copy' if args.dry_run else 'copied'} {copied} objects "
              f"from {args.copy_from}")
        return 0

    parser.print_help()
    return 64


if __name__ == "__main__":
    sys.exit(main())
