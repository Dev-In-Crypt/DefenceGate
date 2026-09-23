"""Pipeline orchestration.

Usage:
    python -m dgate.pipeline ted --days 2
    python -m dgate.pipeline placsp --live
    python -m dgate.pipeline placsp --backfill 2012 2025
    python -m dgate.pipeline seed-buyers

Ordering rule enforced throughout: land the raw payload first, normalise
second, classify third, archive last. If normalisation crashes on an unexpected
shape, the raw record survives and the run can be replayed after a fix without
refetching anything.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import db, rawstore
from .classify import classify, detects_subcontracting
from .config import settings
from .normalise import (
    Opportunity,
    from_atlas_pl,
    from_boamp,
    from_ezamowienia,
    from_ted,
    strip_personal_data,
)
from .rawstore import BufferedWriter, BundleWriter, build_store, storage_key
from .sources import boamp, ezamowienia, placsp, ted

log = logging.getLogger("pipeline")



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


def _finalise(conn, opp: Opportunity, src_id: int) -> Opportunity:
    """Resolve the buyer, run the classifier, attach the signals."""
    org_id = db.resolve_organisation(conn, opp.buyer_name_raw, opp.country,
                                     src_id=src_id)
    opp.buyer_org_id = org_id
    sig = classify(
        legal_basis=opp.legal_basis,
        cpv_codes=opp.cpv_codes,
        buyer_is_defence=db.is_defence_buyer(conn, org_id),
        security_clearance_text="present" if opp.security_clearance_required else None,
        nda_required=opp.nda_required,
    )
    opp.is_defence = sig.is_defence
    opp.sig_legal_basis = sig.legal_basis
    opp.sig_cpv = sig.cpv
    opp.sig_buyer = sig.buyer
    opp.sig_clearance = sig.clearance
    opp.subcontracting_signal = detects_subcontracting(
        opp.description, opp.title_original
    )
    return opp


def run_ted(days: int = 2) -> None:
    """Daily incremental pull. Overlaps by design so a missed run self-heals."""
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), "ted") as writer):
        src_id = db.source_id(conn, "ted")
        run_id = db.start_run(conn, "ted", settings().floor("ted"))
        fetched = new = changed = 0
        try:
            for notice in ted.fetch_window(days_back=days):
                fetched += 1
                _checkpoint(conn, "ted", fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                clean = strip_personal_data(notice)
                h = ted.content_hash(clean)
                try:
                    opp = from_ted(clean)
                except ValueError as exc:
                    log.warning("skipping malformed notice: %s", exc)
                    continue
                key = _store_raw("ted", opp.native_id, clean, writer, content_hash=h)
                db.record_raw(conn, src_id, opp.native_id, h, key)
                opp = _finalise(conn, opp, src_id)
                if not opp.is_defence:
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
        fetched = new = changed = 0
        try:
            for record in boamp.fetch_window(days_back=days):
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                clean = strip_personal_data(record)
                h = ted.content_hash(clean)
                try:
                    opp = from_boamp(clean)
                except ValueError as exc:
                    log.warning("skipping malformed notice: %s", exc)
                    continue
                key = _store_raw(code, opp.native_id, clean, writer, content_hash=h)
                db.record_raw(conn, src_id, opp.native_id, h, key)
                opp = _finalise(conn, opp, src_id)
                if not opp.is_defence:
                    continue
                _, action = db.upsert_opportunity(conn, opp, h, src_id)
                new += action == "new"
                changed += action == "changed"
            writer.drain()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed)
        except Exception as exc:
            conn.rollback()
            db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                          status="failed", error=str(exc))
            raise
    log.info("%s done: %s fetched, %s new, %s changed", code, fetched, new, changed)


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
    if code not in HISTORY_SOURCES:
        raise ValueError(f"no historical load defined for {code!r}")
    return HISTORY_SOURCES[code]


def run_history(source_code: str, start: date, end: date, *, resume: bool = True,
                max_days: int | None = None) -> int:
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
    """
    fetch_day, mapper = _history_source(source_code)
    cfg = settings()
    store = build_store()
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    loaded = 0
    with db.connect(cfg.dsn) as conn:
        src_id = db.source_id(conn, source_code)
        done = db.backfill_days_done(conn, source_code) if resume else set()
        pending = [day for day in days if day not in done]
        log.info("%s history: %s days to load, %s already done",
                 source_code, len(pending), len(days) - len(pending))
        for day in pending:
            if max_days is not None and loaded >= max_days:
                break
            fetched = new = 0
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
                        h = ted.content_hash(clean)
                        try:
                            opp = mapper(clean)
                        except ValueError as exc:
                            log.warning("skipping malformed notice: %s", exc)
                            continue
                        db.record_raw(conn, src_id, opp.native_id, h,
                                      rawstore.record_key(key, line))
                        opp = _finalise(conn, opp, src_id)
                        if not opp.is_defence:
                            continue
                        _, action = db.upsert_opportunity(conn, opp, h, src_id)
                        new += action == "new"
                    conn.commit()
            except Exception:
                # Same rule as the daily runs: roll the uncommitted index rows
                # back rather than record keys whose payloads never landed. The
                # day stays unmarked, so resuming asks for it again, and the
                # bundle it rewrites is byte-for-byte the same object.
                conn.rollback()
                raise
            db.mark_backfill_day(conn, source_code, day, fetched)
            loaded += 1
            log.info("%s history %s: %s notices, %s defence", source_code, day, fetched, new)
    return loaded


def run_ted_history(start: date, end: date, *, resume: bool = True,
                    max_days: int | None = None) -> int:
    return run_history("ted", start, end, resume=resume, max_days=max_days)


def _in_chunks(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    """Group a stream into lists of at most `size`, yielding at least one."""
    chunk: list[Any] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    yield chunk      # the last, possibly empty: an empty day is still a day


def run_ezamowienia(days: int = 2) -> None:
    """Daily incremental pull of the Polish bulletin.

    Same ordering rule as every other source: land the raw record, normalise,
    classify, archive. The connector already narrows to defence angles, so most
    of what arrives here survives classification; the rest is dropped exactly as
    it is for TED.
    """
    code = ezamowienia.SOURCE_CODE
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        fetched = new = changed = 0
        try:
            for record in ezamowienia.fetch_window(days_back=days):
                fetched += 1
                _checkpoint(conn, code, fetched, new, changed, every=100,
                            writer=writer, run_id=run_id)
                clean = strip_personal_data(record)
                h = ted.content_hash(clean)
                try:
                    opp = from_ezamowienia(clean)
                except ValueError as exc:
                    log.warning("skipping malformed notice: %s", exc)
                    continue
                key = _store_raw(code, opp.native_id, clean, writer, content_hash=h)
                db.record_raw(conn, src_id, opp.native_id, h, key)
                opp = _finalise(conn, opp, src_id)
                if not opp.is_defence:
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
    log.info("%s done: %s fetched, %s new, %s changed", code, fetched, new, changed)


def _ingest_placsp(opps: Iterable[Opportunity], label: str,
                   dataset: placsp.Dataset = placsp.MAIN,
                   stale_reason=None) -> None:
    """Ingest one PLACSP stream. `stale_reason()`, if given, is asked once the
    stream is exhausted; a non-empty answer records the run as partial."""
    code = dataset.source_code
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BundleWriter(build_store(), code) as writer):
        src_id = db.source_id(conn, code)
        run_id = db.start_run(conn, code, settings().floor(code))
        fetched = new = changed = 0
        try:
            for opp in opps:
                fetched += 1
                _checkpoint(conn, label, fetched, new, changed, writer=writer,
                            run_id=run_id)
                payload = db.opportunity_payload(opp)
                h = ted.content_hash(payload)
                key = _store_raw(code, opp.native_id, payload, writer, content_hash=h)
                db.record_raw(conn, src_id, opp.native_id, h, key,
                              content_type="application/atom+xml")
                opp = _finalise(conn, opp, src_id)
                if not opp.is_defence:
                    continue
                _, action = db.upsert_opportunity(conn, opp, h, src_id)
                new += action == "new"
                changed += action == "changed"
            writer.drain()
            stale = stale_reason() if stale_reason else None
            if stale:
                db.finish_run(conn, run_id, fetched=fetched, new=new, changed=changed,
                              status="partial", error=stale)
            else:
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
    log.info("%s done: %s fetched, %s new, %s changed", label, fetched, new, changed)


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
    """
    cfg = settings()
    now = now or datetime.now(timezone.utc)
    limit = timedelta(hours=cfg.placsp_stale_hours)
    for ds in (datasets or (placsp.MAIN, placsp.AGGREGATED)):
        seen: dict = {}

        def staleness(seen=seen) -> str | None:
            newest = seen.get("newest")
            if newest is not None and now - newest <= limit:
                return None
            return (f"live feed stale: newest entry {newest.isoformat() if newest else 'none'}, "
                    f"older than {cfg.placsp_stale_hours}h")

        _ingest_placsp(placsp.fetch_live(ds, max_pages=max_pages, observe=seen),
                       f"{ds.source_code}-live", ds, stale_reason=staleness)
        reason = staleness()
        if not reason:
            continue

        from .ops.notify import notify

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


def run_atlas_backfill(year: int, *, path: Path | None = None,
                       limit: int | None = None, resume: bool = True,
                       workers: int | None = None) -> None:
    """One-off historical load of the Polish bulletin from Atlas Przetargow.

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
        seen = already_ingested(conn, code) if resume else set()
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
                if native_id in seen:
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
                opp = _finalise(conn, opp, src_id)
                if not opp.is_defence:
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
    if limit is None:
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
                    ORDER BY id LIMIT 1""",
                (country, norm),
            ).fetchone()
            if row:
                org_id = row["id"]
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
    log.info("seeded %s defence buyers", len(groups))
    return len(groups)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(prog="dgate")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("ted", help="ingest TED defence notices")
    t.add_argument("--days", type=int, default=2)

    s = sub.add_parser("placsp", help="ingest Spanish PLACSP")
    s.add_argument("--live", action="store_true")
    s.add_argument("--pages", type=int, default=20)
    s.add_argument("--backfill", nargs=2, type=int, metavar=("START", "END"))

    e = sub.add_parser("ezamowienia", help="ingest the Polish bulletin (BZP)")
    e.add_argument("--days", type=int, default=2)

    f = sub.add_parser("boamp", help="ingest the French bulletin (BOAMP)")
    f.add_argument("--days", type=int, default=2)

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

    h = sub.add_parser("history",
                       help="one-off historical load of every notice of a source")
    h.add_argument("--source", default="ted", help="ted or fr_boamp")
    h.add_argument("--from", dest="start", type=date.fromisoformat, required=True,
                   help="first publication day, YYYY-MM-DD (the API starts at 2017)")
    h.add_argument("--to", dest="end", type=date.fromisoformat, default=None,
                   help="last publication day; defaults to yesterday")
    h.add_argument("--max-days", type=int, default=None,
                   help="stop after this many days; for a rehearsal")
    h.add_argument("--no-resume", action="store_true",
                   help="reload days already marked done")

    sub.add_parser("seed-buyers", help="seed the defence buyer list")

    a = p.parse_args(argv)
    if a.cmd == "ted":
        run_ted(days=a.days)
    elif a.cmd == "placsp":
        if a.backfill:
            run_placsp_backfill(*a.backfill)
        else:
            run_placsp_live(max_pages=a.pages)
    elif a.cmd == "ezamowienia":
        run_ezamowienia(days=a.days)
    elif a.cmd == "boamp":
        run_boamp(days=a.days)
    elif a.cmd == "atlas-pl":
        run_atlas_backfill(a.year, path=a.file, limit=a.limit,
                           resume=not a.no_resume)
    elif a.cmd == "history":
        run_history(a.source, a.start, a.end or date.today() - timedelta(days=1),
                    resume=not a.no_resume, max_days=a.max_days)
    elif a.cmd == "seed-buyers":
        seed_buyers()
    return 0


if __name__ == "__main__":
    sys.exit(main())
