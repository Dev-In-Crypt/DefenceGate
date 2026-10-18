"""Fill `call.open_to_ukraine` (open to Ukrainian participants) from what we hold (dgate/ukraine.py).

    python -m dgate.ops.ukraine_flags          # report what would change, write nothing
    python -m dgate.ops.ukraine_flags --yes    # write the changes

Idempotent: a second run changes nothing. Reads the call text and the eligibility facts already
extracted; asks no model and no website. Runs nightly in the worker with the cascade flags.
"""

from __future__ import annotations

import argparse
import sys

from .. import db, ukraine
from ..config import settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ukraine-flags", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report)")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        print(ukraine.run(conn, write=a.yes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
