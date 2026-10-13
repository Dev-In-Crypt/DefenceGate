"""Correct the TED notices that were mapped before 12 October 2026.

Until then `from_ted` never set a status (every notice was `open`), took the
dispatch date for the publication date, the first lot for the value, the numeric
subtype for the procedure, and truncated ISO3 country codes. The corrections are
in the mapper now, and new notices come in right. This brings the ones already
stored in line, by adding:

  - a new version for every notice whose versioned fields change, written through
    `append_version` with the list of fields that changed, and annotated with the
    note kind `remapped` so that it is not counted as an amendment by the source;
  - an update of the non-versioned attribute columns (status_native, notice_subtype,
    procedure_identifier, lot_count, value_kind) where they differ, with no version.

A value TED states as a placeholder (0, 0.01, 1, -1) or implausibly (above ten billion) is
not the notice's value: the mapper returns none with `value_kind` not_stated / implausible,
and this tool clears the stored amount and currency (a new version annotated `remapped`;
the earlier versions keep the figure TED stated). Select those notices with
`--numbers-file` (see docs/RUNBOOK.md), and run them as a new `--epoch`.

Nothing is deleted and the archive trigger is never switched off.

Two modes, because they answer different questions:

  --from-raw   re-derives from the payload stored when the notice was seen. It
               needs no request and corrects what that payload can speak for:
               status (from `notice-type`), country, subtype, lot count, and the
               value when it states a total. It cannot know a field that was not
               requested then (publication date, request-to-participate time,
               procedure type, winner status), and says nothing about those.
  --refetch    asks TED for the notices again, a hundred publication numbers per
               request and at most one request a second, lands each payload in the
               raw store, and corrects every field the mapper now owns.

Idempotent: a notice whose stored state already equals the corrected one writes
nothing, and each notice done is recorded in `ted_repair_marker`, so an
interrupted run resumes where it stopped.

    python -m dgate.ops.repair_ted --from-raw                 # report only
    python -m dgate.ops.repair_ted --from-raw --yes
    python -m dgate.ops.repair_ted --refetch --limit 500      # report only, 5 requests
    python -m dgate.ops.repair_ted --refetch --yes
    python -m dgate.ops.repair_ted --refetch --numbers-file numbers.txt --yes
    python -m dgate.ops.repair_ted --from-raw --epoch 2 --yes  # after the mapper changed again

A notice that could not be done (TED did not return it; no payload is stored for its
current version) is marked `refetch-missing` / `raw-missing`, so that `--limit` runs
move on instead of taking the same first notices again.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx

from .. import db
from ..config import settings
from ..normalise import UNSERVED_VALUE_KINDS, Opportunity, from_ted, strip_personal_data
from ..rawstore import BundleWriter, build_store, storage_key
from ..sources import USER_AGENT, new_client, ted

log = logging.getLogger("repair_ted")

MODES = ("raw", "refetch")

# Everything the mapper now owns that a repair may move. Not the title, the CPV
# codes or the legal basis: a repair re-maps, it does not re-read the notice.
REMAPPED = (
    "status", "status_native", "country", "procedure_type", "notice_subtype",
    "procedure_identifier", "lot_count", "value_amount", "value_currency", "value_kind",
    "published_at", "deadline_at", "buyer_identifier",
)

# Columns of the serving row that are attributes, not versioned facts. A change
# here writes no version; `append_version` sets them whenever it writes one.
DIRECT_COLUMNS = ("status_native", "notice_subtype", "procedure_identifier", "lot_count",
                  "value_kind", "buyer_identifier")

# What the serving row holds that a version payload may not: derived signals and
# links. Carried over unchanged, so a repair never reclassifies.
#
# Every column `db.append_version` derives from the classification is here
# (`db._classification_columns`): a version written without them would put the serving
# row back to what the payload says, and a notice demoted to dual-use (a municipality's
# military CPV) would return to `core`. The payload of an older version has none of
# them, because the classification is not versioned.
CARRIED_COLUMNS = (
    "buyer_org_id", "is_defence", "sig_legal_basis", "sig_cpv", "sig_buyer",
    "sig_clearance", "subcontracting_signal", "security_clearance_required",
    "title_en", "summary_en", "ted_ref",
    "sig_cpv_military", "sig_cpv_adjacent", "sig_linked_defence", "dual_use", "buyer_class",
)

# Facts a repair never replaces by an absent one: a notice TED now returns without a
# value, a date, a currency or an identifier has not lost it. Procedure, status and the
# source's own type were wrong rather than missing and are replaced.
PRESERVE = (
    "value_amount", "value_currency", "value_kind", "published_at", "deadline_at", "country",
    "lot_count", "notice_subtype", "procedure_identifier", "buyer_identifier",
)


# The value fields move together. A mapper that says the notice's only amounts are
# placeholders or implausible (`value_kind` not_stated / implausible) returns no amount, and
# that "nothing" is deliberate: it clears what is stored instead of being preserved.
VALUE_FIELDS = ("value_amount", "value_currency", "value_kind")


def _keeps_stored(new: Opportunity, name: str) -> bool:
    if name not in PRESERVE or getattr(new, name) is not None:
        return False
    return not (name in VALUE_FIELDS and new.value_kind in UNSERVED_VALUE_KINDS)


def raw_fields(payload: dict[str, Any], notice_type: str | None) -> list[str]:
    """The fields of REMAPPED that a stored payload can speak for.

    A payload holds exactly what was requested when it was fetched. A field whose
    source was not among them reads as empty, and writing that over the stored
    value would erase a fact; so it is left to --refetch.
    """
    from ..normalise import TED_RESULT_TYPES

    fields = ["status_native", "country", "notice_subtype", "lot_count",
              "buyer_identifier", "deadline_at"]
    # A corrigendum is open when it states a deadline, and a payload fetched before
    # `deadline-receipt-request` was requested may not: its status waits for the
    # refetch rather than being written `unknown` and then corrected again.
    if notice_type != "corr" or "deadline-receipt-request" in payload:
        fields.append("status")
    if "publication-date" in payload:
        fields.append("published_at")
    if "procedure-type" in payload:
        fields.append("procedure_type")
    if "procedure-identifier" in payload:
        fields.append("procedure_identifier")
    # A result notice's value is its total, which an old payload did not request;
    # the estimate it does hold is not what the refetch will say.
    if (notice_type not in TED_RESULT_TYPES
            or "total-value" in payload or "result-value-notice" in payload):
        fields += ["value_amount", "value_currency", "value_kind"]
    return fields


@dataclass
class Change:
    candidate: Opportunity
    changed: list[str]            # versioned fields that differ: a version is due
    direct: dict[str, Any]        # attribute columns that differ: an update is due
    transitions: list[str] = field(default_factory=list)   # "status:open>awarded"

    @property
    def nothing(self) -> bool:
        return not self.changed and not self.direct


def plan_change(current_payload: dict[str, Any], serving: dict[str, Any],
                new: Opportunity, fields: Iterable[str]) -> Change:
    """What correcting one notice would do, without doing it.

    Starts from the stored state (the current version's payload, with the signals
    and links of the serving row on top, which may be fresher) and moves only
    `fields` to what the mapper now says.
    """
    base = db.opportunity_from_payload(current_payload)
    base = replace(base, **{k: serving[k] for k in CARRIED_COLUMNS if k in serving})
    candidate = replace(base, **{f: getattr(new, f) for f in fields
                                 if not _keeps_stored(new, f)})
    payload = db.opportunity_payload(candidate)
    current = {f: current_payload.get(f) for f in db.VERSIONED_FIELDS}
    changed = [f for f in db.VERSIONED_FIELDS if current[f] != payload.get(f)]
    direct = {c: getattr(candidate, c) for c in DIRECT_COLUMNS
              if getattr(candidate, c) != serving.get(c)}
    transitions = [f"{f}:{current[f]}>{payload.get(f)}" for f in ("status", "country")
                   if f in changed]
    return Change(candidate, changed, direct, transitions)


def _note(conn, opp_id: int, version: int, text: str) -> None:
    conn.execute(
        """INSERT INTO opportunity_version_note (opportunity_version_id, kind, note)
           SELECT id, 'remapped', %s FROM opportunity_version
            WHERE opportunity_id = %s AND version = %s
           ON CONFLICT DO NOTHING""",
        (text, opp_id, version),
    )


def apply_change(conn, opp_id: int, current_version: int, raw_hash: str,
                 change: Change, mode: str) -> int | None:
    """Write a planned change. Returns the new version number, if one was written."""
    if change.changed:
        version = db.append_version(conn, opp_id, change.candidate, raw_hash,
                                    change.changed, after=current_version)
        _note(conn, opp_id, version,
              f"TED mapping corrected ({mode}): {', '.join(change.changed)}")
        return version
    if change.direct:
        sets = ", ".join(f"{c} = %s" for c in change.direct)
        conn.execute(f"UPDATE opportunity SET {sets} WHERE id = %s",
                     [*change.direct.values(), opp_id])
    return None


# ----------------------------------------------------------------- the run

@dataclass
class Result:
    examined: int = 0
    versions: int = 0          # versions written (or that would be)
    direct: int = 0            # rows with only attribute columns to fill
    unchanged: int = 0
    missing: int = 0           # --refetch: TED did not return the number
    no_raw: int = 0            # --from-raw: no stored payload for the current version
    failed: int = 0
    requests: int = 0
    by_field: Counter = field(default_factory=Counter)
    transitions: Counter = field(default_factory=Counter)
    stopped: str | None = None

    def count(self, change: Change) -> None:
        self.examined += 1
        if change.nothing:
            self.unchanged += 1
            return
        if change.changed:
            self.versions += 1
        else:
            self.direct += 1
        self.by_field.update(change.changed)
        self.transitions.update(change.transitions)

    def __str__(self) -> str:
        top = ", ".join(f"{k} {v}" for k, v in self.by_field.most_common())
        flow = ", ".join(f"{k} {v}" for k, v in self.transitions.most_common(12))
        return (f"examined {self.examined}, versions {self.versions}, "
                f"attribute-only {self.direct}, unchanged {self.unchanged}, "
                f"missing {self.missing}, no raw {self.no_raw}, failed {self.failed}, "
                f"requests {self.requests}"
                + (f"; fields: {top}" if top else "")
                + (f"; moves: {flow}" if flow else "")
                + (f"; STOPPED: {self.stopped}" if self.stopped else ""))


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _state(conn, src_id: int, numbers: list[str]) -> dict[str, dict[str, Any]]:
    """Per notice: the serving row, plus the current version's number, payload and hash."""
    rows = conn.execute(
        """SELECT o.*, v.version AS v_version, v.payload AS v_payload, v.raw_hash AS v_hash
             FROM opportunity o
             JOIN LATERAL (SELECT version, payload, raw_hash FROM opportunity_version
                            WHERE opportunity_id = o.id ORDER BY version DESC LIMIT 1) v ON TRUE
            WHERE o.source_id = %s AND o.native_id = ANY(%s)""",
        (src_id, numbers),
    ).fetchall()
    return {r["native_id"]: r for r in rows}


def _modes(mode: str) -> list[str]:
    """The marker modes that take a notice out of a run of `mode`: it was done, or it
    was looked for and there was nothing to do it with (migration 0037)."""
    return [mode, f"{mode}-missing"]


def pending_numbers(conn, src_id: int, mode: str, limit: int | None) -> list[str]:
    rows = conn.execute(
        """SELECT o.native_id FROM opportunity o
            WHERE o.source_id = %s
              AND NOT EXISTS (SELECT 1 FROM ted_repair_marker m
                               WHERE m.native_id = o.native_id AND m.mode = ANY(%s))
            ORDER BY o.id LIMIT %s""",
        (src_id, _modes(mode), limit),
    ).fetchall()
    return [r["native_id"] for r in rows]


def _mark(conn, native_id: str, mode: str, version: int | None) -> None:
    conn.execute(
        """INSERT INTO ted_repair_marker (native_id, mode, version) VALUES (%s, %s, %s)
           ON CONFLICT (native_id, mode) DO UPDATE
              SET done_at = clock_timestamp(), version = EXCLUDED.version""",
        (native_id, mode, version),
    )


def _raw_keys(conn, src_id: int, numbers: list[str]) -> dict[str, str]:
    """Where each notice's current payload is stored: the raw index row whose content
    hash is the current version's. Notices with none are simply absent."""
    keys: dict[str, str] = {}
    for chunk in _chunks(numbers, 2000):
        hashes = conn.execute(
            """SELECT o.native_id, v.raw_hash
                 FROM opportunity o
                 JOIN LATERAL (SELECT raw_hash FROM opportunity_version
                                WHERE opportunity_id = o.id
                                ORDER BY version DESC LIMIT 1) v ON TRUE
                WHERE o.source_id = %s AND o.native_id = ANY(%s)""",
            (src_id, chunk)).fetchall()
        for r in conn.execute(
                """SELECT DISTINCT ON (r.native_id) r.native_id, r.storage_key
                     FROM raw_ingest r
                     JOIN unnest(%s::text[], %s::text[]) AS w(native_id, content_hash)
                       ON w.native_id = r.native_id AND w.content_hash = r.content_hash
                    WHERE r.source_id = %s
                    ORDER BY r.native_id, r.fetched_at DESC""",
                ([h["native_id"] for h in hashes], [h["raw_hash"] for h in hashes],
                 src_id)).fetchall():
            keys[r["native_id"]] = r["storage_key"]
    return keys


def run_from_raw(conn, numbers: list[str], *, write: bool, batch: int = 200,
                 workers: int = 1, marker: str = "raw") -> Result:
    from ..reprocess import _read_batch

    result = Result()
    src_id = db.source_id(conn, "ted")
    store = build_store()
    keys = _raw_keys(conn, src_id, numbers)
    unread = [n for n in numbers if n not in keys]
    result.no_raw = len(unread)
    if write:
        # Marked, so that the next `--limit` run takes the next notices and not these
        # again: a notice with no stored payload for its current version is not one this
        # mode can do (--refetch can).
        for number in unread:
            _mark(conn, number, f"{marker}-missing", None)
        conn.commit()
    # In key order, so that the notices of one stored bundle -- a whole publication
    # day -- are read one after another and the bundle is decoded once, not once
    # for every notice in it.
    ordered = sorted(keys, key=lambda n: keys[n])
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
                clean = strip_personal_data(payload)
                new = from_ted(clean)
                change = plan_change(row["v_payload"], row, new,
                                     raw_fields(clean, new.status_native))
            except Exception as exc:  # noqa: BLE001 - one notice must not stop the repair
                log.error("cannot re-derive %s: %s", number, exc)
                result.failed += 1
                continue
            result.count(change)
            if write:
                version = apply_change(conn, row["id"], row["v_version"], row["v_hash"],
                                       change, "raw")
                _mark(conn, number, marker, version)
        if write:
            conn.commit()
        else:
            conn.rollback()
        log.info("repair_ted --from-raw: %s", result)
    return result


def run_refetch(conn, numbers: list[str], *, write: bool, batch: int = 100,
                client: httpx.Client | None = None, pause: float = 1.0,
                marker: str = "refetch") -> Result:
    result = Result()
    src_id = db.source_id(conn, "ted")
    owns = client is None
    client = client or new_client(headers={"User-Agent": USER_AGENT})
    try:
        with BundleWriter(build_store(), "ted") as writer:
            for chunk in _chunks(numbers, batch):
                state = _state(conn, src_id, chunk)
                query = f"publication-number IN ({' '.join(chunk)})"
                try:
                    got = list(ted.search(query, client=client))
                except httpx.HTTPStatusError as exc:
                    # Rate limited or refused: stop and leave the rest for a rerun.
                    result.stopped = f"HTTP {exc.response.status_code} from TED"
                    break
                result.requests += 1
                by_number = {ted._number(n): n for n in got}
                for number in chunk:
                    if number not in state:
                        continue
                    notice = by_number.get(number)
                    if notice is None:
                        result.missing += 1
                        if write:
                            _mark(conn, number, f"{marker}-missing", None)
                        continue
                    row = state[number]
                    try:
                        clean = strip_personal_data(notice)
                        digest = ted.content_hash(clean)
                        new = from_ted(clean)
                        change = plan_change(row["v_payload"], row, new, REMAPPED)
                    except Exception as exc:  # noqa: BLE001
                        log.error("cannot map %s: %s", number, exc)
                        result.failed += 1
                        continue
                    result.count(change)
                    if write:
                        key = writer.put(storage_key("ted", number, content_hash=digest), clean)
                        db.record_raw(conn, src_id, number, digest, key)
                        version = apply_change(conn, row["id"], row["v_version"], digest,
                                               change, "refetch")
                        _mark(conn, number, marker, version)
                if write:
                    writer.drain()          # the payloads land before the rows that point at them
                    conn.commit()
                else:
                    conn.rollback()
                log.info("repair_ted --refetch: %s", result)
                time.sleep(pause)           # at most one request a second
    finally:
        if owns:
            client.close()
    return result


def run(mode: str, *, write: bool = False, limit: int | None = None,
        batch: int | None = None, numbers: list[str] | None = None,
        workers: int = 1, epoch: int = 1, dsn: str | None = None) -> Result:
    # A second pass after the mapper changed again has markers of its own (`raw#2`), so
    # that it needs nothing deleted or reset; the first pass keeps its plain names.
    marker = mode if epoch == 1 else f"{mode}#{epoch}"
    with db.connect(dsn or settings().dsn) as conn:
        src_id = db.source_id(conn, "ted")
        if numbers is None:
            wanted = pending_numbers(conn, src_id, marker, limit)
        else:
            done = {r["native_id"] for r in conn.execute(
                "SELECT native_id FROM ted_repair_marker WHERE mode = ANY(%s)",
                (_modes(marker),)).fetchall()}
            wanted = [n for n in dict.fromkeys(numbers) if n not in done][:limit]
        log.info("repair_ted --%s (epoch %s): %s notices to do%s", mode, epoch, len(wanted),
                 "" if write else " (dry run: nothing is written)")
        if mode == "raw":
            return run_from_raw(conn, wanted, write=write, batch=batch or 200,
                                workers=workers, marker=marker)
        return run_refetch(conn, wanted, write=write, batch=min(batch or 100, 100),
                           marker=marker)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="repair-ted", description=__doc__.split("\n\n")[0])
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--from-raw", action="store_true",
                       help="re-derive from the stored payload; no request")
    which.add_argument("--refetch", action="store_true",
                       help="ask TED again, 100 numbers a request, one request a second")
    p.add_argument("--dry-run", action="store_true",
                   help="report what would change (the default without --yes)")
    p.add_argument("--yes", action="store_true", help="write the corrections")
    p.add_argument("--limit", type=int, help="at most this many notices")
    p.add_argument("--batch", type=int, help="notices per read or request (refetch: 100 at most)")
    p.add_argument("--workers", type=int, default=1,
                   help="--from-raw: payloads read at once (1: a stored day is decoded once)")
    p.add_argument("--numbers-file", type=Path,
                   help="publication numbers, one per line, instead of every stored TED notice")
    p.add_argument("--epoch", type=int, default=1,
                   help="run again after the mapper changed again (separate markers)")
    a = p.parse_args(argv)

    numbers = None
    if a.numbers_file:
        numbers = [ln.strip() for ln in a.numbers_file.read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.startswith("#")]
    result = run("raw" if a.from_raw else "refetch", write=a.yes and not a.dry_run,
                 limit=a.limit, batch=a.batch, numbers=numbers, workers=a.workers,
                 epoch=a.epoch)
    print(result)
    return 0 if result.failed == 0 and result.stopped is None else 1


if __name__ == "__main__":
    sys.exit(main())
