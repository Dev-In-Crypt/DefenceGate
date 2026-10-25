"""WP-132 (round-7 funding audit): apply the corrected funding rules to the calls already stored. No request, no model.

  * Unlisted calls: `call.unlisted_runs` (migration 0134) of every EU portal call the portal last called open or forthcoming, in scope:
    the number of complete, successful nightly runs (a run with its minimum, `expected_min`, met) that started after the call was
    last listed. From UNLISTED_AFTER_RUNS the call is `unlisted` (funding.EFFECTIVE_STATUS). The nightly run counts on from here
    (db.count_unlisted); a call listed again is reset by the run that lists it.
  * The topic text's consortium rule (`min_consortium_size`, `min_member_states`) read again from the stored conditions text with the
    corrected `eu_portal.consortium_rule`.
  * Stored eligibility facts whose quote was not found: checked again against the stored document (`eligibility.reverify_stored`).
  * Then the derived flags from the facts, as the nightly `cascade_flags` job does: cascade, Ukraine, who may apply and (new) the
    "Minimum consortium" row from the facts (`who_apply.consortium_of`).

Only rows whose value would change are written, so a second run writes nothing. The report names every row it changes.

    python -m dgate.ops.wp132_funding            # report only
    python -m dgate.ops.wp132_funding --yes
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import cascade, db, eligibility, ukraine, who_apply
from ..config import settings
from ..funding import UNLISTED_AFTER_RUNS
from ..sources import eu_portal


def unlisted_plan(conn) -> list[dict[str, Any]]:
    """(id, topic, last listed, runs since) of every in-scope EU portal call whose count would change."""
    return conn.execute(
        """SELECT c.id, c.topic_code, c.last_seen_at, c.unlisted_runs AS was,
                  (SELECT count(*) FROM ingest_run r
                    WHERE r.source_id = c.source_id AND r.status = 'success' AND r.expected_min IS NOT NULL
                      AND r.records_fetched >= r.expected_min AND r.started_at > c.last_seen_at)::int AS runs
             FROM call c JOIN source s ON s.id = c.source_id
            WHERE s.code = %s AND c.status IN ('open', 'forthcoming') AND NOT c.out_of_scope
            ORDER BY c.id""", (eu_portal.SOURCE_CODE,)).fetchall()


def consortium_plan(conn) -> list[tuple[int, str, tuple[Any, Any], tuple[Any, Any]]]:
    rows = conn.execute(
        """SELECT c.id, c.topic_code, c.eligibility_text, c.min_consortium_size, c.min_member_states
             FROM call c JOIN source s ON s.id = c.source_id WHERE s.code = %s ORDER BY c.id""",
        (eu_portal.SOURCE_CODE,)).fetchall()
    out = []
    for r in rows:
        before = (r["min_consortium_size"], r["min_member_states"])
        after = eu_portal.consortium_rule(r["eligibility_text"])
        if before != after:
            out.append((r["id"], r["topic_code"] or "", before, after))
    return out


def run(*, write: bool) -> list[str]:
    lines: list[str] = []
    with db.connect(settings().dsn) as conn:
        unlisted = [r for r in unlisted_plan(conn) if r["runs"] != r["was"]]
        lines.append(f"unlisted runs to set: {len(unlisted)}; served as unlisted from {UNLISTED_AFTER_RUNS} runs: "
                     f"{sum(r['runs'] >= UNLISTED_AFTER_RUNS for r in unlisted)}")
        lines += [f"  {r['id']} {r['topic_code']}: last listed {r['last_seen_at']:%Y-%m-%d %H:%M}, runs since {r['was']} -> {r['runs']}"
                  for r in unlisted]
        consortium = consortium_plan(conn)
        lines.append(f"consortium rule of the topic text to correct: {len(consortium)}")
        lines += [f"  {cid} {code}: {before} -> {after}" for cid, code, before, after in consortium]
        if write:
            for r in unlisted:
                conn.execute("UPDATE call SET unlisted_runs = %s WHERE id = %s", (min(r["runs"], 32767), r["id"]))
            for cid, _, _, (size, states) in consortium:
                conn.execute("UPDATE call SET min_consortium_size = %s, min_member_states = %s WHERE id = %s", (size, states, cid))
            conn.commit()
        found = eligibility.reverify_stored(conn, write=write)
        lines.append(f"stored facts checked again: {found['unverified']} unverified, {found['found']} found now")
        lines += [f"  {url}: {', '.join(names)}" for url, names in found["changed"].items()]
        # the flags the facts decide, as the nightly job derives them (a report: what the next run would change)
        lines.append(f"cascade: {cascade.run(conn, write=write)}")
        lines.append(f"open to Ukraine: {ukraine.run(conn, write=write)}")
        lines.append(f"who may apply and minimum consortium: {who_apply.run(conn, write=write)}")
        if write:
            conn.commit()
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wp132-funding", description=__doc__.split("\n\n")[0])
    p.add_argument("--yes", action="store_true", help="write (default: report)")
    a = p.parse_args(argv)
    for line in run(write=a.yes):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
