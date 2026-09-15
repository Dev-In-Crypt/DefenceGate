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
import logging
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence

from . import db
from .config import settings
from .ops.notify import notify, ping
from .pipeline import run_ezamowienia, run_placsp_live, run_ted, seed_buyers

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


def run_job(name: str, fn: Callable[[], None], *, sources: Sequence[str] = ()) -> JobResult:
    """Run one job, decide honestly whether it worked, and be loud if not.

    Three outcomes, and only the first is a green tick:
      success  the callable returned and every source reported success
      partial  the callable returned but a source came in under its floor,
               or recorded no run at all
      failed   the callable raised
    """
    slug = name.replace("_", "-")
    started = time.monotonic()
    ping(slug, "start")
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - a job must not kill the scheduler
        elapsed = time.monotonic() - started
        log.exception("job %s failed", name)
        ping(slug, "fail")
        notify(f"[dgate] job {name} FAILED after {elapsed:.0f}s: {exc}")
        return JobResult(name, "failed", elapsed, str(exc))

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
        return JobResult(name, "partial", elapsed, detail)

    ping(slug, "success")
    log.info("job %s succeeded in %.0fs", name, elapsed)
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


def job_seed_buyers() -> JobResult:
    return run_job("seed_buyers", seed_buyers)


def job_backup() -> JobResult:
    """Nightly dump, pruned to the retention window.

    A dump is not the primary safety net; the raw payload store is, because the
    database is derived from it. What a dump adds is speed, and the observation
    timeline, which a replay cannot reconstruct: it can rebuild what a notice
    said, never when we first saw it say so.
    """
    def _run() -> None:
        from .ops.backup import create, prune

        result = create()
        removed = prune(settings().backup_keep_days)
        log.info("backup %s (%.1f MB), pruned %s old dumps",
                 result.path.name, result.megabytes, len(removed))

    return run_job("backup_nightly", _run)


def job_backup_verify() -> JobResult:
    """Restore the newest dump into a scratch database and count what arrived.

    An unverified backup is a belief. This is the job that turns it into a fact,
    and it is the one whose failure should worry an operator most.
    """
    def _run() -> None:
        from .ops.backup import verify

        counts = verify()
        if not counts.get("opportunity_version"):
            raise RuntimeError(f"restored database has no archive rows: {counts}")
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

    verified = _age_hours(last_backup_verified())
    weekly = hours_since_last_weekly_slot(6, cfg.backup_hour, 30)
    if verified is None or verified > weekly:
        log.warning("catch-up: last restore check %s; verifying the newest dump now",
                    "never recorded" if verified is None else f"{verified:.0f}h ago")
        results.append(job_backup_verify())
    return results


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


def start_backfill_thread() -> threading.Thread | None:
    """Resume an unfinished backfill alongside, not before, the catch-up.

    A thread, so that three days of missed daily collection are not held up
    behind two hours of history, and history is not held up behind them.
    """
    years = pending_backfill_years()
    if not years:
        return None
    log.info("atlas backfill still to finish for %s; resuming in the background", years)
    thread = threading.Thread(target=job_atlas_backfill, name="atlas-backfill",
                              daemon=True)
    thread.start()
    return thread


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
    """Fail any ingest_run left `running` by a process that was killed.

    Safe only at start-up, where "still running" can only mean "was killed",
    because this process has not opened a run yet. Left alone such a row makes
    its source look permanently degraded: coverage is read from the latest run
    per source, so every later alert for it becomes noise.
    """
    try:
        with db.connect(settings().dsn) as conn:
            return db.close_interrupted_runs(conn)
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


def job_catch_up() -> JobResult:
    """The catch-up as a single job, for `--once catch-up`."""
    wait_for_database()
    close_interrupted_runs()
    ensure_buyer_list()
    results = catch_up_backups() + catch_up()
    if not results:
        return JobResult("catch_up", "success", 0.0, "nothing was stale")
    worst = min(results, key=lambda r: ("failed", "partial", "success").index(r.status))
    detail = "; ".join(f"{r.name}={r.status}" for r in results)
    return JobResult("catch_up", worst.status, sum(r.seconds for r in results), detail)


JOBS: dict[str, Callable[[], JobResult]] = {
    "ted": job_ted,
    "ezamowienia": job_ezamowienia,
    "placsp": job_placsp,
    "seed-buyers": job_seed_buyers,
    "health": job_health_report,
    "backup": job_backup,
    "backup-verify": job_backup_verify,
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
    sched.add_job(job_health_report, CronTrigger(hour=cfg.health_hour, minute=0),
                  id="health_report", max_instances=1, misfire_grace_time=3600)
    sched.add_job(job_backup, CronTrigger(hour=cfg.backup_hour, minute=0),
                  id="backup_nightly", max_instances=1, misfire_grace_time=7200)
    sched.add_job(job_backup_verify, CronTrigger(day_of_week="sun", hour=cfg.backup_hour, minute=30),
                  id="backup_verify", max_instances=1, misfire_grace_time=7200)
    return sched


def describe_schedule() -> list[str]:
    cfg = settings()
    return [
        f"ted_daily      {cfg.ted_hour:02d}:{cfg.ted_minute:02d} UTC  "
        f"(window {cfg.ingest_days} days, overlapping on purpose)",
        f"placsp_daily   {cfg.placsp_hour:02d}:{cfg.placsp_minute:02d} UTC  "
        f"(datasets 1 and 2)",
        f"ezamowienia    {cfg.ezam_hour:02d}:{cfg.ezam_minute:02d} UTC  "
        f"(targeted defence queries, not a full scan)",
        f"health_report  {cfg.health_hour:02d}:00 UTC",
        f"backup_nightly {cfg.backup_hour:02d}:00 UTC  "
        f"(keep {cfg.backup_keep_days} days)",
        f"backup_verify  Sun {cfg.backup_hour:02d}:30 UTC  "
        f"(restore into a scratch database and count)",
    ]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(prog="dgate-worker")
    parser.add_argument("--once", choices=sorted(JOBS), help="run one job now and exit")
    parser.add_argument("--list", action="store_true", help="print the schedule and exit")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(describe_schedule()))
        return 0

    if args.once:
        result = JOBS[args.once]()
        print(f"{result.name}: {result.status} in {result.seconds:.0f}s "
              f"{result.detail}".rstrip())
        return 0 if result.ok else 1

    log.info("worker starting at %s UTC", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for line in describe_schedule():
        log.info("scheduled: %s", line)
    # Before the scheduler blocks: tidy up after whatever killed the last
    # process, then cover whatever was missed while it was not running. A cron
    # entry cannot catch up on its own.
    if wait_for_database():
        close_interrupted_runs()
        ensure_buyer_list()
        start_backfill_thread()
        results = catch_up_backups() + catch_up()
    else:
        # Loud rather than silent: a catch-up that could not run is a gap that
        # is still open, and the next scheduled slot may be a day away.
        notify("[dgate] worker started but the database never came up; "
               "catch-up did not run and missed days are still missing")
        results = []
    for result in results:
        log.info("catch-up %s: %s %s", result.name, result.status, result.detail)
    build_scheduler().start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
