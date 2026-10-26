"""Scheduled ingestion worker.

One process, a handful of jobs, no queue infrastructure. Every job is
idempotent and re-runnable, and every job reports whether it actually
collected anything.

The important part is not the scheduler, it is `run_job`: a job is only a
success if it finished *and* every source it touched reported `success`. A run
that finished below its coverage floor is `partial`, and partial is an alert,
not a green tick. That distinction is the whole reason this file exists.

    python -m dgate.worker                 run on schedule, forever
    python -m dgate.worker --once ted      run one job now and exit
    python -m dgate.worker --list          show the schedule
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence

from . import db
from .awards import refresh_award_twins, run_awards
from .config import settings
from .ops.notify import notify, ping
from .pipeline import (
    run_aid,
    run_bdns,
    run_boamp,
    run_de_bkms,
    run_eu_portal,
    run_ezamowienia,
    run_matine,
    run_ncbr,
    run_placsp_live,
    run_ted,
    run_tenderned,
    run_topic_details,
    run_vinnova,
    seed_buyers,
)

log = logging.getLogger("worker")


@dataclass
class JobResult:
    name: str
    status: str            # success | partial | failed
    seconds: float
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "success"


def source_run_status(codes: Sequence[str]) -> list[tuple[str, str, int, str]]:
    """Latest ingest_run per source: (code, status, records_fetched, error)."""
    out: list[tuple[str, str, int, str]] = []
    with db.connect(settings().dsn) as conn:
        for code in codes:
            row = conn.execute(
                """SELECT r.status, r.records_fetched, coalesce(r.error_message, '') err
                     FROM ingest_run r JOIN source s ON s.id = r.source_id
                    WHERE s.code = %s
                    ORDER BY r.started_at DESC LIMIT 1""",
                (code,),
            ).fetchone()
            if row is None:
                out.append((code, "missing", 0, "no run recorded"))
            else:
                out.append((code, row["status"], row["records_fetched"] or 0, row["err"]))
    return out


_RUNNING: set[str] = set()
_RUNNING_LOCK = threading.Lock()


def record_start(name: str) -> int | None:
    """WP-114: a `job_run` row for a job that starts (migration 0126), its id; None when it could not be written. The
    history used to be the container log only, which a redeploy erases. Never fails the job."""
    if not settings().job_runs:
        return None
    try:
        with db.connect(settings().dsn) as conn:
            return conn.execute("INSERT INTO job_run (job, owner) VALUES (%s, %s) RETURNING id",
                                (name, db.RUN_KIND)).fetchone()["id"]
    except Exception as exc:  # noqa: BLE001 - a record is a record, not the job
        log.warning("job %s: run not recorded: %s", name, type(exc).__name__)
        return None


def record_finish(run_id: int | None, status: str, detail: str = "") -> None:
    if run_id is None:
        return
    try:
        with db.connect(settings().dsn) as conn:
            conn.execute("UPDATE job_run SET finished_at = clock_timestamp(), status = %s, detail = %s WHERE id = %s",
                         (status, detail[:2000] or None, run_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("job run %s: end not recorded: %s", run_id, type(exc).__name__)


def run_job(name: str, fn: Callable[[], None], *, sources: Sequence[str] = ()) -> JobResult:
    """Run one job, decide honestly whether it worked, and be loud if not.

    Three outcomes, and only the first is a green tick:
      success  the callable returned and every source reported success
      partial  the callable returned but a source came in under its floor,
               or recorded no run at all
      failed   the callable raised
    """
    slug = name.replace("_", "-")
    with _RUNNING_LOCK:
        busy = name in _RUNNING
        _RUNNING.add(name)
    if busy:
        # The catch-up runs beside the scheduler (internal audit M8): a slot that fires
        # while the catch-up is still on the same job must not start it twice.
        log.warning("job %s is already running in this process; this start is skipped", name)
        return JobResult(name, "success", 0.0, "already running")
    return _run_job(name, fn, slug, sources, record_start(name))


def _run_job(name: str, fn: Callable[[], None], slug: str, sources: Sequence[str], run_id: int | None) -> JobResult:
    started = time.monotonic()
    ping(slug, "start")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - a job must not kill the scheduler
        elapsed = time.monotonic() - started
        log.exception("job %s failed", name)
        ping(slug, "fail")
        notify(f"[dgate] job {name} FAILED after {elapsed:.0f}s: {exc}")
        record_finish(run_id, "failed", str(exc))
        return JobResult(name, "failed", elapsed, str(exc))
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(name)

    elapsed = time.monotonic() - started
    bad: list[str] = []
    if sources:
        try:
            for code, status, fetched, err in source_run_status(sources):
                if status != "success":
                    bad.append(f"{code}: {status} ({fetched} records) {err}".strip())
        except Exception as exc:  # noqa: BLE001
            bad.append(f"could not read ingest_run: {exc}")

    if bad:
        detail = "; ".join(bad)
        ping(slug, "fail")
        notify(f"[dgate] job {name} finished but coverage is degraded: {detail}")
        record_finish(run_id, "partial", detail)
        return JobResult(name, "partial", elapsed, detail)

    ping(slug, "success")
    log.info("job %s succeeded in %.0fs", name, elapsed)
    record_finish(run_id, "success")
    return JobResult(name, "success", elapsed)


# ----------------------------------------------------------------- jobs

def job_ted(days: int | None = None) -> JobResult:
    window = days or settings().ingest_days
    return run_job("ted_daily", lambda: run_ted(days=window), sources=["ted"])


def job_placsp(days: int | None = None) -> JobResult:
    # PLACSP has no date window: the feed is a chain walked backwards, so a
    # wider catch-up means walking further back rather than asking for more days.
    pages = settings().placsp_pages
    if days:
        pages = min(pages * days, settings().placsp_max_pages)
    return run_job("placsp_daily", lambda: run_placsp_live(max_pages=pages),
                   sources=["es_placsp", "es_placsp_agg"])


def job_ezamowienia(days: int | None = None) -> JobResult:
    window = days or settings().ingest_days
    return run_job("ezamowienia_daily", lambda: run_ezamowienia(days=window),
                   sources=[ezam_source()])


def job_boamp(days: int | None = None) -> JobResult:
    window = days or settings().ingest_days
    return run_job("boamp_daily", lambda: run_boamp(days=window), sources=["fr_boamp"])


def job_tenderned(days: int | None = None) -> JobResult:
    window = days or settings().ingest_days
    return run_job("tenderned_daily", lambda: run_tenderned(days=window, reread=True),
                   sources=["nl_tenderned"])


def job_de_bkms(days: int | None = None) -> JobResult:
    """The German notice service. Does nothing, and records no run, while the source is
    inactive: the licence is not verified (migration 0050), so the schedule stays off.
    A manual load is `pipeline de-bkms --force`."""
    from .pipeline import source_is_active

    with db.connect(settings().dsn) as conn:
        if not source_is_active(conn, "de_bkms"):
            return JobResult("de_bkms_daily", "success", 0.0, "source inactive; not run")
    window = days or settings().ingest_days
    return run_job("de_bkms_daily", lambda: run_de_bkms(days=window), sources=["de_bkms"])


def job_matine(days: int | None = None) -> JobResult:
    """Finland's defence ministry research call. `days` is accepted and ignored."""
    return run_job("matine_daily", run_matine, sources=["fi_matine"])


def job_aid(days: int | None = None) -> JobResult:
    """France's defence innovation agency. `days` is accepted and ignored: both lists
    are read whole."""
    return run_job("aid_daily", run_aid, sources=["fr_aid"])


def job_vinnova(days: int | None = None) -> JobResult:
    """Sweden's agency. `days` is accepted and ignored: the whole register is fetched."""
    return run_job("vinnova_daily", run_vinnova, sources=["se_vinnova"])


def job_eu_portal(days: int | None = None) -> JobResult:
    """The grant calendar.

    `days` is accepted and ignored. The catch-up hands every daily job the
    number of days it has to reach back over, and this source has nothing to
    reach back over: the portal republishes the whole in-scope population every
    night, so one run covers any gap. Accepting the argument is not politeness
    -- a job that refuses it raises TypeError inside the catch-up and takes the
    worker's start-up down with it, which is exactly what happened here on
    24 September 2026, the first start after this job existed.
    """
    return run_job("eu_portal_daily", run_eu_portal, sources=["eu_portal"])


def job_bdns(days: int | None = None) -> JobResult:
    """The Spanish subsidy calls. The window is at least a fortnight whatever the
    catch-up asks for: registrations are scanned in full and the cost of a wider
    window is a few pages of search, while a narrower one would miss a call that
    was registered late."""
    window = max(days or 0, 14)
    return run_job("bdns_daily", lambda: run_bdns(days=window), sources=["es_bdns"])


def job_ncbr(days: int | None = None) -> JobResult:
    """The Polish competitions. `days` is accepted and ignored: the API returns the whole
    list every time, so one run covers any gap -- and a job that refuses the argument the
    catch-up passes takes the worker's start-up down with it."""
    return run_job("ncbr_daily", run_ncbr, sources=["pl_ncbr"])


def job_eu_topics() -> JobResult:
    """The topic pages behind the calls.

    Scheduled, but deliberately not in `daily_jobs()` and so not in the
    catch-up: the step reads whatever lacks details, so a night it did not run
    is covered by the next one without anyone computing a window. Adding it to
    the catch-up would also measure it against `eu_portal`'s last success, which
    the calendar job has already written -- it would look fresh whatever it did.
    """
    return run_job("eu_topics_daily", run_topic_details, sources=["eu_portal"])


def job_cordis() -> JobResult:
    """Monthly: the CORDIS projects, organisations and participations (networks.run_cordis, WP-26).
    The service republishes the whole population; one pass reads it and a second one changes
    nothing. About half an hour, one request every second or slower."""
    from . import networks

    return run_job("cordis_monthly", networks.run_cordis, sources=["cordis"])


def job_edf() -> JobResult:
    """Monthly: the EDF project factsheets (networks.run_edf). Every PDF is fetched and hashed
    (one request a second); the model is asked only about a file it has not read in this form."""
    from . import networks

    return run_job("edf_monthly", networks.run_edf, sources=["edf_factsheets"])


def placsp_awards_catchup(today: date | None = None) -> None:
    """The previous month's PLACSP archive, walked once for its award results and notices (WP-61): what the
    nightly walk missed (a frozen feed, a night the worker was down). The archive command's own rules apply:
    resumable, a month done is never read again, a 429 or a disk under 3 GiB stops it, never inside the
    live walk's window. A stopped or failed month raises, so the job is not green."""
    from .ops import placsp_archives
    from .sources import placsp

    today = today or _now().date()
    prev = today.replace(day=1) - timedelta(days=1)
    todo = placsp_archives.units((prev.year, prev.month), (prev.year, prev.month), placsp.MAIN, today)
    if prev.year < today.year:
        # In January the December entries are in the annual archive only. Walked from 1 December and marked as
        # December: the annual unit's own mark (1 January) is January's, done long ago, and would skip it.
        # ponytail: a 2 GB download once a year for one month; a December monthly URL, if the publisher keeps one.
        todo = [placsp_archives.Unit(f"{placsp.MAIN.source_code}-{prev.year}12", todo[0].url, date(prev.year, 12, 1),
                                     datetime(prev.year, 12, 1, tzinfo=timezone.utc), prev.year, 12, todo[0].size)]
    got = placsp_archives.run(todo, placsp.MAIN, floor=3 * 2**30, resume=True, pause=1.0)
    if got["failed"] or got["stopped"]:
        raise RuntimeError(f"PLACSP award catch-up did not finish: {got}")


def job_ted_awards() -> JobResult:
    """WP-103: the winners of the TED result notices not read yet (core scope and VEAT, `awards.candidates`), at most
    `ted_awards_limit` a run; `run_awards` records its `ingest_run` (floor: every notice asked is returned) and renews
    the award twins and the supplier value orders, as the CLI does."""
    return run_job("ted_awards_daily", lambda: run_awards(limit=settings().ted_awards_limit), sources=["ted_awards"])


def job_placsp_awards_catchup() -> JobResult:
    """Monthly, on the 3rd at 12:00 UTC, only with DGATE_PLACSP_AWARDS_CATCHUP=true (see `placsp_awards_catchup`)."""
    return run_job("placsp_awards_monthly", placsp_awards_catchup)


def job_consortium_snapshot() -> JobResult:
    """Monthly, after the two above: one snapshot per project whose consortium changed and the
    consortium.changed row for each difference (networks.snapshot_consortia)."""
    from . import networks

    return run_job("consortium_snapshot", networks.run_snapshot)


def job_seed_buyers() -> JobResult:
    return run_job("seed_buyers", seed_buyers)


def job_backup() -> JobResult:
    """Nightly dump, shipped off the host, pruned to the retention window.

    A dump is not the primary safety net; the raw payload store is, because the
    database is derived from it. What a dump adds is speed, and the observation
    timeline, which a replay cannot reconstruct: it can rebuild what a notice
    said, never when we first saw it say so.

    It is shipped because until 16 September 2026 the dumps sat on the same
    disk as the database they protected, which makes them a copy, not a backup.
    Shipping is part of the job rather than a job of its own so that a dump that
    never left the host fails the night it happens, loudly.
    """
    def _run() -> None:
        from .ops.backup import create, prune, prune_offsite, ship

        cfg = settings()
        result = create()
        removed = prune(cfg.backup_keep_days_local)
        key = ship(result)
        removed_offsite = prune_offsite(cfg.backup_keep_days)
        log.info("backup %s (%.1f MB) shipped to %s; pruned %s local (keep %sd) "
                 "and %s shipped (keep %sd)", result.path.name, result.megabytes, key,
                 len(removed), cfg.backup_keep_days_local,
                 len(removed_offsite), cfg.backup_keep_days)

    return run_job("backup_nightly", _run)


def job_backup_verify() -> JobResult:
    """Restore the newest dump into a scratch database and count what arrived.

    An unverified backup is a belief. This is the job that turns it into a fact,
    and it is the one whose failure should worry an operator most.
    """
    def _run() -> None:
        import tempfile
        from pathlib import Path

        from .ops.backup import fetch_offsite, verify

        # Verify the shipped copy, not the local one. They are the same bytes
        # right up until the day they are not, and the shipped copy is the one
        # a disaster would reach for: checking the other proves nothing about
        # it. Fetched to a temporary directory so the check cannot quietly
        # become the thing that fills the disk.
        with tempfile.TemporaryDirectory(prefix="dgate-verify-") as tmp:
            shipped = fetch_offsite(Path(tmp))
            log.info("verifying the shipped copy %s (%.1f MB)",
                     shipped.path.name, shipped.megabytes)
            counts = verify(shipped)
        if "opportunity_version" in counts:
            # A full restore ran (a machine that holds the private key).
            if not counts["opportunity_version"]:
                raise RuntimeError(f"restored database has no archive rows: {counts}")
        elif not (counts.get("manifest") == 1 and counts.get("frames")):
            raise RuntimeError(f"shipped backup failed its integrity check: {counts}")
        else:
            # The host cannot decrypt (the private key is not here, by design): what
            # was proved is the manifest hash and the structure of every frame. The
            # restore drill is run from the owner's machine; see docs/RUNBOOK.md.
            log.warning("backup structure verified, not restored (no private key here): %s",
                        counts)
        log.info("backup verified: %s", counts)
        # Only a restore that produced archive rows counts. Recorded so a
        # machine that is off on Sunday nights still gets its weekly check.
        from .ops.backup import backup_dir

        (backup_dir() / VERIFIED_MARKER).write_text(_now().isoformat(), encoding="utf-8")

    return run_job("backup_verify", _run)


def job_health_report() -> JobResult:
    """Daily coverage summary. Reports degradation even when nothing crashed."""
    def _report() -> None:
        rows = source_run_status(list(settings().floors))
        lines = [f"{code}: {status}, {fetched} records {err}".rstrip()
                 for code, status, fetched, err in rows]
        unhealthy = [r for r in rows if r[1] != "success"]
        text = "[dgate] daily coverage\n" + "\n".join(lines)
        if unhealthy:
            notify(text)
        else:
            log.info(text)

    return run_job("health_report", _report)


def job_alerts() -> JobResult:
    """Mail each account what is new for its saved searches. A no-op without a mail relay."""
    from .ops.digest import run_digests

    def _run() -> None:
        with db.connect(settings().dsn) as conn:
            log.info("alerts: %s", run_digests(conn))

    return run_job("alerts", _run)


def job_link_twins() -> JobResult:
    """Tie national notices to the TED notice they are the same procurement as.

    Nothing in an ingest does it (data-coverage X3, 14 October 2026): rows read after the
    last manual run stayed unlinked, so the same procurement was listed twice. Idempotent,
    strongest method first (stated TED number, procedure identifier, heuristic), each
    committed before the next. The identifier fill steps are not here: new BOAMP and PLACSP
    rows state their procedure identifier at ingest, and the fill is for the rows read before
    that (`ops/link_twins --fill-raw`, `--fill-placsp`, which also asks the publisher).
    A PLACSP notice without a procedure identifier stays on the heuristic.
    """
    counts: dict[str, int] = {}

    def _run() -> None:
        from .ops import link_twins

        with db.connect(settings().dsn) as conn:
            counts.update(link_twins.run(conn, write=True))
            # A new twin link can make two award rows one award: the supplier map's pairs (migration 0098).
            counts["award_twin_pairs"] = refresh_award_twins(conn)
            conn.commit()
        # The health line: what the pass did. A night with nothing new says 0 0 0.
        log.info("twin links: %s", ", ".join(f"{k} {v}" for k, v in counts.items()))

    result = run_job("link_twins", _run)
    result.detail = result.detail or ", ".join(f"{k} {v}" for k, v in counts.items())
    return result


def job_buyer_families() -> JobResult:
    """Daily: bring the buyer families up to date (ops/buyer_families.py, WP-22), so that
    a new name variant of a body joins its family the next day. Display layer only: no
    organisation, alias or notice is changed. Idempotent."""
    counts: dict[str, int] = {}

    def _run() -> None:
        from .ops import buyer_families, company_groups

        with db.connect(settings().dsn) as conn:
            counts.update(buyer_families.run(conn, write=True))
            # WP-96: the curated company groups too (display layer, idempotent): a new winner of a listed name joins
            counts["company_group_members"] = company_groups.run(conn, write=True, out=log.debug)["members"]
        log.info("buyer families: %s", ", ".join(f"{k} {v}" for k, v in counts.items()))

    result = run_job("buyer_families", _run)
    result.detail = result.detail or ", ".join(f"{k} {v}" for k, v in counts.items())
    return result


def job_warm_lists() -> JobResult:
    """Every four hours: pre-compute the slow tender views (closed and all, every country, the
    first pages, and the scope counts) into `list_snapshot` (ops/warm_lists.py), and the match sets of the frequent
    search words (WP-142, `search_match_set`). The API reads
    a row by key before it runs the query. About ten minutes of one core; derived data only."""
    counts: dict[str, int] = {}

    def _run() -> None:
        from .ops import warm_lists

        with db.connect(settings().dsn) as conn:
            # The supplier map's twin pairs (migration 0098), also after merges since the last award load.
            counts["award_twin_pairs"] = refresh_award_twins(conn)
            conn.commit()
            counts.update(warm_lists.run(conn, write=True))
        log.info("warm lists: %s", ", ".join(f"{k} {v}" for k, v in counts.items()))
        if counts.get("failed"):
            raise RuntimeError(f"{counts['failed']} views failed")

    result = run_job("warm_lists", _run)
    result.detail = result.detail or ", ".join(f"{k} {v}" for k, v in counts.items())
    return result


def job_cascade_flags() -> JobResult:
    """Daily: set `call.cascade` (financial support to third parties) from the call text and the
    eligibility facts already read (cascade.py, WP-31). No model, no website; idempotent."""
    counts: dict[str, int] = {}

    def _run() -> None:
        from . import cascade, ukraine, who_apply

        with db.connect(settings().dsn) as conn:
            counts.update(cascade.run(conn, write=True))
            # WP-36: the "open to Ukraine" flag is derived from the same facts, in the same pass.
            counts.update({f"ukraine_{k}": v for k, v in ukraine.run(conn, write=True).items() if k != "calls"})
            # WP-92: who may apply, from the call's own facts first (the list badge), same pass.
            counts.update({f"who_{k}": v for k, v in who_apply.run(conn, write=True).items() if k != "calls"})
        log.info("cascade flags: %s", ", ".join(f"{k} {v}" for k, v in counts.items()))

    result = run_job("cascade_flags", _run)
    result.detail = result.detail or ", ".join(f"{k} {v}" for k, v in counts.items())
    return result


def job_digest() -> JobResult:
    """Daily: store the weekly digest issues (weekly_digest.py, WP-31): the last two complete weeks
    again and any week still missing, at most eight a run. The pages read the stored row."""
    counts: dict[str, int] = {}

    def _run() -> None:
        from . import weekly_digest

        with db.connect(settings().dsn) as conn:
            counts.update(weekly_digest.refresh(conn))
        log.info("digest: %s", ", ".join(f"{k} {v}" for k, v in counts.items()))

    result = run_job("digest", _run)
    result.detail = result.detail or ", ".join(f"{k} {v}" for k, v in counts.items())
    return result


def job_requalify() -> JobResult:
    """Weekly: insert the notices the classifier dropped at ingest and the rules now qualify.

    Classification is final at ingest and the buyer lists grow afterwards, so a notice of
    a body listed later was landed and not kept (data-coverage X1/X2: 55 of 59 French
    defence-body notices absent). Only TED had a requalify; this runs the same normaliser and
    `_finalise` over every source whose payloads are in the store, day by day, for the last
    `requalify_days`, resumably (`reprocess.requalify_recent`).
    """
    summary: list[str] = []

    def _run() -> None:
        from . import reprocess

        cfg = settings()
        totals = reprocess.requalify_recent(days=cfg.requalify_days)
        unreadable = 0
        for source, counts in totals.items():
            summary.append(f"{source} {counts.get('inserted', 0)}/{counts.get('candidates', 0)}")
            unreadable += counts.get("unreadable", 0)
        log.info("requalify (inserted/candidates): %s", ", ".join(summary))
        if unreadable:
            raise RuntimeError(f"{unreadable} stored payloads could not be read or mapped: "
                               + ", ".join(summary))

    result = run_job("requalify_weekly", _run)
    result.detail = result.detail or ", ".join(summary)
    return result


def job_controls() -> JobResult:
    """Daily: the controls that are not part of a run (ops/controls.py).

    PLACSP has no portal counter, so its two measures are taken from the stored rows; the
    Atlas record on Zenodo is looked at once a week. An alert is announced once, and again
    only after `ALERT_EVERY_HOURS`. Not run_job: a control that finds something is a
    finding, not a failed job.
    """
    from .ops import controls

    started = time.monotonic()
    run_id = record_start("controls")
    result = _controls(controls, started)
    record_finish(run_id, result.status, result.detail)
    return result


def _controls(controls, started: float) -> JobResult:
    try:
        with db.connect(settings().dsn) as conn:
            done = [controls.check_placsp(conn)]
            try:
                atlas = controls.check_atlas(conn)
                if atlas:
                    done.append(atlas)
            except Exception as exc:  # noqa: BLE001 - Zenodo down is not an alert
                log.warning("atlas control could not read Zenodo: %s", type(exc).__name__)
            for row in controls.due_alerts(conn):
                notify(f"[dgate] control {row['control']}: {json.dumps(row['detail'], default=str)}")
        detail = ", ".join(f"{d['control']} {d['status']}" for d in done)
        return JobResult("controls", "success", time.monotonic() - started, detail)
    except Exception as exc:  # noqa: BLE001 - a monitor must report, not crash the scheduler
        log.exception("controls failed")
        notify(f"[dgate] controls could not run: {type(exc).__name__}")
        return JobResult("controls", "failed", time.monotonic() - started, str(exc))


def ezam_source() -> str:
    from .sources.ezamowienia import SOURCE_CODE

    return SOURCE_CODE


# --------------------------------------------------------------- catch-up

def daily_jobs() -> dict[str, tuple[Callable[..., JobResult], tuple[str, ...]]]:
    """Each daily ingest job with the sources it feeds, so a gap can be measured."""
    return {
        "ted_daily": (job_ted, ("ted",)),
        "placsp_daily": (job_placsp, ("es_placsp", "es_placsp_agg")),
        "ezamowienia_daily": (job_ezamowienia, (ezam_source(),)),
        "boamp_daily": (job_boamp, ("fr_boamp",)),
        "tenderned_daily": (job_tenderned, ("nl_tenderned",)),
        "de_bkms_daily": (job_de_bkms, ("de_bkms",)),
        "vinnova_daily": (job_vinnova, ("se_vinnova",)),
        "aid_daily": (job_aid, ("fr_aid",)),
        "matine_daily": (job_matine, ("fi_matine",)),
        "eu_portal_daily": (job_eu_portal, ("eu_portal",)),
        "bdns_daily": (job_bdns, ("es_bdns",)),
        "ncbr_daily": (job_ncbr, ("pl_ncbr",)),
    }


def hours_since_last_success(codes: Sequence[str]) -> float | None:
    """Age of the stalest source's last successful run.

    The job is only as fresh as its most behind source. This used to take the
    newest success across all of them, and on 14 September 2026 a successful
    run of PLACSP dataset 1 hid dataset 2 having failed on a DNS outage: the job
    looked current and was not re-run.

    None means some source here has never succeeded, which is its own kind of
    gap and is treated as one.
    """
    with db.connect(settings().dsn) as conn:
        rows = conn.execute(
            """SELECT s.code, max(r.finished_at) AS t
                 FROM source s LEFT JOIN ingest_run r
                   ON r.source_id = s.id AND r.status = 'success'
                WHERE s.code = ANY(%s)
                GROUP BY s.code""",
            (list(codes),),
        ).fetchall()
    finished = [r["t"] for r in rows]
    if len(finished) < len(set(codes)) or any(t is None for t in finished):
        return None
    return (datetime.now(timezone.utc) - min(finished)).total_seconds() / 3600


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hours_since_last_slot(name: str) -> float:
    """Hours since this job's most recent scheduled slot, today's or yesterday's."""
    cfg = settings()
    hour, minute = {
        "ted_daily": (cfg.ted_hour, cfg.ted_minute),
        "placsp_daily": (cfg.placsp_hour, cfg.placsp_minute),
        "ezamowienia_daily": (cfg.ezam_hour, cfg.ezam_minute),
        "boamp_daily": (cfg.boamp_hour, cfg.boamp_minute),
        "tenderned_daily": (cfg.tenderned_hour, cfg.tenderned_minute),
        "de_bkms_daily": (cfg.de_bkms_hour, cfg.de_bkms_minute),
        "vinnova_daily": (cfg.vinnova_hour, cfg.vinnova_minute),
        "aid_daily": (cfg.aid_hour, cfg.aid_minute),
        "matine_daily": (cfg.matine_hour, cfg.matine_minute),
        "eu_portal_daily": (cfg.eu_portal_hour, cfg.eu_portal_minute),
        "bdns_daily": (cfg.bdns_hour, cfg.bdns_minute),
        "ncbr_daily": (cfg.ncbr_hour, cfg.ncbr_minute),
        "backup_nightly": (cfg.backup_hour, 0),
    }[name]
    now = _now()
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if slot > now:
        slot -= timedelta(days=1)
    return (now - slot).total_seconds() / 3600


def hours_since_last_weekly_slot(weekday: int, hour: int, minute: int) -> float:
    """Hours since the most recent weekly slot (Monday = 0)."""
    now = _now()
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    slot -= timedelta(days=(now.weekday() - weekday) % 7)
    if slot > now:
        slot -= timedelta(days=7)
    return (now - slot).total_seconds() / 3600


VERIFIED_MARKER = "last-verified"


def _age_hours(when: datetime | None) -> float | None:
    return None if when is None else (_now() - when).total_seconds() / 3600


def last_backup_taken() -> datetime | None:
    from .ops.backup import listing

    dumps = listing()
    return dumps[-1].taken_at if dumps else None


def last_backup_verified() -> datetime | None:
    from .ops.backup import backup_dir

    marker = backup_dir() / VERIFIED_MARKER
    try:
        return datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def catch_up_backups() -> list[JobResult]:
    """Take the nightly dump, and run the weekly restore check, if their slots passed.

    The dump is scheduled at 02:00 UTC, which on a laptop is a time it is off.
    From 8 September to 15 September 2026 not one real dump was taken: the
    newest files were three 14 KB test dumps of an empty database, while the
    archive grew to 762 MB. The raw store can rebuild what the notices said, but
    not when each change was first observed -- that exists only in the database,
    so for a week it had no second copy. Catch-up covered ingestion and nothing
    else.

    Runs before the ingest catch-up, so the observation timeline is copied before
    hours of new writing, and costs a minute at the archive's current size.
    """
    cfg = settings()
    if not cfg.catch_up_on_start:
        return []
    results: list[JobResult] = []

    try:
        age = _age_hours(last_backup_taken())
    except Exception as exc:  # noqa: BLE001 - a start-up check must not block start-up
        log.warning("catch-up: cannot list backups: %s", exc)
        return results
    if age is None or age > hours_since_last_slot("backup_nightly"):
        log.warning("catch-up: newest dump %s, before its last slot; taking one now",
                    "missing" if age is None else f"{age:.0f}h old")
        results.append(job_backup())
    else:
        log.info("catch-up: newest dump %.0fh old, after its last slot", age)
        results.extend(catch_up_shipping())

    verified = _age_hours(last_backup_verified())
    weekly = hours_since_last_weekly_slot(6, cfg.backup_hour, 30)
    if verified is None or verified > weekly:
        log.warning("catch-up: last restore check %s; verifying the newest dump now",
                    "never recorded" if verified is None else f"{verified:.0f}h ago")
        results.append(job_backup_verify())
    return results


def catch_up_shipping() -> list[JobResult]:
    """Ship the newest dump if it is still only on this host.

    Its own step because the dump and the copy fail separately: object storage
    can be unreachable for an hour while pg_dump works perfectly, and the result
    is a dump that looks done and protects nothing.
    """
    from .ops.backup import newest, offsite_key, ship

    def _run() -> None:
        from .rawstore import build_store

        dump = newest()
        if dump is None:
            return
        store = build_store()
        if store.size(offsite_key(dump.path.name)) == dump.bytes:
            log.info("catch-up: newest dump is already in the store")
            return
        log.warning("catch-up: newest dump has not been shipped; shipping now")
        ship(dump, store)

    return [run_job("backup_ship", _run)]


BACKUP_ALERT_EVERY_HOURS = 6


def last_offsite_backup() -> datetime | None:
    from .ops.backup import offsite_listing

    shipped = offsite_listing()
    return shipped[-1][1] if shipped else None


def job_backup_freshness() -> JobResult:
    """Hourly: record how old the newest local and shipped dumps are, and say so when
    either is older than `backup_stale_hours`.

    Not run_job: a stale backup is not a failed job (the nightly job may have "succeeded"
    into the wrong place, or not run at all, which is exactly what no job-based alert can
    see). Found 14 October 2026: two nightly dumps failed, one alert each, then nothing
    for 47 hours. Repeats at most every BACKUP_ALERT_EVERY_HOURS, so a bad day is a few
    messages, not sixty.
    """
    started = time.monotonic()
    cfg = settings()
    limit = cfg.backup_stale_hours
    try:
        with db.connect(cfg.dsn) as conn:
            for kind, probe in (("local", last_backup_taken), ("offsite", last_offsite_backup)):
                try:
                    db.record_backup_seen(conn, kind, probe())
                except Exception as exc:  # noqa: BLE001 - an unreadable store is itself the finding
                    log.warning("backup freshness: cannot list %s dumps: %s", kind, type(exc).__name__)
                    conn.rollback()
                    db.record_backup_seen(conn, kind, None, probed=False)
            fresh = db.backup_freshness(conn, limit)
            if fresh["status"] != "stale":
                return JobResult("backup_freshness", "success", time.monotonic() - started,
                                 fresh["status"])
            due = conn.execute(
                "SELECT bool_and(alerted_at IS NULL OR alerted_at < now() - %s * interval '1 hour') AS due"
                " FROM backup_status", (BACKUP_ALERT_EVERY_HOURS,)).fetchone()["due"]
            detail = ", ".join(
                f"{kind} " + ("none found" if fresh[f"{kind}_age_hours"] is None
                              else f"{fresh[f'{kind}_age_hours']:.0f}h old")
                for kind in db.BACKUP_KINDS)
            if due:
                notify(f"[dgate] BACKUP STALE: newest dump {detail} (limit {limit}h). "
                       "Run `--once backup` and check the job log")
                conn.execute("UPDATE backup_status SET alerted_at = now()")
                conn.commit()
            return JobResult("backup_freshness", "failed", time.monotonic() - started, detail)
    except Exception as exc:  # noqa: BLE001 - a monitor must report, not crash the scheduler
        log.exception("backup freshness check failed")
        notify(f"[dgate] backup freshness check could not run: {type(exc).__name__}")
        return JobResult("backup_freshness", "failed", time.monotonic() - started, str(exc))


def ensure_requirements() -> None:
    """Apply the readiness content (`seeds/requirements.json`) on every start. It is idempotent, and
    this is what makes a deploy that changes a rule change the rule, with no separate step. A failure
    is reported and does not stop the worker: the previous rules stay in place."""
    from .readiness.seed import apply, load_file

    try:
        with db.connect(settings().dsn) as conn:
            counts = apply(conn, load_file())
        log.info("readiness content applied: %s", counts)
    except Exception as exc:  # noqa: BLE001 - loud, but must not block start-up
        log.error("could not apply the readiness content: %s", exc)
        notify(f"[dgate] readiness content not applied: {exc}; the previous rules stay in place")


def ensure_regulation() -> None:
    """Apply the regulatory tracker (`seeds/regulation_tracker.json`) on every start, as the readiness
    content is. Idempotent; a failure is reported and does not stop the worker."""
    from .regulation import apply, load_file

    try:
        with db.connect(settings().dsn) as conn:
            counts = apply(conn, load_file())
        log.info("regulatory tracker applied: %s", counts)
    except Exception as exc:  # noqa: BLE001 - loud, but must not block start-up
        log.error("could not apply the regulatory tracker: %s", exc)
        notify(f"[dgate] regulatory tracker not applied: {exc}; the previous entries stay in place")


def ensure_buyer_list() -> None:
    """Seed the defence buyer list before anything is classified.

    The list lives only in the database, so it is lost with it, and nothing in
    the raw store can bring it back. The database was rebuilt on 8 September
    and never reseeded; for five days the buyer signal -- which on its own
    qualifies a notice -- could not fire for any source. Measured afterwards on
    the Polish backfill alone, with just the two Polish entries on the list,
    310 notices from the Ministry of National Defence and the Armament Agency
    were not archived. Seeding is idempotent, so doing it on every start costs
    one query per listed buyer and closes that hole for good.
    """
    from .pipeline import seed_buyers

    try:
        seed_buyers()
    except Exception as exc:  # noqa: BLE001 - loud, but must not block start-up
        log.error("could not seed the defence buyer list: %s", exc)
        notify(f"[dgate] defence buyer list not seeded: {exc}; "
               "the buyer signal cannot fire until it is")


def pending_backfill_years() -> list[int]:
    """Configured Atlas years that have not been loaded completely yet."""
    from .pipeline import atlas_done_marker

    return [y for y in settings().atlas_backfill_years
            if not atlas_done_marker(y).exists()]


def job_atlas_backfill(attempts: int = 6, pause: float = 120.0) -> JobResult:
    """Finish whatever part of the Polish historical backfill is still missing.

    Run by the worker itself rather than by hand, because a hand-started run
    lives in a process that any container restart kills. On 13 September 2026
    that happened three times in one morning -- a reboot, a DNS outage, and the
    WSL virtual machine that Docker runs in restarting under it -- and each time
    the run stopped until someone noticed and started it again.

    Each year is retried in place after a failure, and every retry is cheap
    because the backfill skips what has already landed. Anything still
    unfinished when the process dies is picked up on the next start.
    """
    from .pipeline import run_atlas_backfill

    def _run() -> None:
        for year in pending_backfill_years():
            for attempt in range(1, attempts + 1):
                try:
                    run_atlas_backfill(year, workers=settings().atlas_write_workers)
                    break
                except Exception as exc:  # noqa: BLE001 - retried, then reported
                    if attempt == attempts:
                        raise
                    log.warning("atlas %s attempt %s of %s failed (%s); retrying in %.0fs",
                                year, attempt, attempts, exc, pause)
                    time.sleep(pause)

    return run_job("atlas_backfill", _run, sources=["pl_atlas"])


def ted_history_window() -> tuple[date, date] | None:
    """The configured span of the TED history load, or None if unset.

    Unset is the default on purpose: a load of seven million notices over
    several days is a decision, not something a container inherits by starting.
    """
    cfg = settings()
    if not cfg.ted_history_from:
        return None
    start = date.fromisoformat(cfg.ted_history_from)
    end = (date.fromisoformat(cfg.ted_history_to) if cfg.ted_history_to
           else _now().date() - timedelta(days=1))
    return (start, end) if start <= end else None


def job_ted_history(attempts: int = 8, pause: float = 120.0) -> JobResult:
    """Finish whatever part of the TED history is still missing.

    Owned by the worker for the same reason the Polish backfill is: a load
    measured in days cannot live in a shell someone has to keep open. Each
    attempt resumes from the day markers, so a retry costs the failed day and
    nothing else.
    """
    from .pipeline import run_ted_history

    window = ted_history_window()

    def _run() -> None:
        if window is None:
            return
        start, end = window
        for attempt in range(1, attempts + 1):
            try:
                loaded = run_ted_history(start, end)
                log.info("ted history: %s days loaded this pass", loaded)
                return
            except Exception as exc:  # noqa: BLE001 - retried, then reported
                if attempt == attempts:
                    raise
                log.warning("ted history attempt %s of %s failed (%s); retrying in %.0fs",
                            attempt, attempts, exc, pause)
                time.sleep(pause)

    return run_job("ted_history", _run)


def start_backfill_thread() -> list[threading.Thread]:
    """Resume unfinished history loads alongside, not before, the catch-up.

    Threads, so that three days of missed daily collection are not held up
    behind a decade of history, and the history is not held up behind them.
    """
    threads = []
    years = pending_backfill_years()
    if years:
        log.info("atlas backfill still to finish for %s; resuming in the background", years)
        threads.append(threading.Thread(target=job_atlas_backfill, name="atlas-backfill",
                                        daemon=True))
    window = ted_history_window()
    if window is not None:
        log.info("ted history configured for %s to %s; resuming in the background", *window)
        threads.append(threading.Thread(target=job_ted_history, name="ted-history",
                                        daemon=True))
    for thread in threads:
        thread.start()
    return threads


def wait_for_database(timeout: float = 180.0, interval: float = 3.0) -> bool:
    """Block until Postgres accepts a query, or give up after `timeout` seconds.

    Needed because start-up after a reboot is not start-up after `compose up`.
    `depends_on: service_healthy` is honoured only by compose; when the Docker
    daemon itself restarts containers on boot, it starts them all at once. On
    13 September 2026 the worker came up while Postgres was still replaying its
    log, every catch-up check failed with "the database system is starting up",
    each was logged as a warning, and the scheduler started having covered
    nothing -- after three days off, which is the exact case catch-up exists
    for. Waiting a few seconds would have been enough.
    """
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with db.connect(settings().dsn) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception as exc:  # noqa: BLE001 - any failure here means "not yet"
            last = exc
            time.sleep(interval)
    log.error("database still unavailable after %.0fs: %s", timeout, last)
    return False


def close_interrupted_runs() -> list[int]:
    """Fail the ingest runs a killed process of this kind left `running`.

    Safe only at start-up. A scheduled worker starting proves the previous scheduled
    worker is dead, so its runs are closed; a run an operator's container opened is not
    this process's to judge and is left until it is a day old (`db.close_interrupted_runs`,
    internal audit M7). Left alone, such a row makes its source look permanently degraded:
    coverage is read from the latest run per source, so every later alert for it becomes
    noise.
    """
    try:
        with db.connect(settings().dsn) as conn:
            closed = db.close_interrupted_runs(conn)
            if settings().job_runs:
                # WP-114: the jobs this kind of process left running are `interrupted` (a deploy recreated the worker)
                with conn.transaction():
                    cut = conn.execute("UPDATE job_run SET status = 'interrupted', finished_at = clock_timestamp() "
                                       "WHERE status = 'running' AND owner = %s RETURNING job, started_at",
                                       (db.RUN_KIND,)).fetchall()
                if cut:
                    # WP-139 (requalify_weekly cut at 13:24 after 1 h 24 min, next slot a week away): said, not silent;
                    # `catch_up_jobs` starts each of them again
                    notify("[dgate] a restart cut short: " + ", ".join(
                        f"{r['job']} (started {r['started_at']:%Y-%m-%d %H:%M} UTC)" for r in cut)
                        + "; the start-up catch-up runs them again")
            return closed
    except Exception as exc:  # noqa: BLE001 - a start-up tidy must not block start-up
        log.warning("could not close interrupted runs: %s", exc)
        return []


def catch_up() -> list[JobResult]:
    """Run any daily job whose sources have gone stale, before scheduling starts.

    A cron entry only fires while the process is alive. On a machine that is
    switched off overnight the missed slot is simply lost, and a day of the
    archive cannot be collected twice. So on every start the worker asks how
    long it has been since each source last succeeded, and covers the gap with
    a window wide enough to reach back over it.

    Deliberately not unbounded: a month-long gap is a decision for a person,
    not something to pull silently at start-up, so the window stops at
    `catch_up_max_days` and the shortfall stays visible in the log.
    """
    cfg = settings()
    if not cfg.catch_up_on_start:
        return []

    results: list[JobResult] = []
    for name, (job, codes) in daily_jobs().items():
        try:
            age = hours_since_last_success(codes)
        except Exception as exc:  # noqa: BLE001 - a start-up check must not block start-up
            log.warning("catch-up: cannot read ingest_run for %s: %s", name, exc)
            continue
        # Run when the job's scheduled slot has passed since it last succeeded.
        # This replaced a fixed "older than 20 hours" threshold, which on
        # 14 September 2026 let PLACSP through at 20h ago: its 06:30 slot had
        # been missed with the machine off, the next was a day away, and the
        # gap would have reached 44 hours before anyone noticed.
        if age is not None and age <= hours_since_last_slot(name):
            log.info("catch-up: %s succeeded %.0fh ago, after its last slot; "
                     "nothing to cover", name, age)
            continue
        gap_days = cfg.ingest_days if age is None else int(age // 24) + 1
        window = min(max(gap_days, cfg.ingest_days), cfg.catch_up_max_days)
        log.warning("catch-up: %s last succeeded %s, running now over %s days",
                    name, "never" if age is None else f"{age:.0f}h ago", window)
        results.append(job(days=window))
    return results


# WP-114: the scheduled jobs `catch_up_jobs` does not cover: the ingest jobs and the backups have catch-ups of their own
# (by the sources' last success, by the newest dump), the hourly ones run again within the hour, and the TED history is
# resumed by `start_backfill_thread`.
OWN_CATCH_UP = {"backup_nightly", "backup_verify", "backup_freshness", "alerts_hourly", "ted_history_daily"}
# A job that runs this seldom and has no record at all is not started by a restart: its first scheduled slot is kept
# (a monthly crawl of CORDIS or of the EDF factsheets is hours of requests to a public site, and a model budget).
UNRECORDED_MAX_PERIOD = timedelta(days=1)


def last_slot(trigger, now: datetime) -> tuple[datetime | None, timedelta | None]:
    """(the trigger's most recent fire time at or before `now`, the time between its last two fire times)."""
    t = now - timedelta(days=32)
    fires: list[datetime] = []
    while True:
        t = trigger.get_next_fire_time(fires[-1] if fires else None, t)
        if t is None or t > now:
            break
        fires.append(t)
        t = t + timedelta(seconds=1)
    if not fires:
        return None, None
    return fires[-1], (fires[-1] - fires[-2]) if len(fires) > 1 else None


def last_job_start(names: Sequence[str]) -> tuple[datetime | None, datetime | None]:
    """(when a job, under any of its `names`, last started and was not cut short by a restart; when it last started and
    was), by `job_run`. WP-139: a run a deploy interrupted is not a run of its slot (requalify_weekly, 25 Oct 2026: cut at
    13:24, and the catch-up took its 12:00 start for the slot's run, so the next was a week away)."""
    with db.connect(settings().dsn) as conn:
        row = conn.execute(
            """SELECT max(started_at) FILTER (WHERE status <> 'interrupted') AS t,
                      max(started_at) FILTER (WHERE status = 'interrupted') AS cut
                 FROM job_run WHERE job = ANY(%s)""", (list(names),)).fetchone()
    return (row["t"], row["cut"]) if row else (None, None)


def job_names(job_id: str) -> tuple[str, ...]:
    """The names a scheduled job's runs are recorded under: its run_job name is its id, or its id without `_daily`."""
    return (job_id, job_id.removesuffix("_daily"))


def catch_up_jobs(sched=None, now: datetime | None = None) -> list[JobResult]:
    """Every other scheduled job whose last slot passed since it last started (WP-114, coverage audit of 24 October
    2026: the worker recreated at 15:53 had skipped the 14:10 ted_awards slot, and digest, warm_lists and the rest
    are skipped the same way until their next slot). Run oldest slot first, so the order of a day is kept (the twins,
    then the buyer families, then the digest). A job with no record yet runs if it is daily or more often."""
    cfg = settings()
    if not cfg.catch_up_on_start or not cfg.job_runs:
        return []
    sched = sched or build_scheduler()
    now = now or _now()
    covered = OWN_CATCH_UP | set(daily_jobs())
    due: list[tuple[datetime, Callable[[], JobResult], str]] = []
    for job in sched.get_jobs():
        if job.id in covered:
            continue
        slot, period = last_slot(job.trigger, now)
        if slot is None:
            continue
        try:
            started, cut = last_job_start(job_names(job.id))
        except Exception as exc:  # noqa: BLE001 - a start-up check must not block start-up
            log.warning("catch-up: cannot read job_run for %s: %s", job.id, type(exc).__name__)
            continue
        if started is not None and started >= slot:
            continue
        if started is None and cut is None and (period is None or period > UNRECORDED_MAX_PERIOD):
            log.info("catch-up: %s has no recorded run; its next slot runs it", job.id)
            continue
        due.append((slot, job.func, job.id))
    results = []
    for slot, func, job_id in sorted(due, key=lambda d: d[0]):
        log.warning("catch-up: %s missed its slot of %s UTC, running now", job_id, f"{slot:%Y-%m-%d %H:%M}")
        results.append(func())
    return results


def job_catch_up() -> JobResult:
    """The catch-up as a single job, for `--once catch-up`."""
    wait_for_database()
    close_interrupted_runs()
    ensure_buyer_list()
    results = catch_up_backups() + catch_up() + catch_up_jobs()
    if not results:
        return JobResult("catch_up", "success", 0.0, "nothing was stale")
    worst = min(results, key=lambda r: ("failed", "partial", "success").index(r.status))
    detail = "; ".join(f"{r.name}={r.status}" for r in results)
    return JobResult("catch_up", worst.status, sum(r.seconds for r in results), detail)


JOBS: dict[str, Callable[[], JobResult]] = {
    "ted": job_ted,
    "ezamowienia": job_ezamowienia,
    "boamp": job_boamp,
    "tenderned": job_tenderned,
    "de-bkms": job_de_bkms,
    "vinnova": job_vinnova,
    "aid": job_aid,
    "matine": job_matine,
    "calls": job_eu_portal,
    "bdns": job_bdns,
    "ncbr": job_ncbr,
    "topics": job_eu_topics,
    "placsp": job_placsp,
    "seed-buyers": job_seed_buyers,
    "health": job_health_report,
    "alerts": job_alerts,
    "link-twins": job_link_twins,
    "buyer-families": job_buyer_families,
    "warm-lists": job_warm_lists,
    "cascade-flags": job_cascade_flags,
    "digest": job_digest,
    "cordis": job_cordis,
    "edf": job_edf,
    "consortium-snapshot": job_consortium_snapshot,
    "placsp-awards-catchup": job_placsp_awards_catchup,
    "ted-awards": job_ted_awards,
    "requalify": job_requalify,
    "backup": job_backup,
    "ted-history": job_ted_history,
    "backup-verify": job_backup_verify,
    "backup-freshness": job_backup_freshness,
    "controls": job_controls,
    "catch-up": job_catch_up,
    "atlas-backfill": job_atlas_backfill,
}


# ------------------------------------------------------------- scheduling

def build_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    cfg = settings()
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(job_ted, CronTrigger(hour=cfg.ted_hour, minute=cfg.ted_minute),
                  id="ted_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_placsp, CronTrigger(hour=cfg.placsp_hour, minute=cfg.placsp_minute),
                  id="placsp_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_ezamowienia, CronTrigger(hour=cfg.ezam_hour, minute=cfg.ezam_minute),
                  id="ezamowienia_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_boamp, CronTrigger(hour=cfg.boamp_hour, minute=cfg.boamp_minute),
                  id="boamp_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_tenderned,
                  CronTrigger(hour=cfg.tenderned_hour, minute=cfg.tenderned_minute),
                  id="tenderned_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_de_bkms, CronTrigger(hour=cfg.de_bkms_hour, minute=cfg.de_bkms_minute),
                  id="de_bkms_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_eu_portal,
                  CronTrigger(hour=cfg.eu_portal_hour, minute=cfg.eu_portal_minute),
                  id="eu_portal_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_eu_topics,
                  CronTrigger(hour=cfg.eu_topics_hour, minute=cfg.eu_topics_minute),
                  id="eu_topics_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_bdns, CronTrigger(hour=cfg.bdns_hour, minute=cfg.bdns_minute),
                  id="bdns_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_ncbr, CronTrigger(hour=cfg.ncbr_hour, minute=cfg.ncbr_minute),
                  id="ncbr_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_vinnova, CronTrigger(hour=cfg.vinnova_hour, minute=cfg.vinnova_minute),
                  id="vinnova_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_aid, CronTrigger(hour=cfg.aid_hour, minute=cfg.aid_minute),
                  id="aid_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_matine, CronTrigger(hour=cfg.matine_hour, minute=cfg.matine_minute),
                  id="matine_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_health_report, CronTrigger(hour=cfg.health_hour, minute=0),
                  id="health_report", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_alerts, CronTrigger(minute=20),
                  id="alerts_hourly", max_instances=1, misfire_grace_time=1800)
    sched.add_job(job_link_twins, CronTrigger(hour=cfg.twins_hour, minute=cfg.twins_minute),
                  id="link_twins_daily", max_instances=1, misfire_grace_time=3600)
    # An hour after the twins: the ingests and the buyer cleanup have finished by then.
    sched.add_job(job_buyer_families,
                  CronTrigger(hour=(cfg.twins_hour + 1) % 24, minute=cfg.twins_minute),
                  id="buyer_families_daily", max_instances=1, misfire_grace_time=3600)
    # Four-hourly, away from the ingests' hours by the slot: the snapshots are good for eight.
    sched.add_job(job_warm_lists, CronTrigger(hour="1,5,9,13,17,21", minute=50),
                  id="warm_lists", max_instances=1, misfire_grace_time=3600)
    # After the portal's calls and topics (04:20, 04:35): the text the flag is read from is fresh.
    sched.add_job(job_cascade_flags, CronTrigger(hour=(cfg.eu_topics_hour + 1) % 24, minute=0),
                  id="cascade_flags_daily", max_instances=1, misfire_grace_time=3600)
    # After the twins and the buyer families (09:15, 10:15): the week's notices are collapsed by then.
    sched.add_job(job_digest, CronTrigger(hour=(cfg.twins_hour + 2) % 24, minute=0),
                  id="digest_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_ted_awards, CronTrigger(hour=cfg.ted_awards_hour, minute=cfg.ted_awards_minute),
                  id="ted_awards_daily", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_requalify,
                  CronTrigger(day_of_week="sun", hour=cfg.requalify_hour, minute=0),
                  id="requalify_weekly", max_instances=1, misfire_grace_time=7200)
    sched.add_job(job_backup, CronTrigger(hour=cfg.backup_hour, minute=0),
                  id="backup_nightly", max_instances=1, misfire_grace_time=7200)
    sched.add_job(job_backup_verify, CronTrigger(day_of_week="sun", hour=cfg.backup_hour, minute=30),
                  id="backup_verify", max_instances=1, misfire_grace_time=7200)
    sched.add_job(job_backup_freshness, CronTrigger(minute=40),
                  id="backup_freshness", max_instances=1, misfire_grace_time=1800)
    sched.add_job(job_controls, CronTrigger(hour=cfg.health_hour, minute=10),
                  id="controls_daily", max_instances=1, misfire_grace_time=3600)
    # Networks, monthly and in this order: CORDIS, the EDF factsheets, then the snapshot of both.
    sched.add_job(job_cordis, CronTrigger(day=5, hour=cfg.networks_hour, minute=30),
                  id="cordis_monthly", max_instances=1, misfire_grace_time=86400)
    sched.add_job(job_edf, CronTrigger(day=6, hour=cfg.networks_hour, minute=30),
                  id="edf_monthly", max_instances=1, misfire_grace_time=86400)
    sched.add_job(job_consortium_snapshot, CronTrigger(day=7, hour=cfg.networks_hour, minute=30),
                  id="consortium_snapshot", max_instances=1, misfire_grace_time=86400)
    if cfg.placsp_awards_catchup:
        # Off by default: the nightly walk collects the award results; this re-reads last month's archive.
        sched.add_job(job_placsp_awards_catchup, CronTrigger(day=3, hour=12, minute=0),
                      id="placsp_awards_monthly", max_instances=1, misfire_grace_time=86400)
    if ted_history_window() is not None:
        # The history does not end when it has caught up: every day it ended
        # yesterday, there is a new yesterday. The daily TED job asks only the
        # defence question; this keeps the full collection going behind it, one
        # bundle a day -- one write, whatever the day holds. Running it daily
        # rather than only at start-up is what stops "complete to 18 September"
        # quietly becoming "complete to whenever the worker last restarted".
        sched.add_job(job_ted_history,
                      CronTrigger(hour=(cfg.ted_hour + 1) % 24, minute=cfg.ted_minute),
                      id="ted_history_daily", max_instances=1, misfire_grace_time=7200)
    return sched


def describe_schedule() -> list[str]:
    cfg = settings()
    return [
        f"ted_daily      {cfg.ted_hour:02d}:{cfg.ted_minute:02d} UTC  "
        f"(window {cfg.ingest_days} days, overlapping on purpose)",
        f"placsp_daily   {cfg.placsp_hour:02d}:{cfg.placsp_minute:02d} UTC  "
        f"(datasets 1 and 2)",
        f"ezamowienia    {cfg.ezam_hour:02d}:{cfg.ezam_minute:02d} UTC  "
        f"(every notice, one publication day at a time)",
        f"boamp_daily    {cfg.boamp_hour:02d}:{cfg.boamp_minute:02d} UTC  "
        f"(every notice, one publication day at a time)",
        f"matine_daily   {cfg.matine_hour:02d}:{cfg.matine_minute:02d} UTC  "
        f"(Finnish defence ministry research funding call)",
        f"aid_daily      {cfg.aid_hour:02d}:{cfg.aid_minute:02d} UTC  "
        f"(French defence innovation agency call pages)",
        f"vinnova_daily  {cfg.vinnova_hour:02d}:{cfg.vinnova_minute:02d} UTC  "
        f"(Swedish defence-programme calls, the whole register)",
        f"tenderned_daily {cfg.tenderned_hour:02d}:{cfg.tenderned_minute:02d} UTC  "
        f"(every publication and its detail page, one day at a time)",
        f"de_bkms_daily  {cfg.de_bkms_hour:02d}:{cfg.de_bkms_minute:02d} UTC  "
        f"(German notice day files, last three days; off while the source is inactive)",
        f"eu_portal      {cfg.eu_portal_hour:02d}:{cfg.eu_portal_minute:02d} UTC  "
        f"(grant calls: open, forthcoming, and closed this year)",
        f"eu_topics      {cfg.eu_topics_hour:02d}:{cfg.eu_topics_minute:02d} UTC  "
        f"(topic pages: budget, conditions, consortium rules)",
        f"bdns_daily     {cfg.bdns_hour:02d}:{cfg.bdns_minute:02d} UTC  "
        f"(Spanish subsidy calls, central government)",
        f"ncbr_daily     {cfg.ncbr_hour:02d}:{cfg.ncbr_minute:02d} UTC  "
        f"(Polish NCBR competitions, the whole list)",
        f"health_report  {cfg.health_hour:02d}:00 UTC",
        "alerts_hourly  :20 UTC  (digests of saved searches; nothing without a mail relay)",
        f"link_twins     {cfg.twins_hour:02d}:{cfg.twins_minute:02d} UTC  "
        f"(national notices tied to their TED twins, after every ingest)",
        f"buyer_families {(cfg.twins_hour + 1) % 24:02d}:{cfg.twins_minute:02d} UTC  "
        f"(organisation rows of one body shown as one buyer; display only)",
        f"cascade_flags {(cfg.eu_topics_hour + 1) % 24:02d}:00 UTC  "
        f"(financial support to third parties, set on each call from its text and facts)",
        f"digest         {(cfg.twins_hour + 2) % 24:02d}:00 UTC  "
        f"(weekly digest issues: last two complete weeks and any missing)",
        f"ted_awards     {cfg.ted_awards_hour:02d}:{cfg.ted_awards_minute:02d} UTC  "
        f"(winners of TED result notices not read yet, core scope and VEAT, at most {cfg.ted_awards_limit})",
        f"requalify      Sun {cfg.requalify_hour:02d}:00 UTC  "
        f"(notices the rules now qualify, every source, last {cfg.requalify_days} days)",
        *([f"ted_history    {(cfg.ted_hour + 1) % 24:02d}:{cfg.ted_minute:02d} UTC  "
           f"(every notice of yesterday, one bundle; from {cfg.ted_history_from})"]
          if ted_history_window() is not None else []),
        f"backup_nightly {cfg.backup_hour:02d}:00 UTC  "
        f"(keep {cfg.backup_keep_days} days)",
        f"backup_verify  Sun {cfg.backup_hour:02d}:30 UTC  "
        f"(restore into a scratch database and count)",
        f"cordis_monthly  day 5, {cfg.networks_hour:02d}:30 UTC  "
        f"(research projects, organisations and participations; CORDIS SPARQL service)",
        f"edf_monthly    day 6, {cfg.networks_hour:02d}:30 UTC  "
        f"(EDF project factsheets: crawl, read, resolve; the model only for new files)",
        f"consortium_snapshot day 7, {cfg.networks_hour:02d}:30 UTC  "
        f"(composition snapshot per project and the consortium.changed rows)",
        f"controls      {cfg.health_hour:02d}:10 UTC  (PLACSP measures, Atlas record)",
        ("placsp_awards_monthly day 3, 12:00 UTC  (last month's PLACSP archive for the award results)"
         if cfg.placsp_awards_catchup else
         "placsp_awards_monthly off  (DGATE_PLACSP_AWARDS_CATCHUP=true to run it; the nightly walk collects them)"),
        f"backup_freshness :40 UTC  (alert when the newest dump is over "
        f"{cfg.backup_stale_hours}h old, here or in the store)",
    ]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # See pipeline.main: request URLs can carry the alerting token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="dgate-worker")
    parser.add_argument("--once", choices=sorted(JOBS), help="run one job now and exit")
    parser.add_argument("--list", action="store_true", help="print the schedule and exit")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(describe_schedule()))
        return 0

    # Which processes' runs a start-up may close (`db.close_interrupted_runs`): the
    # scheduled worker's own kind, and for `--once` a kind no other process shares.
    db.RUN_KIND = f"once-{args.once}" if args.once else "worker"

    if args.once:
        result = JOBS[args.once]()
        print(f"{result.name}: {result.status} in {result.seconds:.0f}s "
              f"{result.detail}".rstrip())
        return 0 if result.ok else 1

    log.info("worker starting at %s UTC", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for line in describe_schedule():
        log.info("scheduled: %s", line)
    # Tidy up after whatever killed the last process, then cover whatever was
    # missed while it was not running. A cron entry cannot catch up on its own.
    # The tidying is synchronous: a run closed after the scheduler has opened its own
    # would be this process's. The catch-up runs beside the scheduler, not before it
    # (internal audit M8): a PLACSP catch-up is 15-40 minutes and a week's window hours,
    # and every slot that passed meanwhile was lost. `run_job` keeps a slot from starting
    # a job the catch-up is still running.
    ready = wait_for_database()
    if ready:
        close_interrupted_runs()
        ensure_buyer_list()
        ensure_requirements()
        ensure_regulation()
    start_catch_up_thread(ready)
    build_scheduler().start()
    return 0


def warm_first_views() -> None:
    """WP-98c: at start (a deploy), the Atom feed's API pages and the supplier value orders, when missing or older than four
    hours (`ops.warm_lists.run_first`, seconds), so the first reader after a deploy does not wait for them. Never blocks the
    start: a failure is logged, and the four-hourly run writes them anyway."""
    from .ops import warm_lists

    try:
        with db.connect(settings().dsn) as conn:
            log.info("first views: %s", warm_lists.run_first(conn))
    except Exception:  # noqa: BLE001
        log.exception("first views were not written")


def start_catch_up_thread(database_ready: bool = True) -> threading.Thread:
    thread = threading.Thread(target=_catch_up_in_background, args=(database_ready,),
                              name="catch-up", daemon=True)
    thread.start()
    return thread


def _catch_up_in_background(database_ready: bool) -> None:
    try:
        if database_ready:
            start_backfill_thread()
            threading.Thread(target=warm_first_views, name="first-views", daemon=True).start()
            results = catch_up_backups() + catch_up() + catch_up_jobs()
        else:
            # Loud rather than silent: a catch-up that could not run is a gap that
            # is still open, and the next scheduled slot may be a day away.
            notify("[dgate] worker started but the database never came up; "
                   "catch-up did not run and missed days are still missing")
            results = []
        for result in results:
            log.info("catch-up %s: %s %s", result.name, result.status, result.detail)
    except Exception as exc:  # noqa: BLE001 - a start-up thread must say so, not vanish
        log.exception("catch-up failed")
        notify(f"[dgate] worker catch-up failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
