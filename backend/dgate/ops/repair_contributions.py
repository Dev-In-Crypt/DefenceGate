"""Re-derive the contribution notes of the stored CORDIS participations (WP-41, N1 to N3).

    python -m dgate.ops.repair_contributions          # report what would change, write nothing
    python -m dgate.ops.repair_contributions --yes    # write, then rebuild the directory table

Reads the stored participations and the projects' EU contribution, applies the same rules the CORDIS
loader applies (`networks.settle_amounts`, so the two cannot drift) and writes what differs:

  * a third party stored as 0            -> NULL, note `linked_third_party`
  * an amount that is NULL, no note      -> note `no_payment_stated`
  * a project whose amounts add up to more than its EU contribution
                                         -> every positive amount NULL, kept in `contribution_stated`,
                                            note `exceeds_project_total`
  * a participant or coordinator of a project that has third parties
                                         -> note `gross_of_third_parties` (the amount is unchanged)
  * an EDF participation (no amount, no note) -> note `source_states_none`

No network access, no language model, no row deleted; a stated amount is only ever moved to
`contribution_stated`. Idempotent: a second run finds nothing to change. A project whose amounts
later stop exceeding its total (the service corrected it) gets its amounts back from
`contribution_stated`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from collections.abc import Iterator
from typing import Any

from .. import db, networks
from ..config import settings

log = logging.getLogger("repair_contributions")

BATCH = 5000


def _projects(conn) -> Iterator[list[dict[str, Any]]]:
    """The active CORDIS participations, one list per project. A named cursor: 386,000 rows are not
    held in memory at once."""
    with conn.cursor(name="repair_contributions") as cur:
        cur.itersize = 20000
        cur.execute(
            """SELECT pa.id, pa.project_id, pa.role, pa.contribution, pa.contribution_note,
                      pa.contribution_stated, p.eu_contribution AS fund
                 FROM participation pa JOIN project p ON p.id = pa.project_id
                 JOIN source s ON s.id = p.source_id
                WHERE s.code = 'cordis' AND pa.active ORDER BY pa.project_id, pa.id""")
        group: list[dict[str, Any]] = []
        for row in cur:
            if group and row["project_id"] != group[0]["project_id"]:
                yield group
                group = []
            group.append(row)
        if group:
            yield group


def derive(group: list[dict[str, Any]]) -> list[tuple[int, float | None, str | None, float | None]]:
    """(id, contribution, note, stated) for each participation of one project, as the loader would write them."""
    seen = [networks.source_view(r["role"], r["contribution"], r["contribution_note"],
                                 r["contribution_stated"]) for r in group]
    fund = None if group[0]["fund"] is None else float(group[0]["fund"])
    settled = networks.settle_amounts([(r["role"], a, n) for r, (a, n) in zip(group, seen, strict=True)], fund)
    return [(r["id"], *s) for r, s in zip(group, settled, strict=True)]


def run(conn, *, apply: bool = False, out=print) -> Counter:
    c: Counter = Counter()
    changes: list[tuple[float | None, str | None, float | None, int]] = []
    for group in _projects(conn):          # read to the end first: a commit would close the cursor
        wanted = derive(group)
        withheld = False
        for row, (pid, amount, note, stated) in zip(group, wanted, strict=True):
            c["participations"] += 1
            old = (None if row["contribution"] is None else float(row["contribution"]),
                   row["contribution_note"],
                   None if row["contribution_stated"] is None else float(row["contribution_stated"]))
            if old != (amount, note, stated):
                c["changed"] += 1
                c[f"to_{note or 'plain'}"] += 1
                changes.append((amount, note, stated, pid))
            withheld = withheld or note == "exceeds_project_total"
        c["projects_withheld"] += withheld
    edf = conn.execute(
        """SELECT count(*) AS n FROM participation pa JOIN project p ON p.id = pa.project_id
             JOIN source s ON s.id = p.source_id
            WHERE s.code = 'edf_factsheets' AND pa.contribution IS NULL AND pa.contribution_note IS NULL""").fetchone()["n"]
    c["to_source_states_none"] = edf
    if apply:
        conn.execute(
            """UPDATE participation pa SET contribution_note = 'source_states_none'
                 FROM project p, source s
                WHERE p.id = pa.project_id AND s.id = p.source_id AND s.code = 'edf_factsheets'
                  AND pa.contribution IS NULL AND pa.contribution_note IS NULL""")
        conn.commit()
        with conn.cursor() as cur:
            for i in range(0, len(changes), BATCH):
                cur.executemany(
                    """UPDATE participation SET contribution = %s, contribution_note = %s,
                              contribution_stated = %s WHERE id = %s""", changes[i:i + BATCH])
                conn.commit()
        c["directory_rows"] = networks.refresh_organisation_network(conn)["organisations"]
    out(f"{'written' if apply else 'would change'}: {dict(c)}" + ("" if apply else "  (dry run; add --yes)"))
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes", action="store_true", help="write; without it nothing changes")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with db.connect(settings().dsn) as conn:
        run(conn, apply=a.yes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
