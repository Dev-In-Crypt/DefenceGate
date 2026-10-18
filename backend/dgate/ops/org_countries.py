"""The country of a body, and the basis it rests on (WP-43, N4 of the third verification).

    python -m dgate.ops.org_countries          # report what would change, write nothing
    python -m dgate.ops.org_countries --yes    # write, then rebuild the directory table

The rule, in `cordis.seat_country` (deterministic, no model, nothing merged). A body's CORDIS record states the
address country of each of its sites, the country its site names end with, and a VAT number. For the organisations
that hold a PIC:

  address   one address country and nothing in the record contradicts it. The country stays, the basis is stored.
  vote      the site name and the VAT number agree on one country against the address: the country follows them
            (CSIC: address Trento IT, site "... Madrid ES", VAT ES; 8 of 8 CORDIS project pages show Spain).
            One voice against the address is not enough: the address stays.
  several   sites in several countries and nothing decides: the first in alphabetical order is kept, the whole
            list is stored in `country_sites` (EurOcean: Lisboa PT and The Hague NL).
  NULL      not looked at.

An organisation whose stored country differs from an undisputed address and has no basis is left alone and counted
(`address_differs_kept`): its country may have come from the buyer side. Reads the 72,534 organisations of CORDIS in
15 requests (robots.txt first, one a second), lands the pages, writes no project and no participation.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from .. import db, networks
from ..config import settings
from ..sources import cordis

log = logging.getLogger("org_countries")


def basis_counts(conn) -> dict[str, int]:
    """Organisations that hold a PIC (the ones a CORDIS record can speak for), by basis."""
    return {r["basis"]: r["n"] for r in conn.execute(
        """SELECT COALESCE(country_basis, 'not looked at') AS basis, count(*) AS n FROM organisation
            WHERE eu_pic IS NOT NULL AND merged_into IS NULL GROUP BY 1 ORDER BY 2 DESC""").fetchall()}


def run(*, apply: bool = False, sparql: cordis.Sparql | None = None, out=print) -> Counter:
    with db.connect(settings().dsn) as conn:
        before = basis_counts(conn)
    c = networks.run_cordis_countries(apply=apply, sparql=sparql)
    with db.connect(settings().dsn) as conn:
        after = basis_counts(conn)
    out(f"basis before: {before}")
    out(f"basis after:  {after}" + ("" if apply else "  (dry run: nothing written)"))
    out(f"{'written' if apply else 'would change'}: {dict(c)}" + ("" if apply else "  (add --yes)"))
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
