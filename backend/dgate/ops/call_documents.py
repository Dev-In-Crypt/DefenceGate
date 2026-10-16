"""Fill the document links of the EU calls already stored (ux-funding F9).

`sources.eu_portal.detail_fields` now keeps the links of a topic's conditions block (call
document, application form templates, work programme) in `conditions_raw.documents`. A call
read before that has none, and a closed call is never read again, so this reads the topic
document each call was last built from out of the raw store and writes the links in.

No request is made: the raw store only. Nothing but `conditions_raw.documents` is touched
(`details_hash` stays, so the normal refresh still sees the same document as read), only where
the value would change, so a second run writes nothing.

    python -m dgate.ops.call_documents            # report only
    python -m dgate.ops.call_documents --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from .. import db
from ..config import settings
from ..rawstore import build_store
from ..sources import eu_portal

log = logging.getLogger("call_documents")


@dataclass
class Result:
    calls: int = 0
    no_raw: int = 0           # no stored topic document with the hash the call was built from
    failed: int = 0
    with_documents: int = 0   # the stored document links at least one document
    written: int = 0          # rows whose value changes (or changed, with --yes)

    def __str__(self) -> str:
        return (f"calls {self.calls}, with documents {self.with_documents}, to write/written "
                f"{self.written}, no raw {self.no_raw}, failed {self.failed}")


def run(*, write: bool = False, dsn: str | None = None) -> Result:
    result = Result()
    store = build_store()
    with db.connect(dsn or settings().dsn) as conn:
        src_id = db.source_id(conn, eu_portal.SOURCE_CODE)
        calls = conn.execute(
            """SELECT c.id, c.topic_code, c.details_hash, c.conditions_raw->'documents' AS documents
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
                documents = eu_portal.call_documents(payload)
            except Exception as exc:  # one unreadable object is not the run
                log.warning("call %s (%s): %s", c["id"], c["topic_code"], exc)
                result.failed += 1
                continue
            if documents:
                result.with_documents += 1
            if documents == (c["documents"] or []):
                continue
            result.written += 1
            if write:
                conn.execute(
                    """UPDATE call SET conditions_raw =
                              COALESCE(conditions_raw, '{}'::jsonb) || jsonb_build_object('documents', %s::jsonb)
                        WHERE id = %s""", (Jsonb(documents), c["id"]))
        if write:
            conn.commit()
        else:
            conn.rollback()
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="call-documents", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write the links (default: report)")
    a = p.parse_args(argv)
    result = run(write=a.yes)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
