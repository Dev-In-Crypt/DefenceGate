"""Bring stored notices of the non-TED sources in line with the mappers of 12 October 2026.

`reprocess` cannot do this: it recomputes the content hash of the stored payload, finds it
equal to the current version's, and writes nothing, because the payload did not change,
the mapper did. This tool re-maps the stored payload (the one the current version came
from) and, where a versioned field now differs, appends a new version through
`append_version`, annotated `remapped` so it is never counted as the source's amendment.
Nothing is deleted and the archive trigger is never switched off.

Sources and what the corrections are (see docs/DATA_QUALITY_PLAN_2026-10-12.md):

    fr_boamp      CPV codes, award and estimated values, rectificatif link; from epoch 3
                  the deadline of an eForms notice (read from the body, not DILA's column)
                  and the lot count
    de_bkms       the notice's link (BT-15, the procurement documents on the buyer's
                  platform), which the first mapper left empty (WP-72)
    nl_tenderned  status of prior-information notices, legal basis
    pl_ezam       status (noticeTypeTed fallback), procedure, plan-notice titles, TED link
    pl_atlas      procedure, status of annulled results; from epoch 3 the deadline read as
                  UTC (the dataset states UTC without saying so) -- run with `--latest-raw`,
                  because the columns the mapper needs (`tender_type`, `procedure_result`)
                  were landed on 12 October by `atlas-pl --refresh-known`, which writes no
                  version, so the current version's own payload does not have them
    es_placsp,    from the STORED payload, which is the record the connector parsed (the
    es_placsp_agg Atom entry itself is not kept): the procedure named for the codes that
                  were verified, a prior notice no longer `open`, and a publication date
                  that is after the notice's own deadline cleared. From epoch 2 (WP-12):
                  the entry's own notice date and kind (`notice_date`, `notice_kind`, from
                  its update stamp and status code, not versioned), and a publication date
                  lost to a later award or cancellation entry restored from the folder's
                  earliest version that states one (the call notice's). What needs the entry
                  (value, lots, publication date, no-winner outcome) is the replay's:
                  `pipeline placsp-backfill`.

WP-96 (run each with `--epoch 96`): fr_boamp, an eForms deadline written with a Paris offset is Paris wall time on
its own day (a November deadline stated "+02:00" was an hour early); de_bkms, a notice without BT-15 links its own
page on oeffentlichevergabe.de; pl_ezam, the notice-details page (the old search-list address is PAGE_NOT_FOUND).

WP-113 (epoch 113, run by `ops.wp113_rederive`): fr_boamp, the national forms' deadline in the buyer's zone and overseas
buyers' wall times in their own zone, the legal basis of the other directives; nl_tenderned, the rectified deadline and
the flagged main CPV first (an attribute update: the same codes are not a version); de_bkms, the notice's own page as
the link and BT-15 as the documents link; es_placsp, procedure code 7 named.

Facts are never erased: when the mapper now returns nothing for a value, a date, a CPV
list or a link the row already holds, the stored value is kept. Status and procedure,
which were wrong rather than missing, are replaced. The one exception is a field a mapper
names in `CLEARS`: a value it knows to be wrong (a publication date after the notice's own
deadline) is cleared, as a new version annotated `remapped`.

Idempotent: a notice that already equals its mapped state writes nothing, and each
notice done is recorded in `remap_marker`.

    python -m dgate.ops.remap_source --source pl_ezam                 # report only
    python -m dgate.ops.remap_source --source pl_ezam --yes
    python -m dgate.ops.remap_source --source fr_boamp --limit 5000 --yes
    python -m dgate.ops.remap_source --source fr_boamp --epoch 4 --no-deadline --yes
    python -m dgate.ops.remap_source --source pl_atlas --epoch 4 --latest-raw --status closed --yes
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from datetime import date
from typing import Any

from .. import db
from ..config import settings
from ..normalise import (
    PLACEHOLDER_AMOUNT_MAX,
    Opportunity,
    from_atlas_pl,
    from_boamp,
    from_de_bkms,
    from_ezamowienia,
    from_tenderned,
    strip_personal_data,
)
from ..rawstore import build_store
from ..sources import placsp
from .repair_ted import CARRIED_COLUMNS, Change, Result, _chunks, _raw_keys, _state

log = logging.getLogger("remap_source")


def from_placsp_stored(payload: dict[str, Any]) -> Opportunity:
    """The record the PLACSP connector landed, brought up to the current tables.

    The raw store holds the parsed record (`db.opportunity_payload`), not the Atom entry, so
    only what is a function of the stored fields can be redone here: the procedure's name for
    a verified code (`map_procedure` leaves a code it does not know as it is), and a prior
    notice (`PRE`) that the first mapper filed as `open`. The status is moved only from
    `open`: a `cancelled` the entry's own results gave it is never put back to `awarded`.
    """
    opp = db.opportunity_from_payload(payload)
    status = opp.status
    if opp.status_native and status == "open":
        status = placsp.map_status(opp.status_native)
    amount, currency = opp.value_amount, opp.value_currency
    if amount is not None and amount <= PLACEHOLDER_AMOUNT_MAX:
        amount, currency = None, None          # 0.00, which the mapper no longer offers
    # The entry's own date: the day of its update stamp, as the entry states it (local day).
    notice_date, notice_kind = opp.notice_date, opp.notice_kind
    if notice_date is None and opp.source_updated_at is not None:
        notice_date = opp.source_updated_at.date()
        notice_kind = placsp.notice_kind_of_status(opp.status_native)
    return replace(opp, procedure_type=placsp.map_procedure(opp.procedure_type),
                   status=status, value_amount=amount, value_currency=currency,
                   notice_date=notice_date, notice_kind=notice_kind)


def placsp_call_date(conn, opp_id: int, new: Opportunity) -> Opportunity:
    """The call notice's date, for a folder whose current entry states none: the earliest
    version that did state a publication date (an award or a cancellation entry that came
    later carries no call notice and the first reading of it dropped the date). Only from a
    version carrying the entry's update stamp: one without it was read by the first mapper,
    whose date is the feed's. Not after the notice's own deadline, which is the date of an
    award read as a publication."""
    if new.published_at is not None:
        return new
    row = conn.execute(
        """SELECT payload->>'published_at' AS d FROM opportunity_version
            WHERE opportunity_id = %s AND payload->>'published_at' IS NOT NULL
              AND payload->>'source_updated_at' IS NOT NULL
            ORDER BY version LIMIT 1""", (opp_id,)).fetchone()
    if not row:
        return new
    held = date.fromisoformat(row["d"][:10])
    if new.deadline_at is not None and held > new.deadline_at.date():
        return new
    return replace(new, published_at=held)


def placsp_stored_clears(payload: dict[str, Any], new: Opportunity) -> set[str]:
    """A publication date after the notice's own deadline, in a record the current mapper
    read (it states `source_updated_at`): the date of an award notice, which the mapper no
    longer offers as the tender's publication. A record without the stamp was read by the
    first mapper, whose date is the feed's and which the replay corrects with the right
    one; it is left for that."""
    if (payload.get("source_updated_at") and new.published_at and new.deadline_at
            and new.published_at > new.deadline_at.date()):
        return {"published_at"}
    return set()


MAPPERS = {
    "fr_boamp": from_boamp,
    "nl_tenderned": from_tenderned,
    "pl_ezam": from_ezamowienia,
    "pl_atlas": from_atlas_pl,
    "es_placsp": from_placsp_stored,
    "es_placsp_agg": from_placsp_stored,
    # WP-72: the link to the notice on the buyer's tendering platform (BT-15), which the first
    # mapper never read (`source_url` was empty on all 12,700 German rows).
    "de_bkms": from_de_bkms,
}

# Per source, the fields a mapper knows to be wrong and says so: cleared although a fact is
# otherwise never replaced by an absent one.
CLEARS = {
    "es_placsp": placsp_stored_clears,
    "es_placsp_agg": placsp_stored_clears,
}

# Everything a mapper may move on a stored row.
FIELDS = (
    "status", "status_native", "procedure_type", "legal_basis", "title_original", "title_en",
    "value_amount", "value_currency", "published_at", "deadline_at", "cpv_codes",
    "ted_ref", "related_native_id", "country", "lot_count", "notice_date", "notice_kind",
    "source_url", "documents_url",
)

# Facts: a mapper that now yields nothing does not erase what is stored.
PRESERVE = ("value_amount", "value_currency", "published_at", "deadline_at", "cpv_codes",
            "ted_ref", "related_native_id", "title_en", "legal_basis", "country", "lot_count",
            "notice_date", "notice_kind", "source_url", "documents_url")

# Columns that are not versioned: updated in place when they differ.
DIRECT = ("status_native", "ted_ref", "related_native_id", "title_en", "lot_count",
          "notice_date", "notice_kind")


def plan(current_payload: dict[str, Any], serving: dict[str, Any], new: Opportunity,
         clear: frozenset[str] | set[str] = frozenset()) -> Change:
    base = db.opportunity_from_payload(current_payload)
    base = replace(base, **{k: serving[k] for k in CARRIED_COLUMNS if k in serving})
    base = replace(base, **{k: serving.get(k) for k in ("notice_date", "notice_kind")})
    # A stored amount of one or less that the mapper no longer offers was a placeholder, not
    # a fact the source lost: it is cleared, whichever source it is.
    held = base.value_amount
    if held is not None and held <= PLACEHOLDER_AMOUNT_MAX and new.value_amount is None:
        clear = {*clear, "value_amount", "value_currency"}
    moves: dict[str, Any] = {}
    for f in FIELDS:
        value = None if f in clear else getattr(new, f)
        if value is None and f in PRESERVE and f not in clear:
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
    # WP-113: the main CPV is the first code of the serving row; the same codes in another order are not a version
    # (`db.same_value`: a CPV list is a set), so a corrected main code (TenderNed's flagged one) is an attribute update
    if "cpv_codes" not in changed and candidate.cpv_codes and serving.get("cpv_codes") is not None             and list(candidate.cpv_codes) != list(serving["cpv_codes"]):
        direct["cpv_codes"] = list(candidate.cpv_codes)
    transitions = [f"{f}:{current[f]}>{payload.get(f)}" for f in ("status", "procedure_type")
                   if f in changed]
    return Change(candidate, changed, direct, transitions)


def _latest_raw(conn, src_id: int, numbers: list[str]) -> dict[str, tuple[str, str]]:
    """native_id -> (storage key, content hash) of the newest payload landed for it, which is
    the current version's own unless a refresh landed a newer one without writing a version."""
    found: dict[str, tuple[str, str]] = {}
    for chunk in _chunks(numbers, 2000):
        for r in conn.execute(
                """SELECT DISTINCT ON (native_id) native_id, storage_key, content_hash
                     FROM raw_ingest WHERE source_id = %s AND native_id = ANY(%s)
                    ORDER BY native_id, fetched_at DESC""", (src_id, chunk)).fetchall():
            found[r["native_id"]] = (r["storage_key"], r["content_hash"])
    return found


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
        workers: int = 1, epoch: int = 1, latest_raw: bool = False,
        dsn: str | None = None, status: str | None = None,
        no_deadline: bool = False, procedure: str | None = None) -> Result:
    from ..reprocess import _read_batch

    if source not in MAPPERS:
        raise SystemExit(f"no mapper for {source}; choose one of {', '.join(MAPPERS)}")
    result = Result()
    # A mapper that changed again after a first pass is a second epoch: its markers are
    # separate rows, so nothing is deleted or reset to run it again.
    marker = source if epoch == 1 else f"{source}#{epoch}"
    with db.connect(dsn or settings().dsn) as conn:
        src_id = db.source_id(conn, source)
        # `status` and `no_deadline` select the rows a correction can only reach (the
        # `closed` of 564 Polish rows, the legacy BOAMP notices with no deadline): a run
        # over 36,000 payloads to change 500 is the cost they save.
        numbers = [r["native_id"] for r in conn.execute(
            """SELECT o.native_id FROM opportunity o
                WHERE o.source_id = %s
                  AND (%s::text IS NULL OR o.status = %s)
                  AND (NOT %s OR o.deadline_at IS NULL)
                  AND (%s::text IS NULL OR o.procedure_type = %s)
                  AND NOT EXISTS (SELECT 1 FROM remap_marker m
                                   WHERE m.source_code = %s AND m.native_id = o.native_id)
                ORDER BY o.id LIMIT %s""",
            (src_id, status, status, no_deadline, procedure, procedure, marker, limit)).fetchall()]
        log.info("remap %s: %s notices to do%s", source, len(numbers),
                 "" if write else " (dry run: nothing is written)")
        store = build_store()
        # `latest_raw`: the newest landed payload instead of the one the current version
        # came from. The new version, if one is due, is then recorded against that payload's
        # hash, so the archive still says which raw object it was read from.
        hashes: dict[str, str] = {}
        if latest_raw:
            landed = _latest_raw(conn, src_id, numbers)
            keys = {n: key for n, (key, _) in landed.items()}
            hashes = {n: digest for n, (_, digest) in landed.items()}
        else:
            keys = _raw_keys(conn, src_id, numbers)
        result.no_raw = sum(1 for n in numbers if n not in keys)
        ordered = sorted(keys, key=lambda n: keys[n])
        mapper = MAPPERS[source]
        for chunk in _chunks(ordered, batch):
            state = _state(conn, src_id, chunk)
            order = [n for n in chunk if n in state]
            conn.commit()           # nothing is open across the slow store reads
            payloads = _read_batch(store, [keys[n] for n in order], workers, 4, 10.0)
            for number, payload in zip(order, payloads, strict=True):
                if isinstance(payload, Exception):
                    log.error("cannot read the payload of %s: %s", number, payload)
                    result.failed += 1
                    continue
                row = state[number]
                try:
                    clean = strip_personal_data(payload)
                    new = mapper(clean)
                    if source in CLEARS:        # PLACSP: the call notice's date, if lost
                        new = placsp_call_date(conn, row["id"], new)
                    clears = CLEARS[source](clean, new) if source in CLEARS else set()
                    change = plan(row["v_payload"], row, new, clears)
                except Exception as exc:  # noqa: BLE001 - one notice must not stop the run
                    log.error("cannot re-map %s: %s", number, exc)
                    result.failed += 1
                    continue
                result.count(change)
                if write:
                    version = _apply(conn, row["id"], row["v_version"],
                                     hashes.get(number, row["v_hash"]), change, source)
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
    p.add_argument("--latest-raw", action="store_true",
                   help="read the newest payload landed for each notice, not the current "
                        "version's own (pl_atlas after --refresh-known)")
    p.add_argument("--status", help="only notices stored with this status (e.g. closed)")
    p.add_argument("--no-deadline", action="store_true",
                   help="only notices with no deadline stored")
    a = p.parse_args(argv)
    result = run(a.source, write=a.yes, limit=a.limit, batch=a.batch, workers=a.workers,
                 epoch=a.epoch, latest_raw=a.latest_raw, status=a.status,
                 no_deadline=a.no_deadline)
    print(result)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
