"""Owner-run: organisations decided, row by row, to be a natural person or a sole trader, taken out of every page (WP-138).

    python -m dgate.ops.person_rows --ids 23766,95574,159048     # report: what marking these rows would change
    python -m dgate.ops.person_rows --ids 23766,95574,159048 --yes
    python -m dgate.ops.person_rows --undo [--yes]               # every row this command marked, back as it was

`individuals.individual_reason` marks the persons among project participants (`ops.mark_individuals`) and the award
loader never makes a supplier of a person (`awards.person_reason`); a buyer, and a row made before those rules, is
checked by neither: TED 495013-2020 names a person as its buyer (organisation 159048, served as one), and two Polish
sole traders' rows (a trading name with the owner's name) stood unmarked. The decision is a review of each row (the
name's form, its number, its notices), so rows are marked by id only: `organisation.individual_reason` =
`person_reviewed`, and a row that is the buyer of a notice is withheld as a buyer (a `suppression` of kind
organisation, reason `natural_person`, decided by this command: the trigger of migration 0047 sets
`opportunity.buyer_withheld` on its notices). No rule marks buyers: the winners' person test (`awards.person_reason`)
read 851 of the 6,859 live buyer rows of 25 October 2026 as persons, nearly all of them public bodies ("Bundesamt ...",
a two-word agency). Output is counts, never a name.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone

from .. import db
from ..config import settings
from . import suppress as suppress_ops

REVIEWED = "person_reviewed"
WITHHELD_REASON = "natural_person"
DECIDED_BY = "ops.person_rows"


def mark(conn, ids: list[int], *, write: bool) -> Counter:
    rows = conn.execute(
        """SELECT g.id, (SELECT count(*) FROM opportunity o WHERE o.buyer_org_id = g.id) AS notices
             FROM organisation g
            WHERE g.id = ANY(%s) AND g.merged_into IS NULL AND g.individual_reason IS NULL""", (ids,)).fetchall()
    c: Counter = Counter(asked=len(ids), marked=len(rows), not_live_or_already_marked=len(ids) - len(rows))
    buyers = [r for r in rows if r["notices"]]
    c["buyers_withheld"] = len(buyers)
    c["notices_buyer_withheld"] = sum(r["notices"] for r in buyers)
    if write and rows:
        conn.execute("UPDATE organisation SET individual_reason = %s WHERE id = ANY(%s)",
                     (REVIEWED, [r["id"] for r in rows]))
        for r in buyers:
            suppress_ops.add(conn, kind="organisation", source=None, native_id=None, organisation=r["id"],
                         reason=WITHHELD_REASON, requested_at=datetime.now(timezone.utc), decided_by=DECIDED_BY,
                         note="WP-138: the notice names a natural person as its buyer; no request")
        conn.commit()
    return c


def undo(conn, *, write: bool) -> Counter:
    marked = [r["id"] for r in conn.execute(
        "SELECT id FROM organisation WHERE individual_reason = %s", (REVIEWED,)).fetchall()]
    entries = [r["id"] for r in conn.execute(
        "SELECT id FROM suppression WHERE decided_by = %s AND lifted_at IS NULL", (DECIDED_BY,)).fetchall()]
    c = Counter(unmarked=len(marked), withholdings_lifted=len(entries))
    if write:
        conn.execute("UPDATE organisation SET individual_reason = NULL WHERE id = ANY(%s)", (marked,))
        for e in entries:
            suppress_ops.lift(conn, e, by=DECIDED_BY, note="WP-138 undo")
        conn.commit()
    return c


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dgate.ops.person_rows", description=__doc__.split("\n\n")[0])
    p.add_argument("--ids", help="comma-separated organisation ids decided to be persons")
    p.add_argument("--undo", action="store_true", help="unmark every row this command marked")
    p.add_argument("--yes", action="store_true", help="write (the default is a report)")
    a = p.parse_args(argv)
    if not (a.undo or a.ids):
        p.error("give --ids (rows reviewed as persons) or --undo")
    with db.connect(settings().dsn) as conn:
        if a.undo:
            c = undo(conn, write=a.yes)
        else:
            c = mark(conn, sorted({int(x) for x in a.ids.split(",") if x.strip()}), write=a.yes)
    if a.yes:
        print(suppress_ops.LIST_HINT)
    print("written" if a.yes else "report only (add --yes to write)")
    for k in sorted(c):
        print(f"  {k}: {c[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
