"""All configuration in one place.

Rule for the whole package: no module reads ``os.environ`` directly. Settings
are read here, once, so that a deployment can be reasoned about from one file
and a test can override a value without patching the environment of an import
that already happened.

Values are read lazily through ``settings()``: reading them at import time is
what made the Phase 1 integration test impossible to run anywhere but the
machine it was written on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_int_list(name: str) -> list[int]:
    raw = os.environ.get(name) or ""
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


# Coverage floors, measured against the live sources on 7 September 2026.
#
# A run that finishes below its floor is marked `partial`, never `success`,
# because silent under-collection is the failure that quietly destroys a
# coverage promise.
#
# One number cannot serve, because TED publishes nothing at weekends: measured
# per day, Saturday and Sunday are exactly 0 while weekdays run 60 to 89. The
# daily job at 06:15 UTC covers the two preceding days, so what it should find
# depends on which weekdays those were:
#
#   run day    window covers      measured        floor (~40%)
#   Monday     Sat, Sun           0               0
#   Tuesday    Sun, Mon           ~83             30
#   Wed-Sat    two weekdays       ~150            60
#   Sunday     Fri, Sat           ~76             30
#
# PLACSP publishes in packages chained by rel="next", 405 to 500 entries per
# page, and the daily run walks up to 20 pages. One page is the floor: below
# that, the chain is broken rather than quiet.
_TED_FLOORS = {0: 0, 1: 30, 2: 60, 3: 60, 4: 60, 5: 60, 6: 30}   # Monday = 0
_PLACSP_FLOORS = dict.fromkeys(range(7), 400)
_PLACSP_AGG_FLOORS = dict.fromkeys(range(7), 50)
# Poland, full collection since 15 September 2026. Measured per publication day
# over every notice: Thursday and Friday 10-11 Sep 5,733 together, Saturday 12
# Sep 36, Sunday 13 Sep 61, Monday 14 Sep 2,667, Tuesday 15 Sep 2,449 by 12:15
# UTC. The daily job at 06:45 covers the two preceding days and the morning so
# far. Floors are about 40% of that:
#
#   run day    window covers          measured      floor
#   Monday     Sat, Sun               ~100          40
#   Tuesday    Sun, Mon               ~2,700        1,000
#   Wed-Sat    two weekdays           ~5,500        2,000
#   Sunday     Fri, Sat               ~2,900        1,000
_EZAM_FLOORS = {0: 40, 1: 1000, 2: 2000, 3: 2000, 4: 2000, 5: 2000, 6: 1000}   # Monday = 0


def _weekday_floors(name: str, defaults: dict[int, int]) -> dict[int, int]:
    """Per-weekday floors, overridable with one env var per source.

    ``DGATE_FLOOR_TED=0,30,60,60,60,60,30`` sets Monday through Sunday. A single
    number sets every day, which is what a source with no weekly rhythm wants.
    """
    raw = os.environ.get(name)
    if not raw or not raw.strip():
        return dict(defaults)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        values = [int(p) for p in parts]
    except ValueError:
        return dict(defaults)
    if len(values) == 1:
        return dict.fromkeys(range(7), values[0])
    if len(values) == 7:
        return dict(enumerate(values))
    return dict(defaults)


def _default_floors() -> dict[str, dict[int, int]]:
    return {
        "ted": _weekday_floors("DGATE_FLOOR_TED", _TED_FLOORS),
        "es_placsp": _weekday_floors("DGATE_FLOOR_ES_PLACSP", _PLACSP_FLOORS),
        "es_placsp_agg": _weekday_floors("DGATE_FLOOR_ES_PLACSP_AGG", _PLACSP_AGG_FLOORS),
        "pl_ezam": _weekday_floors("DGATE_FLOOR_PL_EZAM", _EZAM_FLOORS),
        # pl_atlas has no floor on purpose. A floor answers "did today's feed
        # arrive?"; this source is a one-off historical load with no daily
        # rhythm, and a resumed run legitimately reads almost nothing because
        # the rest already landed. None means "not measured", which is honest,
        # and finish_run leaves such a run `success` rather than `partial`.
    }


@dataclass(frozen=True)
class Settings:
    # --- database -------------------------------------------------------
    dsn: str = field(default_factory=lambda: _env(
        "DGATE_DSN", "postgresql://dgate:dgate@localhost:5432/dgate"))
    # Separate DSN for tests. Unset means integration tests skip themselves
    # rather than silently pointing at a real database.
    test_dsn: str | None = field(default_factory=lambda: os.environ.get("DGATE_TEST_DSN"))

    # --- raw payload storage --------------------------------------------
    # `fs` keeps payloads on the same disk as everything else, which protects
    # against a bad parser and nothing else. `s3` is what makes the store a
    # separate failure domain from the database, which is the whole point.
    raw_backend: str = field(default_factory=lambda: _env("DGATE_RAW_BACKEND", "fs"))
    raw_dir: Path = field(default_factory=lambda: Path(_env("DGATE_RAW_DIR", "./raw")))
    s3_bucket: str = field(default_factory=lambda: _env("DGATE_S3_BUCKET", "dgate-raw"))
    # Empty means Amazon. Cloudflare R2 and MinIO need their own endpoint.
    s3_endpoint: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_S3_ENDPOINT") or None)
    s3_region: str = field(default_factory=lambda: _env("DGATE_S3_REGION", "auto"))
    s3_access_key: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_S3_ACCESS_KEY") or None)
    s3_secret_key: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_S3_SECRET_KEY") or None)
    # How many raw payloads are written at once. One payload is one HTTPS round
    # trip -- 530 ms against R2 from this deployment -- so sequential writes cap
    # ingestion at under two records a second, and a daily PLACSP run cannot
    # finish inside a day. Sixteen measured 23.5/s. Set 1 to write straight
    # through, which is what a local filesystem store wants.
    raw_write_workers: int = field(
        default_factory=lambda: _env_int("DGATE_RAW_WRITE_WORKERS", 16))
    # Where the Atlas Przetargow year files are downloaded for the one-off
    # Polish backfill. Hundreds of megabytes, wanted only while the backfill
    # runs, so it is deliberately not the raw store.
    atlas_dir: Path = field(
        default_factory=lambda: Path(_env("DGATE_ATLAS_DIR", "./data/atlas")))
    # Year files the worker should finish loading, e.g. "2024,2025". Empty means
    # the worker never starts a backfill on its own. A year is finished once its
    # `.done` marker exists, so leaving this set costs nothing afterwards.
    # The TED history load. A start date rather than a flag, because "ten years"
    # is not a fact about the source: the Search API answers from 2017 and
    # returns nothing for 2016, so how far back to reach is a measured choice
    # that belongs in configuration, not in code.
    ted_history_from: str = field(
        default_factory=lambda: _env("DGATE_TED_HISTORY_FROM", ""))
    ted_history_to: str = field(
        default_factory=lambda: _env("DGATE_TED_HISTORY_TO", ""))
    atlas_backfill_years: list[int] = field(
        default_factory=lambda: _env_int_list("DGATE_ATLAS_BACKFILL_YEARS"))
    # The backfill writes far more than a daily run and is bound by R2 latency,
    # so it gets its own, wider writer pool: 64 measured 89 rows/s against 27
    # at the daily default of 16.
    atlas_write_workers: int = field(
        default_factory=lambda: _env_int("DGATE_ATLAS_WRITE_WORKERS", 64))

    # --- ingestion ------------------------------------------------------
    floors: dict[str, dict[int, int]] = field(default_factory=_default_floors)
    user_agent: str = field(default_factory=lambda: _env(
        "DGATE_USER_AGENT",
        "dgate/0.1 (+https://github.com/Dev-In-Crypt/DefenceGate)"))

    # --- alerting -------------------------------------------------------
    # All optional. Unconfigured means log-only: an alerting backend must
    # never be able to take the pipeline down with it.
    healthchecks_base: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_HEALTHCHECKS_BASE"))
    telegram_token: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_TELEGRAM_TOKEN"))
    telegram_chat_id: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_TELEGRAM_CHAT_ID"))

    # --- scheduling (UTC) ------------------------------------------------
    # Windows overlap deliberately with the ingest window, so a missed run
    # heals itself on the next one.
    ted_hour: int = field(default_factory=lambda: _env_int("DGATE_TED_HOUR", 6))
    ted_minute: int = field(default_factory=lambda: _env_int("DGATE_TED_MINUTE", 15))
    placsp_hour: int = field(default_factory=lambda: _env_int("DGATE_PLACSP_HOUR", 6))
    placsp_minute: int = field(default_factory=lambda: _env_int("DGATE_PLACSP_MINUTE", 30))
    ezam_hour: int = field(default_factory=lambda: _env_int("DGATE_EZAM_HOUR", 6))
    ezam_minute: int = field(default_factory=lambda: _env_int("DGATE_EZAM_MINUTE", 45))
    health_hour: int = field(default_factory=lambda: _env_int("DGATE_HEALTH_HOUR", 7))
    backup_hour: int = field(default_factory=lambda: _env_int("DGATE_BACKUP_HOUR", 2))
    backup_keep_days: int = field(
        default_factory=lambda: _env_int("DGATE_BACKUP_KEEP_DAYS", 30))
    # Kept on the host for days, in the store for a month. The two differ
    # because they are limited by different things: the store is paid for by
    # the gigabyte and a month of it costs pennies, while the host has one 40 GB
    # disk that also holds the database the dumps are of. At the size the
    # archive reaches with the TED history, thirty dumps on the host would be
    # thirty gigabytes and the database would run out of room first.
    # Writes the object store will make in one day before it refuses. Object
    # storage bills per write and has no cap of its own; see rawstore's fuse.
    # An ordinary day needs about 150; 0 turns the fuse off.
    store_write_limit: int = field(
        default_factory=lambda: _env_int("DGATE_STORE_WRITE_LIMIT", 20000))
    backup_keep_days_local: int = field(
        default_factory=lambda: _env_int("DGATE_BACKUP_KEEP_DAYS_LOCAL", 7))
    ingest_days: int = field(default_factory=lambda: _env_int("DGATE_INGEST_DAYS", 2))
    placsp_pages: int = field(default_factory=lambda: _env_int("DGATE_PLACSP_PAGES", 20))
    # Past this age of its newest entry a PLACSP live feed counts as stopped:
    # the run is partial and the monthly archive covers the gap. Both feeds
    # normally move many times a day; 36 hours tolerates a quiet weekend night.
    placsp_stale_hours: int = field(
        default_factory=lambda: _env_int("DGATE_PLACSP_STALE_HOURS", 36))
    placsp_max_pages: int = field(
        default_factory=lambda: _env_int("DGATE_PLACSP_MAX_PAGES", 120))

    # --- catch-up --------------------------------------------------------
    # A cron entry only fires while the process is alive, so a machine that is
    # off overnight loses that slot entirely. On every start the worker asks how
    # stale each source is and covers the gap.
    catch_up_on_start: bool = field(
        default_factory=lambda: _env("DGATE_CATCH_UP", "1").strip() not in ("0", "false", "no"))
    # A gap of a month is a decision for a person, not something to pull
    # silently at start-up.
    catch_up_max_days: int = field(
        default_factory=lambda: _env_int("DGATE_CATCH_UP_MAX_DAYS", 7))


    def s3_settings(self) -> dict[str, Any]:
        """Client arguments, with empty values dropped rather than passed as None.

        Credentials left unset fall through to the environment and instance
        metadata, which is how a deployment should supply them: they belong in
        the process, never in a file in this repository.
        """
        options: dict[str, Any] = {"region_name": self.s3_region}
        if self.s3_endpoint:
            options["endpoint_url"] = self.s3_endpoint
        if self.s3_access_key and self.s3_secret_key:
            options["aws_access_key_id"] = self.s3_access_key
            options["aws_secret_access_key"] = self.s3_secret_key
        return options

    def floor(self, source_code: str, when: date | None = None) -> int | None:
        """The minimum a healthy run should collect on the given day.

        None means the source has no floor yet, which is honest for a connector
        whose volumes have not been measured. Zero is a real floor: it says
        "nothing is expected today", which is the correct expectation for TED
        on a Monday.
        """
        per_day = self.floors.get(source_code)
        if per_day is None:
            return None
        return per_day.get((when or date.today()).weekday())


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()


def reset_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    settings.cache_clear()
