"""Read the PLACSP archives again for the award winners, and fill the notices they hold (WP-60).

    python -m dgate.ops.placsp_archives                         # dry run: archives, estimated sizes, disk, what is done
    python -m dgate.ops.placsp_archives --from 2026-09 --to 2026-09 --yes     # one month
    python -m dgate.ops.placsp_archives --yes                   # 2023-01 .. this month
    python -m dgate.ops.placsp_archives --land-only --yes       # land the payloads only, no award row
    python -m dgate.ops.placsp_archives --from-store [--yes]    # load from the landed payloads, no download

The raw store never held PLACSP's XML (its "land" step stores the parsed record), so the winners can only be
had by downloading the publisher's archives once more (owner approval of 20 October 2026). Each archive is
walked once for two things, through the normal path: its notices go through `_ingest_placsp` in replay mode
(the dedupe and version rules of every run; this fills the 2025 gap, whose annual archive was never read), and
the award results of every kept record are landed and loaded next to it (`dgate.placsp_awards`).

Polite and safe to stop. One archive at a time, one request a second at most, the connector's User-Agent;
a 429 ends the run. The archive and the parsed entries are temporary files that go with the unit, so at most
one archive is on disk at once; before a unit, and every 64 MiB while it downloads and spools, the free
space is checked, and the run stops cleanly when it would fall under `--min-free-gb` (3 by default). A unit
is marked done in `backfill_day` (`es_placsp-awards`) only once it is committed, and the entries of an
interrupted unit are skipped on the next run (`es_placsp-awards-progress`), so rerunning the same command
resumes. Refuses to start or continue inside the daily live walk's window, or while a live run is going.
The current month is never marked done: it is still being written. Annual archives cover years before this
one. Idempotent: a second run over a done unit is skipped; over a unit with `--no-resume`, it writes no
notice version and no award row that is not new.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
import psycopg

from .. import db, pipeline, placsp_awards
from ..config import settings
from ..sources import placsp

log = logging.getLogger("dgate.ops.placsp_archives")

MARK = "-awards"
# What a unit needs on disk besides the floor, as a multiple of the archive's size: the ZIP itself and the
# spool of parsed entries. Measured on the pilot of 20 October 2026 (2026-09: about 360 MB of ZIP, 440 MB at
# the peak, 1.22 times; docs/verification/product/wp60-selfcheck.md).
SPOOL_FACTOR = 1.25
# The publisher sends no Content-Length (chunked) and drops a HEAD request (measured 20 October 2026), so an
# archive's size is known only once it is down. These are the planning figures: a month as measured on the
# pilot (2026-09), a year as the connector's own ceiling (placsp.MAX_ARCHIVE_BYTES). The disk is checked
# while the download runs either way.
MONTH_ESTIMATE = 400 * 2**20
YEAR_ESTIMATE = placsp.MAX_ARCHIVE_BYTES


@dataclass
class Unit:
    name: str
    url: str
    day: date
    since: datetime
    year: int
    month: int | None
    size: int | None = None


def units(start: tuple[int, int], end: tuple[int, int], ds: placsp.Dataset, today: date) -> list[Unit]:
    """The archives that cover `start`..`end`, oldest first: the annual file for a past year, else months."""
    out: list[Unit] = []
    year, month = start
    while (year, month) <= end:
        if year < today.year:
            if not out or out[-1].year != year:
                out.append(Unit(f"{ds.source_code}-{year}", ds.annual_archive_url(year), date(year, 1, 1),
                                datetime(year, 1, 1, tzinfo=timezone.utc), year, None, YEAR_ESTIMATE))
        else:
            out.append(Unit(f"{ds.source_code}-{year}{month:02d}", ds.monthly_archive_url(year, month),
                            date(year, month, 1), datetime(year, month, 1, tzinfo=timezone.utc), year, month,
                            MONTH_ESTIMATE))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def free_bytes() -> int:
    return shutil.disk_usage(tempfile.gettempdir()).free


def _gib(n: int | None) -> str:
    return "?" if n is None else f"{n / 2**30:.2f} GiB"


def plan(todo: list[Unit], done: set[date], floor: int) -> str:
    lines = [f"{'unit':24} {'est. size':>13} {'peak need':>11}  state  url"]
    for u in todo:
        need = int(u.size * SPOOL_FACTOR) if u.size else None
        lines.append(f"{u.name:24} {_gib(u.size):>13} {_gib(need):>11}  "
                     f"{'done ' if u.day in done else 'to do'}  {u.url}")
    sizes = [u.size for u in todo if u.day not in done]
    known = [s for s in sizes if s]
    biggest = max(known, default=0)
    lines.append(f"to download: {len(sizes)} archives, about {_gib(sum(known))} in all (estimates: the "
                 f"server states no size); one at a time, peak disk about {_gib(int(biggest * SPOOL_FACTOR))}")
    lines.append(f"free now: {_gib(free_bytes())}; floor: {_gib(floor)}; "
                 f"{'enough' if free_bytes() - biggest * SPOOL_FACTOR >= floor else 'NOT enough for the largest'}")
    return "\n".join(lines)


class Incomplete(RuntimeError):
    """A unit whose archive held entries or members that could not be read (QA M7): what was
    read is kept, but the unit is not marked done, so the hole stays visible and a rerun retries."""


def run_unit(u: Unit, ds: placsp.Dataset, *, floor: int, resume: bool,
             land_only: bool = False) -> tuple[int, int, int]:
    pmark = f"{ds.source_code}{MARK}-progress"
    with db.connect(settings().dsn) as conn:
        if not resume:
            db.reset_backfill_progress(conn, pmark, u.day)
        skip = db.backfill_progress(conn, pmark, u.day)
    seen: dict = {}
    stream = placsp.fetch_archive(u.url, ds, since=u.since, with_results=True, min_free_bytes=floor,
                                  observe=seen)
    got = pipeline._ingest_placsp(stream, f"{u.name}-awards", ds, replay=True, resume_from=skip,
                                  progress=(pmark, u.day),
                                  awards=lambda conn: placsp_awards.Loader(conn, land_only=land_only))
    with db.connect(settings().dsn) as conn:
        db.reset_backfill_progress(conn, pmark, u.day)
    if seen.get("entries_failed") or seen.get("members_skipped"):
        raise Incomplete(f"{seen.get('entries_failed', 0)} entries could not be parsed, "
                         f"{seen.get('members_skipped', 0)} archive members skipped")
    return got


def run(todo: list[Unit], ds: placsp.Dataset, *, floor: int, resume: bool, pause: float,
        land_only: bool = False, now=lambda: datetime.now(timezone.utc),
        sleep=time.sleep) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"done": [], "skipped": [], "failed": [], "stopped": []}
    mark = f"{ds.source_code}{MARK}"
    with db.connect(settings().dsn) as conn:
        done = db.backfill_days_done(conn, mark) if resume else set()
    for i, u in enumerate(todo):
        if u.day in done:
            result["skipped"].append(u.name)
            continue
        with db.connect(settings().dsn) as conn:
            running = pipeline._live_walk_running(conn)
        if running or pipeline._in_live_window(now(), settings()):
            log.warning("stopping before %s: the daily live walk is due or running; run again to resume", u.name)
            result["stopped"].append(u.name)
            return result
        need = floor + int((u.size or 0) * SPOOL_FACTOR)
        if free_bytes() < need:
            log.error("stopping before %s: %s free, it needs about %s", u.name, _gib(free_bytes()), _gib(need))
            result["stopped"].append(u.name)
            return result
        if i:
            sleep(pause)
        started = time.monotonic()
        try:
            with db.historical_load("replay"):
                fetched, new, changed = run_unit(u, ds, floor=floor, resume=resume, land_only=land_only)
        except Incomplete as exc:
            log.error("%s incomplete, not marked done: %s", u.name, exc)
            result["failed"].append(u.name)
            continue
        except placsp.DiskLow as exc:
            log.error("stopped in %s: %s; nothing of the unit past its last checkpoint is kept", u.name, exc)
            result["stopped"].append(u.name)
            return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                log.error("rate limited at %s; stopping", u.name)
                result["stopped"].append(u.name)
                return result
            log.error("%s failed: %s", u.name, exc)
            result["failed"].append(u.name)
            continue
        except (psycopg.OperationalError, psycopg.InterfaceError) as exc:
            log.error("%s lost its database (%s); run again to continue after its last checkpoint", u.name, exc)
            result["stopped"].append(u.name)
            return result
        except Exception as exc:  # noqa: BLE001 - one archive must not end the range
            log.error("%s failed: %s", u.name, exc)
            result["failed"].append(u.name)
            continue
        today = now().date()
        if (u.year, u.month or 12) < (today.year, today.month):
            with db.connect(settings().dsn) as conn:
                db.mark_backfill_day(conn, mark, u.day, fetched)
        log.info("%s: %s entries, %s new notices, %s changed, %.0f s, %s free", u.name, fetched, new, changed,
                 time.monotonic() - started, _gib(free_bytes()))
        result["done"].append(u.name)
    return result


def _month(text: str) -> tuple[int, int]:
    y, m = text.split("-")
    if not (2012 <= int(y) <= 2100 and 1 <= int(m) <= 12):
        raise argparse.ArgumentTypeError(f"not a month: {text}")
    return int(y), int(m)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="placsp-archives", description=__doc__.split("\n\n")[0])
    p.add_argument("--from", dest="start", type=_month, default=(2023, 1), help="YYYY-MM (default 2023-01)")
    p.add_argument("--to", dest="end", type=_month, default=None, help="YYYY-MM (default this month)")
    p.add_argument("--dataset", choices=sorted(placsp.DATASETS), default="es_placsp")
    p.add_argument("--min-free-gb", type=float, default=3.0)
    p.add_argument("--pause", type=float, default=1.0, help="seconds between requests (at least 1)")
    p.add_argument("--no-resume", action="store_true", help="redo units marked done, from their first entry")
    p.add_argument("--land-only", action="store_true",
                   help="land the award payloads, write no award row (load later with --from-store)")
    p.add_argument("--from-store", action="store_true",
                   help="load the winners from the landed payloads; downloads nothing (without --yes: "
                        "runs it and rolls back, printing what it would write)")
    p.add_argument("--yes", action="store_true", help="run (default: print the plan)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if a.from_store:
        started = time.monotonic()
        with db.connect(settings().dsn) as conn:
            got = placsp_awards.replay_from_store(conn, commit=a.yes)
        print(dict(got), f"{time.monotonic() - started:.0f} s")
        print("written" if a.yes else "dry run: rolled back, nothing kept; --yes to write")
        return 0
    ds = placsp.DATASETS[a.dataset]
    today = datetime.now(timezone.utc).date()
    todo = units(a.start, a.end or (today.year, today.month), ds, today)
    floor = int(a.min_free_gb * 2**30)
    pause = max(1.0, a.pause)
    with db.connect(settings().dsn) as conn:
        done = db.backfill_days_done(conn, f"{ds.source_code}{MARK}") if not a.no_resume else set()
    print(plan(todo, done, floor))
    if not a.yes:
        print("dry run: nothing downloaded or written; --yes to run")
        return 0
    result = run(todo, ds, floor=floor, resume=not a.no_resume, pause=pause, land_only=a.land_only)
    print(result)
    return 0 if not result["failed"] and not result["stopped"] else 75


if __name__ == "__main__":
    sys.exit(main())
