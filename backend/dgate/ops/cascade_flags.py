"""Fill `call.cascade` (financial support to third parties) from what we hold (dgate/cascade.py).

    python -m dgate.ops.cascade_flags          # report what would change, write nothing
    python -m dgate.ops.cascade_flags --yes    # write the changes

Idempotent: a second run changes nothing. Reads the call text and the eligibility facts already
extracted; asks no model and no website. Runs nightly in the worker (`cascade-flags`).
"""

from __future__ import annotations

import argparse
import sys

from .. import cascade, db, who_apply
from ..config import settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cascade-flags", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report)")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        print(cascade.run(conn, write=a.yes))
        # WP-92: who may apply from the call's own eligibility facts (the list badge), same pass as the nightly job.
        print("who may apply:", who_apply.run(conn, write=a.yes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
