"""Accounts: registration, sign-in with e-mail and password (optional TOTP), password reset,
profile, saved searches, shortlist, follows, dashboard.

Contract: docs/design/ACCOUNT_CONTRACT.md. Requirements: docs/SECURITY_REQUIREMENTS.md
(A1-A10, O1-O3). Data held: docs/DATA_PROTECTION.md. Since WP-123 (25 October 2026, built
as WP-79 on 22 October) there is no sign-in by e-mail link: a link confirms an address or
resets a password, and only the password (and the second step, when it is on) opens a
session. Accounts open by themselves once `accounts_problem()` finds nothing in the way.

The browser never calls this. The site's server (a backend for frontend) does, over the
internal network, with the session in `X-DG-Session`. Consequences that are deliberate:

  - these routes are not in the Caddy allow-list, and a request that carries an `Origin` or
    an `X-Forwarded-For` header (a browser, or something that came through the proxy) is
    refused here as well; once `DGATE_INTERNAL_SECRET` is set the site must also send it
    in `X-DG-Internal`, so the network boundary is not the only control;
  - there is no cookie on this side at all, so there is nothing to forge cross-site (A6);
  - every query on a user-owned table is scoped by the authenticated owner id in SQL (O1);
    a row owned by someone else is a 404, never a 403 and never the row.

Secrets (e-mail tokens, second-step tickets, session ids) exist in plain form only in the
response that hands them to the site and in the e-mail; the database holds SHA-256 hashes.
Passwords are Argon2id hashes, recovery codes keyed HMACs, the TOTP key is sealed
(`dgate/credentials.py`).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import math
import re
import secrets
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from . import credentials, db
from .config import settings
from .hardening import BODY_MAX, TokenBuckets, client_key
from .ops import mailer
from .ops.notify import notify

log = logging.getLogger("accounts")
# WP-123: uvicorn configures only its own loggers, so an INFO line of this one (the security log,
# `_audit`, and the export line of O3) was dropped by the root logger's WARNING default. Its own
# handler on stderr, unless the process configured logging itself (scripts, pytest).
log.setLevel(logging.INFO)
if not log.handlers and not logging.getLogger().handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(_handler)


class _JsonLine(logging.Formatter):
    """One JSON object per line with `ts` (Unix seconds), the shape dgate.ops.logprune cuts by."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"ts": record.created, "level": record.levelname, "msg": record.getMessage()})


def security_log_to_file() -> None:
    """WP-126: with DGATE_SECURITY_LOG set, this logger writes to that file only (not to the
    container's stdout, which Docker rotates by size only), and `logprune` keeps it to 90 days.
    Called at server start (api._lifespan). A path that cannot be opened stops the start."""
    path = settings().security_log
    if not path:
        return
    handler = logging.FileHandler(path, encoding="utf-8")   # append mode: survives the in-place cut
    handler.setFormatter(_JsonLine())
    for old in list(log.handlers):
        log.removeHandler(old)
    log.addHandler(handler)
    log.propagate = False

# ------------------------------------------------------------------ limits
VERIFY_TTL = timedelta(hours=24)     # A7: the confirmation link
RESET_TTL = timedelta(hours=1)       # A9: the reset link
MFA_TTL = timedelta(minutes=5)       # A10: between the password and the code
UNVERIFIED_TTL = timedelta(days=2)   # a registration not confirmed by then is deleted
SESSION_ABSOLUTE = timedelta(days=30)
SESSION_IDLE = timedelta(days=7)
LIMIT_PER_ADDRESS = 5          # account mails per hour, per address (A3)
LIMIT_PER_ADDRESS_PER_IP = 3   # ... of which one client (IPv6: one /64) may ask for 3
LIMIT_PER_IP = 20              # per client IP
LIMIT_PER_IP_CROWDED = 3       # per client IP once half of LIMIT_GLOBAL is spent
LIMIT_GLOBAL = 120             # in total; beyond it the operator is told
LOGIN_FREE = 5                 # A8: failed sign-ins per address in an hour before the delay
LOGIN_FREE_IP = 30             # ... per client IP
LOGIN_DELAY = 30               # seconds after the first counted failure, doubling each time
MAX_SEARCHES = 200             # what an export lists: every plan's ceiling (billing.SEARCH_CEILING, equal by test)
MAX_SHORTLIST = 500
MAX_FOLLOWS = 100
MAX_COUNTRIES = 20
MAX_BODY = BODY_MAX
MAX_SESSIONS = 10              # per account; signing in beyond it ends the oldest
USER_RATE = 30                 # requests a minute per account on searches and the dashboard
MAX_HITS_PER_BATCH = 200       # of the visit counter
MAX_HIT_COUNT = 10_000         # one key's count in one batch
NOTE_MAX = 500
REPORT_NAME_MAX = 80           # WP-155: the name on a consultant's company reports
SEARCH_RESULTS = 100           # how many newest matches are read to count the new ones

# The texts a registration accepts. Bump one when the published page changes: the forms then
# asks again (the form carries the versions it shows) and /me says `termsCurrent: false` for
# an account that accepted an older one. Keep in step with web/app/(public)/terms and privacy,
# and keep a dated copy of the text in docs/legal/versions/.
TERMS_VERSION = "2.2"          # published 26 October 2026 (WP-140)
PRIVACY_VERSION = "1.8"        # published 26 October 2026 (WP-148: Cloudflare as processor; 1.7 by WP-140)
# WP-123: the first privacy notice that describes accounts with a password (published as 1.7,
# docs/legal/versions/privacy-v1.7-2026-10-26.md). Accounts stay closed while the published one is
# older, whatever the mail relay says: nobody is asked for a password the notice says we do not use.
# Stays 1.7 under privacy 1.8 (WP-148): it is a lower bound (accounts_problem compares with <), and 1.8 keeps the password text.
PASSWORD_PRIVACY_VERSION = "1.7"

# What a person may pick on the pricing page and bring to /signup (WP-122 buttons). Remembered on the
# account as a choice; nothing is charged and the plan in force stays `free` until billing (WP-124) sets it.
PLANS = ("free", "pro", "team", "consultant", "founding")
BILLINGS = ("monthly", "yearly")

ROLES = ("supplier", "prime", "consultant", "grant_writer", "other")
TRACKS = ("tenders", "funding")
SCOPES = ("core", "all")
CADENCES = ("instant", "daily", "weekly", "off")
STATUSES = ("watching", "evaluating", "bidding", "submitted", "dropped")

# Providers whose "+tag" is the same mailbox. Dots are ignored only at Gmail.
PLUS_TAG_DOMAINS = {"gmail.com", "outlook.com", "hotmail.com", "live.com", "icloud.com",
                    "me.com", "proton.me", "protonmail.com", "pm.me", "fastmail.com"}
GMAIL = {"gmail.com", "googlemail.com"}

_EMAIL_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}$")
_SESSION = re.compile(r"^[A-Za-z0-9_-]{43}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_DIGITS = re.compile(r"^[0-9]{1,18}$")


class AccountError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def account_error_handler(_: Request, exc: AccountError) -> JSONResponse:
    return JSONResponse({"error": exc.code, "message": exc.message},
                        status_code=exc.status, headers=exc.headers)


# ------------------------------------------------------------------ identity
def canonical_email(raw: str) -> tuple[str, str]:
    """(canonical form for comparison, address to send to). ValueError when it is not an
    address. A1: trimmed, domain lower-cased and IDN-encoded, `+tag` and dots handled only
    for providers where they name the same mailbox."""
    text = (raw or "").strip()
    if not text or len(text) > 254 or any(c in text for c in "\r\n\t\x00 "):
        raise ValueError("not an address")
    if text.count("@") != 1:
        raise ValueError("not an address")
    local, domain = text.split("@")
    if not _EMAIL_LOCAL.match(local) or local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("not an address")
    try:
        domain = domain.strip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("not an address") from exc
    label = r"(?!-)[a-z0-9-]{1,63}(?<!-)"
    if not re.fullmatch(rf"{label}(\.{label})+", domain) or len(domain) > 253:
        raise ValueError("not an address")
    canonical_local = local.lower()
    if domain in GMAIL:
        canonical_local = canonical_local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    elif domain in PLUS_TAG_DOMAINS:
        canonical_local = canonical_local.split("+", 1)[0]
    if not canonical_local:
        raise ValueError("not an address")
    return f"{canonical_local}@{domain}", f"{local}@{domain}"


def _hash(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _server_key() -> bytes:
    """The key only the API holds (never in the database, and not on the site's server:
    DGATE_ACCOUNT_KEY, WP-123). Rotating it resets the throttle counters and makes recovery
    codes and sealed TOTP keys unusable: an account with two-step sign-in is then locked out
    until its totp_* columns and recovery codes are cleared (ponytail: one key; a key ring with
    versions if it must ever rotate). Without it (development, tests) the internal secret is
    the key; production keeps accounts closed instead (`accounts_problem`)."""
    cfg = settings()
    return (cfg.account_key or cfg.internal_secret or cfg.app_password).encode("utf-8")


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def accounts_problem() -> str | None:
    """Why accounts are closed, or None when they are open: a mail relay that is configured and
    passed its health check, a published privacy notice that describes password accounts, and in
    production a key of the API's own for the account secrets and the owner's switch
    (DGATE_ACCOUNTS_OPEN=1, WP-140: publishing the notice must not open sign-in by itself)."""
    if _version(PRIVACY_VERSION) < _version(PASSWORD_PRIVACY_VERSION):
        return "privacy notice"
    cfg = settings()
    if cfg.env == "production" and not cfg.account_key.strip():
        return "DGATE_ACCOUNT_KEY"
    if cfg.env == "production" and not cfg.accounts_open:
        return "DGATE_ACCOUNTS_OPEN"
    if not mailer.ready():
        return "mail"
    return None


def _audit(event: str, user_id: Any = None, **facts: Any) -> None:
    """The security log of the accounts: what happened to which account id, never an address,
    a password, a token, a code or a session id (test_audit_lines_hold_no_secret)."""
    extra = "".join(f" {k}={v}" for k, v in facts.items())
    log.info("account event=%s user=%s%s", event, user_id if user_id is not None else "-", extra)


def _event_key(kind: str, value: str) -> bytes:
    """Key of a throttle counter: HMAC-SHA256 under a key only the server holds. A plain hash
    of an address or an IP can be reversed by trying candidates; this cannot without the key."""
    return hmac.new(_server_key(), f"{kind}\x00{value}".encode("utf-8"), hashlib.sha256).digest()


def _secret() -> str:
    return secrets.token_urlsafe(32)      # 256 bits, 43 URL-safe characters


def _client_ip(value: str | None) -> str:
    """The throttle key of a client: its address, an IPv6 one as its /64 (a subscriber is
    handed 2^64 addresses; counted one by one the per-IP limits were no limit)."""
    try:
        return client_key(str(ipaddress.ip_address((value or "").strip())))
    except ValueError:
        return "unknown"


# ------------------------------------------------------------------ plumbing
def get_conn():
    cfg = settings()
    with db.bounded_connect(cfg.app_dsn or cfg.dsn, cfg.app_connections, cfg.pool_wait_ms / 1000) as conn:
        yield conn


def internal_headers(request: Request) -> None:
    """`internal_only` without the size check: for the billing webhook (WP-124), whose own cap is
    larger (billing.WEBHOOK_MAX, hardening.BodyLimit)."""
    secret = settings().internal_secret
    if secret:
        given = request.headers.get("x-dg-internal")
        if given is None or not hmac.compare_digest(given.encode("utf-8"), secret.encode("utf-8")):
            raise AccountError(403, "forbidden", "not available from here")
    if request.headers.get("origin") is not None or request.headers.get("x-forwarded-for") is not None:
        raise AccountError(403, "forbidden", "not available from here")


def internal_only(request: Request) -> None:
    """A6, defence in depth: the site's server calls this over the compose network and adds
    neither header. A browser sends `Origin` on a cross-site write; a request that came
    through the proxy carries `X-Forwarded-For`. Either means it is not the site, and so does
    an empty one: presence is tested, not truthiness. With DGATE_INTERNAL_SECRET set the
    site's own header `X-DG-Internal` must match it as well (a second control, not the
    network alone). The size check is a first look at a declared length; BodyLimit counts
    the bytes that really arrive."""
    internal_headers(request)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY:
        raise AccountError(413, "too_large", "request body too large")


def no_store(response: Response) -> None:
    """Nothing here is for a shared cache: the API's default for a GET is to be cacheable."""
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/v1/account", dependencies=[Depends(internal_only), Depends(no_store)])
internal_router = APIRouter(dependencies=[Depends(internal_only)])


# WP-158: the plan an association's licence gives the account `u` (dgate/associations.py): team for its admin, pro for a member.
ASSOC_PLAN_SQL = """(SELECT CASE WHEN a.admin_id = u.id THEN 'team' ELSE 'pro' END FROM association_member m
                       JOIN association a ON a.id = m.association_id AND a.licensed_at IS NOT NULL AND a.licensed_until > now()
                      WHERE m.account_id = u.id) AS assoc_plan"""
# WP-157: the workspace an account `u` is in (`wm`, `w`) and its owner's subscription and association plan, the `ws_*` columns
# of billing.plan_of. Used by `current` and ops/digest.DUE_SQL.
WS_JOIN_SQL = """LEFT JOIN workspace_member wm ON wm.user_id = u.id
             LEFT JOIN workspace w ON w.id = wm.workspace_id
             LEFT JOIN billing_subscription wb ON wb.account_id = w.owner_id"""
WS_PLAN_SQL = ("wb.plan AS ws_plan, wb.status AS ws_status, wb.current_period_end AS ws_period_end, "
               + ASSOC_PLAN_SQL.replace("u.id", "w.owner_id").replace("AS assoc_plan", "AS ws_assoc_plan"))


def current(request: Request, conn=Depends(get_conn),
            x_dg_session: str | None = Header(None)) -> dict[str, Any]:
    """The authenticated account and the session it came with, or 401. With the subscription
    (WP-124), the association's plan (WP-158) and the workspace the account is in with its owner's subscription and
    association plan (WP-157), so every gate reads the plan in force through `billing.plan_of` (PLAN_KEYS)."""
    if not x_dg_session or not _SESSION.match(x_dg_session):
        raise AccountError(401, "unauthenticated", "sign in required")
    row = conn.execute(
        f"""SELECT s.public_id AS session_id, s.id_hash, u.*, b.plan AS sub_plan, b.status AS sub_status,
                  b.current_period_end AS sub_period_end, {ASSOC_PLAN_SQL},
                  wm.workspace_id AS ws_id, wm.role AS ws_role, {WS_PLAN_SQL}
             FROM app_session s JOIN app_user u ON u.id = s.user_id
             LEFT JOIN billing_subscription b ON b.account_id = u.id
             {WS_JOIN_SQL}
            WHERE s.id_hash = %s AND s.expires_at > now()
              AND s.last_seen_at > now() - %s::interval""",
        (_hash(x_dg_session), SESSION_IDLE)).fetchone()
    if not row:
        raise AccountError(401, "unauthenticated", "sign in required")
    conn.execute("UPDATE app_session SET last_seen_at = now() "
                 "WHERE id_hash = %s AND last_seen_at < now() - interval '1 minute'",
                 (row["id_hash"],))
    return row


# The columns `current` adds to the account row for the plan gates (billing.plan_of) and the workspace (WP-157).
PLAN_KEYS = ("sub_plan", "sub_status", "sub_period_end", "assoc_plan",
             "ws_id", "ws_role", "ws_plan", "ws_status", "ws_period_end", "ws_assoc_plan")


def shared_scope(user: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    """O1 with WP-157: the SQL condition (and its parameters) of the rows an account sees in app_saved_search, app_shortlist
    and app_follow: its own, and its workspace's while its plan has the workspace (the rows stay when it has not; the
    sharing stops). One helper for every such query."""
    from .billing import may

    ws = user.get("ws_id") if user.get("ws_id") and may(user, "team_workspace") else None
    return "(owner_id = %s OR workspace_id = %s::uuid)", (user["id"], ws)


_user_buckets = TokenBuckets(capacity=USER_RATE, refill=USER_RATE / 60)


def throttled(user: dict[str, Any] = Depends(current)) -> dict[str, Any]:
    """`current`, plus a per-account bucket (30 a minute) for the calls that run a search:
    one account cannot spend the database, whatever the global limits say."""
    allowed, wait = _user_buckets.take(str(user["id"]), 1)
    if not allowed:
        raise AccountError(429, "rate_limited", "too many requests, try again shortly",
                           {"Retry-After": str(max(1, math.ceil(wait)))})
    return user


# ------------------------------------------------------------------ models
class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Register(_Body):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)   # the policy says 128: longer is its own error
    # The tick on the form, with the versions of the two texts the form showed.
    acceptTerms: bool = False
    termsVersion: str | None = Field(None, max_length=20)
    privacyVersion: str | None = Field(None, max_length=20)
    # WP-123: the plan picked on the pricing page, remembered (no payment, no entitlement).
    plan: Literal["free", "pro", "team", "consultant", "founding"] | None = None
    billing: Literal["monthly", "yearly"] | None = None


class Login(_Body):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class SecondStep(_Body):
    ticket: str = Field(max_length=64)
    code: str = Field(max_length=32)


class TokenIn(_Body):
    token: str = Field(max_length=64)


class ResetRequest(_Body):
    email: str = Field(max_length=320)


class ResetConfirm(_Body):
    token: str = Field(max_length=64)
    password: str = Field(max_length=1024)


class PasswordChange(_Body):
    currentPassword: str = Field(max_length=1024)
    newPassword: str = Field(max_length=1024)


class PasswordOnly(_Body):
    password: str = Field(max_length=1024)


class CodeIn(_Body):
    code: str = Field(max_length=32)


class TermsAcceptance(_Body):
    termsVersion: str = Field(max_length=20)
    privacyVersion: str = Field(max_length=20)


class ProfilePatch(_Body):
    role: Literal["supplier", "prime", "consultant", "grant_writer", "other"] | None = None
    tracks: list[Literal["tenders", "funding"]] | None = Field(None, max_length=2)
    countries: list[str] | None = Field(None, max_length=MAX_COUNTRIES)
    scope: Literal["core", "all"] | None = None
    cadence: Literal["instant", "daily", "weekly", "off"] | None = None
    # WP-155: the name printed on the account's company reports (Consultant); "" removes it
    reportName: str | None = Field(None, max_length=REPORT_NAME_MAX)


class DeleteAccount(_Body):
    confirm: str = Field(max_length=320)
    # WP-123: an account with a password re-enters it (a session alone, left open on a shared
    # computer, cannot delete the account).
    password: str | None = Field(None, max_length=1024)


class SearchIn(_Body):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["tender", "call", "ending"]           # WP-160: `ending`, contracts ending soon (Pro)
    filters: dict[str, Any] = Field(default_factory=dict)
    cadence: Literal["instant", "daily", "weekly", "off"] = "daily"
    clientId: str | None = Field(None, max_length=36)       # WP-157: a client profile of the workspace


class SearchPatch(_Body):
    name: str | None = Field(None, min_length=1, max_length=80)
    filters: dict[str, Any] | None = None
    cadence: Literal["instant", "daily", "weekly", "off"] | None = None
    clientId: str | None = Field(None, max_length=36)       # WP-157: null (sent) takes the search off its client


class ShortlistIn(_Body):
    status: Literal["watching", "evaluating", "bidding", "submitted", "dropped"] = "watching"
    note: str = Field("", max_length=NOTE_MAX)
    clientId: str | None = Field(None, max_length=36)       # WP-157: left out keeps the entry's client, null clears it


class StateKey(_Body):
    type: Literal["shortlist", "follow"]
    kind: str = Field(max_length=16)
    ref: str = Field(max_length=32)


class StateIn(_Body):
    keys: list[StateKey] = Field(max_length=50)


class Hit(_Body):
    route: str = Field(max_length=200)
    referrer: str = Field("", max_length=300)
    mobile: bool = False


class HitCount(Hit):
    count: int = Field(1, ge=1, le=MAX_HIT_COUNT)


class HitBatch(_Body):
    hits: list[HitCount] = Field(max_length=MAX_HITS_PER_BATCH)


# ------------------------------------------------------------------ status
_last_prune = 0.0


def _prune(conn) -> None:
    """Counters and tokens expired for more than a day, and registrations never confirmed
    within UNVERIFIED_TTL, deleted (an index on each time column). What the Privacy notice
    says is then true."""
    conn.execute("DELETE FROM app_auth_event WHERE at < now() - interval '1 day'")
    conn.execute("DELETE FROM app_auth_token WHERE expires_at < now() - interval '1 day'")
    conn.execute("DELETE FROM app_user WHERE email_verified_at IS NULL "
                 "AND created_at < now() - %s::interval", (UNVERIFIED_TTL,))
    # WP-155: the report counts of months before the last one are read by nothing (only the current month counts)
    conn.execute("DELETE FROM company_report_open WHERE month < date_trunc('month', now() AT TIME ZONE 'UTC') "
                 "- interval '1 month'")
    # WP-162: a supplier report's count is read for its month, or for its calendar year (an association's pool)
    conn.execute("DELETE FROM sell_report_use WHERE month < date_trunc('year', now() AT TIME ZONE 'UTC') - interval '1 year'")


def prune_expired(conn) -> None:
    """`_prune`, from the status call too (the site asks every minute): with no sign-in
    request rows would otherwise wait. Throttled to one pass in ten minutes per process."""
    global _last_prune
    if _last_prune and time.monotonic() - _last_prune < 600:   # 0.0: never run (a fresh host's clock is under 600)
        return
    _last_prune = time.monotonic()
    _prune(conn)


@router.get("/status")
def status(conn=Depends(get_conn)) -> JSONResponse:
    try:
        prune_expired(conn)
    except Exception:  # noqa: BLE001 - the status answer must not depend on housekeeping
        log.warning("status: prune failed")
    from .billing import billing_problem, plans_on_sale

    is_open = accounts_problem() is None
    # WP-155: `plansOnSale` tells the site whether a paid feature is the plans' yet (until then it is withheld from nobody)
    return JSONResponse({"open": is_open, "billing": is_open and billing_problem() is None,
                         "plansOnSale": plans_on_sale(),
                         "termsVersion": TERMS_VERSION,
                         "privacyVersion": PRIVACY_VERSION},
                        headers={"Cache-Control": "public, max-age=60"})


# ------------------------------------------------------------------ throttles
_last_global_page = 0.0
_page_lock = threading.Lock()


def _recent(conn, kind: str, key: str) -> int:
    """How many accepted requests this key has in the last hour. Read only: a request that
    is refused must leave nothing behind, or an attacker could fill the table and keep a
    victim's counter hot with requests that were never served."""
    return conn.execute(
        "SELECT count(*) AS n FROM app_auth_event WHERE kind = %s AND key_hash = %s "
        "AND at > now() - interval '1 hour'", (kind, _event_key(kind, key))).fetchone()["n"]


def _retry_after(conn, kind: str, key: str) -> int:
    """Seconds until the oldest counted request of this key leaves the hour: the first
    moment a request of the same kind can be accepted again."""
    row = conn.execute(
        "SELECT extract(epoch FROM min(at) + interval '1 hour' - now()) AS wait "
        "FROM app_auth_event WHERE kind = %s AND key_hash = %s "
        "AND at > now() - interval '1 hour'", (kind, _event_key(kind, key))).fetchone()
    wait = row["wait"] if row and row["wait"] is not None else 3600
    return max(1, min(3600, math.ceil(wait)))


def _page_operator(message: str) -> None:
    global _last_global_page
    with _page_lock:
        if time.monotonic() - _last_global_page < 3600:
            return
        _last_global_page = time.monotonic()
    notify(message)


def _throttle_mail(conn, canonical: str, ip: str) -> None:
    """A3, for every request that can send a mail (registration, password reset).
    Counts are read first and written only for a request that is accepted, and every
    refusal is a visible 429 with the wait (audit M2, X-6). It is no oracle: any address is
    refused the same way after the same number of requests, whether or not it has an
    account. Three layers, the smallest first:
      - one client (IPv6: one /64) asks for one address at most LIMIT_PER_ADDRESS_PER_IP
        times an hour, so a stranger needs several clients to use up a victim's five
      - an address has LIMIT_PER_ADDRESS an hour in all (the mail-bomb ceiling)
      - a client has LIMIT_PER_IP an hour, and LIMIT_PER_IP_CROWDED once half of the
        global budget is gone: six clients with twenty each can no longer switch the
        mails off for everyone, they run into their share first"""
    pair = f"{canonical}|{ip}"
    total = _recent(conn, "all", "all")
    if total >= LIMIT_GLOBAL:
        _page_operator(f"Account mail requests are over {LIMIT_GLOBAL} an hour: possible abuse.")
    ip_cap = LIMIT_PER_IP if total < LIMIT_GLOBAL // 2 else LIMIT_PER_IP_CROWDED
    for kind, value, cap in (("ip", ip, ip_cap),
                             ("addr_ip", pair, LIMIT_PER_ADDRESS_PER_IP),
                             ("addr", canonical, LIMIT_PER_ADDRESS)):
        if _recent(conn, kind, value) >= cap:
            raise AccountError(429, "rate_limited", "too many requests, try again later",
                               {"Retry-After": str(_retry_after(conn, kind, value))})
    if total >= LIMIT_GLOBAL:
        raise AccountError(429, "rate_limited", "too many requests, try again later",
                           {"Retry-After": str(_retry_after(conn, "all", "all"))})
    for kind, value in (("addr", canonical), ("addr_ip", pair), ("ip", ip), ("all", "all")):
        conn.execute("INSERT INTO app_auth_event (kind, key_hash) VALUES (%s, %s)",
                     (kind, _event_key(kind, value)))


def login_wait(failures: int, since_last: float, free: int) -> int:
    """A8: seconds before the next attempt is answered. `free` failures in the hour cost
    nothing; from there each one doubles the wait after the last, from LOGIN_DELAY up to an
    hour (12 failures of one address in an hour: locked until the hour has passed)."""
    if failures < free:
        return 0
    wait = min(3600, LOGIN_DELAY * 2 ** min(failures - free, 12))
    return max(0, math.ceil(wait - since_last))


def _login_gate(conn, canonical: str, ip: str) -> None:
    """Refuses before any password is checked while the address or the client has to wait.
    Keyed by the address typed, whether or not it has an account, so the delay itself tells
    nothing; the counters are HMACs as for the mail limits."""
    for kind, value, free in (("login_addr", canonical, LOGIN_FREE), ("login_ip", ip, LOGIN_FREE_IP)):
        row = conn.execute(
            "SELECT count(*) AS n, extract(epoch FROM now() - max(at)) AS since FROM app_auth_event "
            "WHERE kind = %s AND key_hash = %s AND at > now() - interval '1 hour'",
            (kind, _event_key(kind, value))).fetchone()
        wait = login_wait(row["n"], float(row["since"] or 0), free)
        if wait:
            raise AccountError(429, "rate_limited", "too many failed attempts, try again later",
                               {"Retry-After": str(wait)})


def _login_failed(conn, canonical: str, ip: str) -> None:
    for kind, value in (("login_addr", canonical), ("login_ip", ip)):
        conn.execute("INSERT INTO app_auth_event (kind, key_hash) VALUES (%s, %s)",
                     (kind, _event_key(kind, value)))
    conn.commit()                     # the error that follows rolls the request back


def _login_succeeded(conn, canonical: str) -> None:
    conn.execute("DELETE FROM app_auth_event WHERE kind = 'login_addr' AND key_hash = %s",
                 (_event_key("login_addr", canonical),))


# ------------------------------------------------------------------ helpers
def _open() -> None:
    """The switch: no working relay (nothing could confirm an address), no published notice
    for password accounts, or no account key in production: no accounts."""
    if accounts_problem():
        raise AccountError(503, "not_open", "sign-in is not open yet")


def _address(raw: str) -> tuple[str, str]:
    try:
        return canonical_email(raw)
    except ValueError:
        raise AccountError(422, "invalid_email", "that does not look like an e-mail address") from None


_PASSWORD_MESSAGES = {
    "too_short": f"use at least {credentials.PASSWORD_MIN} characters",
    "too_long": f"use at most {credentials.PASSWORD_MAX} characters",
    "common": "this password is too common or too easy to guess: choose another",
}


def _check_password(password: str, canonical: str) -> None:
    problem = credentials.password_problem(password, canonical)
    if problem:
        raise AccountError(422, f"password_{problem}", _PASSWORD_MESSAGES[problem])


def _disposable(conn, canonical: str) -> bool:
    return conn.execute("SELECT 1 FROM app_disposable_domain WHERE domain = %s",
                        (canonical.rsplit("@", 1)[1],)).fetchone() is not None


def _issue(conn, user_id, purpose: str, ttl: timedelta) -> str:
    raw = _secret()
    conn.execute("INSERT INTO app_auth_token (token_hash, user_id, purpose, expires_at) "
                 "VALUES (%s, %s, %s, now() + %s::interval)", (_hash(raw), user_id, purpose, ttl))
    return raw


def _spend(conn, raw: str, purpose: str) -> dict[str, Any] | None:
    """A token of this purpose, unused and unexpired, used up in the same statement: two
    requests with one token cannot both pass."""
    if not _TOKEN.match(raw or ""):
        return None
    return conn.execute(
        "UPDATE app_auth_token SET used_at = now() WHERE token_hash = %s AND purpose = %s "
        "AND used_at IS NULL AND expires_at > now() RETURNING user_id",
        (_hash(raw), purpose)).fetchone()


def _set_password(conn, user_id, password: str) -> None:
    conn.execute("UPDATE app_user SET password_hash = %s, password_changed_at = now() WHERE id = %s",
                 (credentials.hash_password(password), user_id))


def _new_session(conn, user_id, is_new: bool) -> dict[str, Any]:
    raw = _secret()                        # A5: a fresh session id at every sign-in
    conn.execute("DELETE FROM app_session WHERE user_id = %s AND expires_at <= now()", (user_id,))
    # At most MAX_SESSIONS per account: the oldest beyond the cap go (the account's own
    # session rows; a person who signs in on many devices ends the one they used least recently).
    conn.execute(
        "DELETE FROM app_session WHERE user_id = %s AND id_hash IN ("
        "  SELECT id_hash FROM app_session WHERE user_id = %s "
        "   ORDER BY created_at DESC OFFSET %s)", (user_id, user_id, MAX_SESSIONS - 1))
    expires = conn.execute(
        "INSERT INTO app_session (id_hash, user_id, expires_at) VALUES (%s, %s, now() + %s::interval) "
        "RETURNING expires_at", (_hash(raw), user_id, SESSION_ABSOLUTE)).fetchone()["expires_at"]
    return {"session": raw, "expiresAt": expires, "isNew": is_new}


MAILS = {
    "verify": ("Confirm your DefenceGate account",
               "Confirm your e-mail address to finish creating your DefenceGate account. The link works "
               "once and expires in 24 hours:\n\n{link}\n\n"
               "If you did not create an account, ignore this message. An account that is not "
               "confirmed is deleted within two days."),
    "already": ("You already have a DefenceGate account",
                "Someone, probably you, tried to create a DefenceGate account with this address. "
                "There already is one. Sign in at:\n\n{site}/signin\n\n"
                "If you do not remember the password, set a new one at {site}/reset.\n\n"
                "If it was not you, ignore this message. Nothing has changed."),
    "reset": ("Set a new DefenceGate password",
              "To set a new password for your DefenceGate account, open this link. It works once and "
              "expires in one hour:\n\n{link}\n\n"
              "Setting a new password signs out every browser signed in to the account.\n\n"
              "If you did not ask for this, ignore this message. Your password stays as it is."),
    "changed": ("Your DefenceGate password was changed",
                "The password of your DefenceGate account was just changed, and every other browser "
                "signed in to it was signed out.\n\n"
                "If this was not you, set a new password at once at {site}/reset."),
}
_MAIL_PATHS = {"verify": "/auth/verify", "reset": "/auth/reset"}


def _mail(address: str, kind: str, token: str | None = None) -> None:
    site = settings().site_url.rstrip("/")
    link = f"{site}{_MAIL_PATHS[kind]}?token={token}" if token else ""
    subject, body = MAILS[kind]
    mailer.send_mail(address, subject, body.format(site=site, link=link) + "\n")


# ------------------------------------------------------------------ registration
OK: dict[str, bool] = {"ok": True}


@router.post("/auth/register", status_code=202)
def register(body: Register, background: BackgroundTasks, conn=Depends(get_conn),
             x_dg_client_ip: str | None = Header(None)) -> dict[str, bool]:
    """A7. The answer is the same 202 for a new address, one that has an account and a
    disposable one; only the mail differs ("confirm" or "you already have an account")."""
    _open()
    canonical, display = _address(body.email)
    # The tick is required, and it is for the texts as they stand now: a form rendered
    # before a new version went live is asked again, not silently accepted.
    if not (body.acceptTerms and body.termsVersion == TERMS_VERSION
            and body.privacyVersion == PRIVACY_VERSION):
        raise AccountError(422, "terms_not_accepted",
                           "accept the terms of use and the privacy notice to create an account")
    _check_password(body.password, canonical)
    _prune(conn)
    conn.commit()                          # a request refused below does not undo it
    _throttle_mail(conn, canonical, _client_ip(x_dg_client_ip))
    password_hash = credentials.hash_password(body.password)   # always: the time says nothing
    if _disposable(conn, canonical):       # A4: refused quietly, identical answer
        return OK
    existing = conn.execute("SELECT id, email_verified_at FROM app_user WHERE email_canonical = %s "
                            "FOR UPDATE", (canonical,)).fetchone()
    if existing and existing["email_verified_at"] is not None:
        background.add_task(_mail, display, "already")
        return OK
    plan = body.plan
    billing = body.billing if plan and plan != "free" else None
    if existing:
        # Not confirmed: whoever registered it earlier never showed they hold the mailbox, so
        # the newer registration replaces it and the earlier link stops working.
        user_id = existing["id"]
        conn.execute(
            "UPDATE app_user SET password_hash = %s, password_changed_at = now(), email_display = %s, "
            "created_at = now(), terms_version = %s, privacy_version = %s, accepted_at = now(), "
            "plan_choice = %s, billing_choice = %s WHERE id = %s",
            (password_hash, display, TERMS_VERSION, PRIVACY_VERSION, plan, billing, user_id))
        conn.execute("DELETE FROM app_auth_token WHERE user_id = %s", (user_id,))
    else:
        row = conn.execute(
            "INSERT INTO app_user (email_canonical, email_display, password_hash, password_changed_at, "
            "terms_version, privacy_version, accepted_at, plan_choice, billing_choice) "
            "VALUES (%s, %s, %s, now(), %s, %s, now(), %s, %s) "
            "ON CONFLICT (email_canonical) DO NOTHING RETURNING id",
            (canonical, display, password_hash, TERMS_VERSION, PRIVACY_VERSION, plan, billing)).fetchone()
        if not row:                        # registered a moment ago by a parallel request
            return OK
        user_id = row["id"]
    _audit("registered", user_id)
    background.add_task(_mail, display, "verify", _issue(conn, user_id, "verify", VERIFY_TTL))
    return OK


@router.post("/auth/verify")
def verify(body: TokenIn, conn=Depends(get_conn)) -> dict[str, Any]:
    """Confirms the address. It does not sign in: the password does that, so a link
    forwarded or opened by a mail scanner gives nobody a session. The answer carries the plan
    chosen at registration, so the page can say it again (WP-123); nothing else."""
    row = _spend(conn, body.token, "verify")
    if not row:
        raise AccountError(400, "invalid_or_expired", "this link is not valid")
    chosen = conn.execute(
        "UPDATE app_user SET email_verified_at = coalesce(email_verified_at, now()) "
        "WHERE id = %s RETURNING plan_choice, billing_choice", (row["user_id"],)).fetchone()
    _audit("confirmed", row["user_id"])
    if not chosen["plan_choice"]:
        return OK
    return {"ok": True, "plan": chosen["plan_choice"], "billing": chosen["billing_choice"]}


# ------------------------------------------------------------------ sign-in
@router.post("/auth/login")
def login(body: Login, conn=Depends(get_conn),
          x_dg_client_ip: str | None = Header(None)) -> dict[str, Any]:
    """A8. One answer for an unknown address, an account without a password and a wrong
    password, after the same Argon2id work. An unconfirmed account is told so only after
    its password was right."""
    _open()
    canonical, _ = _address(body.email)
    ip = _client_ip(x_dg_client_ip)
    _prune(conn)
    conn.commit()
    _login_gate(conn, canonical, ip)
    user = conn.execute("SELECT id, password_hash, email_verified_at, totp_enabled_at, onboarded "
                        "FROM app_user WHERE email_canonical = %s", (canonical,)).fetchone()
    if not credentials.verify_password(body.password, user["password_hash"] if user else None):
        _login_failed(conn, canonical, ip)
        _audit("sign_in_failed", user["id"] if user else None)
        raise AccountError(401, "invalid_credentials", "the e-mail address or the password is wrong")
    if user["email_verified_at"] is None:
        raise AccountError(403, "not_verified",
                           "confirm your e-mail address first: open the link we sent you")
    if user["totp_enabled_at"] is not None:
        # The failures stay until the code is right too: a password alone must not buy a
        # fresh set of free guesses at the code.
        _audit("password_ok_second_step", user["id"])
        return {"secondStep": True, "ticket": _issue(conn, user["id"], "mfa", MFA_TTL)}
    _login_succeeded(conn, canonical)
    _audit("signed_in", user["id"])
    return _new_session(conn, user["id"], not user["onboarded"])


def _second_factor(conn, row: dict[str, Any], code: str) -> bool:
    """A TOTP code (each step once), or one unused recovery code, which is then used up."""
    secret = credentials.unseal(row["totp_secret_enc"], _server_key(), str(row["user_id"])) \
        if row["totp_secret_enc"] is not None else None
    if secret is not None:
        step = credentials.totp_step(secret, code, time.time(), row["totp_last_step"])
        if step is not None:
            conn.execute("UPDATE app_user SET totp_last_step = %s WHERE id = %s", (step, row["user_id"]))
            return True
    return conn.execute(
        "UPDATE app_recovery_code SET used_at = now() WHERE user_id = %s AND code_hash = %s "
        "AND used_at IS NULL RETURNING 1",
        (row["user_id"], credentials.recovery_code_hash(code, _server_key()))).fetchone() is not None


@router.post("/auth/login/second")
def login_second(body: SecondStep, conn=Depends(get_conn),
                 x_dg_client_ip: str | None = Header(None)) -> dict[str, Any]:
    """A10. The ticket from the password step (5 minutes) and a code. Wrong codes count as
    failed sign-ins of the address, so the delay of A8 bounds guessing."""
    fail = AccountError(400, "invalid_or_expired", "sign in again")
    if not _TOKEN.match(body.ticket):
        raise fail
    row = conn.execute(
        "SELECT t.token_hash, t.user_id, u.email_canonical, u.totp_secret_enc, u.totp_last_step, u.onboarded "
        "FROM app_auth_token t JOIN app_user u ON u.id = t.user_id "
        "WHERE t.token_hash = %s AND t.purpose = 'mfa' AND t.used_at IS NULL AND t.expires_at > now() "
        "AND u.totp_enabled_at IS NOT NULL FOR UPDATE OF t, u", (_hash(body.ticket),)).fetchone()
    if not row:
        raise fail
    ip = _client_ip(x_dg_client_ip)
    _login_gate(conn, row["email_canonical"], ip)
    if not _second_factor(conn, row, body.code):
        _login_failed(conn, row["email_canonical"], ip)
        _audit("second_step_failed", row["user_id"])
        raise AccountError(401, "invalid_code", "that code is not valid")
    conn.execute("UPDATE app_auth_token SET used_at = now() WHERE token_hash = %s", (row["token_hash"],))
    _login_succeeded(conn, row["email_canonical"])
    _audit("signed_in", row["user_id"], second_step=True)
    return _new_session(conn, row["user_id"], not row["onboarded"])


@router.post("/auth/logout", status_code=204)
def auth_logout(conn=Depends(get_conn), x_dg_session: str | None = Header(None)) -> Response:
    if x_dg_session and _SESSION.match(x_dg_session):
        gone = conn.execute("DELETE FROM app_session WHERE id_hash = %s RETURNING user_id",
                            (_hash(x_dg_session),)).fetchone()
        if gone:
            _audit("signed_out", gone["user_id"])
    return Response(status_code=204)


# ------------------------------------------------------------------ password reset
@router.post("/auth/reset/request", status_code=202)
def reset_request(body: ResetRequest, background: BackgroundTasks, conn=Depends(get_conn),
                  x_dg_client_ip: str | None = Header(None)) -> dict[str, bool]:
    """A9. The same 202 whether or not the address has an account; a mail only if it has.
    The mail goes to the address the account holds, not to the spelling typed."""
    _open()
    canonical, _ = _address(body.email)
    _prune(conn)
    conn.commit()
    _throttle_mail(conn, canonical, _client_ip(x_dg_client_ip))
    if _disposable(conn, canonical):
        return OK
    user = conn.execute("SELECT id, email_display FROM app_user WHERE email_canonical = %s",
                        (canonical,)).fetchone()
    if user:
        conn.execute("DELETE FROM app_auth_token WHERE user_id = %s AND purpose = 'reset'", (user["id"],))
        _audit("reset_requested", user["id"])
        background.add_task(_mail, user["email_display"], "reset",
                            _issue(conn, user["id"], "reset", RESET_TTL))
    return OK


@router.post("/auth/reset/confirm")
def reset_confirm(body: ResetConfirm, background: BackgroundTasks, conn=Depends(get_conn)) -> dict[str, bool]:
    """Sets the password, confirms the address (the link reached it) and signs out every
    session. A refused password does not use the link up. TOTP stays as it was: a mailbox
    alone does not pass the second step. The account is told by mail, as for a change."""
    fail = AccountError(400, "invalid_or_expired", "this link is not valid")
    if not _TOKEN.match(body.token):
        raise fail
    row = conn.execute(
        "SELECT u.email_canonical, u.email_display, u.totp_enabled_at FROM app_auth_token t "
        "JOIN app_user u ON u.id = t.user_id "
        "WHERE t.token_hash = %s AND t.purpose = 'reset' AND t.used_at IS NULL AND t.expires_at > now()",
        (_hash(body.token),)).fetchone()
    if not row:
        raise fail
    _check_password(body.password, row["email_canonical"])
    spent = _spend(conn, body.token, "reset")
    if not spent:
        raise fail
    user_id = spent["user_id"]
    _set_password(conn, user_id, body.password)
    conn.execute("UPDATE app_user SET email_verified_at = coalesce(email_verified_at, now()) WHERE id = %s",
                 (user_id,))
    conn.execute("DELETE FROM app_session WHERE user_id = %s", (user_id,))
    conn.execute("DELETE FROM app_auth_token WHERE user_id = %s AND purpose IN ('reset', 'mfa')", (user_id,))
    if row["totp_enabled_at"] is None:     # with a second step, the mailbox does not reset its delay
        _login_succeeded(conn, row["email_canonical"])
    _audit("password_reset", user_id)
    background.add_task(_mail, row["email_display"], "changed")
    return OK


# ------------------------------------------------------------------ password and TOTP in settings
def _require_password(conn, user: dict[str, Any], password: str, ip: str) -> None:
    """Re-entry of the current password, under the same delay as a sign-in."""
    _login_gate(conn, user["email_canonical"], ip)
    if not credentials.verify_password(password, user["password_hash"]):
        _login_failed(conn, user["email_canonical"], ip)
        raise AccountError(403, "wrong_password", "the current password is wrong")


@router.post("/me/password")
def change_password(body: PasswordChange, background: BackgroundTasks, conn=Depends(get_conn),
                    user=Depends(current), x_dg_client_ip: str | None = Header(None)) -> dict[str, bool]:
    """Every other session ends; this one stays. The account is told by mail."""
    _require_password(conn, user, body.currentPassword, _client_ip(x_dg_client_ip))
    _check_password(body.newPassword, user["email_canonical"])
    _set_password(conn, user["id"], body.newPassword)
    conn.execute("DELETE FROM app_session WHERE user_id = %s AND id_hash <> %s", (user["id"], user["id_hash"]))
    _audit("password_changed", user["id"])
    background.add_task(_mail, user["email_display"], "changed")
    return OK


@router.post("/me/totp/setup")
def totp_setup(body: PasswordOnly, conn=Depends(get_conn), user=Depends(current),
               x_dg_client_ip: str | None = Header(None)) -> dict[str, str]:
    """A new key, held sealed and inactive until a code from it is entered (`enable`)."""
    _require_password(conn, user, body.password, _client_ip(x_dg_client_ip))
    if user["totp_enabled_at"] is not None:
        raise AccountError(409, "totp_enabled", "two-step sign-in is already on")
    secret = credentials.new_totp_secret()
    conn.execute("UPDATE app_user SET totp_secret_enc = %s, totp_last_step = NULL WHERE id = %s",
                 (credentials.seal(secret, _server_key(), str(user["id"])), user["id"]))
    return {"secret": credentials.b32(secret), "uri": credentials.otpauth_uri(secret, user["email_display"])}


@router.post("/me/totp/enable")
def totp_enable(body: CodeIn, conn=Depends(get_conn), user=Depends(current),
                x_dg_client_ip: str | None = Header(None)) -> dict[str, list[str]]:
    """Switches the key on with a first code and hands out the recovery codes, once."""
    if user["totp_enabled_at"] is not None or user["totp_secret_enc"] is None:
        raise AccountError(409, "totp_state", "start the set-up again")
    ip = _client_ip(x_dg_client_ip)
    _login_gate(conn, user["email_canonical"], ip)
    secret = credentials.unseal(user["totp_secret_enc"], _server_key(), str(user["id"]))
    step = credentials.totp_step(secret, body.code, time.time(), None) if secret else None
    if step is None:
        _login_failed(conn, user["email_canonical"], ip)
        raise AccountError(422, "invalid_code", "that code is not valid")
    codes = credentials.new_recovery_codes()
    conn.execute("DELETE FROM app_recovery_code WHERE user_id = %s", (user["id"],))
    for code in codes:
        conn.execute("INSERT INTO app_recovery_code (user_id, code_hash) VALUES (%s, %s)",
                     (user["id"], credentials.recovery_code_hash(code, _server_key())))
    conn.execute("UPDATE app_user SET totp_enabled_at = now(), totp_last_step = %s WHERE id = %s",
                 (step, user["id"]))
    _audit("totp_on", user["id"])
    return {"recoveryCodes": codes}


@router.post("/me/totp/disable")
def totp_disable(body: PasswordOnly, conn=Depends(get_conn), user=Depends(current),
                 x_dg_client_ip: str | None = Header(None)) -> dict[str, bool]:
    _require_password(conn, user, body.password, _client_ip(x_dg_client_ip))
    conn.execute("UPDATE app_user SET totp_secret_enc = NULL, totp_enabled_at = NULL, totp_last_step = NULL "
                 "WHERE id = %s", (user["id"],))
    conn.execute("DELETE FROM app_recovery_code WHERE user_id = %s", (user["id"],))
    _audit("totp_off", user["id"])
    return OK


# ------------------------------------------------------------------ account
def _user_out(u: dict[str, Any]) -> dict[str, Any]:
    from . import billing

    return {
        "id": str(u["id"]), "email": u["email_display"], "createdAt": u["created_at"],
        "profile": {"role": u["role"], "tracks": list(u["tracks"]), "countries": list(u["countries"]),
                    "scope": u["scope"], "cadence": u["cadence"], "reportName": u.get("report_name")},
        "onboarded": u["onboarded"], "lastVisitAt": u["last_visit_at"],
        "security": {"hasPassword": u.get("password_hash") is not None,
                     "totp": u.get("totp_enabled_at") is not None},
        "terms": {"termsVersion": u.get("terms_version"), "privacyVersion": u.get("privacy_version"),
                  "acceptedAt": u.get("accepted_at"),
                  "current": (u.get("terms_version") == TERMS_VERSION
                              and u.get("privacy_version") == PRIVACY_VERSION)},
        # WP-123: `chosen` and `billing` are what the person picked on the pricing page, remembered and nothing
        # more. WP-124: `current` is the plan in force from the verified payment events (billing.plan_of),
        # `features` the paid features the account may use (all of them while no plan is on sale).
        "plan": {"current": billing.plan_of(u), "chosen": u.get("plan_choice"),
                 "billing": u.get("billing_choice")},
        # WP-153: `api_keys` while the data API's keys are open (the account area then shows API keys); WP-155: and the
        # account holds a licence (no plan grants it)
        "features": billing.features(u) + (["api_keys"] if settings().api_keys_open and u.get("api_licensed_at") else []),
        # WP-155: saved searches the plan allows, company reports a month (None: no limit)
        "limits": {"savedSearches": billing.search_limit(u), "reportsPerMonth": billing.report_limit(u)},
        # WP-157: the workspace the account is in (None: none), and whether its sharing works under the plan in force
        "workspace": {"role": u["ws_role"], "active": billing.may(u, "team_workspace")} if u.get("ws_id") else None,
    }


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏ -‮⁦-⁩]")


def clean_report_name(raw: str) -> str | None:
    """Plain text on one line: control and direction characters out, spaces collapsed. None when nothing is left.
    The site prints it as text (escaped); it is never markup."""
    text = " ".join(_CONTROL.sub(" ", raw).split())
    return text[:REPORT_NAME_MAX] or None


@router.get("/me")
def me(user=Depends(current)) -> dict[str, Any]:
    return _user_out(user)


@router.post("/me/terms")
def accept_terms(body: TermsAcceptance, conn=Depends(get_conn),
                 user=Depends(current)) -> dict[str, Any]:
    """A signed-in account accepts the current texts (the re-prompt after a new version)."""
    if body.termsVersion != TERMS_VERSION or body.privacyVersion != PRIVACY_VERSION:
        raise AccountError(422, "terms_version", "those are not the current versions")
    conn.execute("UPDATE app_user SET terms_version = %s, privacy_version = %s, accepted_at = now() "
                 "WHERE id = %s", (TERMS_VERSION, PRIVACY_VERSION, user["id"]))
    return {"termsVersion": TERMS_VERSION, "privacyVersion": PRIVACY_VERSION, "current": True}


@router.patch("/me")
def patch_me(body: ProfilePatch, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "countries" in changes and changes["countries"] is not None:
        codes = []
        for c in changes["countries"]:
            code = str(c).strip().upper()
            if not re.fullmatch(r"[A-Z]{2}", code):
                raise AccountError(422, "invalid_country", "countries are two-letter codes")
            if code not in codes:
                codes.append(code)
        changes["countries"] = codes
    if "tracks" in changes and changes["tracks"] is not None:
        changes["tracks"] = list(dict.fromkeys(changes["tracks"]))
    if changes.get("reportName") is not None:
        from .billing import require

        require(user, "branded_reports")
        conn.execute("UPDATE app_user SET report_name = %s WHERE id = %s",
                     (clean_report_name(changes["reportName"]), user["id"]))
    changes.pop("reportName", None)
    sets, params = [], []
    for key, value in changes.items():
        if value is None and key != "role":
            continue
        sets.append(f"{key} = %s")
        params.append(value)
    if sets:
        conn.execute(f"UPDATE app_user SET {', '.join(sets)} WHERE id = %s", params + [user["id"]])
    row = conn.execute("SELECT * FROM app_user WHERE id = %s", (user["id"],)).fetchone()
    row.update({k: user.get(k) for k in PLAN_KEYS})   # the plan, as `current` reads it
    done = bool(row["role"]) and bool(row["tracks"])
    if done != row["onboarded"]:
        conn.execute("UPDATE app_user SET onboarded = %s WHERE id = %s", (done, user["id"]))
        row["onboarded"] = done
    return _user_out(row)


@router.delete("/me", status_code=204)
def delete_me(body: DeleteAccount, conn=Depends(get_conn), user=Depends(current),
              x_dg_client_ip: str | None = Header(None)) -> Response:
    """Self-service deletion: the typed address, and the password when the account has one.
    The account row goes and every table that holds the account id with it (ON DELETE CASCADE):
    sessions, saved searches, shortlist, follows, confirmation and reset links, second-step
    tickets, recovery codes; the password hash and the TOTP key are columns of the row. The
    throttle counters hold no account id (keyed hashes, gone within a day)."""
    try:
        typed, _ = canonical_email(body.confirm)
    except ValueError:
        raise AccountError(422, "confirmation_mismatch", "type your e-mail address to confirm") from None
    if typed != user["email_canonical"]:
        raise AccountError(422, "confirmation_mismatch", "type your e-mail address to confirm")
    if user["password_hash"] is not None:
        _require_password(conn, user, body.password or "", _client_ip(x_dg_client_ip))
    # WP-124: a subscription Creem may still charge is cancelled first (Billing, Manage subscription): deleting
    # the account would leave it running with nobody able to manage it here. Once cancelled, the row goes too.
    from .billing import over

    if not over(user["sub_status"], user["sub_period_end"]):           # WP-161: expired, or a cancelled period run out
        raise AccountError(409, "subscription_active",
                           "cancel your subscription first (Billing, Manage subscription), then delete the account")
    conn.execute("DELETE FROM app_user WHERE id = %s", (user["id"],))   # cascades to everything owned
    _audit("deleted", user["id"])
    return Response(status_code=204)


@router.get("/export")
def export(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    """Art. 15 and 20 GDPR: everything held about the account, in one document. Secrets are
    never in it (the password hash, the TOTP key, codes and tokens are said to exist, with
    their dates, not given)."""
    uid = user["id"]
    _audit("export", uid)                           # O3: logged with the account id
    held = conn.execute(
        "SELECT email_verified_at, password_changed_at, totp_enabled_at, "
        "  (SELECT count(*) FROM app_recovery_code r WHERE r.user_id = u.id AND r.used_at IS NULL) AS codes_left "
        "FROM app_user u WHERE id = %s", (uid,)).fetchone()
    return {
        "exportedAt": datetime.now(timezone.utc),
        "account": _user_out(user),
        "security": {"emailConfirmedAt": held["email_verified_at"],
                     "passwordChangedAt": held["password_changed_at"],
                     "twoStepOnSince": held["totp_enabled_at"],
                     "recoveryCodesLeft": held["codes_left"]},
        "sessions": [{"createdAt": r["created_at"], "lastSeenAt": r["last_seen_at"], "expiresAt": r["expires_at"]}
                     for r in conn.execute(
                         "SELECT created_at, last_seen_at, expires_at FROM app_session "
                         "WHERE user_id = %s ORDER BY created_at LIMIT 50", (uid,)).fetchall()],
        "searches": [{**_search_row(r), "lastAlertedAt": r["last_alerted_at"]} for r in conn.execute(
            "SELECT * FROM app_saved_search WHERE owner_id = %s ORDER BY created_at LIMIT %s",
            (uid, MAX_SEARCHES)).fetchall()],
        "shortlist": [{"kind": r["kind"], "ref": r["ref"], "status": r["status"], "note": r["note"],
                       "createdAt": r["created_at"], "updatedAt": r["updated_at"]}
                      for r in conn.execute(
                          "SELECT * FROM app_shortlist WHERE owner_id = %s ORDER BY created_at LIMIT %s",
                          (uid, MAX_SHORTLIST)).fetchall()],
        "subscription": [{"plan": r["plan"], "period": r["period"], "status": r["status"],
                          "currentPeriodEnd": r["current_period_end"], "refundedAt": r["refunded_at"],
                          "creemCustomerId": r["creem_customer_id"],
                          "creemSubscriptionId": r["creem_subscription_id"], "updatedAt": r["updated_at"]}
                         for r in conn.execute("SELECT * FROM billing_subscription WHERE account_id = %s",
                                               (uid,)).fetchall()],
        "apiKeys": _api_keys_export(conn, uid),
        "workspace": _workspace_export(conn, user),        # WP-157
        "apiLicensedAt": user.get("api_licensed_at"),
        "association": _association_export(conn, uid),
        # WP-155: the company reports counted against the plan (company and month)
        "companyReports": [{"month": r["month"], "organisationId": r["org_id"], "openedAt": r["opened_at"]}
                           for r in conn.execute("SELECT * FROM company_report_open WHERE account_id = %s "
                                                 "ORDER BY month, opened_at LIMIT 1000", (uid,)).fetchall()],
        # WP-162: the supplier reports counted (no field of a form is in them), the form kept with consent, the cover logo
        "supplierReports": [{"month": r["month"], "organisationId": r["org_id"], "usedAt": r["used_at"]}
                            for r in conn.execute("SELECT * FROM sell_report_use WHERE account_id = %s "
                                                  "ORDER BY used_at LIMIT 1000", (uid,)).fetchall()],
        "supplierProfile": next((r["body"] for r in conn.execute(
            "SELECT body FROM sell_profile WHERE account_id = %s", (uid,)).fetchall()), None),
        "reportLogo": next(({"type": r["type"], "bytes": r["n"], "setAt": r["set_at"]} for r in conn.execute(
            "SELECT type, octet_length(data) AS n, set_at FROM report_logo WHERE account_id = %s", (uid,)).fetchall()), None),
        "follows": [{"kind": r["kind"], "ref": r["ref"], "createdAt": r["created_at"]}
                    for r in conn.execute(
                        "SELECT * FROM app_follow WHERE owner_id = %s ORDER BY created_at LIMIT %s",
                        (uid, MAX_FOLLOWS)).fetchall()],
    }


def _association_export(conn, uid) -> dict[str, Any] | None:
    """WP-158: the account's membership of an association and its digest choice."""
    from .associations import export_row

    return export_row(conn, uid)


def _api_keys_export(conn, uid) -> list[dict[str, Any]]:
    """WP-153: name, prefix, scopes, dates and daily counts of the keys; never the hash."""
    from .apikeys import export_rows

    return export_rows(conn, uid)


def _workspace_export(conn, user: dict[str, Any]) -> dict[str, Any] | None:
    """WP-157: the membership, and for the owner the invitations it sent and the client profiles."""
    from .workspace import export_rows

    return export_rows(conn, user)


@router.get("/sessions")
def sessions(conn=Depends(get_conn), user=Depends(current)) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT public_id, created_at, last_seen_at FROM app_session "
        "WHERE user_id = %s AND expires_at > now() ORDER BY created_at DESC LIMIT 50",
        (user["id"],)).fetchall()
    return [{"id": str(r["public_id"]), "createdAt": r["created_at"], "lastSeenAt": r["last_seen_at"],
             "current": r["public_id"] == user["session_id"]} for r in rows]


@router.delete("/sessions", status_code=204)
def revoke_other_sessions(conn=Depends(get_conn), user=Depends(current)) -> Response:
    conn.execute("DELETE FROM app_session WHERE user_id = %s AND id_hash <> %s",
                 (user["id"], user["id_hash"]))
    return Response(status_code=204)


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", session_id):
        raise AccountError(404, "not_found", "no such session")
    gone = conn.execute("DELETE FROM app_session WHERE public_id = %s AND user_id = %s RETURNING 1",
                        (session_id, user["id"])).fetchone()
    if not gone:
        raise AccountError(404, "not_found", "no such session")
    return Response(status_code=204)


# ------------------------------------------------------------------ searches
_TENDER_KEYS = {"q", "country", "cpv", "status", "scope", "goods", "buyer", "from", "to", "min", "max",
                "currency", "sort", "cpvMain", "notCpv"}
_CALL_KEYS = {"q", "programme", "regime", "country", "status", "from", "to", "min", "max",
              "currency", "sort", "who"}
# WP-160: a search of contracts ending soon (expiring.py): GET /v1/tenders/ending's own filters
_ENDING_KEYS = {"country", "cpv", "buyer", "within", "estimated"}
_KEYS = {"tender": _TENDER_KEYS, "call": _CALL_KEYS, "ending": _ENDING_KEYS}
_ENUMS = {
    ("ending", "within"): {"3", "6", "12"},
    ("ending", "estimated"): {"true"},
    ("tender", "status"): {"open", "closed", "all"},
    ("tender", "scope"): {"relevant", "core", "supply", "all"},
    ("tender", "goods"): {"defence"},
    ("tender", "cpvMain"): {"true"},
    ("tender", "sort"): {"deadline-asc", "published-desc"},
    ("call", "status"): {"open", "forthcoming", "closing-soon", "closed", "all"},
    ("call", "sort"): {"deadline-asc", "deadline-desc", "budget-desc"},
    ("call", "who"): {"companies", "public"},
}
_MAX_LEN = {"q": 100, "country": 200, "cpv": 400, "notCpv": 400, "programme": 200, "regime": 100}


def clean_filters(kind: str, filters: dict[str, Any]) -> dict[str, str]:
    """The stored form of a search: only the public list endpoint's own parameters, each
    checked against the rule that endpoint applies, as strings. Anything else is refused."""
    allowed = _KEYS[kind]
    if len(json.dumps(filters)) > 2000:
        raise AccountError(422, "invalid_filters", "filters are too large")
    out: dict[str, str] = {}
    for key, raw in filters.items():
        if key not in allowed:
            raise AccountError(422, "invalid_filters", f"unknown filter: {key}")
        if raw is None or raw == "":
            continue
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise AccountError(422, "invalid_filters", f"invalid value for {key}")
        value = str(raw).replace("\x00", "").strip()
        if not value:
            continue
        if key in _MAX_LEN and len(value) > _MAX_LEN[key]:
            raise AccountError(422, "invalid_filters", f"{key} is too long")
        if (kind, key) in _ENUMS and value not in _ENUMS[(kind, key)]:
            raise AccountError(422, "invalid_filters", f"invalid value for {key}")
        if key in ("from", "to"):
            try:
                value = date.fromisoformat(value).isoformat()
            except ValueError:
                raise AccountError(422, "invalid_filters", f"{key} must be a date") from None
        elif key in ("min", "max"):
            try:
                number = float(value)
            except ValueError:
                raise AccountError(422, "invalid_filters", f"{key} must be a number") from None
            if not 0 <= number <= 1e13:
                raise AccountError(422, "invalid_filters", f"{key} is out of range")
        elif key == "currency" and not re.fullmatch(r"[A-Za-z]{3}", value):
            raise AccountError(422, "invalid_filters", "currency is a three-letter code")
        elif key == "buyer" and not _DIGITS.match(value):
            raise AccountError(422, "invalid_filters", "buyer is an id")
        out[key] = value
    return out


def _call_kwargs(kind: str, filters: dict[str, str]) -> dict[str, Any]:
    """Every parameter of the public list function, explicitly: it is called as a plain
    function here, so a default left out would be a `Query` object, not a value."""
    f = filters
    base: dict[str, Any] = {
        "q": f.get("q"), "country": f.get("country"),
        "from_": date.fromisoformat(f["from"]) if "from" in f else None,
        "to": date.fromisoformat(f["to"]) if "to" in f else None,
        "min_": float(f["min"]) if "min" in f else None,
        "max_": float(f["max"]) if "max" in f else None,
        "currency": f.get("currency"), "page": 1,
    }
    if kind == "tender":
        base.update(cpv=f.get("cpv"), status=f.get("status", "open"), scope=f.get("scope", "relevant"),
                    goods=f.get("goods"), confidence=None,
                    cpvMain=f.get("cpvMain") == "true", notCpv=f.get("notCpv"),
                    buyer=int(f["buyer"]) if "buyer" in f else None)
    else:
        base.update(programme=f.get("programme"), regime=f.get("regime"),
                    status=f.get("status", "open"), cascade=None, ukraine=None, who=f.get("who"))
    return base


CACHE_SECONDS = 120
CACHE_ENTRIES = 200            # an LRU: the least recently used entry goes first
CACHED_ITEMS = 20              # items kept per cached search; the rest of the 100 are only dated
SINGLE_FLIGHT_WAIT = 15.0      # seconds a follower waits for the one computing its key
_cache: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
_cache_lock = threading.Lock()
_inflight: dict[tuple, Future] = {}


def _cached(key: tuple, compute, ttl: float = CACHE_SECONDS):
    """LRU cache with single flight: concurrent callers of one key share one compute (the
    first computes, the others wait for its result or its error)."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            _cache.move_to_end(key)
            return hit[1]
        flight = _inflight.get(key)
        leader = flight is None
        if leader:
            flight = _inflight[key] = Future()
    if not leader:
        try:
            return flight.result(timeout=SINGLE_FLIGHT_WAIT)
        except TimeoutError:
            return compute()                 # the leader is stuck: do not wait on it forever
    try:
        value = compute()
    except BaseException as exc:
        with _cache_lock:
            _inflight.pop(key, None)
        flight.set_exception(exc)
        raise
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_ENTRIES:
            _cache.popitem(last=False)
        _inflight.pop(key, None)
    flight.set_result(value)
    return value


def _stamp(kind: str, item: dict[str, Any]):
    # When the portal first collected it, for tenders and calls alike. Not a publication
    # date: a notice published yesterday and first collected today is new today, and a
    # day compared with a timestamp missed most of them (internal audit H3).
    # WP-160: a contract ending soon is new when it entered the search's window (`expiring.entered`).
    return item.get("enteredAt") if kind == "ending" else item.get("firstSeenAt")


def _run_ending(conn, f: dict[str, str], full: bool) -> dict[str, Any]:
    """WP-160: an `ending` search: every contract of its window with when it entered it, newest entry first; the items of
    the first SEARCH_RESULTS (CACHED_ITEMS when cached) as the list shows them, each with its `enteredAt`."""
    from . import expiring

    try:
        rows = expiring.entered(conn, int(f.get("within", "12")), f.get("country"), f.get("cpv"),
                                int(f["buyer"]) if "buyer" in f else None, f.get("estimated") == "true")
    except HTTPException as exc:
        raise AccountError(422, "invalid_filters", str(exc.detail)) from None
    shown = rows[:SEARCH_RESULTS if full else CACHED_ITEMS]
    stamps = {r["id"]: r["enteredAt"] for r in shown}
    items = expiring.present(conn, [r["id"] for r in shown])
    for it in items:
        it["enteredAt"] = stamps[int(it["id"])]
    return {"total": len(rows), "items": items, "stamps": [r["enteredAt"] for r in rows]}


def run_search(conn, kind: str, filters: dict[str, str], *, full: bool = False) -> dict[str, Any]:
    """The newest SEARCH_RESULTS matches (tenders by publication, calls by deadline) and
    the total, through the same function the public endpoint is. What is cached is what the
    dashboard needs: the total, the first CACHED_ITEMS items, and the date each of all the
    matches was published or first seen (so "new since your last visit" still counts among
    the whole SEARCH_RESULTS). `full=True` is for the digest: every item, not cached."""
    from .funding import list_funding
    from .tenders import list_tenders

    def compute() -> dict[str, Any]:
        if kind == "ending":
            return _run_ending(conn, filters, full)
        kwargs = _call_kwargs(kind, filters)
        try:
            if kind == "tender":
                page = list_tenders(sort="published-desc", pageSize=SEARCH_RESULTS, conn=conn, **kwargs)
            else:
                page = list_funding(sort="deadline-asc", pageSize=SEARCH_RESULTS, conn=conn, **kwargs)
        except HTTPException as exc:
            raise AccountError(422, "invalid_filters", str(exc.detail)) from None
        items = page["items"]
        return {"total": page["total"], "items": items if full else items[:CACHED_ITEMS],
                "stamps": [_stamp(kind, i) for i in items]}

    if full:
        return compute()
    return _cached((kind, json.dumps(filters, sort_keys=True)), compute)


def _stamp_is_new(stamp: Any, since: datetime) -> bool:
    if stamp is None:
        return False
    if isinstance(stamp, datetime):
        return stamp >= since
    return datetime.combine(stamp, datetime.min.time(), tzinfo=timezone.utc) >= since


def _is_new(kind: str, item: dict[str, Any], since: datetime) -> bool:
    return _stamp_is_new(_stamp(kind, item), since)


def _new_count(result: dict[str, Any], since: datetime) -> int:
    return sum(1 for stamp in result["stamps"] if _stamp_is_new(stamp, since))


def _since(user: dict[str, Any]) -> datetime:
    return user["last_visit_at"] or (datetime.now(timezone.utc) - timedelta(days=7))


def _search_row(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(r["id"]), "name": r["name"], "kind": r["kind"], "filters": r["filters"],
            "cadence": r["cadence"], "createdAt": r["created_at"],
            "clientId": str(r["client_id"]) if r.get("client_id") else None}


# WP-155: an account's searches with their place, oldest first (0, 1, ...): the first `billing.search_limit` are run, the
# others (kept after a move to a plan with fewer) are paused, as all of them are without the feature.
RANKED_SEARCHES = ("(SELECT s.*, row_number() OVER (ORDER BY s.created_at, s.id) - 1 AS plan_rank "
                   "FROM app_saved_search s WHERE s.owner_id = %s) ranked")


def search_kind_allowed(user: dict[str, Any], kind: str) -> bool:
    """WP-160: a search of contracts ending soon (and its alert) needs `expiring_contracts` as well (Pro)."""
    from .billing import may

    return kind != "ending" or may(user, "expiring_contracts")


def _search_out(conn, r: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    from .billing import may, search_limit

    out = _search_row(r)
    out["mine"] = r["owner_id"] == user["id"]     # WP-157: a teammate's search is shown, changed only by its author
    rank = r.get("plan_rank")
    if rank is None:
        rank = conn.execute("SELECT count(*) AS n FROM app_saved_search WHERE owner_id = %s AND (created_at, id) < (%s, %s)",
                            (r["owner_id"], r["created_at"], r["id"])).fetchone()["n"]
    # WP-124: a search kept after a downgrade is not run (the paid feature stops, the data stays).
    out["paused"] = not may(user, "saved_searches") or rank >= search_limit(user) or not search_kind_allowed(user, r["kind"])
    if out["paused"]:
        out.update(matchCount=None, newCount=0, lastMatchAt=None)
        return out
    result = run_search(conn, r["kind"], r["filters"])
    since = _since(user)
    out["matchCount"] = result["total"]
    out["newCount"] = _new_count(result, since)
    out["lastMatchAt"] = None
    return out


def _owned_search(conn, search_id: str, user) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", search_id):
        raise AccountError(404, "not_found", "no such search")
    row = conn.execute("SELECT * FROM app_saved_search WHERE id = %s AND owner_id = %s",
                       (search_id, user["id"])).fetchone()
    if not row:
        raise AccountError(404, "not_found", "no such search")
    return row


def _client_filter(conn, user: dict[str, Any], client: str | None) -> tuple[str, tuple[Any, ...]]:
    """WP-157: `?client=` of a list: only the rows of that client profile of the account's workspace (404 otherwise)."""
    if client is None:
        return "", ()
    from .workspace import client_id

    return " AND client_id = %s", (client_id(conn, user, client),)


@router.get("/searches")
def list_searches(client: str | None = None, conn=Depends(get_conn), user=Depends(throttled)) -> dict[str, Any]:
    from .billing import SEARCH_CEILING, search_limit

    where, params = shared_scope(user)
    extra, extra_params = _client_filter(conn, user, client)
    # WP-157: the workspace's searches too, each ranked among its author's (the plan's number counts per author)
    rows = conn.execute(
        "SELECT * FROM (SELECT s.*, row_number() OVER (PARTITION BY s.owner_id ORDER BY s.created_at, s.id) - 1 AS plan_rank "
        f"FROM app_saved_search s WHERE {where}) ranked WHERE true{extra} ORDER BY created_at DESC LIMIT %s",
        (*params, *extra_params, SEARCH_CEILING)).fetchall()
    return {"items": [_search_out(conn, r, user) for r in rows], "limit": search_limit(user)}


@router.post("/searches", status_code=201)
def create_search(body: SearchIn, conn=Depends(get_conn), user=Depends(throttled)) -> dict[str, Any]:
    from .billing import require, search_limit
    from .workspace import client_id

    require(user, "saved_searches")
    if body.kind == "ending":
        require(user, "expiring_contracts")
    client = client_id(conn, user, body.clientId) if body.clientId is not None else None
    n = conn.execute("SELECT count(*) AS n FROM app_saved_search WHERE owner_id = %s",
                     (user["id"],)).fetchone()["n"]
    limit = search_limit(user)
    if n >= limit:
        raise AccountError(409, "limit_reached", f"at most {limit} saved searches on your plan")
    filters = clean_filters(body.kind, body.filters)
    run_search(conn, body.kind, filters)             # a filter the list endpoint refuses is refused here
    row = conn.execute(
        "INSERT INTO app_saved_search (owner_id, name, kind, filters, cadence, workspace_id, client_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
        (user["id"], body.name.strip(), body.kind, json.dumps(filters), body.cadence, user.get("ws_id"),
         client)).fetchone()
    return _search_out(conn, row, user)


@router.patch("/searches/{search_id}")
def patch_search(search_id: str, body: SearchPatch, conn=Depends(get_conn),
                 user=Depends(throttled)) -> dict[str, Any]:
    from .billing import require

    row = _owned_search(conn, search_id, user)
    require(user, "saved_searches")
    if row["kind"] == "ending":
        require(user, "expiring_contracts")
    name =body.name.strip() if body.name is not None else row["name"]
    cadence = body.cadence if body.cadence is not None else row["cadence"]
    filters = row["filters"]
    if body.filters is not None:
        filters = clean_filters(row["kind"], body.filters)
        run_search(conn, row["kind"], filters)
    client = row["client_id"]
    if "clientId" in body.model_fields_set:              # WP-157
        from .workspace import client_id

        client = client_id(conn, user, body.clientId) if body.clientId is not None else None
    row = conn.execute(
        "UPDATE app_saved_search SET name = %s, cadence = %s, filters = %s, client_id = %s "
        "WHERE id = %s AND owner_id = %s RETURNING *",
        (name, cadence, json.dumps(filters), client, search_id, user["id"])).fetchone()
    return _search_out(conn, row, user)


@router.delete("/searches/{search_id}", status_code=204)
def delete_search(search_id: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    _owned_search(conn, search_id, user)
    conn.execute("DELETE FROM app_saved_search WHERE id = %s AND owner_id = %s", (search_id, user["id"]))
    return Response(status_code=204)


class AlertStopIn(BaseModel):
    token: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.post("/alerts/unsubscribe")
def stop_alerts(body: AlertStopIn, conn=Depends(get_conn)) -> dict[str, bool]:
    """WP-161: the stop link of an alert mail (migration 0153), without signing in: every saved search of that account stops
    mailing (cadence 'off'; the searches stay). The answer is the same for a token that matches nothing."""
    row = conn.execute("UPDATE app_saved_search SET cadence = 'off' WHERE owner_id = "
                       "(SELECT id FROM app_user WHERE alerts_stop_token = %s) RETURNING owner_id", (body.token,)).fetchone()
    if row:
        _audit("alerts_unsubscribed", row["owner_id"])
    return {"done": True}


# ------------------------------------------------------------------ hydration
def _tenders_by_id(conn, ids: list[int]) -> dict[str, dict[str, Any]]:
    from .tenders import TENDER_SELECT, _present

    if not ids:
        return {}
    rows = conn.execute(f"{TENDER_SELECT} WHERE o.id = ANY(%s) AND o.is_defence "
                        f"AND NOT o.suppressed", (ids,)).fetchall()
    return {t["id"]: t for t in _present(conn, rows)}


def _calls_by_id(conn, ids: list[int]) -> dict[str, dict[str, Any]]:
    from .funding import SELECT, to_call

    if not ids:
        return {}
    rows = conn.execute(f"{SELECT} WHERE c.id = ANY(%s) AND NOT c.suppressed",
                        (ids,)).fetchall()
    return {c["id"]: c for c in (to_call(r) for r in rows)}


def _buyers_by_id(conn, ids: list[int]) -> dict[str, dict[str, Any]]:
    from .tenders import _buyer, _buyer_names, buyer_base, family_defence

    if not ids:
        return {}
    # A followed buyer may be a member of a family: it shows the family (migration 0055); WP-133: or merged into another row
    heads = {r["id"]: r["h"] for r in conn.execute(
        "SELECT i AS id, dgate_buyer_head(dgate_live_org(i)) AS h FROM unnest(%s::bigint[]) AS i", (ids,)).fetchall()}
    # The counts are the buyer list's (kept and shared: the aggregate is a pass over every core notice).
    org_ids, totals, open_n, last_published, variants = buyer_base(conn)
    at = {org: i for i, org in enumerate(org_ids)}
    found = conn.execute(
        f"""SELECT org.id, org.canonical_name, org.country, {family_defence('org')} AS is_defence_buyer
             FROM organisation org WHERE org.id = ANY(%s)""",
        ([h for h in sorted(set(heads.values())) if h in at],)).fetchall()
    rows = [{**r, "n": totals[at[r["id"]]], "open_n": open_n[at[r["id"]]],
             "last_published": last_published[at[r["id"]]], "variants": variants[at[r["id"]]]} for r in found]
    names = _buyer_names(conn, [r["id"] for r in rows])
    by_head = {r["id"]: _buyer(r, names) for r in rows}
    return {str(i): by_head[h] for i, h in heads.items() if h in by_head}


PROGRAMME_NAMES = {"EDF": "European Defence Fund", "EDIP": "European Defence Industry Programme",
                   "EDIP-USI": "EDIP Ukraine Support Instrument",
                   "HORIZON": "Horizon Europe", "DIGITAL": "Digital Europe",
                   "NATIONAL": "National programmes"}


def _programmes(conn) -> dict[str, dict[str, Any]]:
    """Programme chips (EDF, EDIP, HORIZON, DIGITAL, NATIONAL) with their open calls."""
    from .funding import EFFECTIVE_STATUS, programme_of

    rows = conn.execute(
        f"""SELECT p.code, p.name, c.topic_code, ({EFFECTIVE_STATUS} = 'open') AS is_open, c.deadline_at
              FROM call c JOIN programme p ON p.id = c.programme_id""").fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        # the chip the call is labelled with (WP-91: an EDIP or a Ukraine Support Instrument topic filed under the EDF is not EDF)
        chip = programme_of(r["code"], r["topic_code"])
        entry = out.setdefault(chip, {"code": chip, "name": PROGRAMME_NAMES.get(chip, chip),
                                      "openCount": 0})
        if r["is_open"]:
            entry["openCount"] += 1
    return out


def _hydrate_shortlist(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tenders = _tenders_by_id(conn, [int(r["ref"]) for r in rows if r["kind"] == "tender" and r["ref"].isdigit()])
    calls = _calls_by_id(conn, [int(r["ref"]) for r in rows if r["kind"] == "call" and r["ref"].isdigit()])
    out = []
    for r in rows:
        item = (tenders if r["kind"] == "tender" else calls).get(r["ref"])
        out.append({"kind": r["kind"], "ref": r["ref"], "status": r["status"], "note": r["note"],
                    "createdAt": r["created_at"], "updatedAt": r["updated_at"], "item": item,
                    "clientId": str(r["client_id"]) if r.get("client_id") else None})
    return out


# ------------------------------------------------------------------ shortlist
def _norm_ref(ref: str) -> str | None:
    """The stored form of a numeric reference: digits only, no leading zeros, so `007` and `7`
    are one item and a row can be found again by the id the page shows."""
    if not _DIGITS.fullmatch(ref) or int(ref) > 9_223_372_036_854_775_807:
        return None
    return str(int(ref))


def _check_ref(conn, kind: str, ref: str) -> str:
    """The normalised reference of an existing item, or 404."""
    if kind not in ("tender", "call"):
        raise AccountError(404, "not_found", "unknown kind")
    norm = _norm_ref(ref)
    if norm is None:
        raise AccountError(404, "not_found", "no such item")
    found = (conn.execute("SELECT 1 FROM opportunity WHERE id = %s AND is_defence AND NOT suppressed",
                              (int(norm),)).fetchone()
             if kind == "tender"
             else conn.execute("SELECT 1 FROM call WHERE id = %s AND NOT suppressed",
                                (int(norm),)).fetchone())
    if not found:
        raise AccountError(404, "not_found", "no such item")
    return norm


@router.get("/shortlist")
def get_shortlist(client: str | None = None, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    where, params = shared_scope(user)
    extra, extra_params = _client_filter(conn, user, client)
    rows = conn.execute(f"SELECT * FROM app_shortlist WHERE {where}{extra} "
                        "ORDER BY updated_at DESC LIMIT %s", (*params, *extra_params, MAX_SHORTLIST)).fetchall()
    return {"items": _hydrate_shortlist(conn, rows)}


@router.put("/shortlist/{kind}/{ref}")
def put_shortlist(kind: str, ref: str, body: ShortlistIn, conn=Depends(get_conn),
                  user=Depends(current)) -> dict[str, Any]:
    ref = _check_ref(conn, kind, ref)
    where, params = shared_scope(user)
    # WP-157: one entry per item in a workspace: a teammate's entry is the one changed (status, note, client)
    exists = conn.execute(f"SELECT owner_id, client_id FROM app_shortlist WHERE {where} AND kind = %s AND ref = %s "
                          "ORDER BY owner_id = %s DESC LIMIT 1", (*params, kind, ref, user["id"])).fetchone()
    if not exists:
        n = conn.execute("SELECT count(*) AS n FROM app_shortlist WHERE owner_id = %s",
                         (user["id"],)).fetchone()["n"]
        if n >= MAX_SHORTLIST:
            raise AccountError(409, "limit_reached", f"at most {MAX_SHORTLIST} shortlisted items")
    client = exists["client_id"] if exists else None
    if "clientId" in body.model_fields_set:
        from .workspace import client_id

        client = client_id(conn, user, body.clientId) if body.clientId is not None else None
    owner = exists["owner_id"] if exists else user["id"]
    note = body.note.replace("\x00", "").strip()
    row = conn.execute(
        """INSERT INTO app_shortlist (owner_id, kind, ref, status, note, workspace_id, client_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (owner_id, kind, ref)
           DO UPDATE SET status = EXCLUDED.status, note = EXCLUDED.note, client_id = EXCLUDED.client_id, updated_at = now()
           RETURNING *""", (owner, kind, ref, body.status, note, user.get("ws_id"), client)).fetchone()
    return _hydrate_shortlist(conn, [row])[0]


@router.delete("/shortlist/{kind}/{ref}", status_code=204)
def delete_shortlist(kind: str, ref: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    ref = _norm_ref(ref) or ""
    where, params = shared_scope(user)
    gone = conn.execute(f"DELETE FROM app_shortlist WHERE {where} AND kind = %s AND ref = %s "
                        "RETURNING 1", (*params, kind, ref)).fetchone()
    if not gone:
        raise AccountError(404, "not_found", "not on your shortlist")
    return Response(status_code=204)


# ------------------------------------------------------------------ follows
def _check_follow(conn, kind: str, ref: str) -> str:
    """The normalised reference of an existing buyer or programme, or 404."""
    if kind == "buyer":
        norm = _norm_ref(ref)
        if norm is None or not conn.execute(
                "SELECT 1 FROM organisation WHERE id = %s AND NOT suppressed",
                (int(norm),)).fetchone():
            raise AccountError(404, "not_found", "no such buyer")
        return norm
    if kind == "programme":
        if ref not in _programmes(conn):
            raise AccountError(404, "not_found", "no such programme")
        return ref
    raise AccountError(404, "not_found", "unknown kind")


def _hydrate_follows(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buyers = _buyers_by_id(conn, [int(r["ref"]) for r in rows if r["kind"] == "buyer" and r["ref"].isdigit()])
    programmes = _programmes(conn) if any(r["kind"] == "programme" for r in rows) else {}
    out = []
    for r in rows:
        item = buyers.get(r["ref"]) if r["kind"] == "buyer" else programmes.get(r["ref"])
        out.append({"kind": r["kind"], "ref": r["ref"], "createdAt": r["created_at"], "item": item})
    return out


@router.get("/follows")
def get_follows(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    where, params = shared_scope(user)
    rows = conn.execute(f"SELECT * FROM app_follow WHERE {where} ORDER BY created_at DESC LIMIT %s",
                        (*params, MAX_FOLLOWS)).fetchall()
    return {"items": _hydrate_follows(conn, rows)}


@router.put("/follows/{kind}/{ref}")
def put_follow(kind: str, ref: str, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    ref = _check_follow(conn, kind, ref)
    where, params = shared_scope(user)
    # WP-157: followed by a teammate already: that follow is the workspace's, nothing new
    exists = conn.execute(f"SELECT * FROM app_follow WHERE {where} AND kind = %s AND ref = %s "
                          "ORDER BY owner_id = %s DESC LIMIT 1", (*params, kind, ref, user["id"])).fetchone()
    if exists:
        return _hydrate_follows(conn, [exists])[0]
    n = conn.execute("SELECT count(*) AS n FROM app_follow WHERE owner_id = %s",
                     (user["id"],)).fetchone()["n"]
    if n >= MAX_FOLLOWS:
        raise AccountError(409, "limit_reached", f"at most {MAX_FOLLOWS} follows")
    row = conn.execute(
        "INSERT INTO app_follow (owner_id, kind, ref, workspace_id) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (owner_id, kind, ref) DO UPDATE SET kind = EXCLUDED.kind RETURNING *",
        (user["id"], kind, ref, user.get("ws_id"))).fetchone()
    return _hydrate_follows(conn, [row])[0]


@router.delete("/follows/{kind}/{ref}", status_code=204)
def delete_follow(kind: str, ref: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    if kind != "programme":
        ref = _norm_ref(ref) or ""
    where, params = shared_scope(user)
    gone = conn.execute(f"DELETE FROM app_follow WHERE {where} AND kind = %s AND ref = %s "
                        "RETURNING 1", (*params, kind, ref)).fetchone()
    if not gone:
        raise AccountError(404, "not_found", "not followed")
    return Response(status_code=204)


@router.post("/state")
def state(body: StateIn, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    where, params = shared_scope(user)
    for key in body.keys:
        table = "app_shortlist" if key.type == "shortlist" else "app_follow"
        extra = ", status" if key.type == "shortlist" else ""
        ref = key.ref if key.kind == "programme" else (_norm_ref(key.ref) or "")
        row = conn.execute(
            f"SELECT 1 AS saved{extra} FROM {table} WHERE {where} AND kind = %s AND ref = %s "
            "ORDER BY owner_id = %s DESC LIMIT 1", (*params, key.kind, ref, user["id"])).fetchone()
        entry: dict[str, Any] = {"type": key.type, "kind": key.kind, "ref": key.ref, "saved": row is not None}
        if row and key.type == "shortlist":
            entry["status"] = row["status"]
        items.append(entry)
    return {"items": items}


# ------------------------------------------------------------------ dashboard
PULSE_SECONDS = 600


def pulse(conn) -> dict[str, Any]:
    """Public figures only: counts of notices, never spend or market size."""
    from . import api
    from .tenders import CORE, NOT_AN_AMENDMENT

    def compute() -> dict[str, Any]:
        eff = api.EFFECTIVE_STATUS_SQL
        base = f"o.is_defence AND NOT o.suppressed AND {CORE}"
        row = conn.execute(f"""
            SELECT count(*) FILTER (WHERE o.published_at >= now() - interval '30 days') AS p30,
                   count(*) FILTER (WHERE o.published_at >= now() - interval '60 days'
                                      AND o.published_at < now() - interval '30 days') AS prev30,
                   count(*) FILTER (WHERE {eff} = 'open') AS open_n,
                   count(*) FILTER (WHERE {eff} = 'open' AND o.deadline_at >= now()
                                      AND o.deadline_at < now() + interval '14 days') AS closing14
              FROM opportunity o WHERE {base}""").fetchone()
        amended = conn.execute(f"""
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE EXISTS (
                        SELECT 1 FROM opportunity_version v
                         WHERE v.opportunity_id = o.id AND v.version > 1
                           AND v.changed_fields <> ARRAY['published_at']
                           AND NOT EXISTS (SELECT 1 FROM opportunity_version_note nn
                                            WHERE nn.opportunity_version_id = v.id
                                              AND nn.kind IN {NOT_AN_AMENDMENT}))) AS amended
              FROM opportunity o
             WHERE {base} AND o.published_at >= now() - interval '30 days'""").fetchone()
        window = conn.execute(f"""
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY
                     extract(epoch FROM (o.deadline_at - o.published_at)) / 86400.0) AS median_days
              FROM opportunity o
             WHERE {base} AND o.published_at >= now() - interval '90 days'
               AND o.deadline_at IS NOT NULL AND o.deadline_at > o.published_at""").fetchone()
        n = amended["n"] or 0
        return {
            "asOf": datetime.now(timezone.utc),
            "tendersPublished30d": row["p30"], "tendersPublishedPrev30d": row["prev30"],
            "openTenders": row["open_n"], "closingWithin14d": row["closing14"],
            "amendedShare30d": round(amended["amended"] / n, 3) if n else 0.0,
            "medianWindowDays": round(float(window["median_days"]), 1)
            if window["median_days"] is not None else None,
        }

    return _cached(("pulse",), compute, PULSE_SECONDS)


def _deadline(item: dict[str, Any]) -> datetime | None:
    d = item.get("deadline")
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return None


@router.get("/dashboard")
def dashboard(conn=Depends(get_conn), user=Depends(throttled)) -> dict[str, Any]:
    from .tenders import tender_versions

    now = datetime.now(timezone.utc)
    since = _since(user)
    horizon = now + timedelta(days=14)

    from .billing import may, search_limit

    searches = conn.execute(   # WP-124: kept, not run; WP-155: those over the plan's number neither
        f"SELECT * FROM {RANKED_SEARCHES} WHERE plan_rank < %s ORDER BY created_at DESC LIMIT 6",
        (user["id"], search_limit(user))).fetchall() if may(user, "saved_searches") else []
    matches, searched_items = [], []
    for s in searches:
        if not search_kind_allowed(user, s["kind"]):
            continue
        res = run_search(conn, s["kind"], s["filters"])
        fresh = [i for i in res["items"] if _is_new(s["kind"], i, since)]
        matches.append({"search": {"id": str(s["id"]), "name": s["name"], "kind": s["kind"]},
                        "newCount": _new_count(res, since), "totalCount": res["total"],
                        "items": (fresh or res["items"])[:5]})
        # WP-160: an ending search's items are tenders (their deadline long passed)
        searched_items += [("tender" if s["kind"] == "ending" else s["kind"], i) for i in res["items"]]

    where, params = shared_scope(user)          # WP-157: the workspace's shortlist and follows
    shortlist_rows = conn.execute(
        f"SELECT * FROM app_shortlist WHERE {where} ORDER BY updated_at DESC LIMIT %s",
        (*params, MAX_SHORTLIST)).fetchall()
    shortlist = _hydrate_shortlist(conn, shortlist_rows)
    counts: dict[str, int] = {s: 0 for s in STATUSES}
    for r in shortlist_rows:
        counts[r["status"]] += 1

    closing, seen = [], set()
    for entry in shortlist:
        item = entry["item"]
        d = _deadline(item) if item else None
        if d and now <= d < horizon and entry["status"] != "dropped":
            closing.append({"kind": entry["kind"], "item": item, "source": "shortlist"})
            seen.add((entry["kind"], entry["ref"]))
    for kind, item in searched_items:
        d = _deadline(item)
        if d and now <= d < horizon and (kind, item["id"]) not in seen:
            closing.append({"kind": kind, "item": item, "source": "search"})
            seen.add((kind, item["id"]))
    closing.sort(key=lambda c: _deadline(c["item"]) or horizon)

    follow_rows = conn.execute(
        f"SELECT * FROM app_follow WHERE {where} ORDER BY created_at DESC LIMIT %s",
        (*params, MAX_FOLLOWS)).fetchall()
    followed = _hydrate_follows(conn, follow_rows)
    following = []
    for f in followed:
        it = f["item"] or {}
        following.append({"kind": f["kind"], "ref": f["ref"], "name": it.get("name") or f["ref"],
                          "openCount": it.get("openCount", 0),
                          "latestAt": it.get("lastPublishedAt")})

    # Changes since the last visit on what the account follows or shortlisted. Tenders only.
    watched = [int(r["ref"]) for r in shortlist_rows if r["kind"] == "tender" and r["ref"].isdigit()]
    buyers = [int(f["ref"]) for f in followed if f["kind"] == "buyer" and f["ref"].isdigit()]
    changes: list[dict[str, Any]] = []
    if watched or buyers:
        ids = [r["opportunity_id"] for r in conn.execute(
            """SELECT v.opportunity_id, max(v.observed_at) AS seen
                 FROM opportunity_version v
                WHERE v.version > 1 AND v.observed_at > %s
                  AND NOT EXISTS (SELECT 1 FROM opportunity_version_note n
                                   WHERE n.opportunity_version_id = v.id
                                     AND n.kind = ANY(%s))
                  AND (v.opportunity_id = ANY(%s)
                       OR v.opportunity_id IN (SELECT id FROM opportunity
                                                WHERE buyer_org_id IN (
                                                          SELECT unnest(dgate_family_ids(b))
                                                            FROM unnest(%s::bigint[]) AS b)
                                                  AND is_defence
                                                  AND NOT suppressed AND NOT buyer_withheld))
                GROUP BY v.opportunity_id ORDER BY seen DESC LIMIT 10""",
            (since, list(db.NOT_AMENDMENT_NOTES), watched, buyers)).fetchall()]
        items = _tenders_by_id(conn, ids)
        for oid in ids:
            item = items.get(str(oid))
            if not item:
                continue
            try:
                versions = tender_versions(str(oid), conn)
            except HTTPException:
                continue
            for v in versions:
                if v["detectedAt"] > since and v["changes"]:
                    changes.append({"kind": "tender", "item": item, "observedAt": v["detectedAt"],
                                    "changes": v["changes"]})
                    break
    changes.sort(key=lambda c: c["observedAt"], reverse=True)

    upcoming = sorted((e for e in shortlist if e["item"] and _deadline(e["item"])
                       and _deadline(e["item"]) >= now),
                      key=lambda e: _deadline(e["item"]))
    rest = [e for e in shortlist if e not in upcoming]
    short_items = (upcoming + rest)[:5]

    previous_visit = user["last_visit_at"]
    conn.execute("UPDATE app_user SET last_visit_at = now() WHERE id = %s", (user["id"],))
    return {
        "lastVisitAt": previous_visit,
        "matches": matches,
        "closingSoon": closing[:10],
        "changes": changes[:10],
        "following": following,
        "shortlist": {"counts": counts, "items": short_items},
        "pulse": pulse(conn),
    }


# ------------------------------------------------------------------ visit counter
_KNOWN_ROUTES = {"", "funding", "tenders", "buyers", "data", "market", "calendar", "cpv", "glossary",
                 "methodology", "about", "terms",
                 "privacy", "imprint", "pricing", "alerts", "pack", "signin", "register", "signup", "reset", "app"}
_DETAIL_ROUTES = {"funding", "tenders", "buyers"}


def route_key(path: str) -> str:
    """A page, not a record: `/tenders/123-some-title` counts as `/tenders/[slug]`, and an
    unknown path is `/other`, so the table cannot grow with what a visitor types."""
    parts = [p for p in urlsplit(path).path.split("/") if p]
    head = parts[0] if parts else ""
    if head not in _KNOWN_ROUTES:
        return "/other"
    if head in _DETAIL_ROUTES and len(parts) >= 2:
        return f"/{head}/[slug]"
    return "/" + head if head else "/"


# The referrer is kept only when it is one of these, as the name on the right; everything
# else is `other`, and none is `""`. A free-text host would let anyone with a request grow the
# table without bound; this way it holds at most routes x names x devices rows a day.
_REFERRER_BY_LABEL = {
    "google": "google.com", "bing": "bing.com", "duckduckgo": "duckduckgo.com",
    "ecosia": "ecosia.org", "yahoo": "yahoo.com", "yandex": "yandex.com", "baidu": "baidu.com",
    "linkedin": "linkedin.com", "facebook": "facebook.com", "reddit": "reddit.com",
    "github": "github.com", "wikipedia": "wikipedia.org",
}
_REFERRER_EXACT = {"x.com": "x.com", "twitter.com": "x.com", "t.co": "x.com", "lnkd.in": "linkedin.com",
                   "news.ycombinator.com": "news.ycombinator.com"}
_HOST = re.compile(r"^[a-z0-9.-]{1,80}$")


def referrer_host(value: str) -> str:
    """The referrer reduced to `""` (direct, or our own site), a name from the allow-list,
    or `other`. Takes a URL or, as the site's counter sends it, a bare host."""
    try:
        text = (value or "").strip()
        host = (urlsplit(text if "//" in text else "//" + text).hostname or "").lower().strip(".")
    except ValueError:
        return ""
    own = (urlsplit(settings().site_url).hostname or "").lower()
    if not host or host == own or host == f"www.{own}" or not _HOST.fullmatch(host):
        return ""
    labels = host.split(".")
    if len(labels) >= 2:
        label = labels[-3] if len(labels) >= 3 and labels[-2] in ("co", "com", "org", "net") else labels[-2]
        if label in _REFERRER_BY_LABEL:
            return _REFERRER_BY_LABEL[label]
    for domain, name in _REFERRER_EXACT.items():
        if host == domain or host.endswith("." + domain):
            return name
    return "other"


def _count_hits(conn, hits: list[tuple[str, str, bool, int]]) -> None:
    """Add counts to today's rows in one statement. Keys are merged first: a row cannot be
    touched twice by one INSERT ... ON CONFLICT."""
    merged: dict[tuple[str, str, str], int] = {}
    for route, referrer, mobile, count in hits:
        if not route.startswith("/"):
            continue
        key = (route_key(route), referrer_host(referrer), "mobile" if mobile else "desktop")
        merged[key] = merged.get(key, 0) + count
    if not merged:
        return
    keys = list(merged)
    conn.execute(
        """INSERT INTO app_hit_daily (day, route, referrer, device, hits)
           SELECT (now() AT TIME ZONE 'UTC')::date, t.route, t.referrer, t.device, t.n
             FROM unnest(%s::text[], %s::text[], %s::text[], %s::int[]) AS t(route, referrer, device, n)
           ON CONFLICT (day, route, referrer, device)
           DO UPDATE SET hits = app_hit_daily.hits + EXCLUDED.hits""",
        ([k[0] for k in keys], [k[1] for k in keys], [k[2] for k in keys], [merged[k] for k in keys]))


@internal_router.post("/v1/internal/hit", status_code=204)
def hit(body: Hit, conn=Depends(get_conn)) -> Response:
    _count_hits(conn, [(body.route, body.referrer, body.mobile, 1)])
    return Response(status_code=204)


@internal_router.post("/v1/internal/hits", status_code=204)
def hits(body: HitBatch, conn=Depends(get_conn)) -> Response:
    """The site's counter sends what it has gathered every few seconds, already summed per
    page, referrer host and device class."""
    _count_hits(conn, [(h.route, h.referrer, h.mobile, h.count) for h in body.hits])
    return Response(status_code=204)
