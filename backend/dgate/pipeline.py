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
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import db
from .classify import classify, detects_subcontracting
from .config import settings
from .normalise import Opportunity, from_atlas_pl, from_ezamowienia, from_ted, strip_personal_data
from .rawstore import BufferedWriter, build_store, storage_key
from .sources import ezamowienia, placsp, ted

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
          BufferedWriter(build_store(), cfg.raw_write_workers) as writer):
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
          BufferedWriter(build_store(), cfg.raw_write_workers) as writer):
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
                   dataset: placsp.Dataset = placsp.MAIN) -> None:
    code = dataset.source_code
    cfg = settings()
    with (db.connect(cfg.dsn) as conn,
          BufferedWriter(build_store(), cfg.raw_write_workers) as writer):
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


def run_placsp_live(max_pages: int = 20, datasets: Iterable[placsp.Dataset] = ()) -> None:
    """Daily incremental for both PLACSP datasets.

    Dataset 2 carries the autonomous communities, which reach PLACSP through
    aggregation. Running only dataset 1 loses every regional buyer without any
    error being raised, so both run by default and each has its own floor.
    """
    for ds in (datasets or (placsp.MAIN, placsp.AGGREGATED)):
        _ingest_placsp(placsp.fetch_live(ds, max_pages=max_pages),
                       f"{ds.source_code}-live", ds)


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
    elif a.cmd == "atlas-pl":
        run_atlas_backfill(a.year, path=a.file, limit=a.limit,
                           resume=not a.no_resume)
    elif a.cmd == "seed-buyers":
        seed_buyers()
    return 0


if __name__ == "__main__":
    sys.exit(main())
