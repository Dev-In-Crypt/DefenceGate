"""Bring stored notices of the non-TED sources in line with the mappers of 12 October 2026.

`reprocess` cannot do this: it recomputes the content hash of the stored payload, finds it
equal to the current version's, and writes nothing, because the payload did not change,
the mapper did. This tool re-maps the stored payload (the one the current version came
from) and, where a versioned field now differs, appends a new version through
`append_version`, annotated `remapped` so it is never counted as the source's amendment.
Nothing is deleted and the archive trigger is never switched off.

Sources and what the corrections are (see docs/DATA_QUALITY_PLAN_2026-10-12.md):

    fr_boamp      CPV codes, award and estimated values, rectificatif link
    nl_tenderned  status of prior-information notices, legal basis
    pl_ezam       status (noticeTypeTed fallback), procedure, plan-notice titles, TED link
    pl_atlas      procedure, status of annulled results

Facts are never erased: when the mapper now returns nothing for a value, a date, a CPV
list or a link the row already holds, the stored value is kept. Status and procedure,
which were wrong rather than missing, are replaced.

Idempotent: a notice that already equals its mapped state writes nothing, and each
notice done is recorded in `remap_marker`.

    python -m dgate.ops.remap_source --source pl_ezam                 # report only
    python -m dgate.ops.remap_source --source pl_ezam --yes
    python -m dgate.ops.remap_source --source fr_boamp --limit 5000 --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from typing import Any

from .. import db
from ..config import settings
from ..normalise import (
    Opportunity,
    from_atlas_pl,
    from_boamp,
    from_ezamowienia,
    from_tenderned,
    strip_personal_data,
)
from ..rawstore import build_store
from .repair_ted import CARRIED_COLUMNS, Change, Result, _chunks, _raw_keys, _state

log = logging.getLogger("remap_source")

MAPPERS = {
    "fr_boamp": from_boamp,
    "nl_tenderned": from_tenderned,
    "pl_ezam": from_ezamowienia,
    "pl_atlas": from_atlas_pl,
}

# Everything a mapper may move on a stored row.
FIELDS = (
    "status", "status_native", "procedure_type", "legal_basis", "title_original", "title_en",
    "value_amount", "value_currency", "published_at", "deadline_at", "cpv_codes",
    "ted_ref", "related_native_id", "country",
)

# Facts: a mapper that now yields nothing does not erase what is stored.
PRESERVE = ("value_amount", "value_currency", "published_at", "deadline_at", "cpv_codes",
            "ted_ref", "related_native_id", "title_en", "legal_basis", "country")

# Columns that are not versioned: updated in place when they differ.
DIRECT = ("status_native", "ted_ref", "related_native_id", "title_en")


def plan(current_payload: dict[str, Any], serving: dict[str, Any], new: Opportunity) -> Change:
    base = db.opportunity_from_payload(current_payload)
    base = replace(base, **{k: serving[k] for k in CARRIED_COLUMNS if k in serving})
    moves: dict[str, Any] = {}
    for f in FIELDS:
        value = getattr(new, f)
        if value is None and f in PRESERVE:
            continue
        if f == "cpv_codes" and not value:
            continue
        moves[f] = value
    candidate = replace(base, **moves)
    payload = db.opportunity_payload(candidate)
    current = {f: current_payload.get(f) for f in db.VERSIONED_FIELDS}
    changed = [f for f in db.VERSIONED_FIELDS if not db.same_value(f, current[f], payload.get(f))]
    direct = {c: getattr(candidate, c) for c in DIRECT
              if getattr(candidate, c) != serving.get(c)}
    transitions = [f"{f}:{current[f]}>{payload.get(f)}" for f in ("status", "procedure_type")
                   if f in changed]
    return Change(candidate, changed, direct, transitions)


def _apply(conn, opp_id: int, version: int, raw_hash: str, change: Change, source: str) -> int | None:
    if change.changed:
        new_version = db.append_version(conn, opp_id, change.candidate, raw_hash,
                                        change.changed, after=version)
        conn.execute(
            """INSERT INTO opportunity_version_note (opportunity_version_id, kind, note)
               SELECT id, 'remapped', %s FROM opportunity_version
                WHERE opportunity_id = %s AND version = %s ON CONFLICT DO NOTHING""",
            (f"{source} mapping corrected: {', '.join(change.changed)}", opp_id, new_version))
        return new_version
    if change.direct:
        sets = ", ".join(f"{c} = %s" for c in change.direct)
        conn.execute(f"UPDATE opportunity SET {sets} WHERE id = %s",
                     [*change.direct.values(), opp_id])
    return None


def run(source: str, *, write: bool = False, limit: int | None = None, batch: int = 200,
        workers: int = 1, epoch: int = 1, dsn: str | None = None) -> Result:
    from ..reprocess import _read_batch

    if source not in MAPPERS:
        raise SystemExit(f"no mapper for {source}; choose one of {', '.join(MAPPERS)}")
    result = Result()
    # A mapper that changed again after a first pass is a second epoch: its markers are
    # separate rows, so nothing is deleted or reset to run it again.
    marker = source if epoch == 1 else f"{source}#{epoch}"
    with db.connect(dsn or settings().dsn) as conn:
        src_id = db.source_id(conn, source)
        numbers = [r["native_id"] for r in conn.execute(
            """SELECT o.native_id FROM opportunity o
                WHERE o.source_id = %s
                  AND NOT EXISTS (SELECT 1 FROM remap_marker m
                                   WHERE m.source_code = %s AND m.native_id = o.native_id)
                ORDER BY o.id LIMIT %s""", (src_id, marker, limit)).fetchall()]
        log.info("remap %s: %s notices to do%s", source, len(numbers),
                 "" if write else " (dry run: nothing is written)")
        store = build_store()
        keys = _raw_keys(conn, src_id, numbers)
        result.no_raw = sum(1 for n in numbers if n not in keys)
        ordered = sorted(keys, key=lambda n: keys[n])
        mapper = MAPPERS[source]
        for chunk in _chunks(ordered, batch):
            state = _state(conn, src_id, chunk)
            order = [n for n in chunk if n in state]
            payloads = _read_batch(store, [keys[n] for n in order], workers, 4, 10.0)
            for number, payload in zip(order, payloads, strict=True):
                if isinstance(payload, Exception):
                    log.error("cannot read the payload of %s: %s", number, payload)
                    result.failed += 1
                    continue
                row = state[number]
                try:
                    change = plan(row["v_payload"], row, mapper(strip_personal_data(payload)))
                except Exception as exc:  # noqa: BLE001 - one notice must not stop the run
                    log.error("cannot re-map %s: %s", number, exc)
                    result.failed += 1
                    continue
                result.count(change)
                if write:
                    version = _apply(conn, row["id"], row["v_version"], row["v_hash"], change, source)
                    conn.execute(
                        """INSERT INTO remap_marker (source_code, native_id, version) VALUES (%s, %s, %s)
                           ON CONFLICT (source_code, native_id) DO UPDATE
                              SET done_at = clock_timestamp(), version = EXCLUDED.version""",
                        (marker, number, version))
            if write:
                conn.commit()
            else:
                conn.rollback()
            log.info("remap %s: %s", source, result)
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="remap-source", description=__doc__.split("\n\n")[0])
    p.add_argument("--source", required=True, choices=sorted(MAPPERS))
    p.add_argument("--yes", action="store_true", help="write the corrections (default: report)")
    p.add_argument("--limit", type=int)
    p.add_argument("--batch", type=int, default=200)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--epoch", type=int, default=1,
                   help="run again after the mapper changed again (separate markers)")
    a = p.parse_args(argv)
    result = run(a.source, write=a.yes, limit=a.limit, batch=a.batch, workers=a.workers,
                 epoch=a.epoch)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
