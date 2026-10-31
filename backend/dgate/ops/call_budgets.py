"""WP-167: the call document's own budget total on each EU call (`call.document_budget`), from the documents already stored.

The portal states the voted EU budget; the call document may state a larger "estimated available call budget" and, in a
footnote, how much of it is the voted EU budget (`eu_portal.document_budget`). This reads the stored text of each call's
call document (`call_document_text`, the documents the call's detail lists as "Call document"), so no request is made:
a document not yet stored is read by the eligibility reader first, and the next run picks it up. Only the calls whose value
changes are written, so a second run writes nothing. Runs nightly in the worker with the cascade flags.

    python -m dgate.ops.call_budgets            # report only
    python -m dgate.ops.call_budgets --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from psycopg.types.json import Jsonb

from .. import db
from ..config import settings
from ..sources import eu_portal

log = logging.getLogger("call_budgets")


def run(conn, *, write: bool = False, changes: list[dict[str, Any]] | None = None) -> dict[str, int]:
    # Each document once: the calls of one call share its document.
    budgets = {r["url"]: b for r in conn.execute(
        r"SELECT url, text FROM call_document_text WHERE text ~* 'estimated\s+available\s+call\s+budget'").fetchall()
        if (b := eu_portal.document_budget(r["text"])) is not None}
    rows = conn.execute(
        """SELECT c.id, c.topic_code, c.document_budget,
                  array_remove(array_agg(doc.value->>'url' ORDER BY doc.ord)
                               FILTER (WHERE doc.value->>'label' ILIKE '%%call document%%'), NULL) AS urls
             FROM call c
             LEFT JOIN LATERAL jsonb_array_elements(COALESCE(c.conditions_raw->'documents', '[]'::jsonb)) WITH ORDINALITY AS doc(value, ord)
               ON TRUE
            GROUP BY c.id ORDER BY c.id""").fetchall()
    counts = {"calls": len(rows), "with_total": 0, "with_voted": 0, "changed": 0}
    for r in rows:
        url = next((u for u in r["urls"] or [] if u in budgets), None)
        value = {**budgets[url], "url": url} if url else None
        counts["with_total"] += value is not None
        counts["with_voted"] += bool(value and value["voted"] is not None)
        if value == r["document_budget"]:
            continue
        counts["changed"] += 1
        if changes is not None:
            changes.append({"id": r["id"], "topic": r["topic_code"], "before": r["document_budget"], "after": value})
        if write:
            conn.execute("UPDATE call SET document_budget = %s WHERE id = %s", (Jsonb(value) if value else None, r["id"]))
    if write:
        conn.commit()
    else:
        conn.rollback()
    return counts


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="call-budgets", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report)")
    a = p.parse_args(argv)
    changes: list[dict[str, Any]] = []
    with db.connect(settings().dsn) as conn:
        counts = run(conn, write=a.yes, changes=changes)
    for c in changes:
        log.info("%s call %s %s: %s -> %s", "written" if a.yes else "would change", c["id"], c["topic"] or "", c["before"], c["after"])
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
