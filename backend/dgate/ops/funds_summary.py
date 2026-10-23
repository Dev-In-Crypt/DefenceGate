"""Fill `call.funds_summary` of the EU calls already stored, from the raw store (WP-92).

`sources.eu_portal.detail_fields` now writes the commercial summary of a topic's Objective / Expected
outcome (dgate/topic_summary.py) on every topic-details run. A call read before that has none, and a
closed call is never read again, so this reads the topic document each call was last built from out of
the raw store and writes the summary in.

No request is made: the raw store only. Nothing but `funds_summary` is touched (`details_hash` stays),
only where the value would change, so a second run writes nothing. A summary that no longer passes the
filter is cleared.

    python -m dgate.ops.funds_summary            # report only
    python -m dgate.ops.funds_summary --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from .. import db
from ..config import settings
from ..rawstore import build_store
from ..sources import eu_portal
from ..topic_summary import funds_summary

log = logging.getLogger("funds_summary")


@dataclass
class Result:
    calls: int = 0
    no_raw: int = 0            # no stored topic document with the hash the call was built from
    no_description: int = 0    # the stored document has no description
    failed: int = 0
    with_summary: int = 0      # a sentence passed the filter
    written: int = 0           # rows whose value changes (or changed, with --yes)

    def __str__(self) -> str:
        return (f"calls {self.calls}, with summary {self.with_summary}, to write/written {self.written}, "
                f"no description {self.no_description}, no raw {self.no_raw}, failed {self.failed}")


def run(*, write: bool = False, dsn: str | None = None) -> Result:
    result = Result()
    store = build_store()
    with db.connect(dsn or settings().dsn) as conn:
        src_id = db.source_id(conn, eu_portal.SOURCE_CODE)
        calls = conn.execute(
            """SELECT c.id, c.topic_code, c.details_hash, c.funds_summary
                 FROM call c
                WHERE c.source_id = %s AND c.topic_code IS NOT NULL AND c.details_hash IS NOT NULL
                ORDER BY c.id""", (src_id,)).fetchall()
        for c in calls:
            result.calls += 1
            raw = conn.execute(
                """SELECT storage_key FROM raw_ingest
                    WHERE source_id = %s AND native_id = %s AND content_hash = %s
                    ORDER BY fetched_at DESC LIMIT 1""",
                (src_id, c["topic_code"], c["details_hash"])).fetchone()
            if raw is None:
                result.no_raw += 1
                continue
            try:
                payload = store.get(raw["storage_key"])
                if not (isinstance(payload, dict) and payload.get("description")):
                    result.no_description += 1
                summary = funds_summary(payload)
            except Exception as exc:  # one unreadable object is not the run
                log.warning("call %s (%s): %s", c["id"], c["topic_code"], exc)
                result.failed += 1
                continue
            if summary:
                result.with_summary += 1
            if summary == c["funds_summary"]:
                continue
            result.written += 1
            if write:
                conn.execute("UPDATE call SET funds_summary = %s WHERE id = %s", (summary, c["id"]))
        if write:
            conn.commit()
        else:
            conn.rollback()
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="funds-summary", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write the summaries (default: report)")
    a = p.parse_args(argv)
    result = run(write=a.yes)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
