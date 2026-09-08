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

def job_ted() -> JobResult:
    return run_job("ted_daily", lambda: run_ted(days=settings().ingest_days),
                   sources=["ted"])


def job_placsp() -> JobResult:
    return run_job("placsp_daily", run_placsp_live,
                   sources=["es_placsp", "es_placsp_agg"])


def job_ezamowienia() -> JobResult:
    return run_job("ezamowienia_daily",
                   lambda: run_ezamowienia(days=settings().ingest_days),
                   sources=[ezam_source()])


def job_seed_buyers() -> JobResult:
    return run_job("seed_buyers", seed_buyers)


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


JOBS: dict[str, Callable[[], JobResult]] = {
    "ted": job_ted,
    "ezamowienia": job_ezamowienia,
    "placsp": job_placsp,
    "seed-buyers": job_seed_buyers,
    "health": job_health_report,
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
    build_scheduler().start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
