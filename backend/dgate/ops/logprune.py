"""Bound the age of the reverse proxy's log files (Privacy section 2: 14 days).

Docker's json-file driver rotates by size only, so a line's age depends on traffic. Caddy
therefore writes its logs as JSON to files in a volume (infra/Caddyfile), and this runs
beside it (compose service `logprune`, hourly):

  * a rolled file (`access-2026-10-15T08-12-33.123.log[.gz]`) is deleted once its last write
    is older than the limit, so no line in it is older than the limit plus the interval;
  * the active file (`access.log`, `caddy.log`) is cut in place: lines older than the limit
    are removed from its head. Caddy holds it open for appending, so it is rewritten under
    the same inode and not replaced. A line appended during the rewrite can be lost; for a
    request log that is accepted. (ponytail: a few lines may be lost per run; a log shipper
    with its own retention would replace this if the logs ever matter for more than abuse.)

    python -m dgate.ops.logprune --dir /var/log/caddy --days 14 [--every 3600]

Without --every it runs once and exits. It reads only the timestamp (`ts`, Unix seconds)
of each line and never parses or prints the rest.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger("logprune")

ROLLED = re.compile(r"-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}")


def _ts(line: bytes) -> float | None:
    try:
        value = json.loads(line).get("ts")
    except (ValueError, AttributeError):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def trim_active(path: Path, cutoff: float) -> int:
    """Remove lines older than `cutoff` from the head of `path`. Returns lines removed.
    A line that carries no timestamp takes the age of the line before it (a log starts
    with one that does); the file is chronological."""
    with open(path, "r+b") as fh:
        lines = fh.read().splitlines(keepends=True)
        first_kept, last = 0, None
        for i, line in enumerate(lines):
            got = _ts(line)
            last = got if got is not None else last
            if last is not None and last >= cutoff:
                first_kept = i
                break
        else:
            first_kept = len(lines)
        if first_kept == 0:
            return 0
        fh.seek(0)
        fh.write(b"".join(lines[first_kept:]))
        fh.truncate()
    return first_kept


def prune(directory: Path, days: float, now: float | None = None) -> tuple[int, int]:
    """(rolled files deleted, lines cut from active files) for one pass."""
    now = time.time() if now is None else now
    cutoff = now - days * 86400
    deleted = cut = 0
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(".gz") or (name.endswith(".log") and ROLLED.search(name)):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        elif name.endswith(".log"):
            cut += trim_active(path, cutoff)
    return deleted, cut


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.logprune", description=__doc__.split("\n\n")[0])
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--days", type=float, default=14)
    p.add_argument("--every", type=float, default=0, help="seconds between passes; 0 = once")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    while True:
        try:
            deleted, cut = prune(args.dir, args.days)
            log.info("pass done: %s rolled files deleted, %s lines cut", deleted, cut)
        except OSError as exc:  # a missing volume is retried, not fatal
            log.warning("pass failed: %s", type(exc).__name__)
        if not args.every:
            return 0
        time.sleep(args.every)


if __name__ == "__main__":
    raise SystemExit(main())
