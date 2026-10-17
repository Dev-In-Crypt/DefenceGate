"""Build and store the weekly digest issues (dgate/weekly_digest.py).

    python -m dgate.ops.build_digest                 # list the weeks and which are stored
    python -m dgate.ops.build_digest --yes           # store the missing weeks and the last two again
    python -m dgate.ops.build_digest --yes --week 2026-W41 --max 1

Runs daily in the worker (`digest`). Derived from the archive; asks no website and no model.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from .. import db, weekly_digest
from ..config import settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="build-digest", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="store (default: list)")
    p.add_argument("--max", type=int, default=8, help="at most this many weeks per run")
    p.add_argument("--week", help="only this week, e.g. 2026-W41 (built again even if stored)")
    a = p.parse_args(argv)
    now = datetime.now(timezone.utc)
    with db.connect(settings().dsn) as conn:
        if a.week:
            if a.week not in weekly_digest.all_weeks(now):
                print(f"{a.week} is not an issue (before the archive, or not ended)")
                return 1
            if a.yes:
                started = time.monotonic()
                weekly_digest.refresh_week(conn, a.week, now=now)
                print(f"{a.week} stored in {time.monotonic() - started:.1f}s")
            return 0
        if not a.yes:
            held = {r["week"] for r in conn.execute("SELECT DISTINCT week FROM digest_issue").fetchall()}
            for w in weekly_digest.all_weeks(now):
                print(w, "stored" if w in held else "missing")
            return 0
        started = time.monotonic()
        print(weekly_digest.refresh(conn, now=now, max_builds=a.max), f"{time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
