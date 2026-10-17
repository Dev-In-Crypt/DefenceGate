"""Pipeline orchestration.

Usage:
    python -m dgate.pipeline ted --days 2
    python -m dgate.pipeline placsp --live
    python -m dgate.pipeline placsp --backfill 2012 2025
    python -m dgate.pipeline placsp-backfill --from 2026-08 [--to 2026-10]
    python -m dgate.pipeline seed-buyers

Ordering rule enforced throughout: land the raw payload first, normalise
second, classify third, archive last. If normalisation crashes on an unexpected
shape, the raw record survives and the run can be replayed after a fix without
refetching anything.
"""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import httpx
import psycopg

from . import db, rawstore
from .buyer_vocab import effective_buyer_class
from .classify import classify, detects_subcontracting
from .config import settings
from .normalise import (
    TED_INFORMATION_TYPES,
    TED_STATUS_BY_TYPE,
    Opportunity,
    from_aid,
    from_atlas_pl,
    from_bdns,
    from_boamp,
    from_de_bkms,
    from_eu_call,
    from_ezamowienia,
    from_matine,
    from_ncbr,
    from_ted,
    from_tenderned,
    from_vinnova,
    scrub_opportunity,
    strip_personal_data,
    ted_notice_type,
)
from .rawstore import BufferedWriter, BundleWriter, build_store, storage_key
from .sources import (
    RateLimited,
    aid,
    bdns,
    boamp,
    de_bkms,
    eu_portal,
    ezamowienia,
    matine,
    ncbr,
    new_client,
    placsp,
    ted,
    tenderned,
    vinnova,
)

log = logging.getLogger("pipeline")

# The exit status of a historical load the source stopped (EX_TEMPFAIL): not a
# success, and not a crash. A wrapper that re-runs the same command until it
# exits 0 does the right thing, because the command resumes where it stopped.
EXIT_STOPPED = 75


class HistoryStopped(RuntimeError):
    """A historical load was stopped by the source's rate limit, cleanly.

    Every day before `day` is marked done, `day` is not, and `resume_after` is
    when the source may be asked again (recorded in `backfill_stop`). Rerunning
    the same command continues from `day`.
    """

    def __init__(self, source_code: str, day: date | None, resume_after: datetime,
                 loaded: int) -> None:
        where = f"stopped at {day} after {loaded} days" if day else "is on hold"
        super().__init__(
            f"{source_code} history {where}; may resume after {resume_after.isoformat()}")
        self.source_code, self.day = source_code, day
        self.resume_after, self.loaded = resume_after, loaded



def _store_raw(source: str, native_id: str, payload: dict,
               writer: BufferedWriter | None = None,
               content_hash: str | None = None) -> str:
    """Land the raw payload and return the storage key recorded in raw_ingest.

    With a writer the store happens on a background thread and this returns as
    soon as the key is known. The payload is guaranteed to be in the store only
    once the writer has been drained, which `_checkpoint` does before it
    commits, so no committed `raw_ingest` row can point at an object that was
    never written.
    """
    key = storage_key(source, native_id, content_hash=content_hash)
    if writer is not None:
        return writer.put(key, payload)
    return build_store().put(key, payload)


def _checkpoint(conn, label: str, fetched: int, new: int, changed: int,
                every: int = 200, writer: BufferedWriter | None = None,
                run_id: int | None = None) -> None:
    """Commit what has been collected so far, and say so.

    Must be called before anything in the loop that can `continue`. It was not,
    and the consequence was invisible: in a feed that is mostly non-defence --
    which is every feed we ingest -- the skip fired on almost every record, so
    neither the commit nor the progress line was ever reached. A PLACSP run
    held one transaction open for its whole length, printed nothing for half an
    hour, and would have thrown away every `raw_ingest` row on any failure
    while the payloads it had already written to object storage stayed there.
    An index that rolls back away from the store it indexes is the one
    divergence this design is supposed to prevent.
    """
    if fetched and fetched % every == 0:
        if writer is not None:
            writer.drain()
        if run_id is not None:
            db.record_progress(conn, run_id, fetched=fetched, new=new, changed=changed)
        conn.commit()
        log.info("%s: %s fetched, %s new, %s changed", label, fetched, new, changed)


IDLE_COMMIT_SECONDS = 30.0


def _pulled(conn, items: Iterable[Any], writer: BufferedWriter | None = None,
            every: float = IDLE_COMMIT_SECONDS, clock=time.monotonic) -> Iterator[Any]:
    """Yield `items`, never asking for the next one inside an old transaction.

    A generator does its work when it is asked, and the first request of an archive
    replay is a download of hundreds of megabytes plus a parse that took 30-40 minutes
    on 16 October 2026. The connection had run a query to find the source and sat
    "idle in transaction" all that time, and the worker role's
    `idle_in_transaction_session_timeout` of 30 minutes closed it ("the connection is
    lost"). So the first request, and any later one after `every` seconds without a
    commit, is preceded by a commit (the writer drained first, as `_checkpoint` does).
    """
    it = iter(items)
    last = None
    while True:
        if last is None or clock() - last >= every:
            if writer is not None:
                writer.drain()
            conn.commit()
            last = clock()
        try:
            item = next(it)
        except StopIteration:
            return
        yield item


# What one badly shaped record can raise. Connection and server failures
# (OperationalError, InterfaceError, anything not listed) are not here on purpose:
# those are the run's, and they still fail it.
RECORD_ERRORS = (ValueError, TypeError, KeyError, AttributeError, IndexError,
                 psycopg.DataError, psycopg.IntegrityError)
MAX_QUARANTINED = 50
_ID_KEYS = ("native_id", "publication-number", "notice-identifier", "idweb", "id", "slug",
            "Diarienummer", "publicatieId", "bzpNumber", "noticeNumber", "objectId",
            "ccm2Id", "path", "numeroConvocatoria", "file")


def _record_id(record: Any) -> str:
    if isinstance(record, dict):
        for key in _ID_KEYS:
            if record.get(key):
                value = record[key]
                return str(value[0] if isinstance(value, list) and value else value)[:60]
        return "?"
    return str(getattr(record, "native_id", None) or "?")[:60]


class Quarantine:
    """Keep one poisoned record from failing its whole source every night.

    Until this existed, any exception on one notice rolled the run back, and because
    the record stays inside the fetch window the next run failed on it again: one
    bad notice silenced a source for as long as it was in range. `guard` runs one
    record inside a savepoint -- an explicit one: `conn.transaction()` would commit
    for real whenever the connection is idle, which is right after a checkpoint, and
    commit is `_checkpoint`'s to do once the writer has drained.

    A record that raises is rolled back alone, noted, and the run ends `partial`
    naming it, so it is loud but not blocking. More than MAX_QUARANTINED of them is
    not a poisoned record but a source that changed its shape, and that still fails
    the run.

    Only for the daily runs, whose window overlaps the last one and so tries the
    record again tomorrow. `run_history` marks a day done, which would turn a
    quarantined record into a permanent hole, and the Atlas load is a one-off file:
    both keep failing loudly instead.
    """

    def __init__(self, label: str, limit: int = MAX_QUARANTINED) -> None:
        self.label = label
        self.limit = limit
        self.items: list[tuple[str, str, str]] = []

    @contextmanager
    def guard(self, conn, record: Any) -> Iterator[None]:
        conn.execute("SAVEPOINT dgate_record")
        try:
            yield
        except RECORD_ERRORS as exc:
            conn.execute("ROLLBACK TO SAVEPOINT dgate_record")
            conn.execute("RELEASE SAVEPOINT dgate_record")
            item = (_record_id(record), type(exc).__name__, str(exc)[:200])
            self.items.append(item)
            log.warning("%s: record %s quarantined (%s: %s)", self.label, *item)
            if len(self.items) > self.limit:
                raise RuntimeError(
                    f"{self.label}: more than {self.limit} records could not be processed "
                    f"(last: {item[0]} {item[1]}); the source's shape has probably "
                    f"changed") from exc
        else:
            conn.execute("RELEASE SAVEPOINT dgate_record")

    def note(self) -> str | None:
        if not self.items:
            return None
        shown = ", ".join(f"{i} ({t})" for i, t, _ in self.items[:10])
        more = f" and {len(self.items) - 10} more" if len(self.items) > 10 else ""
        return f"{len(self.items)} records quarantined: {shown}{more}"

    def merge(self, status: str, error: str | None) -> tuple[str, str | None]:
        """Fold the quarantine into a run's own status and message."""
        if not self.items:
            return status, error
        note = self.note()
        return ("partial" if status == "success" else status,
                "; ".join(part for part in (error, note) if part))

    def outcome(self) -> dict[str, str]:
        """`finish_run` keyword arguments for a run with nothing else to say."""
        if not self.items:
            return {}
        status, error = self.merge("success", None)
        return {"status": status, "error": error}


def _kept(conn, src_id: int, opp: Opportunity) -> bool:
    """Whether a classified notice is archived: it qualifies, or it is already held.

    A notice that stops qualifying (a later payload drops its CPV or its legal basis, a
    buyer is un-listed) used to be skipped here for ever, so the serving row kept its stale
    state -- `open`, with a deadline passed -- and no version said otherwise (internal
    audit M6). One that is held is archived whatever the verdict; the verdict itself is
    recorded on the row (`is_defence` false), which the lists do not serve.
    """
    return opp.is_defence or db.is_archived(conn, src_id, opp)


def _twin_is_defence(conn, opp: Opportunity) -> bool:
    """Whether the same procurement is already a defence notice in the other direction.

    A TED notice is defence when a national defence notice says it was forwarded under
    its number. A national notice is defence when the TED notice it states (`ted_ref`, or
    the eForms procedure identifier) is a defence row we hold: a republished TED notice
    whose national body lacks the CPV and legal basis was landed and then dropped (7 of 7
    sampled Polish ones, 2026/S 68-238462 among them). Nothing is guessed: only a stated
    reference or an identical procedure identifier counts.
    """
    if opp.source_code == "ted":
        return conn.execute(
            "SELECT 1 FROM opportunity WHERE ted_ref = %s AND is_defence LIMIT 1",
            (opp.native_id,)).fetchone() is not None
    if opp.ted_ref and conn.execute(
            """SELECT 1 FROM opportunity t WHERE t.native_id = %s AND t.is_defence
                  AND t.source_id = (SELECT id FROM source WHERE code = 'ted') LIMIT 1""",
            (opp.ted_ref,)).fetchone():
        return True
    pid = (opp.procedure_identifier or "").strip("{} ")
    return bool(pid) and conn.execute(
        """SELECT 1 FROM opportunity t WHERE t.procedure_identifier = ANY(%s) AND t.is_defence
              AND t.source_id = (SELECT id FROM source WHERE code = 'ted') LIMIT 1""",
        ([pid, pid.lower(), pid.upper()],)).fetchone() is not None


def _finalise(conn, opp: Opportunity, src_id: int, *, linked_defence: bool = False) -> Opportunity:
    """Resolve the buyer, run the classifier, attach the signals."""
    org_id = db.resolve_organisation(conn, opp.buyer_name_raw, opp.country,
                                     src_id=src_id, identifier=opp.buyer_identifier)
    opp.buyer_org_id = org_id
    if not linked_defence:
        linked_defence = _twin_is_defence(conn, opp)
    listed = db.is_defence_buyer(conn, org_id)
    buyer_class = effective_buyer_class(opp.buyer_name_raw, opp.country, listed)
    sig = classify(
        legal_basis=opp.legal_basis,
        cpv_codes=opp.cpv_codes,
        buyer_is_defence=listed,
        security_clearance_text="present" if opp.security_clearance_required else None,
        nda_required=opp.nda_required,
        buyer_class=buyer_class,
        linked_defence=linked_defence,
    )
    opp.is_defence = sig.is_defence
    opp.sig_legal_basis = sig.legal_basis
    opp.sig_cpv = sig.cpv
    opp.sig_buyer = sig.buyer
    opp.sig_clearance = sig.clearance
    opp.sig_cpv_military = sig.military_cpv
    opp.sig_cpv_adjacent = sig.cpv_adjacent
    opp.sig_linked_defence = sig.linked_defence
    opp.dual_use = sig.dual_use
    opp.buyer_class = buyer_class
    opp.subcontracting_signal = detects_subcontracting(
        opp.description, opp.title_original
    )
    return opp


def _completeness(code: str, landed: dict[date, int], days_back: int | None,
                  skip: Iterable[date] = ()) -> tuple[dict[str, Any] | None, str | None]:
    """Nightly control: the days a run walked against the portal's own day totals
    (`ops/controls.check_days`). Never raises; (None, None) when off or nothing to compare.
    Re-read notices of older days are outside the window and not counted."""
    if days_back is None or not landed or not settings().completeness_check:
        return None, None
    from .ops import controls

    today = date.today()
    window = {today - timedelta(days=n) for n in range(days_back + 1)}
    try:
        detail, problem = controls.check_days(
            code, {d: n for d, n in landed.items() if d in window}, skip=set(skip), today=today)
    except Exception as exc:  # noqa: BLE001 - a control must not fail the run it checks
        log.warning("%s: completeness control could not run: %s", code, type(exc).__name__)
        return None, None
    return {"completeness": detail}, problem


def run_ted(days: int = 2) -> None:
    """Daily incremental pull. Overlaps by design so a missed run self-heals.

    The window is the defence query over `days` plus every notice of today and
    yesterday (`ted.DailyPull`), so a buyer-list-only notice is not a day late.
    """
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), "ted") as writer):
        src_id = db.source_id(conn, "ted")
        run_id = db.start_run(conn, "ted", settings().floor("ted"))
        q = Quarantine("ted")
        fetched = new = changed = 0
        unmapped: dict[str, int] = {}
        stream = ted.fetch_window(days_back=days)
        try:
            for notice in stream:
                fetched += 1
                _checkpoint(conn, "ted", fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                with q.guard(conn, notice):
                    clean = strip_personal_data(notice)
                    h = ted.content_hash(clean)
                    try:
                        opp = from_ted(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed notice: %s", exc)
                        continue
                    if (ted_notice_type(clean) not in TED_STATUS_BY_TYPE
                            and ted_notice_type(clean) not in TED_INFORMATION_TYPES):
                        kind = ted_notice_type(clean) or "(none)"
                        unmapped[kind] = unmapped.get(kind, 0) + 1
                    key = _store_raw("ted", opp.native_id, clean, writer, content_hash=h)
                    db.record_raw(conn, src_id, opp.native_id, h, key)
                    opp = _finalise(conn, opp, src_id)
                    if not _kept(conn, src_id, opp):
                        continue
                    _, action = db.upsert_opportunity(conn, opp, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            writer.drain()
            # The floor is for what the defence query returned; whole days are
            # extra and say nothing about whether that query worked.
            floor_count = getattr(stream, "defence_fetched", fetched)
            status, error = "success", None
            if unmapped:
                # A type we do not map is stored `unknown` and never served as open.
                # It is loud rather than silent: the next one is a new rule to read.
                status = "partial"
                error = "unmapped TED notice types: " + ", ".join(
                    f"{k} ({n})" for k, n in sorted(unmapped.items()))
                log.warning("ted: %s", error)
            status, error = q.merge(status, error)
            db.finish_run(conn, run_id, fetched=floor_count, new=new, changed=changed,
                          status=status, error=error)
        except Exception as exc:
            # Roll back first. finish_run commits, and without this it committed
            # the raw_ingest rows written since the last checkpoint along with the
            # failure -- including rows whose payloads never reached the store,
            # because the write that failed is what raised. Resume then skipped
            # those identifiers as landed. Found on 13 September 2026 as a key the
            # index listed and R2 did not have.
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("ted done: %s fetched, %s new, %s changed", fetched, new, changed)


# A day of TED is 3,600 notices and about 40 MB held in memory before the write.
# Ten thousand is the point past which that stops being obviously safe, and a
# source that changes its habits must not turn it into a number nobody chose.
BUNDLE_CHUNK = 10_000


def run_boamp(days: int = 2) -> None:
    """Daily pull of the French bulletin, every notice of each day.

    Same shape as Poland: land everything, classify afterwards. France states
    the procurement regime in `perimetre`, so the legal-basis signal comes from
    the source rather than from an inference.
    """
    code = boamp.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        fetched = new = changed = 0
        landed: dict[date, int] = {}
        try:
            for record in boamp.fetch_window(days_back=days):
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                with q.guard(conn, record):
                    clean = strip_personal_data(record)
                    h = ted.content_hash(clean)
                    try:
                        opp = from_boamp(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed notice: %s", exc)
                        continue
                    key = _store_raw(code, opp.native_id, clean, writer, content_hash=h)
                    db.record_raw(conn, src_id, opp.native_id, h, key)
                    if opp.published_at:
                        landed[opp.published_at] = landed.get(opp.published_at, 0) + 1
                    opp = _finalise(conn, opp, src_id)
                    if not _kept(conn, src_id, opp):
                        continue
                    _, action = db.upsert_opportunity(conn, opp, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            writer.drain()
            detail, short = _completeness(code, landed, days)
            status, error = q.merge("partial" if short else "success", short)
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status=status, error=error, detail=detail)
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s fetched, %s new, %s changed", code, fetched, new, changed)


# A European TenderNed notice gets its TED number after it is published: 443697 was read
# on the day, states `pbNummerTed` now, and was never read again, so its twin was served
# as a second tender. Notices of the last REREAD_DAYS days that are under a European
# directive and hold no TED number are read again, at most REREAD_LIMIT a night.
TENDERNED_REREAD_DAYS = 14
TENDERNED_REREAD_LIMIT = 60


def _tenderned_unlinked(conn, src_id: int, store, *, days_back: int,
                        pause: float = tenderned.REQUEST_PAUSE) -> Iterator[dict[str, Any]]:
    """Stored notices still waiting for their TED number, with a fresh detail page.

    Only the detail is requested (the list row is what was landed, minus the volatile
    counters), one request each, at the connector's own pace. A notice whose page cannot
    be read is skipped for tonight, not landed thin.
    """
    ids = [r["native_id"] for r in conn.execute(
        """SELECT native_id FROM opportunity
            WHERE source_id = %s AND ted_ref IS NULL AND legal_basis IS NOT NULL
              AND published_at >= current_date - %s AND published_at < current_date - %s
            ORDER BY published_at DESC LIMIT %s""",
        (src_id, TENDERNED_REREAD_DAYS, days_back, TENDERNED_REREAD_LIMIT)).fetchall()]
    if not ids:
        return
    client = tenderned._client()
    try:
        for pid in ids:
            held = conn.execute(
                "SELECT storage_key FROM raw_ingest WHERE source_id = %s AND native_id = %s "
                "ORDER BY fetched_at DESC LIMIT 1", (src_id, pid)).fetchone()
            if held is None:
                continue
            try:
                detail = tenderned.fetch_detail(pid, client=client)
                listed = {k: v for k, v in store.get(held["storage_key"]).items()
                          if k not in ("detail", "detailError")}
            except Exception as exc:  # noqa: BLE001 - tonight's other notices must still run
                log.warning("nl_tenderned: no re-read of %s: %s", pid, exc)
                continue
            yield tenderned.merge_detail(listed, detail)
            time.sleep(pause)
    finally:
        client.close()


def run_tenderned(days: int = 2, *, reread: bool = False) -> None:
    """Daily pull of the Dutch platform, every publication of each day.

    `reread` adds the notices still waiting for their TED number (`_tenderned_unlinked`):
    the scheduled run and the command line ask for it; a test of the window does not, as
    it would then make requests.

    Same shape as France: land everything, classify afterwards. The defence
    directive is stated by the form, so the legal-basis signal comes from the
    source. A publication seen for the first time whose detail page could not be
    read is still landed, and makes the run `partial` -- thinner than the rest, and
    said so. One already archived is left as it is: see below.
    """
    code = tenderned.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        fetched = new = changed = thin = 0
        landed: dict[date, int] = {}
        try:
            window = tenderned.fetch_window(days_back=days)
            waiting = (_tenderned_unlinked(conn, src_id, build_store(), days_back=days)
                       if reread else iter(()))
            for record in itertools.chain(window, waiting):
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                with q.guard(conn, record):
                    if "detailError" in record:
                        # A notice already archived keeps what it has. Landing a thin copy
                        # of it would append a version with its CPV codes emptied, and when
                        # the page came back the full record's hash would match that older
                        # version and be skipped, so the loss would be permanent. One seen
                        # for the first time is landed thin and counted, once: from the
                        # next night it is known and the page is tried again.
                        pid = str(record.get("publicatieId") or "")
                        if conn.execute("SELECT 1 FROM raw_ingest WHERE source_id = %s "
                                        "AND native_id = %s LIMIT 1", (src_id, pid)).fetchone():
                            log.info("%s: detail page of %s unreadable tonight; kept as archived",
                                     code, pid)
                            continue
                        thin += 1
                    clean = strip_personal_data(record)
                    h = ted.content_hash(clean)
                    try:
                        opp = from_tenderned(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed publication: %s", exc)
                        continue
                    key = _store_raw(code, opp.native_id, clean, writer, content_hash=h)
                    db.record_raw(conn, src_id, opp.native_id, h, key)
                    if opp.published_at:
                        landed[opp.published_at] = landed.get(opp.published_at, 0) + 1
                    opp = _finalise(conn, opp, src_id)
                    if not _kept(conn, src_id, opp):
                        continue
                    _, action = db.upsert_opportunity(conn, opp, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            writer.drain()
            detail, short = _completeness(code, landed, days)
            problems = [m for m in (
                f"{thin} publications without their detail page" if thin else None, short) if m]
            status, error = q.merge("partial" if problems else "success",
                                    "; ".join(problems) or None)
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status=status, error=error, detail=detail)
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s fetched, %s new, %s changed, %s thin", code, fetched, new,
             changed, thin)


def source_is_active(conn, code: str) -> bool:
    """`source.active`. A source seeded inactive is collected only on a manual `--force`."""
    row = conn.execute("SELECT active FROM source WHERE code = %s", (code,)).fetchone()
    return bool(row and row["active"])


# A publication day under this many files is short: 40% of the weekday median (732 on
# 14 October 2026). A day before today only: today's file is still being filled.
DE_BKMS_DAY_FLOOR = 290


def run_de_bkms(days: int = 2, *, force: bool = False, today: date | None = None) -> None:
    """Daily pull of the German notice service: the last `days + 1` publication days.

    Day files are regenerated and hold late arrivals, so three days overlap on purpose and
    the run is idempotent (a payload already held has its hash in `raw_ingest`, and an
    unchanged notice adds no version). Days go oldest first so a notice's versions arrive
    in order.

    While the source is inactive (its licence is not verified; migration 0050) the run
    does nothing unless `force`: the scheduled job stays off, a manual run lands data,
    and the rows it writes are held back from every public read by the database.

    The count check: for each day the files the zip held are compared with the payloads
    landed from it. A file that is not a notice (`unreadable`), a day short of
    `DE_BKMS_DAY_FLOOR`, or a landed count that differs from the zip's own makes the run
    `partial`, never `success`.
    """
    code = de_bkms.SOURCE_CODE
    cfg = settings()
    with db.connect(cfg.dsn) as conn:
        if not force and not source_is_active(conn, code):
            log.info("%s: source is inactive; nothing collected (use --force for a manual run)",
                     code)
            return
    today = today or date.today()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        # One run of this source at a time, whoever started it. The scheduled job and a
        # manual `--once` overlapped on 16 October 2026 and both inserted the same new
        # notice: a UniqueViolation, quarantined, the run `partial`. A session lock is
        # released when the connection closes.
        if not conn.execute("SELECT pg_try_advisory_lock(hashtext('dgate_run:de_bkms')) AS ok"
                            ).fetchone()["ok"]:
            log.warning("%s: another run is in progress; this one is skipped", code)
            return
        conn.commit()
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        fetched = new = changed = unreadable = 0
        problems: list[str] = []
        client = de_bkms._client()
        try:
            for day in de_bkms.window_days(days, today):
                opened = de_bkms.open_day(day, client=client)
                if opened is None:
                    if day == today:
                        continue     # today's file does not exist yet
                    raise RuntimeError(f"{code}: no file for {day}")
                landed = 0
                with opened as day_file:
                    for record in day_file.records():
                        fetched += 1
                        _checkpoint(conn, code, fetched, new, changed, every=100,
                                    writer=writer, run_id=run_id)
                        with q.guard(conn, record):
                            clean = strip_personal_data(record)
                            h = ted.content_hash(clean)
                            try:
                                opp = from_de_bkms(clean)
                            except ValueError as exc:
                                # Landed all the same: the file is evidence, and replayable
                                # when the mapper learns the shape.
                                unreadable += 1
                                log.warning("%s: %s: %s", code, record.get("file"), exc)
                                native = str(record.get("notice_id") or record.get("file"))
                                key = _store_raw(code, native, clean, writer, content_hash=h)
                                db.record_raw(conn, src_id, native, h, key)
                                landed += 1
                                continue
                            key = _store_raw(code, opp.native_id, clean, writer, content_hash=h)
                            db.record_raw(conn, src_id, opp.native_id, h, key)
                            landed += 1
                            opp = _finalise(conn, opp, src_id)
                            if not _kept(conn, src_id, opp):
                                continue
                            _, action = db.upsert_opportunity(conn, opp, h, src_id)
                            new += action == "new"
                            changed += action == "changed"
                    entries = day_file.entries
                log.info("%s: %s files on %s, %s landed", code, entries, day, landed)
                if landed != entries:
                    problems.append(f"{day}: {entries} files in the zip, {landed} landed")
                if day < today and entries < DE_BKMS_DAY_FLOOR:
                    problems.append(f"{day}: {entries} files, under {DE_BKMS_DAY_FLOOR}")
                time.sleep(de_bkms.REQUEST_PAUSE)
            writer.drain()
            if unreadable:
                problems.append(f"{unreadable} files were not readable notices")
            status, error = q.merge("partial" if problems else "success",
                                    "; ".join(problems) or None)
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status=status, error=error)
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
        finally:
            client.close()
    log.info("%s done: %s fetched, %s new, %s changed, %s unreadable", code, fetched, new,
             changed, unreadable)


def run_eu_portal() -> None:
    """Daily pull of the EU grant calendar: every call and topic in scope.

    Grants are the layer this product is for, so this is the run that matters
    most, and it is the cheapest one in the system: one request, no key, no
    paging. The whole in-scope population arrives at once -- about 150 topics --
    which is why it is a standing set that gets refreshed rather than a window
    that gets walked.

    Only a call whose payload has never been seen before is landed in the raw
    store. The portal republishes the same document every night, so landing
    everything would write the same 150 payloads 365 times a year and pay for
    each write; the hash already in `raw_ingest` says which ones are genuinely
    new. Every call is still upserted, because `last_seen_at` is how a
    withdrawn call becomes visible as one that stopped being confirmed.
    """
    code = eu_portal.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        known = {row["content_hash"] for row in conn.execute(
            "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
        fetched = new = changed = landed = 0
        try:
            for record in eu_portal.fetch_calls():
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                with q.guard(conn, record):
                    clean = strip_personal_data(record)
                    h = ted.content_hash(clean)
                    try:
                        call = from_eu_call(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed call: %s", exc)
                        continue
                    if h not in known:
                        key = _store_raw(code, call.native_id, clean, writer, content_hash=h)
                        db.record_raw(conn, src_id, call.native_id, h, key)
                        known.add(h)
                        landed += 1
                    _, action, fields_ = db.upsert_call(conn, call, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
                    if action == "changed":
                        log.info("call %s changed: %s", call.topic_code or call.native_id, fields_)
            writer.drain()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          **q.outcome())
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s calls in scope, %s new, %s changed, %s payloads landed",
             code, fetched, new, changed, landed)


def run_ncbr() -> None:
    """Daily pull of the Polish research agency's competitions, the whole list.

    A standing list, not a window: the API returns every competition NCBR has listed and
    the pull is judged by whether all of them arrived, which `ncbr.fetch_all` proves or
    refuses. Every record is landed (once per distinct content), and only a competition
    the publisher has tagged for defence or security, that a company may apply to, and
    that is open or closed this year, becomes a call.

    The description is landed and never served: it is CC BY-SA text.
    """
    code = ncbr.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        known = {row["content_hash"] for row in conn.execute(
            "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
        fetched = new = changed = landed = 0
        try:
            for record in ncbr.fetch_all():
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                with q.guard(conn, record):
                    path = record.get("path") or ""
                    clean = strip_personal_data(record)
                    h = ted.content_hash(clean)
                    if path and h not in known:
                        key = _store_raw(code, path, clean, writer, content_hash=h)
                        db.record_raw(conn, src_id, path, h, key)
                        known.add(h)
                        landed += 1
                    if not ncbr.in_scope(clean):
                        continue
                    try:
                        call = from_ncbr(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed competition: %s", exc)
                        continue
                    _, action, _ = db.upsert_call(conn, call, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            writer.drain()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          **q.outcome())
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s competitions listed, %s new, %s changed, %s payloads landed",
             code, fetched, new, changed, landed)


def run_matine() -> None:
    """Daily pull of the Finnish defence ministry's research funding call pages.

    One call a year, so one or two pages; read whole, landed once per distinct content,
    and every one in scope becomes a call. An unreadable landing page fails the run.
    """
    code = matine.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        known = {row["content_hash"] for row in conn.execute(
            "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
        fetched = new = changed = landed = 0
        try:
            for record in matine.fetch_all():
                fetched += 1
                with q.guard(conn, record):
                    slug = record.get("slug") or ""
                    clean = strip_personal_data(record)
                    h = ted.content_hash(clean)
                    if slug and h not in known:
                        key = _store_raw(code, slug, clean, writer, content_hash=h)
                        db.record_raw(conn, src_id, slug, h, key)
                        known.add(h)
                        landed += 1
                    if not matine.in_scope(clean):
                        continue
                    try:
                        call = from_matine(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed page: %s", exc)
                        continue
                    _, action, _ = db.upsert_call(conn, call, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            writer.drain()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          **q.outcome())
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s pages, %s new, %s changed, %s payloads landed",
             code, fetched, new, changed, landed)


def run_aid() -> None:
    """Daily pull of the French defence innovation agency's call pages.

    No API: both lists and every page under them are read, about forty requests at one
    a second. Every page is landed once per distinct content; each one becomes a call,
    because everything the agency lists is its own. A page that could not be read is
    left out and says so in the run, rather than the run being a success.
    """
    code = aid.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        known = {row["content_hash"] for row in conn.execute(
            "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
        fetched = new = changed = landed = 0
        try:
            pages = aid.fetch_all()
            unreadable: list[str] = list(getattr(pages, "failed", ()))
            for record in pages:
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=20,
                            writer=writer, run_id=run_id)
                with q.guard(conn, record):
                    slug = record.get("slug") or ""
                    clean = strip_personal_data(record)
                    h = ted.content_hash(clean)
                    if slug and h not in known:
                        key = _store_raw(code, slug, clean, writer, content_hash=h)
                        db.record_raw(conn, src_id, slug, h, key)
                        known.add(h)
                        landed += 1
                    if not aid.in_scope(clean):
                        continue
                    try:
                        call = from_aid(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed page: %s", exc)
                        continue
                    _, action, _ = db.upsert_call(conn, call, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            writer.drain()
            status, error = q.merge(
                "partial" if unreadable else "success",
                f"{len(unreadable)} pages could not be read: " + ", ".join(unreadable[:5])
                if unreadable else None)
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status=status, error=error)
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s pages, %s new, %s changed, %s payloads landed",
             code, fetched, new, changed, landed)


def run_vinnova() -> None:
    """Daily pull of Sweden's innovation agency, the whole register.

    A standing set like Poland's: three small lists, joined, fetched whole every night.
    Every round is landed once per distinct content, and only a round of the publisher's
    defence programmes that a supplier may answer becomes a call.
    """
    code = vinnova.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        known = {row["content_hash"] for row in conn.execute(
            "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
        fetched = new = changed = landed = matched = 0
        try:
            for record in vinnova.fetch_all():
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=200,
                            writer=writer, run_id=run_id)
                with q.guard(conn, record):
                    dnr = record.get("Diarienummer") or ""
                    clean = strip_personal_data(record)
                    if vinnova.regime(clean) is not None:
                        matched += 1
                        if int(clean.get("Publik") or 0) == 1 and vinnova.deadline(clean) is None:
                            log.warning("%s: round %s of a defence programme has no closing "
                                        "date and is not kept", code, dnr)
                    h = ted.content_hash(clean)
                    if dnr and h not in known:
                        key = _store_raw(code, dnr, clean, writer, content_hash=h)
                        db.record_raw(conn, src_id, dnr, h, key)
                        known.add(h)
                        landed += 1
                    if not vinnova.in_scope(clean):
                        continue
                    try:
                        call = from_vinnova(clean)
                    except ValueError as exc:
                        log.warning("skipping malformed round: %s", exc)
                        continue
                    _, action, _ = db.upsert_call(conn, call, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            if not matched:
                # 3,800 rounds fetched and none in a defence programme is not a quiet
                # night: the programme titles or the join to them changed, and every
                # call already stored would go on being touched while nothing new came.
                raise RuntimeError(
                    f"{code}: none of {fetched} rounds belongs to a defence programme; "
                    f"the programme titles or the call/programme join changed")
            writer.drain()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          **q.outcome())
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s rounds listed, %s new, %s changed, %s payloads landed",
             code, fetched, new, changed, landed)


def run_bdns(days: int = 14, since: date | None = None) -> None:
    """Daily pull of the Spanish subsidy register, central government only.

    Search is walked in full, because it is cheap and a classifier that changes
    must be able to look at calls that were once passed over; the detail record --
    one request each, a second apart -- is fetched only for the calls that could
    matter, plus every call already held that can still change. A call is kept
    only if `bdns.in_scope` says a supplier could answer it.

    Calls only. Awards name the people who received them, and the register restricts
    reuse of that to control and research.
    """
    code = bdns.SOURCE_CODE
    cfg = settings()
    start = since or bdns.window_start(days)
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        q = Quarantine(code)
        known = {row["content_hash"] for row in conn.execute(
            "SELECT content_hash FROM raw_ingest WHERE source_id = %s", (src_id,)).fetchall()}
        fetched = new = changed = landed = failed = 0
        client = bdns._client()
        try:
            rows = list(bdns.search_central(start, client=client))
            fetched = len(rows)
            wanted: dict[str, None] = {}
            for row in rows:
                with q.guard(conn, row):
                    number = str(row.get("numeroConvocatoria") or "")
                    clean = strip_personal_data(row)
                    h = ted.content_hash(clean)
                    if number and h not in known:
                        key = _store_raw(code, number, clean, writer, content_hash=h)
                        db.record_raw(conn, src_id, number, h, key)
                        known.add(h)
                        landed += 1
                    if number and bdns.is_candidate(row):
                        wanted[number] = None
            for held in conn.execute(
                    """SELECT c.native_id FROM call c JOIN source s ON s.id = c.source_id
                        WHERE s.code = %s AND c.status IN ('open', 'forthcoming')""",
                    (code,)).fetchall():
                wanted[held["native_id"]] = None
            log.info("%s: %s calls scanned since %s, %s details to read", code, fetched,
                     start, len(wanted))
            for done, number in enumerate(wanted, 1):
                try:
                    detail = bdns.fetch_detail(number, client=client)
                except Exception as exc:
                    # One call that cannot be read is not the run.
                    log.warning("%s: call %s could not be read: %s", code, number, exc)
                    failed += 1
                    continue
                with q.guard(conn, {"numeroConvocatoria": number}):
                    clean = strip_personal_data(detail)
                    h = ted.content_hash(clean)
                    if h not in known:
                        key = _store_raw(code, number, clean, writer, content_hash=h)
                        db.record_raw(conn, src_id, number, h, key)
                        known.add(h)
                        landed += 1
                    if bdns.in_scope(clean):
                        try:
                            call = from_bdns(clean)
                        except ValueError as exc:
                            log.warning("skipping malformed call: %s", exc)
                            continue
                        _, action, _ = db.upsert_call(conn, call, h, src_id)
                        new += action == "new"
                        changed += action == "changed"
                _checkpoint(conn, code, done, new, changed, every=25,
                            writer=writer, run_id=run_id)
                time.sleep(bdns.REQUEST_PAUSE)
            writer.drain()
            status, error = q.merge(
                "partial" if failed and not new and not changed else "success",
                f"{failed} calls unreadable" if failed else None)
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status=status, error=error)
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
        finally:
            client.close()
    log.info("%s done: %s scanned, %s new, %s changed, %s payloads landed, %s unreadable",
             code, fetched, new, changed, landed, failed)


def run_topic_details(limit: int | None = None, refresh_after_days: int = 7) -> None:
    """Read the topic page of every call that needs one.

    The calendar says a call exists. This says whether it is worth applying to:
    the budget, the conditions of participation, the submission links, and --
    for the programmes that state it in words rather than in a PDF -- how many
    members the consortium needs and from how many countries.

    Self-healing rather than caught up. The step processes whatever lacks
    details, so a missed night is covered by the next one without anybody
    working out how far back to reach; that is why it has a schedule slot and no
    entry in the catch-up.

    One request a second, and only a document whose hash is new is landed. A
    closed call is read once and never again.
    """
    code = eu_portal.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code, tag="topics") as writer):
        src_id = db.source_id(conn, code)
        pending = db.calls_needing_details(conn, src_id,
                                           refresh_after_days=refresh_after_days,
                                           limit=limit)
        log.info("%s: %s topic pages to read", code, len(pending))
        if not pending:
            return
        run_id = db.start_run(conn, code, None)
        fetched = changed = failed = 0
        client = new_client(headers={"User-Agent": eu_portal.USER_AGENT,
                                       "Accept": "application/json"},
                              follow_redirects=True)
        try:
            for row in pending:
                identifier = row["topic_code"]
                try:
                    details = eu_portal.fetch_topic_details(identifier, client=client)
                except Exception as exc:
                    # One topic page is not the run. A 404 on a withdrawn topic,
                    # or one malformed document, must not cost the other 149.
                    log.warning("%s: topic %s could not be read: %s", code, identifier, exc)
                    failed += 1
                    continue
                fetched += 1
                clean = strip_personal_data(details)
                h = ted.content_hash(clean)
                if h != row["details_hash"]:
                    key = _store_raw(code, identifier, clean, writer, content_hash=h)
                    db.record_raw(conn, src_id, identifier, h, key)
                fields = eu_portal.detail_fields(clean, identifier)
                changed += db.update_call_details(conn, row["id"], fields, h) == "changed"
                _checkpoint(conn, code, fetched, 0, changed, every=25,
                            writer=writer, run_id=run_id)
                time.sleep(eu_portal.DETAIL_PAUSE)
            writer.drain()
            db.finish_run(conn, run_id, fetched=fetched, new=0, changed=changed,
                          status="partial" if failed and not fetched else "success",
                          error=f"{failed} topic pages unreadable" if failed else None)
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=0, changed=changed,
                          status="failed", error=str(exc))
            raise
        finally:
            client.close()
    log.info("%s topics done: %s read, %s updated, %s unreadable", code, fetched,
             changed, failed)


# What a historical load needs to know about a source: how to ask it for one
# publication day, and how to turn a record into an Opportunity. Everything else
# -- bundles, day markers, checkpoints, the rollback rule -- is the same whoever
# publishes, so it lives once.
HISTORY_SOURCES: dict[str, tuple[Any, Any]] = {}


def _history_source(code: str) -> tuple[Any, Any]:
    if not HISTORY_SOURCES:
        HISTORY_SOURCES["ted"] = (
            lambda day: ted.search(ted.day_query(day)), from_ted)
        HISTORY_SOURCES[boamp.SOURCE_CODE] = (
            lambda day: boamp.search(boamp.day_query(day)), from_boamp)
        HISTORY_SOURCES[tenderned.SOURCE_CODE] = (
            lambda day: tenderned.fetch_day(day), from_tenderned)
        # Poland: a weekday is about 270 pages at one request a second, so a
        # month is more than an hour and the whole of 2026 is most of a day. A
        # page that keeps failing raises, the day stays unmarked, and the next
        # run starts at that day.
        HISTORY_SOURCES[ezamowienia.SOURCE_CODE] = (
            lambda day: ezamowienia.fetch_day(day), from_ezamowienia)
        # Germany: a day is one zip request of 500 to 1,050 files; from 2023-10-25 on.
        HISTORY_SOURCES[de_bkms.SOURCE_CODE] = (
            lambda day: de_bkms.fetch_day(day), from_de_bkms)
    if code not in HISTORY_SOURCES:
        raise ValueError(f"no historical load defined for {code!r}")
    return HISTORY_SOURCES[code]


@db.historical("history")
def run_history(source_code: str, start: date, end: date, *, resume: bool = True,
                max_days: int | None = None, force: bool = False) -> int:
    """Load every notice a source published between two dates, one day at a time.

    The daily jobs collect defence notices; this collects everything, because
    the classifier will change and refetching a decade will not be an option.
    Only notices carrying a defence signal become opportunities -- the rest are
    landed, indexed in `raw_ingest`, and wait there for a better question.

    A day is stored as one gzipped file of JSON lines, not as thousands of
    objects: object storage bills for writes, and the first 4.8 million notices
    of the TED history cost about 22 dollars written one at a time. Each record
    is still addressed individually -- `raw_ingest.storage_key` holds
    `<bundle>#<line>` -- so replay reads a single payload exactly as before.

    Resumable by construction: the bundle is written before any `raw_ingest`
    row that points into it is committed, and the day is marked done only after
    those rows commit. An interrupted run loses at most the day it was in, and
    re-running skips what is already marked. Returns the number of days loaded.

    A source that refuses for rate (`RateLimited`: HTTP 429, or the 403 a burst
    is answered with, still there after the connector's whole retry ladder) ends
    the run cleanly instead of crashing it: the day in progress is rolled back
    and left unmarked, `backfill_stop` records why and until when, and
    `HistoryStopped` is raised for the caller to turn into a non-zero exit. The
    French history stopped this way on 23 September 2026 and was never resumed.
    The next run refuses to start before `resume_after`, so a rerun loop cannot
    keep a rate limiter open.
    """
    fetch_day, mapper = _history_source(source_code)
    cfg = settings()
    if source_code == de_bkms.SOURCE_CODE and start < de_bkms.HISTORY_FROM:
        raise ValueError(f"{source_code}: files before {de_bkms.HISTORY_FROM} are not eForms")
    if source_code == de_bkms.SOURCE_CODE and not force:
        with db.connect(cfg.dsn) as probe:
            if not source_is_active(probe, source_code):
                raise RuntimeError(f"{source_code} is inactive (licence not verified); "
                                   f"a manual load needs --force")
    store = build_store()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    loaded = 0
    with db.connect(cfg.dsn) as conn:
        src_id = db.source_id(conn, source_code)
        held = db.backfill_resume_after(conn, source_code)
        if held is not None:
            raise HistoryStopped(source_code, None, held, 0)
        done = db.backfill_days_done(conn, source_code) if resume else set()
        pending = [day for day in days if day not in done]
        log.info("%s history: %s days to load, %s already done",
                 source_code, len(pending), len(days) - len(pending))
        for day in pending:
            if max_days is not None and loaded >= max_days:
                break
            fetched = new = thin = 0
            try:
                for part, chunk in enumerate(_in_chunks(fetch_day(day), BUNDLE_CHUNK)):
                    cleaned = [strip_personal_data(notice) for notice in chunk]
                    key = rawstore.bundle_key(source_code, day, part)
                    stored = store.put_records(key, cleaned)
                    if stored != len(cleaned):
                        raise RuntimeError(
                            f"bundle {key} holds {stored} records, not {len(cleaned)}")
                    for line, clean in enumerate(cleaned):
                        fetched += 1
                        thin += "detailError" in clean
                        h = ted.content_hash(clean)
                        try:
                            opp = mapper(clean)
                        except ValueError as exc:
                            log.warning("skipping malformed notice: %s", exc)
                            continue
                        db.record_raw(conn, src_id, opp.native_id, h,
                                      rawstore.record_key(key, line))
                        if "detailError" in clean and db.is_archived(conn, src_id, opp):
                            # Landed, indexed, and not archived: a notice already held
                            # keeps what it has. A thin copy appended as a version has its
                            # CPV codes emptied, and when the page came back the full
                            # record's hash matched that older version and was skipped
                            # (`run_tenderned` has the same guard; internal audit M5).
                            continue
                        opp = _finalise(conn, opp, src_id)
                        if not _kept(conn, src_id, opp):
                            continue
                        _, action = db.upsert_opportunity(conn, opp, h, src_id)
                        new += action == "new"
                    conn.commit()
            except RateLimited as exc:
                conn.rollback()
                resume_after = db.record_backfill_stop(
                    conn, source_code, day, str(exc), exc.retry_after)
                log.error("%s history stopped by the source at %s (%s days loaded): %s; "
                          "rerun the same command after %s", source_code, day, loaded,
                          exc, resume_after.isoformat())
                raise HistoryStopped(source_code, day, resume_after, loaded) from exc
            except Exception:
                # Same rule as the daily runs: roll the uncommitted index rows
                # back rather than record keys whose payloads never landed. The
                # day stays unmarked, so resuming asks for it again, and the
                # bundle it rewrites is byte-for-byte the same object.
                conn.rollback()
                raise
            if thin:
                # Marked done all the same, so a backfill is not stalled for ever by one
                # withdrawn page; the payloads carry `detailError`, which is how they are
                # found again.
                log.warning("%s history %s: %s of %s notices landed without their detail "
                            "page (see `detailError` in the raw payload)",
                            source_code, day, thin, fetched)
            db.mark_backfill_day(conn, source_code, day, fetched)
            loaded += 1
            log.info("%s history %s: %s notices, %s defence", source_code, day, fetched, new)
        if max_days is None or loaded < max_days:
            db.note_backfill_finished(conn, source_code)
    return loaded


def run_ted_history(start: date, end: date, *, resume: bool = True,
                    max_days: int | None = None) -> int:
    return run_history("ted", start, end, resume=resume, max_days=max_days)


# ---------------------------------------------------------------- TED defence history
#
# Before 17 April 2024 the TED notices we hold are those that qualified when they were
# landed, under the rules of that day. `ted-defence-history` asks the API for the notices
# today's rules can qualify without the full day (legal basis, military CPV, a defence stem
# in the buyer's name: `ted.defence_history_query`) and runs them through the daily
# pipeline's own steps. Windows are months; one above the API's paging cap is split into
# weeks and those into days. A window is marked in `backfill_day` under
# `ted-defence:<M|W|D>`, so an interrupted run resumes at the window it was in.
DEFENCE_HISTORY_MARK = "ted-defence"
DEFENCE_WINDOW_CAP = 10_000        # TED refuses paging past 15,000 results in one query
DEFENCE_PAGE = 100


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    out, cur = [], start
    while cur <= end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((cur, min(end, nxt - timedelta(days=1))))
        cur = nxt
    return out


def _split_window(start: date, end: date, level: str) -> list[tuple[date, date]]:
    """A month into weeks, a week into days."""
    if level == "M":
        return [(a, min(end, a + timedelta(days=6)))
                for a in (start + timedelta(days=7 * i) for i in range((end - start).days // 7 + 1))]
    return [(start + timedelta(days=i),) * 2 for i in range((end - start).days + 1)]


def plan_ted_defence_history(conn, start: date, end: date, *, pause: float = 1.0,
                             resume: bool = True) -> list[dict[str, Any]]:
    """Every window the load would walk with its notice count (one request each, plus the
    split of a window above the cap). `done` windows are counted as zero requests."""
    done = {lv: (db.backfill_days_done(conn, f"{DEFENCE_HISTORY_MARK}:{lv}") if resume else set())
            for lv in "MWD"}
    plan: list[dict[str, Any]] = []

    def walk(a: date, b: date, level: str) -> None:
        if a in done[level]:
            plan.append({"start": a, "end": b, "level": level, "notices": 0, "requests": 0,
                         "done": True})
            return
        time.sleep(pause)
        total = ted.count(ted.defence_history_query(a, b))
        if total > DEFENCE_WINDOW_CAP and level != "D":
            nxt = "W" if level == "M" else "D"
            for sa, sb in _split_window(a, b, level):
                walk(sa, sb, nxt)
            return
        plan.append({"start": a, "end": b, "level": level, "notices": total,
                     "requests": -(-total // DEFENCE_PAGE) + 1, "done": False})

    for a, b in _month_windows(start, end):
        walk(a, b, "M")
    return plan


def print_defence_plan(plan: list[dict[str, Any]]) -> None:
    years: dict[int, list[int]] = {}
    for w in plan:
        row = years.setdefault(w["start"].year, [0, 0, 0])
        row[0] += 1
        row[1] += w["notices"]
        row[2] += w["requests"]
        print(f"{w['level']} {w['start']}..{w['end']}  "
              + ("done" if w["done"] else f"{w['notices']} notices, {w['requests']} requests"))
    print("year  windows  notices  requests")
    for y, (n, notices, requests) in sorted(years.items()):
        print(f"{y}  {n:7}  {notices:7}  {requests:8}")
    total = sum(w["requests"] for w in plan)
    print(f"total  {sum(w['notices'] for w in plan)} notices, {total} requests "
          f"(about {total / 60:.0f} minutes at one request a second)")


@db.historical("history")
def run_ted_defence_history(start: date, end: date, *, resume: bool = True,
                            max_windows: int | None = None, pause: float = 1.0) -> int:
    """Load the notices of a publication range that today's rules can qualify. Returns the
    number of windows loaded. Safe to repeat and to interrupt."""
    cfg = settings()
    store = build_store()
    loaded = 0
    with db.connect(cfg.dsn) as conn:
        src_id = db.source_id(conn, "ted")
        held = db.backfill_resume_after(conn, DEFENCE_HISTORY_MARK)
        if held is not None:
            raise HistoryStopped(DEFENCE_HISTORY_MARK, None, held, 0)
        done = {lv: (db.backfill_days_done(conn, f"{DEFENCE_HISTORY_MARK}:{lv}") if resume
                     else set()) for lv in "MWD"}

        def load(a: date, b: date, level: str) -> bool:
            """False when `max_windows` is reached."""
            nonlocal loaded
            if a in done[level]:
                return True
            if max_windows is not None and loaded >= max_windows:
                return False
            query = ted.defence_history_query(a, b)
            time.sleep(pause)
            total = ted.count(query)
            if total > DEFENCE_WINDOW_CAP and level != "D":
                nxt = "W" if level == "M" else "D"
                return all(load(sa, sb, nxt) for sa, sb in _split_window(a, b, level))
            fetched = new = 0
            try:
                stream = ted.search(query, page_size=DEFENCE_PAGE, pause=pause)
                for part, chunk in enumerate(_in_chunks(stream, BUNDLE_CHUNK)):
                    cleaned = [strip_personal_data(notice) for notice in chunk]
                    key = rawstore.bundle_key(DEFENCE_HISTORY_MARK, a, part)
                    if store.put_records(key, cleaned) != len(cleaned):
                        raise RuntimeError(f"bundle {key} did not take all {len(cleaned)} records")
                    for line, clean in enumerate(cleaned):
                        fetched += 1
                        h = ted.content_hash(clean)
                        try:
                            opp = from_ted(clean)
                        except ValueError as exc:
                            log.warning("skipping malformed notice: %s", exc)
                            continue
                        if not conn.execute(
                                """SELECT 1 FROM raw_ingest WHERE source_id = %s AND native_id = %s
                                      AND content_hash = %s LIMIT 1""",
                                (src_id, opp.native_id, h)).fetchone():
                            db.record_raw(conn, src_id, opp.native_id, h,
                                          rawstore.record_key(key, line))
                        opp = _finalise(conn, opp, src_id)
                        if not _kept(conn, src_id, opp):
                            continue
                        _, action = db.upsert_opportunity(conn, opp, h, src_id)
                        new += action == "new"
                    conn.commit()
                if fetched != total:
                    raise RuntimeError(f"TED window {a}..{b}: {fetched} notices read, "
                                       f"{total} stated; not marking it done")
            except RateLimited as exc:
                conn.rollback()
                resume_after = db.record_backfill_stop(
                    conn, DEFENCE_HISTORY_MARK, a, str(exc), exc.retry_after)
                raise HistoryStopped(DEFENCE_HISTORY_MARK, a, resume_after, loaded) from exc
            except Exception:
                conn.rollback()
                raise
            db.mark_backfill_day(conn, f"{DEFENCE_HISTORY_MARK}:{level}", a, fetched)
            done[level].add(a)
            loaded += 1
            log.info("ted-defence %s %s..%s: %s notices, %s new defence", level, a, b, fetched, new)
            return True

        for a, b in _month_windows(start, end):
            if not load(a, b, "M"):
                break
        else:
            db.note_backfill_finished(conn, DEFENCE_HISTORY_MARK)
    return loaded


def _in_chunks(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    """Group a stream into lists of at most `size`, yielding at least one."""
    chunk: list[Any] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    yield chunk      # the last, possibly empty: an empty day is still a day


def ezam_refresh_targets(conn, src_id: int, limit: int,
                         min_age_hours: float = ezamowienia.REFRESH_MIN_AGE_HOURS,
                         ) -> list[tuple[str, str]]:
    """The notices whose current state should be asked for again: (native id,
    notice number), the least recently read first.

    A notice is a target while it can still change in a way that matters: its
    deadline has not passed (or passed within three days, for a late extension),
    or it is `open` without a deadline and was published in the last 120 days.
    "Last read" is the newest `raw_ingest` row for the identifier, which every
    read writes, whichever job made it; nothing new is stored for it.

    The notice number is the identifier plus the revision the archived version
    carries (`2026/BZP 00448576` + 1 -> `2026/BZP 00448576/01`); a notice
    republished from TED has no revision and its number is the identifier.
    """
    rows = conn.execute(
        """WITH reads AS (
               SELECT native_id, max(fetched_at) AS last_read_at
                 FROM raw_ingest
                WHERE source_id = %(src)s AND fetched_at > now() - interval '60 days'
                GROUP BY native_id)
           SELECT o.native_id, v.payload->>'notice_version' AS revision
             FROM opportunity o
             JOIN opportunity_version v
               ON v.opportunity_id = o.id AND v.version = o.current_version
             LEFT JOIN reads r ON r.native_id = o.native_id
            WHERE o.source_id = %(src)s
              AND (o.deadline_at > now() - interval '3 days'
                   OR (o.status = 'open' AND o.deadline_at IS NULL
                       AND o.published_at > current_date - 120))
              AND (r.last_read_at IS NULL
                   OR r.last_read_at < now() - interval '1 hour' * %(age)s)
            ORDER BY r.last_read_at NULLS FIRST, o.deadline_at NULLS LAST
            LIMIT %(limit)s""",
        {"src": src_id, "age": min_age_hours, "limit": limit}).fetchall()
    return [(r["native_id"],
             r["native_id"] + (f"/{int(r['revision']):02d}"
                               if (r["revision"] or "").isdigit() else ""))
            for r in rows]


def run_ezamowienia(days: int | None = 2, *,
                    refresh_limit: int = ezamowienia.REFRESH_LIMIT) -> None:
    """Daily incremental pull of the Polish bulletin.

    Same ordering rule as every other source: land the raw record, normalise,
    classify, archive. The connector already narrows to defence angles, so most
    of what arrives here survives classification; the rest is dropped exactly as
    it is for TED.

    Then up to `refresh_limit` notices that are still open are asked for by
    number, least recently read first, one request a second. The publication-day
    window cannot see a change made in place (a deadline moved keeps the notice
    number and the publication date): on 12 October 2026, 296 of 311 open
    notices had not been read for over three days and one deadline was a day
    out. With about 300 open and 200 a day, each is re-read within two days.
    `days=None` skips the window (a re-read only); `refresh_limit=0` skips the
    re-read.
    """
    code = ezamowienia.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        # The floors describe a publication window; a re-read alone has none.
        run_id = db.start_run(conn, code, settings().floor(code) if days is not None else None)
        q = Quarantine(code)
        fetched = new = changed = refreshed = 0
        problems: list[str] = []
        landed: dict[date, int] = {}
        unread: list[date] = []

        def ingest(record: dict[str, Any]) -> date | None:
            nonlocal new, changed
            with q.guard(conn, record):
                clean = strip_personal_data(record)
                h = ted.content_hash(clean)
                try:
                    opp = from_ezamowienia(clean)
                except ValueError as exc:
                    log.warning("skipping malformed notice: %s", exc)
                    return None
                key = _store_raw(code, opp.native_id, clean, writer, content_hash=h)
                db.record_raw(conn, src_id, opp.native_id, h, key)
                opp = _finalise(conn, opp, src_id)
                if not _kept(conn, src_id, opp):
                    return opp.published_at
                _, action = db.upsert_opportunity(conn, opp, h, src_id)
                new += action == "new"
                changed += action == "changed"
                return opp.published_at
            return None

        try:
            if days is not None:
                for record in ezamowienia.fetch_window(days_back=days, failed=unread):
                    fetched += 1
                    _checkpoint(conn, code, fetched, new, changed, every=100,
                                writer=writer, run_id=run_id)
                    day = ingest(record)
                    if day:
                        landed[day] = landed.get(day, 0) + 1
                if unread:
                    # Said by day, so the owner can load exactly those days with
                    # `history --source pl_ezam --from D --to D`. The run is
                    # `partial`, so catch-up widens the next window over them.
                    problems.append("publication days not read to their end: "
                                    + ", ".join(d.isoformat() for d in unread))
            if refresh_limit > 0:
                targets = ezam_refresh_targets(conn, src_id, refresh_limit)
                log.info("%s: %s open notices to re-read", code, len(targets))
                refreshed, unreadable, missing, in_a_row = 0, 0, 0, 0
                client = new_client(headers={"User-Agent": ezamowienia.USER_AGENT,
                                             "Accept": "application/json"},
                                    follow_redirects=True)
                try:
                    for i, (_, number) in enumerate(targets):
                        if i:
                            time.sleep(ezamowienia.REFRESH_PAUSE)
                        try:
                            record = ezamowienia.fetch_notice(number, client=client)
                            in_a_row = 0
                        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
                            unreadable += 1
                            in_a_row += 1
                            log.warning("%s: re-read of %s failed: %s", code, number, exc)
                            if in_a_row >= 3:
                                # The source is unwell. What is left is the
                                # oldest-read set again tomorrow.
                                problems.append("re-read stopped after 3 failures in a row")
                                break
                            continue
                        if record is None:
                            missing += 1
                            continue
                        refreshed += 1
                        _checkpoint(conn, f"{code}-reread", fetched + refreshed, new, changed,
                                    every=50, writer=writer, run_id=run_id)
                        ingest(record)
                finally:
                    client.close()
                log.info("%s: re-read %s, %s unreadable, %s not found", code, refreshed,
                         unreadable, missing)
                if unreadable:
                    problems.append(f"{unreadable} open notices could not be re-read")
            writer.drain()
            detail, short = _completeness(code, landed, days, skip=unread)
            if short:
                problems.append(short)
            status, error = q.merge("partial" if problems else "success",
                                    "; ".join(problems) or None)
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status=status, error=error, detail=detail)
        except Exception as exc:
            # Roll back first. finish_run commits, and without this it committed
            # the raw_ingest rows written since the last checkpoint along with the
            # failure -- including rows whose payloads never reached the store,
            # because the write that failed is what raised. Resume then skipped
            # those identifiers as landed. Found on 13 September 2026 as a key the
            # index listed and R2 did not have.
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s fetched, %s new, %s changed", code, fetched, new, changed)


def _ingest_placsp(opps: Iterable[Opportunity], label: str,
                   dataset: placsp.Dataset = placsp.MAIN,
                   stale_reason=None, *, replay: bool = False, resume_from: int = 0,
                   progress: tuple[str, date] | None = None) -> tuple[int, int, int]:
    """Ingest one PLACSP stream. `stale_reason()`, if given, is asked once the
    stream is exhausted; a non-empty answer records the run as partial.

    A live walk hands in, as `stale_reason.seen`, the dict its generator reads and
    writes (see `placsp.fetch_live`): the newest entry the previous complete run saw
    goes in before the walk starts, and what this walk saw is kept on the run after.

    `replay` re-reads archives to correct what is already held. It is not a
    collection run, so it writes no `ingest_run` row -- catch-up would take it for
    today's collection -- and it lands a raw payload only for the records it
    archives, because re-landing a month of non-defence entries would spend the
    object store's daily write allowance on records no row depends on.

    `progress` is a `(marker, day)` key in `backfill_day`: at every checkpoint the count
    of entries finished is written into it in the same transaction as their rows, and
    `resume_from` skips that many entries of the (identically ordered) archive, so a
    unit that failed late is not redone from its first entry.

    Returns (fetched, new, changed).
    """
    code = dataset.source_code
    cfg = settings()
    seen: dict | None = getattr(stale_reason, "seen", None)
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = None if replay else db.start_run(conn, code, settings().floor(code))
        if seen is not None:
            row = conn.execute(
                """SELECT newest_entry_at FROM ingest_run
                    WHERE source_id = %s AND newest_entry_at IS NOT NULL
                    ORDER BY started_at DESC LIMIT 1""", (src_id,)).fetchone()
            seen["until"] = row["newest_entry_at"] if row else None
        q = Quarantine(label)
        fetched = new = changed = resume_from
        try:
            for opp in itertools.islice(_pulled(conn, opps, writer), resume_from, None):
                fetched += 1
                if progress and fetched % 200 == 0:
                    db.write_backfill_progress(conn, *progress, fetched - 1)
                _checkpoint(conn, label, fetched, new, changed, writer=writer,
                            run_id=run_id)
                with q.guard(conn, opp):
                    # This connector parses while fetching, so there is no raw payload to
                    # pass through strip_personal_data: sweep the record itself.
                    opp = scrub_opportunity(opp)
                    payload = db.opportunity_payload(opp)
                    h = ted.content_hash(payload)
                    if replay:
                        opp = _finalise(conn, opp, src_id)
                        if not _kept(conn, src_id, opp):
                            continue
                    # Landed once per content (internal audit M10): the live feed re-reads
                    # about 19,000 unchanged entries a night, each of which was a new
                    # index row and a new store line saying what the first one said.
                    if not db.raw_held(conn, src_id, opp.native_id, h):
                        key = _store_raw(code, opp.native_id, payload, writer, content_hash=h)
                        db.record_raw(conn, src_id, opp.native_id, h, key,
                                      content_type="application/atom+xml")
                    if not replay:
                        opp = _finalise(conn, opp, src_id)
                        if not _kept(conn, src_id, opp):
                            continue
                    _, action = db.upsert_opportunity(conn, opp, h, src_id)
                    new += action == "new"
                    changed += action == "changed"
            writer.drain()
            stale = stale_reason() if stale_reason else None
            status, error = q.merge("partial" if stale else "success", stale)
            if run_id is None:
                log.info("%s replay done: %s fetched, %s new, %s changed%s", label, fetched,
                         new, changed, f" ({status}: {error})" if error else "")
                return fetched, new, changed
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status=status, error=error)
            if (seen is not None and seen.get("newest") is not None
                    and not seen.get("capped") and not seen.get("refused")):
                # Only a walk that reached the previous one's newest entry says where
                # the next must reach back to; one that did not leaves the older
                # mark standing, and the gap stays the next run's to close. Committed
                # with the connection, which does it on a clean exit.
                conn.execute("UPDATE ingest_run SET newest_entry_at = %s WHERE id = %s",
                             (seen["newest"], run_id))
        except Exception as exc:
            # Roll back first. finish_run commits, and without this it committed
            # the raw_ingest rows written since the last checkpoint along with the
            # failure -- including rows whose payloads never reached the store,
            # because the write that failed is what raised. Resume then skipped
            # those identifiers as landed. Found on 13 September 2026 as a key the
            # index listed and R2 did not have.
            conn.rollback()
            if run_id is not None:
                db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                              status="failed", error=str(exc))
            raise
    log.info("%s done: %s fetched, %s new, %s changed", label, fetched, new, changed)
    return fetched, new, changed


def run_placsp_live(max_pages: int = 20, datasets: Iterable[placsp.Dataset] = (),
                    now: datetime | None = None) -> None:
    """Daily incremental for both PLACSP datasets.

    Dataset 2 carries the autonomous communities, which reach PLACSP through
    aggregation. Running only dataset 1 loses every regional buyer without any
    error being raised, so both run by default and each has its own floor.

    A live feed can stop moving while still answering. Dataset 1's head file was
    last modified on 8 September 2026 and was still served unchanged on the
    14th, and for six days every run re-read the same 19,497 entries, cleared its
    floor of 400, and reported success -- a floor counts what was read, not what
    was new. So the newest entry's own timestamp is checked: past
    `placsp_stale_hours` the live run is partial and loud, and the current
    month's archive, which the publisher rebuilds daily through the previous
    day, is ingested to cover the gap. Early in a month the previous month's
    archive is read too, since the current one may not yet hold the days before.

    `max_pages` is how far the walk goes at least. Past it the walk goes on until
    a page's oldest entry is no newer than the newest one the previous complete
    run saw, up to `placsp_max_pages`; a walk that hits that cap, or is sent off
    the feed's own directory, ends the run `partial` and says what to run.
    """
    cfg = settings()
    now = now or datetime.now(timezone.utc)
    limit = timedelta(hours=cfg.placsp_stale_hours)
    for ds in (datasets or (placsp.MAIN, placsp.AGGREGATED)):
        seen: dict = {"hard_cap": max(max_pages, cfg.placsp_max_pages)}

        def staleness(seen=seen) -> str | None:
            newest = seen.get("newest")
            if newest is not None and now - newest <= limit:
                return None
            return (f"live feed stale: newest entry {newest.isoformat() if newest else 'none'}, "
                    f"older than {cfg.placsp_stale_hours}h")

        def gap(seen=seen) -> str | None:
            until = seen.get("until")
            if seen.get("capped"):
                since = f"{until:%Y-%m}" if until else "YYYY-MM"
                return (f"live walk stopped at its cap of {seen.get('pages')} pages before the "
                        f"previous run's newest entry ({until.isoformat() if until else 'none'}); "
                        f"entries in between are unread: run `placsp-backfill --from {since}`")
            if seen.get("refused"):
                return f"live walk left the feed's directory at {seen['refused']}"
            return None

        def verdict(seen=seen) -> str | None:
            return "; ".join(r for r in (staleness(), gap()) if r) or None

        # The walk reads and writes this dict; `_ingest_placsp` finds it here.
        verdict.seen = seen

        _ingest_placsp(placsp.fetch_live(ds, max_pages=max_pages, observe=seen),
                       f"{ds.source_code}-live", ds, stale_reason=verdict)
        from .ops.notify import notify

        if gap():
            log.warning("%s %s", ds.source_code, gap())
            notify(f"[dgate] {ds.source_code} {gap()}")
        reason = staleness()
        if not reason:
            continue

        months = [(now.year, now.month)]
        if now.day <= 3:
            prev = (now.replace(day=1) - timedelta(days=1))
            months.insert(0, (prev.year, prev.month))
        log.warning("%s %s; covering from the monthly archive %s",
                    ds.source_code, reason, months)
        notify(f"[dgate] {ds.source_code} {reason}; covering from monthly archive")
        live_newest = seen.get("newest")
        for year, month in months:
            first = datetime(year, month, 1, tzinfo=timezone.utc)
            since = (first - timedelta(days=1)).replace(day=1)
            arch: dict = {}
            entries = list(placsp.fetch_archive(ds.monthly_archive_url(year, month), ds,
                                                observe=arch, since=since))
            newest = arch.get("newest")
            if newest is None or (live_newest is not None and newest <= live_newest):
                # An archive holding nothing newer than the frozen live feed
                # cannot close the gap; the source has stopped publishing, not
                # just its feed. Ingesting it anyway re-reads what we have and
                # says nothing new, so it is skipped and said out loud.
                msg = (f"{ds.source_code} archive {year}{month:02d} holds nothing newer than the "
                       f"live feed (newest {newest.isoformat() if newest else 'none'}); "
                       "the source itself appears to have stopped publishing")
                log.warning(msg)
                notify(f"[dgate] {msg}")
                continue
            _ingest_placsp(iter(entries), f"{ds.source_code}-{year}{month:02d}", ds)


@db.historical("backfill")
def run_placsp_backfill(start: int, end: int,
                        datasets: Iterable[placsp.Dataset] = ()) -> None:
    """Historical load. Run once, oldest first, then never again.

    This is the part that cannot be repeated later by a competitor starting
    after us, so it is worth the hours it takes.
    """
    for ds in (datasets or (placsp.MAIN, placsp.AGGREGATED)):
        for url in placsp.backfill_years(start, end, ds):
            log.info("backfilling %s", url)
            try:
                _ingest_placsp(placsp.fetch_archive(url, ds),
                               f"{ds.source_code}-{url[-8:-4]}", ds)
            except Exception as exc:
                log.error("backfill failed for %s: %s", url, exc)


# The marker `backfill_day` keeps for a replayed month, kept apart from the source's
# own code so that nothing reads it as a day of collection.
REPLAY_MARK = "-replay"


def _in_live_window(now: datetime, cfg) -> bool:
    """True from ten minutes before the daily PLACSP slot to two hours after it."""
    slot = now.replace(hour=cfg.placsp_hour, minute=cfg.placsp_minute, second=0, microsecond=0)
    return slot - timedelta(minutes=10) <= now <= slot + timedelta(hours=2)


def _live_walk_running(conn) -> bool:
    return conn.execute(
        """SELECT 1 FROM ingest_run r JOIN source s ON s.id = r.source_id
            WHERE s.code IN ('es_placsp', 'es_placsp_agg') AND r.status = 'running'
            LIMIT 1""").fetchone() is not None


REPLAY_ATTEMPTS = 3


def _replay_unit(url, ds, since, name, pmark, day, resume, sleep) -> tuple[int, int, int]:
    """Replay one archive, and again from where it got to if the database goes away.

    A lost connection loses the work since the last checkpoint and nothing else; the
    entries finished are in `backfill_day` under `pmark`. Reading the archive again is
    the cost (it is a download), not the entries. A fresh `--no-resume` run starts the
    unit over; a retry inside this run, and a plain rerun, continue.
    """
    for attempt in range(1, REPLAY_ATTEMPTS + 1):
        with db.connect(settings().dsn) as conn:
            if attempt == 1 and not resume:
                db.reset_backfill_progress(conn, pmark, day)
            skip = db.backfill_progress(conn, pmark, day)
        try:
            got = _ingest_placsp(placsp.fetch_archive(url, ds, since=since), f"{name}-replay",
                                 ds, replay=True, resume_from=skip, progress=(pmark, day))
            with db.connect(settings().dsn) as conn:    # finished: the next read starts at 0
                db.reset_backfill_progress(conn, pmark, day)
            return got
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            if attempt == REPLAY_ATTEMPTS:
                raise
            log.warning("replay of %s lost its database connection (%s); attempt %s of %s "
                        "continuing after the finished entries", url, exc, attempt + 1, REPLAY_ATTEMPTS)
            sleep(30.0 * attempt)
    raise AssertionError("unreachable")


@db.historical("replay")
def run_placsp_replay(start: tuple[int, int], end: tuple[int, int] | None = None,
                      datasets: Iterable[placsp.Dataset] = (), *, resume: bool = True,
                      pause: float = 1.0, now: datetime | None = None,
                      sleep=None) -> dict[str, list[str]]:
    """Re-read the publisher's archives for a range of months and archive what they say.

    Raw storage holds PLACSP's normalised record, not the entry, so a correction to
    how an entry is read (value, publication date, legal basis, procedure) can reach
    the rows already held only by reading the entries again. The archives are the
    only place older entries can be had from, and each month is one file.

    Goes through `upsert_opportunity` like any other run, so a notice whose
    corrected record differs from the held one gets a new version naming the fields
    that moved, and one the archive no longer improves is left alone. Oldest month
    first, so versions of one notice arrive in the order they happened.

    Safe to repeat and to interrupt: a month is marked done in `backfill_day` only
    once it has been committed, and `resume` skips marked months (the current month
    is never marked, as it is still being written). One request every `pause`
    seconds at most, a 429 ends the run, and the run refuses to start or continue
    inside the daily live walk's window, or while a live run is in progress.
    Archives from a year before the current one are the annual file, read once.

    Returns the units done, skipped and failed, by name.
    """
    import time

    import httpx

    sleep = sleep or time.sleep
    cfg = settings()
    clock = (lambda: now) if now else (lambda: datetime.now(timezone.utc))
    now = clock()
    end = end or (now.year, now.month)
    units: list[tuple[int, int | None]] = []
    year, month = start
    while (year, month) <= end:
        if year < now.year:
            if (year, None) not in units:
                units.append((year, None))     # the annual file covers every month
        else:
            units.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    result: dict[str, list[str]] = {"done": [], "skipped": [], "failed": [], "stopped": []}
    for ds in (datasets or (placsp.MAIN, placsp.AGGREGATED)):
        mark = f"{ds.source_code}{REPLAY_MARK}"
        with db.connect(cfg.dsn) as conn:
            done = db.backfill_days_done(conn, mark) if resume else set()
        for year, month in units:
            name = f"{ds.source_code}-{year}" + (f"{month:02d}" if month else "")
            day = date(year, month or 1, 1)
            if day in done:
                result["skipped"].append(name)
                continue
            with db.connect(cfg.dsn) as conn:
                running = _live_walk_running(conn)
            if running or _in_live_window(clock(), cfg):
                log.warning("%s: stopping before %s, the daily live walk is due or running; "
                            "run the same command again to resume", ds.source_code, name)
                result["stopped"].append(name)
                return result
            sleep(pause)
            url = (ds.monthly_archive_url(year, month) if month
                   else ds.annual_archive_url(year))
            since = datetime(year, month or 1, 1, tzinfo=timezone.utc)
            pmark = f"{mark}-progress"
            try:
                fetched, new, changed = _replay_unit(
                    url, ds, since, name, pmark, day, resume, sleep)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    log.error("%s: rate limited at %s; stopping", ds.source_code, name)
                    result["stopped"].append(name)
                    return result
                log.error("replay of %s failed: %s", url, exc)
                result["failed"].append(name)
                continue
            except Exception as exc:  # noqa: BLE001 -- one month must not end the range
                log.error("replay of %s failed: %s", url, exc)
                result["failed"].append(name)
                continue
            if (year, month or 12) < (now.year, now.month):
                with db.connect(cfg.dsn) as conn:
                    db.mark_backfill_day(conn, mark, day, fetched)
            log.info("%s replayed: %s entries, %s new, %s changed", name, fetched, new, changed)
            result["done"].append(name)
    return result


# Seed list for the buyer signal. Expand per country as coverage grows; this is
# the signal that catches defence buyers publishing under the general
# directives, which CPV alone misses.
DEFENCE_BUYERS = [
    ("ES", "Ministerio de Defensa"),
    ("ES", "Direccion General de Armamento y Material"),
    ("ES", "Jefatura de Asuntos Economicos del Ejercito de Tierra"),
    ("ES", "Instituto Nacional de Tecnica Aeroespacial"),
    ("ES", "Armada Espanola"),
    ("ES", "Ejercito del Aire y del Espacio"),
    ("FR", "Ministere des Armees"),
    ("FR", "Direction Generale de l'Armement"),
    ("DE", "Bundesamt fur Ausrustung Informationstechnik und Nutzung der Bundeswehr"),
    ("DE", "Bundeswehr"),
    ("NL", "Ministerie van Defensie"),
    ("NL", "Defensie Materieel Organisatie"),
    ("NL", "Ministerie van Defensie, Commando Materieel en IT, Afdeling Inkoop IT"),
    ("PL", "Agencja Uzbrojenia"),
    ("PL", "Ministerstwo Obrony Narodowej"),
    ("PT", "Ministerio da Defesa Nacional"),
    ("RO", "Ministerul Apararii Nationale"),
    ("CZ", "Ministerstvo obrany"),
    ("LT", "Krasto apsaugos ministerija"),
    ("LV", "Aizsardzibas ministrija"),
    ("EE", "Kaitseministeerium"),
]



def already_ingested(conn, code: str) -> set[str]:
    """Identifiers this source has already landed.

    A backfill of two thirds of a million rows takes hours, and the machine it
    runs on has demonstrably been switched off mid-run. Re-running from the
    start would be correct but wasteful, so the ones already recorded are read
    once and skipped. Held as a set because asking the database per row would
    cost more than the whole rest of the loop.
    """
    rows = conn.execute(
        """SELECT r.native_id FROM raw_ingest r JOIN source s ON s.id = r.source_id
            WHERE s.code = %s AND r.native_id IS NOT NULL""",
        (code,),
    ).fetchall()
    return {r["native_id"] for r in rows}


def atlas_done_marker(year: int) -> Path:
    """The file whose existence means a year has been loaded completely.

    A marker rather than a row count, because rows the mapper refuses are never
    recorded, so a count could fall short of the file for ever and the worker
    would reload the year on every start. It lives beside the downloaded file;
    losing that volume only costs a resumed run, which skips what has landed.
    """
    from .sources import atlas_pl

    return Path(settings().atlas_dir) / (atlas_pl.YEAR_FILES[year] + ".done")


@db.historical("backfill")
def run_atlas_backfill(year: int, *, path: Path | None = None,
                       limit: int | None = None, resume: bool = True,
                       workers: int | None = None, refresh_known: bool = False) -> None:
    """One-off historical load of the Polish bulletin from Atlas Przetargow.

    `refresh_known=True` is the second pass of 12 October 2026: it lands the
    current column set again (`tender_type`, `procedure_result`) for the rows
    that are already opportunities, and only lands -- no opportunity is written
    here, so a corrected mapping reaches the archive through one replay
    (`python -m dgate.reprocess --source pl_atlas`) that can mark the new versions
    as remapped, not as amendments made by the publisher.

    Run once per year file, then never again: this is the part of the archive a
    competitor starting after us cannot obtain, and the dataset is immutable
    and citable by DOI, so a second run would only rewrite what is already
    there.

    Every row is recorded in `raw_ingest`, whether or not it is defence. That
    is the point of the record: when the classifier improves, what we have
    already looked at is known, and can be looked at again without guessing.
    Only rows carrying a defence signal become opportunities.
    """
    from .sources import atlas_pl

    cfg = settings()
    code = atlas_pl.SOURCE_CODE
    filename = atlas_pl.YEAR_FILES.get(year)
    if filename is None:
        raise ValueError(
            f"no dataset file for {year}; the release covers "
            f"{sorted(atlas_pl.YEAR_FILES)}")

    if path is None:
        path = Path(cfg.atlas_dir) / filename
        atlas_pl.download(filename, path)
    total = atlas_pl.row_count(path)
    log.info("atlas %s: %s rows in %s", year, total, path.name)

    with (db.connect(cfg.dsn) as conn,
          BufferedWriter(build_store(), workers or cfg.raw_write_workers) as writer):
        src_id = db.source_id(conn, code)
        known: set[str] = set()
        if refresh_known:
            known = {r["native_id"] for r in conn.execute(
                "SELECT native_id FROM opportunity WHERE source_id = %s", (src_id,)).fetchall()}
            log.info("atlas %s: refreshing the %s rows that are opportunities", year, len(known))
        seen = already_ingested(conn, code) if resume and not refresh_known else set()
        if seen:
            log.info("atlas %s: %s identifiers already landed, skipping those",
                     year, len(seen))
        run_id = db.start_run(conn, code, cfg.floor(code))
        fetched = new = changed = skipped = 0
        try:
            for record in atlas_pl.read_rows(path):
                if limit is not None and fetched >= limit:
                    break
                native_id = str(record.get("id") or "")
                if native_id in seen or (refresh_known and native_id not in known):
                    skipped += 1
                    continue
                fetched += 1
                _checkpoint(conn, f"atlas-{year}", fetched, new, changed,
                            writer=writer, run_id=run_id)
                clean = strip_personal_data(record)
                h = atlas_pl.content_hash(clean)
                try:
                    opp = from_atlas_pl(clean)
                except ValueError as exc:
                    log.warning("skipping malformed row: %s", exc)
                    continue
                key = _store_raw(code, opp.native_id, clean, writer, content_hash=h)
                db.record_raw(conn, src_id, opp.native_id, h, key)
                if refresh_known:
                    continue
                opp = _finalise(conn, opp, src_id)
                if not _kept(conn, src_id, opp):
                    continue
                _, action = db.upsert_opportunity(conn, opp, h, src_id)
                new += action == "new"
                changed += action == "changed"
            writer.drain()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed)
        except Exception as exc:
            # Roll back first. finish_run commits, and without this it committed
            # the raw_ingest rows written since the last checkpoint along with the
            # failure -- including rows whose payloads never reached the store,
            # because the write that failed is what raised. Resume then skipped
            # those identifiers as landed. Found on 13 September 2026 as a key the
            # index listed and R2 did not have.
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("atlas %s done: %s rows read, %s already had, %s new, %s changed",
             year, fetched, skipped, new, changed)
    if limit is None and not refresh_known:
        atlas_done_marker(year).write_text(
            "completed " + datetime.now(timezone.utc).isoformat(timespec="seconds"),
            encoding="utf-8")


SEEDS_FILE = Path(__file__).resolve().parents[1] / "seeds" / "defence_buyers.csv"


def load_seed_rows(path: Path | None = None) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """The seed file grouped by organisation: (country, canonical) -> spellings.

    Falls back to the hand-curated DEFENCE_BUYERS when the file is absent, so
    an image built without it still has a working buyer signal rather than
    none -- which is the failure this list already had once.
    """
    import csv

    path = path or SEEDS_FILE
    groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    if not path.exists():
        log.warning("seed file %s not found; using the built-in list", path)
        for country, name in DEFENCE_BUYERS:
            groups.setdefault((country, name), []).append((name, "curated"))
        return groups
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row["country"].strip(), row["canonical_name"].strip())
            groups.setdefault(key, []).append((row["raw_name"].strip(), row["category"]))
    return groups


# Buyers proposed by a rule over names (dgate/buyer_vocab.py, written by
# `python -m dgate.ops.derive_buyers --derived-dir`), one file per country. A row is
# loaded as a buyer signal when its confidence reaches the floor, or when a person
# has set `reviewed` to true; `reviewed` set to `rejected` keeps it out for good.
#
# 0.80 because that is where the rule labels change character. At 0.85 and above a
# name begins with the ministry, the armed force, a procurement agency or a
# military unit; read in a 40-name sample, all 40 were defence bodies. The 0.70
# rows are a defence word somewhere in the name ("Cercle national des armees",
# a tender title typed into the buyer field), and in a 40-name sample about one in
# seven was not a procurement body.
DERIVED_GLOB = "defence_buyers_derived_*.csv"
DERIVED_MIN_CONFIDENCE = 0.80


def load_derived_rows(directory: Path | None = None,
                      min_confidence: float = DERIVED_MIN_CONFIDENCE) -> list[dict[str, Any]]:
    """The derived buyer rows that count as a signal, as dicts."""
    import csv

    directory = directory or SEEDS_FILE.parent
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob(DERIVED_GLOB)):
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                status = (row.get("reviewed") or "").strip().lower()
                if status in ("rejected", "no", "reject"):
                    continue
                try:
                    confidence = float(row.get("confidence") or 0)
                except ValueError:
                    continue
                if status in ("true", "yes", "1") or confidence >= min_confidence:
                    out.append({"country": row["country"].strip(), "name": row["name"].strip(),
                                "identifier": (row.get("identifier") or "").strip() or None,
                                "reason": row.get("reason") or "", "confidence": confidence})
    return out


def seed_derived_buyers(conn, directory: Path | None = None) -> int:
    """Flag the organisations the derived list names. Returns how many were flagged.

    Creates the organisation when none holds the name, as the seed list does, so
    the signal is there when the first notice from that body arrives.
    """
    from .normalise import normalise_identifier, normalise_org_name

    flagged = 0
    for row in load_derived_rows(directory):
        country, norm = row["country"], normalise_org_name(row["name"])
        if not country or not norm:
            continue
        found = conn.execute(
            """SELECT id FROM organisation
                WHERE country = %s AND lower(canonical_name) = %s
                ORDER BY (merged_into IS NOT NULL), id LIMIT 1""",
            (country, norm)).fetchone()
        if found:
            org_id = db._live(conn, found["id"])
            conn.execute(
                """UPDATE organisation
                      SET is_defence_buyer = TRUE,
                          defence_buyer_source = COALESCE(defence_buyer_source, 'derived_rule'),
                          defence_buyer_reason = COALESCE(defence_buyer_reason, %s),
                          defence_buyer_confidence = COALESCE(defence_buyer_confidence, %s)
                    WHERE id = %s""",
                (row["reason"][:120], round(row["confidence"], 2), org_id))
        else:
            org_id = conn.execute(
                """INSERT INTO organisation
                     (canonical_name, country, org_role, is_defence_buyer, confidence,
                      review_status, defence_buyer_source, defence_buyer_reason,
                      defence_buyer_confidence)
                   VALUES (%s, %s, 'buyer', TRUE, %s, 'rule_derived', 'derived_rule', %s, %s)
                   RETURNING id""",
                (norm, country, round(row["confidence"], 2), row["reason"][:120],
                 round(row["confidence"], 2))).fetchone()["id"]
            conn.execute(
                """INSERT INTO organisation_alias
                     (organisation_id, raw_name, normalised_name, country_hint,
                      match_method, confidence)
                   VALUES (%s, %s, %s, %s, 'derived_rule', %s)
                   ON CONFLICT DO NOTHING""",
                (org_id, row["name"], norm, country, round(row["confidence"], 2)))
        ident = normalise_identifier(row["identifier"], country)
        if ident:
            conn.execute(
                """UPDATE organisation SET national_reg_no = %s, identifier_method = 'derived_list',
                          identifier_confidence = %s
                    WHERE id = %s AND national_reg_no IS NULL
                      AND NOT EXISTS (SELECT 1 FROM organisation o2
                                       WHERE o2.country = %s AND o2.national_reg_no = %s)""",
                (ident, round(row["confidence"], 2), org_id, country, ident))
        flagged += 1
    return flagged


def seed_buyers(path: Path | None = None) -> int:
    """Mark the defence buyers, idempotently. Returns organisations seeded.

    Each organisation gets one row and one alias per real spelling. The
    canonical spelling is a human decision (confidence 1.00); the others were
    grouped by a written rule in dgate/ops/derive_buyers.py (0.98), which puts
    them above the 0.95 an automatic exact-name match gets, so a seeded
    spelling wins when ingestion has already created an alias of its own.

    Any organisation ingestion already created under one of those spellings is
    flagged as well. Merging it into the canonical one would be an
    entity-resolution decision without a stored method; flagging both means
    the buyer signal fires whichever of them a notice resolves to.
    """
    from .normalise import normalise_org_name

    groups = load_seed_rows(path)
    with db.connect(settings().dsn) as conn:
        for (country, canonical), spellings in groups.items():
            norm = normalise_org_name(canonical)
            row = conn.execute(
                """SELECT id FROM organisation
                    WHERE country = %s AND lower(canonical_name) = %s
                    ORDER BY (merged_into IS NOT NULL), id LIMIT 1""",
                (country, norm),
            ).fetchone()
            if row:
                org_id = db._live(conn, row["id"])
                conn.execute(
                    "UPDATE organisation SET is_defence_buyer = TRUE WHERE id = %s",
                    (org_id,),
                )
            else:
                org_id = conn.execute(
                    """INSERT INTO organisation
                         (canonical_name, country, org_role, is_defence_buyer,
                          confidence, review_status)
                       VALUES (%s, %s, 'buyer', TRUE, 1.00, 'human_verified')
                       RETURNING id""",
                    (norm, country),
                ).fetchone()["id"]

            for raw, _category in spellings:
                raw_norm = normalise_org_name(raw)
                is_canonical = raw_norm == norm
                conn.execute(
                    """INSERT INTO organisation_alias
                         (organisation_id, raw_name, normalised_name, country_hint,
                          match_method, confidence)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (org_id, raw, raw_norm, country,
                     "human" if is_canonical else "seed_rule",
                     1.00 if is_canonical else 0.98),
                )
                conn.execute(
                    """UPDATE organisation SET is_defence_buyer = TRUE
                        WHERE country = %s AND lower(canonical_name) = %s
                          AND NOT is_defence_buyer""",
                    (country, raw_norm),
                )
        derived = seed_derived_buyers(conn)
    log.info("seeded %s defence buyers, %s from the derived list", len(groups), derived)
    return len(groups)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request URL at INFO, and a Telegram bot token and a
    # healthchecks ping key sit in the URL path.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="dgate")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("ted", help="ingest TED defence notices")
    t.add_argument("--days", type=int, default=2)

    s = sub.add_parser("placsp", help="ingest Spanish PLACSP")
    s.add_argument("--live", action="store_true")
    s.add_argument("--pages", type=int, default=20)
    s.add_argument("--backfill", nargs=2, type=int, metavar=("START", "END"))

    rp = sub.add_parser(
        "placsp-backfill",
        help="re-read PLACSP monthly archives and archive corrected records (resumable)")
    rp.add_argument("--from", dest="start", required=True, metavar="YYYY-MM",
                    help="first month to re-read")
    rp.add_argument("--to", dest="end", default=None, metavar="YYYY-MM",
                    help="last month; defaults to the current month")
    rp.add_argument("--dataset", action="append", choices=["es_placsp", "es_placsp_agg"],
                    help="one dataset only; repeat for both (the default)")
    rp.add_argument("--no-resume", action="store_true",
                    help="re-read months already marked done")

    e = sub.add_parser("ezamowienia", help="ingest the Polish bulletin (BZP)")
    e.add_argument("--days", type=int, default=2)
    e.add_argument("--refresh-limit", type=int, default=ezamowienia.REFRESH_LIMIT,
                   help="open notices to re-read by number after the window; 0 for none")
    e.add_argument("--refresh-only", action="store_true",
                   help="skip the publication-day window and only re-read open notices")

    f = sub.add_parser("boamp", help="ingest the French bulletin (BOAMP)")
    f.add_argument("--days", type=int, default=2)

    nl = sub.add_parser("tenderned", help="ingest the Dutch platform (TenderNed)")
    nl.add_argument("--days", type=int, default=2)

    de = sub.add_parser("de-bkms", help="ingest the German notice service (BKMS day files)")
    de.add_argument("--days", type=int, default=2, help="days before today; the window is days+1")
    de.add_argument("--force", action="store_true",
                    help="run although the source is inactive (its licence is not verified)")

    sub.add_parser("calls", help="refresh the EU grant calendar (calls for proposals)")

    sub.add_parser("ncbr", help="refresh the Polish NCBR competitions")

    sub.add_parser("vinnova", help="refresh the Swedish Vinnova defence-programme calls")

    sub.add_parser("aid", help="refresh the French defence innovation agency call pages")

    sub.add_parser("matine", help="refresh the Finnish MATINE research funding call")

    bd = sub.add_parser("bdns", help="refresh the Spanish subsidy calls (BDNS, central government)")
    bd.add_argument("--days", type=int, default=14)
    bd.add_argument("--since", type=date.fromisoformat, default=None,
                    help="first registration day, YYYY-MM-DD; for the initial load")

    td = sub.add_parser("topics", help="read the topic page of every call that needs one")
    td.add_argument("--limit", type=int, default=None, help="stop after this many pages")
    td.add_argument("--refresh-after-days", type=int, default=7,
                    help="re-read an open call's page after this many days")

    b = sub.add_parser("atlas-pl",
                       help="one-off Polish historical backfill (Atlas Przetargow)")
    b.add_argument("--year", type=int, required=True,
                   help="dataset year; the 2026.Q2 release covers 2024 and 2025")
    b.add_argument("--file", type=Path, default=None,
                   help="use a local parquet file instead of downloading")
    b.add_argument("--limit", type=int, default=None,
                   help="stop after this many rows; for a rehearsal")
    b.add_argument("--no-resume", action="store_true",
                   help="re-read rows already landed instead of skipping them")
    b.add_argument("--refresh-known", action="store_true",
                   help="only land again the rows that are opportunities, with the "
                        "current column set; writes no opportunity (replay afterwards)")

    h = sub.add_parser("history",
                       help="one-off historical load of every notice of a source")
    h.add_argument("--source", default="ted",
                   help="ted, fr_boamp, nl_tenderned, pl_ezam or de_bkms")
    h.add_argument("--from", dest="start", type=date.fromisoformat, required=True,
                   help="first publication day, YYYY-MM-DD (the API starts at 2017)")
    h.add_argument("--to", dest="end", type=date.fromisoformat, default=None,
                   help="last publication day; defaults to yesterday")
    h.add_argument("--max-days", type=int, default=None,
                   help="stop after this many days; for a rehearsal")
    h.add_argument("--no-resume", action="store_true",
                   help="reload days already marked done")
    h.add_argument("--force", action="store_true",
                   help="load an inactive source (de_bkms: licence not verified)")

    dh = sub.add_parser(
        "ted-defence-history",
        help="TED notices before the full-day load that today's rules qualify (dry run by default)")
    dh.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    dh.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    dh.add_argument("--yes", action="store_true", help="load; without it only count")
    dh.add_argument("--no-resume", action="store_true")
    dh.add_argument("--max-windows", type=int, default=None)

    sub.add_parser("seed-buyers", help="seed the defence buyer list")

    co = sub.add_parser("cordis", help="load CORDIS projects, organisations and participations "
                                       "(SPARQL service; monthly)")
    co.add_argument("--programme", action="append", choices=["H2020", "HORIZON", "FP7"],
                    help="keep only this framework's projects; repeat for several (default: all)")
    co.add_argument("--max-pages", type=int, default=None,
                    help="read this many pages of each kind; a rehearsal, marks nothing inactive")
    co.add_argument("--no-candidates", action="store_true",
                    help="do not queue trigram candidates for the organisations created "
                         "(stage 3; about 40 ms an organisation, so 45 minutes on a first load; "
                         "`resolution-candidates` does it later, in chunks)")

    ed = sub.add_parser("edf", help="load the EDF project factsheets (crawl, read, resolve)")
    ed.add_argument("--year", type=int, action="append", help="a call year; repeat (default: all)")
    ed.add_argument("--max-files", type=int, default=None, help="stop after this many factsheets")
    ed.add_argument("--reread", action="store_true",
                    help="fetch files read in the last 25 days again (the site rate-limits)")

    qc = sub.add_parser("resolution-candidates",
                        help="stage 3 for organisations already held: trigram candidates into the "
                             "review queue (resumable)")
    qc.add_argument("--after-id", type=int, default=0)
    qc.add_argument("--limit", type=int, default=5000)
    qc.add_argument("--all", action="store_true", help="every live organisation, not only those with a PIC")

    sub.add_parser("consortium-snapshot",
                   help="write the consortium snapshots and the consortium.changed rows")

    re_ = sub.add_parser("resolution-eval", help="precision and recall of each resolution stage")
    re_.add_argument("--gold", type=Path, default=None)
    re_.add_argument("--load", action="store_true")
    re_.add_argument("--json", action="store_true")

    a = p.parse_args(argv)
    if a.cmd == "ted":
        run_ted(days=a.days)
    elif a.cmd == "placsp":
        if a.backfill:
            run_placsp_backfill(*a.backfill)
        else:
            run_placsp_live(max_pages=a.pages)
    elif a.cmd == "placsp-backfill":
        def _month(text: str) -> tuple[int, int]:
            year, month = (int(part) for part in text.split("-"))
            if not 1 <= month <= 12:
                raise SystemExit(f"not a month: {text}")
            return year, month

        summary = run_placsp_replay(
            _month(a.start), _month(a.end) if a.end else None,
            [placsp.DATASETS[code] for code in (a.dataset or [])],
            resume=not a.no_resume)
        print(summary)
        if summary["failed"] or summary["stopped"]:
            raise SystemExit(1)
    elif a.cmd == "ezamowienia":
        run_ezamowienia(days=None if a.refresh_only else a.days, refresh_limit=a.refresh_limit)
    elif a.cmd == "boamp":
        run_boamp(days=a.days)
    elif a.cmd == "tenderned":
        run_tenderned(days=a.days, reread=True)
    elif a.cmd == "de-bkms":
        run_de_bkms(days=a.days, force=a.force)
    elif a.cmd == "calls":
        run_eu_portal()
    elif a.cmd == "ncbr":
        run_ncbr()
    elif a.cmd == "vinnova":
        run_vinnova()
    elif a.cmd == "aid":
        run_aid()
    elif a.cmd == "matine":
        run_matine()
    elif a.cmd == "bdns":
        run_bdns(days=a.days, since=a.since)
    elif a.cmd == "topics":
        run_topic_details(limit=a.limit, refresh_after_days=a.refresh_after_days)
    elif a.cmd == "atlas-pl":
        run_atlas_backfill(a.year, path=a.file, limit=a.limit,
                           resume=not a.no_resume, refresh_known=a.refresh_known)
    elif a.cmd == "history":
        try:
            run_history(a.source, a.start, a.end or date.today() - timedelta(days=1),
                        resume=not a.no_resume, max_days=a.max_days, force=a.force)
        except HistoryStopped as stop:
            # Already logged and recorded. Not a success: the exit status says so.
            log.error("%s", stop)
            return EXIT_STOPPED
    elif a.cmd == "ted-defence-history":
        if not a.yes:
            with db.connect(settings().dsn) as conn:
                plan = plan_ted_defence_history(conn, a.start, a.end, resume=not a.no_resume)
            print_defence_plan(plan)
            return 0
        try:
            run_ted_defence_history(a.start, a.end, resume=not a.no_resume,
                                    max_windows=a.max_windows)
        except HistoryStopped as stop:
            log.error("%s", stop)
            return EXIT_STOPPED
    elif a.cmd == "seed-buyers":
        seed_buyers()
    elif a.cmd == "cordis":
        from . import networks

        networks.run_cordis(programmes=set(a.programme) if a.programme else None,
                            max_pages=a.max_pages, candidates=not a.no_candidates)
    elif a.cmd == "edf":
        from . import networks

        networks.run_edf(years=set(a.year) if a.year else None, max_files=a.max_files,
                         reread=a.reread)
    elif a.cmd == "resolution-candidates":
        from . import networks

        with db.connect(settings().dsn) as conn:
            print(networks.queue_candidates(conn, after_id=a.after_id, limit=a.limit,
                                            all_orgs=a.all))
    elif a.cmd == "consortium-snapshot":
        from . import networks

        print(networks.run_snapshot())
    elif a.cmd == "resolution-eval":
        from .resolution import evaluate

        args = ["--gold", str(a.gold)] if a.gold else []
        args += ["--load"] if a.load else []
        args += ["--json"] if a.json else []
        return evaluate.main(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
