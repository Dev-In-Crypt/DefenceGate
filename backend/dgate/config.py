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
from functools import lru_cache
from pathlib import Path


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


def _default_floors() -> dict[str, int]:
    """Coverage floors per source.

    A run that finishes below its floor is marked ``partial``, never
    ``success``. Tune from observed volumes after two weeks of running; silent
    under-collection is the failure that quietly destroys a coverage promise.
    """
    return {
        "ted": _env_int("DGATE_FLOOR_TED", 5),
        "es_placsp": _env_int("DGATE_FLOOR_ES_PLACSP", 20),
        "es_placsp_agg": _env_int("DGATE_FLOOR_ES_PLACSP_AGG", 10),
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
    raw_backend: str = field(default_factory=lambda: _env("DGATE_RAW_BACKEND", "fs"))
    raw_dir: Path = field(default_factory=lambda: Path(_env("DGATE_RAW_DIR", "./raw")))

    # --- ingestion ------------------------------------------------------
    floors: dict[str, int] = field(default_factory=_default_floors)
    user_agent: str = field(default_factory=lambda: _env(
        "DGATE_USER_AGENT",
        "dgate/0.1 (+https://github.com/defencegate; contact in repository)"))

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
    health_hour: int = field(default_factory=lambda: _env_int("DGATE_HEALTH_HOUR", 7))
    ingest_days: int = field(default_factory=lambda: _env_int("DGATE_INGEST_DAYS", 2))

    def floor(self, source_code: str) -> int | None:
        return self.floors.get(source_code)


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()


def reset_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    settings.cache_clear()
