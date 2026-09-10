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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
    """Age of the most recent successful run across these sources.

    None means no source here has ever succeeded, which is its own kind of gap
    and is treated as one.
    """
    with db.connect(settings().dsn) as conn:
        row = conn.execute(
            """SELECT max(r.finished_at) AS t
                 FROM ingest_run r JOIN source s ON s.id = r.source_id
                WHERE s.code = ANY(%s) AND r.status = 'success'""",
            (list(codes),),
        ).fetchone()
    finished = row["t"] if row else None
    if finished is None:
        return None
    return (datetime.now(timezone.utc) - finished).total_seconds() / 3600


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
        if age is not None and age < cfg.catch_up_after_hours:
            log.info("catch-up: %s succeeded %.0fh ago, nothing to cover", name, age)
            continue
        gap_days = cfg.ingest_days if age is None else int(age // 24) + 1
        window = min(max(gap_days, cfg.ingest_days), cfg.catch_up_max_days)
        log.warning("catch-up: %s last succeeded %s, running now over %s days",
                    name, "never" if age is None else f"{age:.0f}h ago", window)
        results.append(job(days=window))
    return results


def job_catch_up() -> JobResult:
    """The catch-up as a single job, for `--once catch-up`."""
    close_interrupted_runs()
    results = catch_up()
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
    close_interrupted_runs()
    for result in catch_up():
        log.info("catch-up %s: %s %s", result.name, result.status, result.detail)
    build_scheduler().start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
