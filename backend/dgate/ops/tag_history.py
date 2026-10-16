"""Annotate, as `history`, the versions a command that loads the past already wrote.

Until migration 0054 a history load, the replay of an archive or a backfill wrote its
versions like any other: `observed_at` is the day we read them, so `/v1/changes` listed
"11,231 amendments in 14 days" that were deadline moves of 2022 (UX walk-throughs of 16
October 2026). From then on those commands annotate what they write (`db.historical_load`);
this tool does the same for the versions written before, from the evidence there is:

  A. the version was observed within 36 hours before a day marker of a history or replay run
     for its source was written (`backfill_day`: the source's own code for `history`,
     `<code>-replay` and `<code>-replay-progress` for a replay, `<code>-requalify-*` for a
     re-qualification, `ted-defence:*` for the TED defence history), or while a
     command an operator started (an `ingest_run` row whose owner is `cli:`, as a PLACSP
     backfill writes) was running for it; and
  B. the version's own source date (`source_updated_at`, else `published_at`) is more than
     LAG_DAYS days before the day it was observed. A live collection sees a change within a
     day or two; a change dated weeks earlier was read from the past.

Both must hold. A live amendment seen while a history run was busy is dated that week and is
left alone; so is an old version no marker explains (it is counted and shown, not tagged).
A version already annotated as not the publisher's doing (`remapped`, `reread`, `out_of_order`,
`correction`: 273k of them from the re-derivation of 12-13 October) is left as it is, as it is not
listed anyway. One note per version and kind, so a second run writes nothing, and nothing is
deleted or changed in place.

    python -m dgate.ops.tag_history --since-days 16       # report only, the recent versions
    python -m dgate.ops.tag_history --yes                 # annotate, all versions

Run it again after a history load that was still running has finished: the day it was in has
no marker until it ends.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from .. import db
from ..config import settings

log = logging.getLogger("tag_history")

LAG_DAYS = 7
MARKER_WINDOW = "36 hours"
NOTE = "tagged afterwards: seen by a history/replay/backfill run; the change is older than the observation"

# The versions of one chunk of ids that qualify (A and B). The ids come from `UNANNOTATED`, so that no
# payload is read for a version that is not in question (273k versions of the 12-13 October re-derivation sit
# in the last 14 days: a plan that reads every payload took over a minute on production).
CANDIDATES = f"""
    SELECT v.id, s.code AS source_code, o.native_id, v.observed_at,
           left(coalesce(v.payload->>'source_updated_at', v.payload->>'published_at'), 10) AS own_date
      FROM opportunity_version v
      JOIN opportunity o ON o.id = v.opportunity_id
      JOIN source s ON s.id = o.source_id
     WHERE v.id = ANY(%(ids)s)
       AND coalesce(v.payload->>'source_updated_at', v.payload->>'published_at') ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
       AND (v.observed_at AT TIME ZONE 'UTC')::date
           - left(coalesce(v.payload->>'source_updated_at', v.payload->>'published_at'), 10)::date
           > {LAG_DAYS}
       AND ( EXISTS (SELECT 1 FROM backfill_day b
                      WHERE (b.source_code IN (s.code, s.code || '-replay', s.code || '-replay-progress')
                             OR b.source_code LIKE s.code || '-requalify-%%'
                             OR (s.code = 'ted' AND b.source_code LIKE 'ted-defence:%%'))
                        AND b.finished_at >= v.observed_at
                        AND b.finished_at < v.observed_at + interval '{MARKER_WINDOW}')
          OR EXISTS (SELECT 1 FROM ingest_run r
                      WHERE r.source_id = s.id AND r.owner LIKE 'cli:%%'
                        AND v.observed_at >= r.started_at
                        AND v.observed_at <= coalesce(r.finished_at, now())) )
"""

# Later versions that no note says anything about yet, observed since a date.
UNANNOTATED = """
    SELECT v.id FROM opportunity_version v
     WHERE v.version > 1 AND v.observed_at >= %(since)s
       AND NOT EXISTS (SELECT 1 FROM opportunity_version_note n
                        WHERE n.opportunity_version_id = v.id
                          AND n.kind IN ('history', 'remapped', 'reread', 'out_of_order', 'correction'))
"""
CHUNK = 5000


def run(*, write: bool = False, dsn: str | None = None, since_days: int | None = None) -> dict[str, int]:
    """`since_days`: look only at versions observed in the last N days (the 14 days the change
    list shows are what matters first, and it is a much smaller read); default: all of them."""
    with db.connect(dsn or settings().dsn) as conn:
        conn.execute("SET statement_timeout = 0")
        since = (datetime.now(timezone.utc) - timedelta(days=since_days) if since_days is not None
                 else datetime(2000, 1, 1, tzinfo=timezone.utc))
        ids = [r["id"] for r in conn.execute(UNANNOTATED, {"since": since}).fetchall()]
        by_source: dict[str, int] = {}
        written = 0
        for start in range(0, len(ids), CHUNK):
            args = {"ids": ids[start:start + CHUNK], "note": NOTE}
            found = conn.execute(CANDIDATES, args).fetchall()
            for r in found:
                by_source[r["source_code"]] = by_source.get(r["source_code"], 0) + 1
            if write and found:
                written += conn.execute(
                    """INSERT INTO opportunity_version_note (opportunity_version_id, kind, note)
                       SELECT x, 'history', %(note)s FROM unnest(%(found)s::bigint[]) AS x
                       ON CONFLICT (opportunity_version_id, kind) DO NOTHING""",
                    {"note": NOTE, "found": [r["id"] for r in found]}).rowcount
                conn.commit()
        log.info("%s versions %s: %s", sum(by_source.values()), "annotated" if write else "to annotate",
                 by_source)
        if write:
            log.info("annotated %s versions", written)
        # What is old and unexplained: counted for the report, never tagged.
        unexplained = 0
        for start in range(0, len(ids), CHUNK):
            unexplained += conn.execute(
                f"""SELECT count(*) AS n FROM opportunity_version v
                     WHERE v.id = ANY(%(ids)s) AND v.observed_at >= now() - interval '14 days'
                       AND coalesce(v.payload->>'source_updated_at', v.payload->>'published_at')
                           ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                       AND (v.observed_at AT TIME ZONE 'UTC')::date
                           - left(coalesce(v.payload->>'source_updated_at',
                                           v.payload->>'published_at'), 10)::date > {LAG_DAYS}
                       AND NOT EXISTS (SELECT 1 FROM opportunity_version_note n
                                        WHERE n.opportunity_version_id = v.id AND n.kind = 'history')""",
                {"ids": ids[start:start + CHUNK]}).fetchone()["n"]
        log.info("old versions of the last 14 days still shown as changes: %s", unexplained)
    return {**by_source, "_unexplained_last_14_days": unexplained}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--yes", action="store_true", help="annotate; without it only report")
    parser.add_argument("--since-days", type=int, default=None,
                        help="only versions observed in the last N days (default: all)")
    args = parser.parse_args(argv)
    run(write=args.yes, since_days=args.since_days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
