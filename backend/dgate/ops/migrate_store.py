"""Copy every object from one store to another, and prove each copy.

The raw store is the archive's insurance: the database holds only an index into
it, so while the move from R2 to a Storage Box is in flight there is exactly one
copy of nine million notices. The order is therefore the whole design, and it is
the compaction's order -- nothing is trusted because a call returned:

  1. download the object and hash it;
  2. upload it under the same key;
  3. download it *from the destination* and hash that;
  4. count it copied only if the two hashes are equal.

Keys are identical on both sides, so `raw_ingest.storage_key` needs no change:
the index points at `ted/2026/10/05/bundle-0000.jsonl.gz#17` whichever backend
answers.

It never deletes anything, on either side. Removing the originals is a separate,
deliberate act after the copy has been audited against the index.

Resumable: an object already at the destination with the source's byte count is
skipped. That is safe because every write is whole or absent -- a `.part-` file
renamed into place -- so a destination object of the right size was completed by
an earlier run of this tool.

    python -m dgate.ops.migrate_store --from-backend s3 --to-backend sftp --dry-run
    python -m dgate.ops.migrate_store --from-backend s3 --to-backend sftp
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from ..rawstore import RawStore, build_store

log = logging.getLogger("migrate-store")

CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class Report:
    copied: int = 0
    skipped: int = 0
    absent: int = 0
    bytes_copied: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"{self.copied} copied ({self.bytes_copied / 1e9:.2f} GB), "
                f"{self.skipped} already there, {self.absent} not files, "
                f"{len(self.failed)} failed")


def copy_one(source: RawStore, target: RawStore, key: str) -> tuple[str, int]:
    """Copy and verify one object. Returns (outcome, bytes).

    Outcomes: "absent" (the source key is not a file), "skipped" (already at the
    destination, same size), "copied". Raises if the copy cannot be proved.
    """
    size = source.size(key)
    if size is None:
        return "absent", 0
    if target.size(key) == size:
        return "skipped", size

    with tempfile.TemporaryDirectory(prefix="migrate-") as work:
        down, back = Path(work) / "down", Path(work) / "back"
        source.fetch(key, down)
        if down.stat().st_size != size:
            raise RuntimeError(f"{key}: downloaded {down.stat().st_size} bytes, "
                               f"the source says {size}")
        digest = sha256_of(down)
        target.put_file(key, down)
        down.unlink()                               # the disk holds one object at a time
        target.fetch(key, back)
        if sha256_of(back) != digest:
            raise RuntimeError(f"{key}: what the destination holds is not what was sent")
    return "copied", size


def migrate(source: RawStore, target: RawStore, *, prefix: str = "", workers: int = 3,
            dry_run: bool = False) -> Report:
    report = Report()
    keys = [key for key, _ in source.listing(prefix, suffix="")]
    log.info("%s objects listed under %r", len(keys), prefix)
    started = time.monotonic()

    def one(key: str) -> tuple[str, str, int, str | None]:
        try:
            if dry_run:
                size = source.size(key)
                if size is None:
                    return key, "absent", 0, None
                return key, ("skipped" if target.size(key) == size else "copied"), size, None
            outcome, size = copy_one(source, target, key)
            return key, outcome, size, None
        except Exception as exc:                    # one bad object must not stop the rest
            return key, "failed", 0, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, (key, outcome, size, error) in enumerate(pool.map(one, keys), 1):
            if outcome == "copied":
                report.copied += 1
                report.bytes_copied += size
            elif outcome == "skipped":
                report.skipped += 1
            elif outcome == "absent":
                report.absent += 1
            else:
                report.failed.append((key, error or "unknown"))
                log.error("FAILED %s: %s", key, error)
            if done % 250 == 0 or done == len(keys):
                seconds = max(time.monotonic() - started, 1e-9)
                log.info("%s/%s -- %s -- %.1f MB/s", done, len(keys), report,
                         report.bytes_copied / 1e6 / seconds)
    return report


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("botocore", "boto3", "urllib3", "paramiko"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="dgate-migrate-store")
    parser.add_argument("--from-backend", required=True, choices=["fs", "s3", "sftp"])
    parser.add_argument("--to-backend", required=True, choices=["fs", "s3", "sftp"])
    parser.add_argument("--prefix", default="", help="only keys under this prefix")
    parser.add_argument("--workers", type=int, default=3,
                        help="parallel objects; the box caps sessions per account and is shared")
    parser.add_argument("--dry-run", action="store_true",
                        help="count what would be copied, touch nothing")
    args = parser.parse_args(argv)
    if args.from_backend == args.to_backend:
        parser.error("source and destination are the same backend")

    report = migrate(build_store(args.from_backend), build_store(args.to_backend),
                     prefix=args.prefix, workers=args.workers, dry_run=args.dry_run)
    print(report)
    for key, error in report.failed[:20]:
        print(f"failed: {key}: {error}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
