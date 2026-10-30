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
# France. Measured per publication day over three weeks to 21 September 2026,
# minimum of each weekday: Mon 171, Tue 271, Wed 361, Thu 383, Fri 393, Sat 106,
# Sun 283. BOAMP publishes seven days a week, and Saturday is a fifth of a
# Friday, so a flat number would either never fire or fire every Monday. Each
# floor is about 40% of the two preceding days the run covers:
#
#   run day    window covers      measured min   floor
#   Monday     Sat, Sun           389            150
#   Tuesday    Sun, Mon           454            180
#   Wednesday  Mon, Tue           442            175
#   Thursday   Tue, Wed           632            250
#   Friday     Wed, Thu           744            290
#   Saturday   Thu, Fri           776            310
#   Sunday     Fri, Sat           499            200
_BOAMP_FLOORS = {0: 150, 1: 180, 2: 175, 3: 250, 4: 290, 5: 310, 6: 200}   # Monday = 0

# The Netherlands. Measured per publication day over 2026 to 10 October (283
# days): Mon p10 21, Tue 56, Wed 85, Thu 90, Fri 74, Sat 16, Sun 47. The run
# reads the two days before it, so each floor is about 40% of the two
# preceding days' tenth-percentile sum:
#
#   run day    window covers      p10 sum    floor
#   Monday     Sat, Sun             63         25
#   Tuesday    Sun, Mon             68         25
#   Wednesday  Mon, Tue            77         30
#   Thursday   Tue, Wed           141         55
#   Friday     Wed, Thu           175         70
#   Saturday   Thu, Fri           164         65
#   Sunday     Fri, Sat            90         35
_TENDERNED_FLOORS = {0: 25, 1: 25, 2: 30, 3: 55, 4: 70, 5: 65, 6: 35}   # Monday = 0

# Germany, the national notice service. The run reads three publication days. Measured
# 13-14 October 2026: a weekday 732 to 1,035 files, Sunday 506; the per-day check in
# `run_de_bkms` is the sharp one (290), this floor only catches a run that read next to
# nothing. Flat: the window always holds one weekday and two other days.
_DE_BKMS_FLOORS = {d: 400 for d in range(7)}

# Sweden. Not a daily feed: the whole register of application rounds is fetched every
# night and the question is whether all of it arrived. 3,840 rounds on 10 October 2026,
# growing; the floor is under 80% of that so a shortfall is loud and ordinary growth
# is not.
_VINNOVA_FLOORS = {d: 3000 for d in range(7)}

# France's defence innovation agency. About 37 pages on 10 October 2026 (17 current, 19
# closed, RAPID); the floor is under two thirds of that, so a list that came back
# half empty is loud and a few calls closing are not.
_AID_FLOORS = {d: 20 for d in range(7)}

# Finland's defence ministry research call. One page a year, sometimes two while the
# new year's is posted before the old one is taken down; the floor is one.
_MATINE_FLOORS = {d: 1 for d in range(7)}

# Grants. Not a daily feed: the in-scope set of calls is a standing population
# that the portal republishes whole, measured at 150 on 24 September 2026 (40
# defence, 110 dual-use). The floor asks one question -- did the whole reference
# data document arrive and did the scope filter still match it? -- so it is well
# below the population and flat across the week. Around the turn of a year the
# open set is at its smallest, which is what 50 leaves room for.
_EU_PORTAL_FLOORS = {day: 50 for day in range(7)}

# WP-139 (r8 audit: run 488 of 25 Oct fetched 0 with expected_min 0 and was "success"). The TED award reader's floor was
# only the notices it asked (WP-103), so a day on which nothing was asked passed. It reads the core result notices the
# 06:15 TED run brought: measured per TED publication day, 7 Sep - 23 Oct 2026, 5 to 27 (mean 13), Monday to Friday, none
# at weekends. The 14:10 run of Tuesday to Saturday finds one publication day; Sunday's and Monday's find none. The floor
# is about 40% of the smallest day and counts the whole UTC day: a second run after a catch-up that read them all is not
# short (`awards.run_awards`).
_TED_AWARDS_FLOORS = {0: 0, 1: 2, 2: 2, 3: 2, 4: 2, 5: 2, 6: 0}   # Monday = 0

# Spain, the national subsidies register. The run scans every call central
# government registered in a fourteen-day window, then keeps the few a supplier
# could answer, so what the floor guards is the scan: 1,344 calls in the 279 days
# of 2026 to 6 October, 4.8 a day, 67 expected in a window. 15 is a fifth of that
# and flat across the week -- registrations bunch on weekdays, but a fortnight
# always contains ten of them.
_BDNS_FLOORS = {day: 15 for day in range(7)}

# Poland, NCBR. Not a feed but a standing list: the API returns every competition it
# has ever listed, 364 on 6 October 2026, and the count only grows. The floor asks
# whether the whole list arrived; 300 leaves room for the portal pruning its oldest
# entries and nowhere near enough to hide a walk that stopped at the second page.
_NCBR_FLOORS = {day: 300 for day in range(7)}

# Networks (WP-26). Monthly, whole-population jobs. CORDIS: the SPARQL service held 72,534
# organisations, 80,208 projects and 398,584 participations on 17 October 2026, 551,000 rows in
# all; the floor is under three quarters of that. EDF factsheets: 61 + 41 + 60 + 63 + 61 files
# on the five results pages (2021 to 2025); 150 asks whether the pages were reached at all.
# These are NOT in the weekday-floor table below, which `/v1/health` also reads as "this source has
# a daily rhythm" and would call a monthly source stale after 36 hours: they are plain settings
# (`Settings.cordis_floor`, `Settings.edf_floor`).


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
        "fr_boamp": _weekday_floors("DGATE_FLOOR_FR_BOAMP", _BOAMP_FLOORS),
        "nl_tenderned": _weekday_floors("DGATE_FLOOR_NL_TENDERNED", _TENDERNED_FLOORS),
        "de_bkms": _weekday_floors("DGATE_FLOOR_DE_BKMS", _DE_BKMS_FLOORS),
        "eu_portal": _weekday_floors("DGATE_FLOOR_EU_PORTAL", _EU_PORTAL_FLOORS),
        "ted_awards": _weekday_floors("DGATE_FLOOR_TED_AWARDS", _TED_AWARDS_FLOORS),
        "es_bdns": _weekday_floors("DGATE_FLOOR_ES_BDNS", _BDNS_FLOORS),
        "pl_ncbr": _weekday_floors("DGATE_FLOOR_PL_NCBR", _NCBR_FLOORS),
        "se_vinnova": _weekday_floors("DGATE_FLOOR_SE_VINNOVA", _VINNOVA_FLOORS),
        "fr_aid": _weekday_floors("DGATE_FLOOR_FR_AID", _AID_FLOORS),
        "fi_matine": _weekday_floors("DGATE_FLOOR_FI_MATINE", _MATINE_FLOORS),
        # pl_atlas has no floor on purpose. A floor answers "did today's feed
        # arrive?"; this source is a one-off historical load with no daily
        # rhythm, and a resumed run legitimately reads almost nothing because
        # the rest already landed. None means "not measured", which is honest,
        # and finish_run leaves such a run `success` rather than `partial`.
    }


@dataclass(frozen=True)
class Settings:
    # --- database -------------------------------------------------------
    dsn: str = field(repr=False, default_factory=lambda: _env(
        "DGATE_DSN", "postgresql://dgate:dgate@localhost:5432/dgate"))
    # WP-114: every run of a scheduled job is recorded in `job_run` (worker.run_job); "0" turns it off (the unit tests,
    # which have no database)
    job_runs: bool = field(default_factory=lambda: os.environ.get("DGATE_JOB_RUNS") != "0")
    # WP-96: the folder of the defence buyer lists (seeds/); empty: found next to the package, in the working directory or
    # at /app/seeds (`pipeline.seeds_dir`)
    seeds_dir: str = field(default_factory=lambda: _env("DGATE_SEEDS_DIR", ""))
    # The public API's own connection, a role that can only read (migration 0024).
    # Unset means it uses `dsn`, so a rollout can move the API first.
    api_dsn: str | None = field(repr=False, default_factory=lambda: os.environ.get("DGATE_API_DSN") or None)
    # The account endpoints' own role (migration 0027): it alone may read and write the
    # app_* tables. Unset means `dsn`, as for the API role.
    app_dsn: str | None = field(repr=False, default_factory=lambda: os.environ.get("DGATE_APP_DSN") or None)
    # How many database connections one API process holds at once, per role, and how long a request waits for a free
    # one before it is answered 503 with Retry-After (db.bounded_connect). The roles allow 30 (dgate_api) and 10
    # (dgate_app), migrations 0024 and 0027; the API runs one process with a pool of 40 threads, so without a bound a
    # burst of 40 requests exceeded the role ("too many connections for role dgate_api", 18 October 2026) and pages
    # said "could not be loaded". The rest of the role's limit is left to the health check and an operator's psql.
    api_connections: int = field(default_factory=lambda: _env_int("DGATE_API_CONNECTIONS", 24))
    app_connections: int = field(default_factory=lambda: _env_int("DGATE_APP_CONNECTIONS", 8))
    pool_wait_ms: int = field(default_factory=lambda: _env_int("DGATE_POOL_WAIT_MS", 3000))
    # Shared secret of the site's server and the account API: the site sends it in
    # `X-DG-Internal`, and the API refuses an account or counter call without it, so the
    # network boundary is not the only control. Unset (tests, development) keeps the
    # header checks alone. It also keys the HMAC of the sign-in throttle counters;
    # `app_password` (the accounts role's login) is the fallback key when it is unset.
    internal_secret: str = field(repr=False, default_factory=lambda: _env("DGATE_INTERNAL_SECRET", ""))
    app_password: str = field(repr=False, default_factory=lambda: _env("DGATE_APP_PASSWORD", ""))
    # `production` on the deployed services (infra/docker-compose.yml). There the internal secret
    # is required: without it a compromised container on the compose network could pass for the
    # site's server (QA M10). `require_production_secrets` refuses to start the API.
    env: str = field(default_factory=lambda: _env("DGATE_ENV", "").strip().lower())
    # The per-address request limiter. On unless DGATE_RATE_LIMIT=0 (the test suite
    # makes hundreds of requests from one "address" and says so in conftest).
    rate_limit: bool = field(default_factory=lambda: os.environ.get("DGATE_RATE_LIMIT") != "0")
    # Interactive API docs and the OpenAPI document are off unless asked for: they
    # describe every parameter to anyone, which is wanted in development only.
    docs_enabled: bool = field(default_factory=lambda: os.environ.get("DGATE_DOCS") == "1")
    # PLACSP award winners (WP-60) are stored, not served, until the owner has read the reuse terms
    # (docs/sources/es_placsp.md) and decided: the supplier map leaves them out unless this is "true".
    placsp_awards_public: bool = field(
        default_factory=lambda: os.environ.get("DGATE_PLACSP_AWARDS_PUBLIC", "false").strip().lower() == "true")
    # WP-154: the paid part of the company signals (/v1/account/signals: the full lists and the site's CSV). Closed unless
    # "true"; the first rows of each signal are public either way (`signals.FREE_ROWS`).
    signals_full_open: bool = field(
        default_factory=lambda: os.environ.get("DGATE_SIGNALS_FULL_OPEN", "false").strip().lower() == "true")
    # The monthly PLACSP archive catch-up of the award results (WP-61, `worker.job_placsp_awards_catchup`): a
    # safety net behind the nightly walk, which collects them already. Off unless this is "true" (one download of
    # the previous month's archive, about 400 MB, on the 3rd of each month).
    placsp_awards_catchup: bool = field(
        default_factory=lambda: os.environ.get("DGATE_PLACSP_AWARDS_CATCHUP", "false").strip().lower() == "true")
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
    s3_access_key: str | None = field(repr=False,
        default_factory=lambda: os.environ.get("DGATE_S3_ACCESS_KEY") or None)
    s3_secret_key: str | None = field(repr=False,
        default_factory=lambda: os.environ.get("DGATE_S3_SECRET_KEY") or None)
    # The `sftp` backend: a directory on an SSH host, in practice a Hetzner
    # Storage Box. `sftp_root` is relative to the login directory, so with a
    # sub-account whose home is the project's directory it is just `store`.
    # The key file is a path, never the key: it is mounted into the container
    # and does not live in the environment or in the repository.
    sftp_host: str | None = field(default_factory=lambda: os.environ.get("DGATE_SFTP_HOST") or None)
    sftp_port: int = field(default_factory=lambda: _env_int("DGATE_SFTP_PORT", 23))
    sftp_user: str | None = field(default_factory=lambda: os.environ.get("DGATE_SFTP_USER") or None)
    sftp_key_file: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_SFTP_KEY_FILE") or None)
    sftp_known_hosts: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_SFTP_KNOWN_HOSTS") or None)
    sftp_root: str = field(default_factory=lambda: _env("DGATE_SFTP_ROOT", "store"))
    # Hetzner caps simultaneous sessions per box and a second project shares it,
    # so this stays small however many threads write.
    sftp_connections: int = field(default_factory=lambda: _env_int("DGATE_SFTP_CONNECTIONS", 4))
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

    # --- language model (eligibility extraction; the worker only) ----------
    # The key is read from the environment and never written to a file in the repository.
    # `llm_monthly_cap_usd` is our own stop: the provider's project limit is the real one.
    # The prices are per million tokens and deliberately on the high side of the published
    # ones, so that the counter stops early rather than late.
    openai_api_key: str = field(repr=False, default_factory=lambda: _env("DGATE_OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: _env("DGATE_OPENAI_MODEL", ""))
    llm_monthly_cap_usd: float = field(
        default_factory=lambda: float(_env("DGATE_LLM_MONTHLY_CAP_USD", "5") or 5))
    llm_price_in_per_m: float = field(
        default_factory=lambda: float(_env("DGATE_LLM_PRICE_IN_PER_M", "0.30") or 0.30))
    llm_price_out_per_m: float = field(
        default_factory=lambda: float(_env("DGATE_LLM_PRICE_OUT_PER_M", "1.50") or 1.50))

    # --- mail (sign-in links, alert digests) ----------------------------
    # Accounts are "open" only when mail can actually be delivered: without a relay a
    # sign-in link would be issued and never arrive. The password is read from the
    # environment, never from a file in the repository.
    smtp_host: str | None = field(default_factory=lambda: os.environ.get("DGATE_SMTP_HOST") or None)
    smtp_port: int = field(default_factory=lambda: _env_int("DGATE_SMTP_PORT", 587))
    smtp_user: str | None = field(default_factory=lambda: os.environ.get("DGATE_SMTP_USER") or None)
    smtp_password: str | None = field(repr=False,
        default_factory=lambda: os.environ.get("DGATE_SMTP_PASSWORD") or None)
    smtp_from: str | None = field(default_factory=lambda: os.environ.get("DGATE_SMTP_FROM") or None)
    # starttls (587), ssl (465) or none (a relay on this host only: ops/mailer.py refuses it for any other).
    smtp_security: str = field(default_factory=lambda: _env("DGATE_SMTP_SECURITY", "starttls"))
    # WP-123, development and tests only: write every mail as an .eml file into this directory instead of
    # sending it (ops/mailer.py). Ignored when DGATE_ENV is production.
    mail_catcher_dir: str | None = field(default_factory=lambda: os.environ.get("DGATE_MAIL_CATCHER_DIR") or None)
    # WP-123: the key of the account secrets that the server reads back or compares (sealed TOTP keys, recovery
    # code HMACs, throttle counter HMACs). The API's own: the site's server does not hold it, unlike
    # DGATE_INTERNAL_SECRET. Without it (development) the internal secret is the key; in production accounts
    # stay closed until it is set (accounts.accounts_problem).
    account_key: str = field(repr=False, default_factory=lambda: _env("DGATE_ACCOUNT_KEY", ""))
    # WP-140: the owner's switch. In production accounts stay closed, whatever the relay, the notice and the key
    # say, until DGATE_ACCOUNTS_OPEN=1 (any other value, or none, is closed). Development and tests ignore it.
    accounts_open: bool = field(default_factory=lambda: _env("DGATE_ACCOUNTS_OPEN", "0").strip() == "1")
    # WP-152: the company report (a supplier page's print-ready report, a paid feature, `billing.FEATURES`) exists only with
    # DGATE_COMPANY_REPORT_OPEN=1; off (the default), no account may open it and the supplier page does not offer it.
    company_report_open: bool = field(default_factory=lambda: _env("DGATE_COMPANY_REPORT_OPEN", "0").strip() == "1")
    # WP-155: the one company report open to everyone (signed in or not, uncounted), linked from the report's paywall as a
    # sample. A supplier slug or its id; Indra Sistemas SA by default (a large prime with some 400 contracts on the map).
    sample_report_slug: str = field(default_factory=lambda: _env("DGATE_SAMPLE_REPORT_SLUG", "406963-indra-sistemas-sa").strip())
    # WP-153: the data API with keys (dgate/apikeys.py), the owner's switch: closed until DGATE_API_KEYS_OPEN=1. Closed,
    # no key is issued and a request that presents one is refused (401); keys already issued are listed and revocable.
    api_keys_open: bool = field(default_factory=lambda: _env("DGATE_API_KEYS_OPEN", "0").strip() == "1")
    # The sources a key-authenticated request may read: the ones docs/research/DATA_LICENCES_2026-10-27.md finds
    # resellable, decided by the owner. Comma-separated source codes; TED and TenderNed (CC0) by default (WP-159). Not
    # BKMS (inactive, GDPR items open); Vinnova feeds calls, which a key does not read.
    api_key_sources: tuple[str, ...] = field(default_factory=lambda: tuple(
        s.strip() for s in _env("DGATE_API_KEY_SOURCES", "ted,nl_tenderned").split(",") if s.strip()))
    # WP-126: the file the accounts security log is written to (JSON lines), kept to 90 days by
    # dgate.ops.logprune. Unset (development, tests): the log goes to stderr as before.
    security_log: str | None = field(default_factory=lambda: os.environ.get("DGATE_SECURITY_LOG") or None)
    # The public address links in mail point at.
    site_url: str = field(default_factory=lambda: _env("DGATE_SITE_URL", "https://defencegatehub.com"))

    # --- payments (WP-124): Creem, merchant of record. Billing is open only when the key, the webhook secret and
    # every product id are set (billing.billing_problem); values live on the server, never in a file here.
    creem_api_key: str = field(repr=False, default_factory=lambda: _env("DGATE_CREEM_API_KEY", ""))
    creem_webhook_secret: str = field(repr=False, default_factory=lambda: _env("DGATE_CREEM_WEBHOOK_SECRET", ""))
    # B5: the secret being replaced, accepted as well while a rotation is under way (runbook in docs/verification/accounts/wp124-selfcheck.md).
    creem_webhook_secret_previous: str = field(
        repr=False, default_factory=lambda: _env("DGATE_CREEM_WEBHOOK_SECRET_PREVIOUS", ""))
    # Test mode (Creem's test-api host, test keys, test cards) unless DGATE_CREEM_TEST_MODE=0.
    creem_test_mode: bool = field(default_factory=lambda: _env("DGATE_CREEM_TEST_MODE", "1").strip() != "0")
    # Development and tests only: a local stand-in for Creem's API (tests/creem_mock.py). Ignored in production.
    creem_api_url: str = field(default_factory=lambda: _env("DGATE_CREEM_API_URL", ""))
    creem_products: dict[str, str] = field(default_factory=lambda: {
        key: _env(f"DGATE_CREEM_PRODUCT_{key.upper()}", "").strip()
        for key in ("pro_monthly", "pro_yearly", "team_monthly", "team_yearly",
                    "consultant_monthly", "consultant_yearly", "founding_yearly")})

    # --- alerting -------------------------------------------------------
    # All optional. Unconfigured means log-only: an alerting backend must
    # never be able to take the pipeline down with it.
    healthchecks_base: str | None = field(
        default_factory=lambda: os.environ.get("DGATE_HEALTHCHECKS_BASE"))
    telegram_token: str | None = field(repr=False,
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
    boamp_hour: int = field(default_factory=lambda: _env_int("DGATE_BOAMP_HOUR", 5))
    boamp_minute: int = field(default_factory=lambda: _env_int("DGATE_BOAMP_MINUTE", 45))
    # The Dutch platform, ten minutes after the French bulletin and before TED.
    tenderned_hour: int = field(default_factory=lambda: _env_int("DGATE_TENDERNED_HOUR", 5))
    tenderned_minute: int = field(default_factory=lambda: _env_int("DGATE_TENDERNED_MINUTE", 55))
    # The German notice service. The scheduled job does nothing while the source is inactive.
    de_bkms_hour: int = field(default_factory=lambda: _env_int("DGATE_DE_BKMS_HOUR", 6))
    de_bkms_minute: int = field(default_factory=lambda: _env_int("DGATE_DE_BKMS_MINUTE", 5))
    # The reference data document is 124 MiB and is rebuilt by the Commission
    # overnight; 04:20 is before the tender runs so a deadline that moved is
    # known by the time the morning health report is written.
    eu_portal_hour: int = field(default_factory=lambda: _env_int("DGATE_EU_PORTAL_HOUR", 4))
    eu_portal_minute: int = field(default_factory=lambda: _env_int("DGATE_EU_PORTAL_MINUTE", 20))
    # Fifteen minutes after the calendar, so the topics it added are read the
    # same morning rather than the next one.
    # Spain's register, after the EU grant jobs and before the French tender run.
    bdns_hour: int = field(default_factory=lambda: _env_int("DGATE_BDNS_HOUR", 5))
    bdns_minute: int = field(default_factory=lambda: _env_int("DGATE_BDNS_MINUTE", 5))
    # Poland's competitions, after the Spanish register and before the French tenders.
    ncbr_hour: int = field(default_factory=lambda: _env_int("DGATE_NCBR_HOUR", 5))
    ncbr_minute: int = field(default_factory=lambda: _env_int("DGATE_NCBR_MINUTE", 25))
    # Sweden's agency, straight after Poland's competitions.
    vinnova_hour: int = field(default_factory=lambda: _env_int("DGATE_VINNOVA_HOUR", 5))
    vinnova_minute: int = field(default_factory=lambda: _env_int("DGATE_VINNOVA_MINUTE", 30))
    # France's agency pages, after Sweden's register and before the French bulletin.
    aid_hour: int = field(default_factory=lambda: _env_int("DGATE_AID_HOUR", 5))
    aid_minute: int = field(default_factory=lambda: _env_int("DGATE_AID_MINUTE", 35))
    # Finland's ministry page, after France's agency pages.
    matine_hour: int = field(default_factory=lambda: _env_int("DGATE_MATINE_HOUR", 5))
    matine_minute: int = field(default_factory=lambda: _env_int("DGATE_MATINE_MINUTE", 40))
    eu_topics_hour: int = field(default_factory=lambda: _env_int("DGATE_EU_TOPICS_HOUR", 4))
    eu_topics_minute: int = field(default_factory=lambda: _env_int("DGATE_EU_TOPICS_MINUTE", 35))
    health_hour: int = field(default_factory=lambda: _env_int("DGATE_HEALTH_HOUR", 7))
    # After every ingest job has had its slot (the Polish re-read is the longest): ties
    # national notices to their TED twins (`ops/link_twins`), which no ingest does.
    twins_hour: int = field(default_factory=lambda: _env_int("DGATE_TWINS_HOUR", 9))
    twins_minute: int = field(default_factory=lambda: _env_int("DGATE_TWINS_MINUTE", 15))
    # WP-103 (owner, 24 October 2026): the TED award load (`pipeline awards`: core scope and VEAT), daily, at an hour no
    # heavy job holds (ingests 04-07, health 07, twins / families / digest 09-11, Sunday requalify 12, backups and
    # networks 02), and at most `ted_awards_limit` notices a run: 15 requests of 100 plus at most one document per
    # older-format notice, well under an hour; a backlog drains over the following days.
    ted_awards_hour: int = field(default_factory=lambda: _env_int("DGATE_TED_AWARDS_HOUR", 14))
    ted_awards_minute: int = field(default_factory=lambda: _env_int("DGATE_TED_AWARDS_MINUTE", 10))
    ted_awards_limit: int = field(default_factory=lambda: _env_int("DGATE_TED_AWARDS_LIMIT", 1500))
    # Weekly (Sunday): notices the classifier dropped at ingest and the rules now qualify,
    # for every source whose payloads are in the store, over the last `requalify_days`.
    requalify_hour: int = field(default_factory=lambda: _env_int("DGATE_REQUALIFY_HOUR", 12))
    requalify_days: int = field(default_factory=lambda: _env_int("DGATE_REQUALIFY_DAYS", 30))
    # The monthly networks jobs (CORDIS on the 5th, EDF factsheets on the 6th, the consortium
    # snapshot on the 7th), all at this hour.
    networks_hour: int = field(default_factory=lambda: _env_int("DGATE_NETWORKS_HOUR", 2))
    cordis_floor: int = field(default_factory=lambda: _env_int("DGATE_FLOOR_CORDIS", 400_000))
    edf_floor: int = field(default_factory=lambda: _env_int("DGATE_FLOOR_EDF_FACTSHEETS", 150))
    # WP-139: the EU portal's second daily run (`pipeline.run_topic_details`, 04:35) recorded no floor (runs 409, 428, 449,
    # 485). It reads the topic pages that lack details, 1 to 150 a run; in its 18 runs of 24 Sep - 25 Oct 2026 every page
    # asked was read. Its floor is this share of the pages asked (at least one): a withdrawn topic or two stays quiet, a
    # portal that stops answering part-way is `partial`.
    eu_topics_floor_share: float = 0.5
    # Per-day official total against what a run landed (ops/controls.py); one request a day
    # per source. Off in the test suite.
    completeness_check: bool = field(
        default_factory=lambda: _env_int("DGATE_COMPLETENESS_CHECK", 1) == 1)
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
    # How long a list response (tenders, buyers, opportunities) is reused by the API
    # (listcache.py). 0 turns it off.
    list_cache_seconds: int = field(
        default_factory=lambda: _env_int("DGATE_LIST_CACHE_SECONDS", 60))
    # WP-120: the time box of a text search's one read of its matches (`tenders.search_ids`); 0 (the default) leaves every
    # statement to test the text per row, as before. Off until measured on production: on the synthetic archive the read
    # cost more than it saved for every word tried (docs/verification/round6/wp120-selfcheck.md, item 3).
    search_ids_ms: int = field(
        default_factory=lambda: _env_int("DGATE_SEARCH_IDS_MS", 0))
    # WP-142: searches the worker keeps a match set for (`tenders.refresh_search_sets`) beside the first term of every product
    # group, comma-separated, as typed on the site ("boots": the home page links it)
    search_set_words: list[str] = field(
        default_factory=lambda: [w.strip() for w in _env("DGATE_SEARCH_SET_WORDS", "boots").split(",") if w.strip()])
    backup_keep_days_local: int = field(
        default_factory=lambda: _env_int("DGATE_BACKUP_KEEP_DAYS_LOCAL", 7))
    # Past this age of its newest dump (on the host, and in the store) the backup is
    # stale: the worker alerts and /v1/health reports degraded. A nightly dump plus a
    # failed night plus slack: a single missed night must already be loud.
    backup_stale_hours: int = field(
        default_factory=lambda: _env_int("DGATE_BACKUP_STALE_HOURS", 30))
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
    # WP-143 (r13 deploy, 26 October 2026): a missed scheduled job (requalify_weekly, hours of one core) waits this long after
    # the worker started, so a deploy's first minutes, when the site and the API start cold, are not also its busiest.
    catch_up_jobs_delay_seconds: int = field(
        default_factory=lambda: _env_int("DGATE_CATCH_UP_JOBS_DELAY_SECONDS", 300))


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


class ConfigError(RuntimeError):
    """A setting the deployment must have and does not; raised at start-up, not at first use."""


def require_production_secrets(cfg: "Settings | None" = None) -> None:
    cfg = cfg or settings()
    if cfg.env == "production" and not cfg.internal_secret.strip():
        raise ConfigError(
            "DGATE_INTERNAL_SECRET is not set and DGATE_ENV is production: the API refuses to start. "
            "Generate one with `openssl rand -hex 32`, put it in infra/.env and redeploy api and web.")


def reset_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    settings.cache_clear()
