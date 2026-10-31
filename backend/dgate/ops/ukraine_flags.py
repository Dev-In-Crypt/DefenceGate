"""Fill `call.open_to_ukraine` (open to Ukrainian participants) from what we hold (dgate/ukraine.py).

    python -m dgate.ops.ukraine_flags          # report what would change, write nothing
    python -m dgate.ops.ukraine_flags --yes    # write the changes

Idempotent: a second run changes nothing. Reads the call text and the eligibility facts already
extracted; asks no model and no website. Runs nightly in the worker with the cascade flags.
Every call whose answer changes is listed and logged (WP-167: the EDF calls under Ukraine's association).
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from .. import db, ukraine
from ..config import settings

log = logging.getLogger("ukraine_flags")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="ukraine-flags", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report)")
    a = p.parse_args(argv)
    changes: list[dict[str, Any]] = []
    with db.connect(settings().dsn) as conn:
        counts = ukraine.run(conn, write=a.yes, changes=changes)
    for c in changes:
        log.info("%s call %s %s: %s -> %s", "written" if a.yes else "would change", c["id"], c["topic"] or "", c["before"], c["after"])
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
