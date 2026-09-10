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
# Poland. The connector runs targeted queries rather than scanning the bulletin,
# so what it fetches is a fraction of the 2,200-odd notices a Polish weekday
# carries. Measured over two-day windows: 384 across a Wednesday and Thursday,
# 139 across a Saturday and Sunday. Unlike TED, the Polish bulletin does publish
# at weekends, so one number serves every day; it is set below the weekend
# figure so a quiet Monday window cannot raise a false alarm.
_EZAM_FLOORS = dict.fromkeys(range(7), 50)


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
    ingest_days: int = field(default_factory=lambda: _env_int("DGATE_INGEST_DAYS", 2))
    placsp_pages: int = field(default_factory=lambda: _env_int("DGATE_PLACSP_PAGES", 20))
    placsp_max_pages: int = field(
        default_factory=lambda: _env_int("DGATE_PLACSP_MAX_PAGES", 120))

    # --- catch-up --------------------------------------------------------
    # A cron entry only fires while the process is alive, so a machine that is
    # off overnight loses that slot entirely. On every start the worker asks how
    # stale each source is and covers the gap.
    catch_up_on_start: bool = field(
        default_factory=lambda: _env("DGATE_CATCH_UP", "1").strip() not in ("0", "false", "no"))
    catch_up_after_hours: int = field(
        default_factory=lambda: _env_int("DGATE_CATCH_UP_AFTER_HOURS", 20))
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
