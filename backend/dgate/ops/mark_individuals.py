"""Owner-run: mark the organisations that are natural persons and take them out of the directory (WP-39, N2).

    python -m dgate.ops.mark_individuals            # dry run: how many, by reason, and what would change
    python -m dgate.ops.mark_individuals --yes      # mark them and rebuild the directory table

`dgate.individuals.individual_reason` decides from the name; the monthly CORDIS and EDF loads and the snapshot job
do the same through `networks.refresh_organisation_network`, so this command is for the first run after the
rule lands and for a run after the rule is corrected. Nothing is deleted: `organisation.individual_reason` is set
(or cleared when a corrected rule no longer finds the name), and the directory rebuild leaves the organisation
out of `organisation_network`. The dry run prints counts only, never a name.
"""

from __future__ import annotations

import argparse
import sys

from .. import db, individuals, networks
from ..config import settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.mark_individuals", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (the default is a dry run)")
    a = p.parse_args(argv)
    with db.connect(settings().dsn) as conn:
        if not a.yes:
            res = individuals.mark_individuals(conn, write=False)
            n = conn.execute("SELECT count(*) AS n FROM organisation_network").fetchone()["n"]
            print("dry run (add --yes):", res, "| organisations in the directory now:", n)
            return 0
        done = networks.refresh_organisation_network(conn)
        persons = conn.execute("SELECT count(*) AS n FROM organisation WHERE individual_reason IS NOT NULL").fetchone()["n"]
        print("marked and rebuilt:", done, "| organisations marked as natural persons:", persons)
    return 0


if __name__ == "__main__":
    sys.exit(main())
