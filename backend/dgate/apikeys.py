"""Keys of the data API (WP-153): issued to a signed-in account, read-only, for a licensee's own scripts.

Built to docs/SECURITY_REQUIREMENTS.md:
  K1  a key is `dgk_<prefix>_<secret>`: the secret is 256 random bits, the prefix (48 bits, public) finds the row.
      The key is shown once, in the answer that created it; the database holds its SHA-256. A key has a name,
      scopes (`tenders`, `archive`), an expiry (one year) and `last_used_at`. Expired, revoked or out of scope:
      refused.
  K2  creating and revoking a key asks for the account's password again: a fresh sign-in, every time.
  K3  a key is charged on the limiter of hardening.py (`TokenBuckets`, the same request costs), in a bucket of its
      own sized by its row (requests a minute, and a daily quota), never on the address it comes from.
  O1  every query on the key tables is scoped by the owner id in SQL; another account's key is a 404.
  O2  ids are UUIDs.
An audit log of the keys (`api_key_event`: created, revoked) and a count of requests per key and day
(`api_key_usage`) are kept with the account and deleted with it.

What a key reads (`ROUTES`): the defence notices, one notice and its archive (`/v1/opportunities*`), and of those only
the sources the licence table allows (`settings().api_key_sources`, TED by default; docs/research/
DATA_LICENCES_2026-10-27.md). The source filter is written into the request as the routes' own `source` parameter, so
the list cache keys on it and a key's answer is never an anonymous one or the other way round.

Closed until DGATE_API_KEYS_OPEN=1: no key is issued, and a request that presents a key is refused (401). Keys already
issued stay listed and revocable.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import secrets
from datetime import date, timedelta
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from . import accounts, db
from .accounts import (
    AccountError,
    _audit,
    _Body,
    _client_ip,
    _require_password,
    current,
    get_conn,
    no_store,
)
from .config import settings
from .hardening import TokenBuckets, client_key, request_cost

SCOPES = ("tenders", "archive")
KEY_TTL = timedelta(days=365)
MAX_KEYS = 5                     # active (not revoked, not expired) per account
NAME_MAX = 60
FAILED_COST = 5                  # what a refused key costs the address that sent it: probing stays slow

_KEY = re.compile(r"^dgk_([0-9a-f]{12})_([A-Za-z0-9_-]{43})$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# What a key may call: (path pattern, scope). Anything else is refused with 403, whatever the public API serves.
# web/lib/data/api-endpoints.json lists the same paths for the /api page (tests/unit/test_apikeys.py holds them equal).
ROUTES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^/v1/opportunities$"), "tenders"),
    (re.compile(r"^/v1/opportunities/[0-9]{1,19}$"), "tenders"),
    (re.compile(r"^/v1/opportunities/[0-9]{1,19}/versions$"), "archive"),
)


def scope_of(path: str) -> str | None:
    return next((scope for pattern, scope in ROUTES if pattern.match(path)), None)


def _hash(raw: str) -> bytes:
    return hashlib.sha256(raw.encode("utf-8")).digest()


def new_key() -> tuple[str, str]:
    """(the key, its prefix)."""
    prefix = secrets.token_hex(6)
    return f"dgk_{prefix}_{secrets.token_urlsafe(32)}", prefix


def presented(request: Request) -> str | None:
    """The key a request carries (`Authorization: Bearer ...`), or None when it carries none."""
    value = request.headers.get("authorization")
    if value is None:
        return None
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


# ------------------------------------------------------------------ authentication (the public API side)
def authenticate(raw: str) -> dict[str, Any] | None:
    """The key's row when the key is valid now (shape, hash, not revoked, not expired), else None. A valid one is
    counted (`api_key_usage`) and its `last_used_at` moved (at most once a minute)."""
    m = _KEY.match(raw)
    if not m:
        return None
    cfg = settings()
    with db.bounded_connect(cfg.app_dsn or cfg.dsn, cfg.app_connections, cfg.pool_wait_ms / 1000) as conn:
        row = conn.execute(
            "SELECT id, key_hash, scopes, rate_per_minute, daily_quota FROM api_key "
            "WHERE prefix = %s AND revoked_at IS NULL AND expires_at > now()", (m.group(1),)).fetchone()
        if not row or not hmac.compare_digest(bytes(row["key_hash"]), _hash(raw)):
            return None
        conn.execute("UPDATE api_key SET last_used_at = now() WHERE id = %s "
                     "AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute')", (row["id"],))
        conn.execute("INSERT INTO api_key_usage (key_id, day, requests) VALUES (%s, current_date, 1) "
                     "ON CONFLICT (key_id, day) DO UPDATE SET requests = api_key_usage.requests + 1", (row["id"],))
        conn.commit()
    return row


# Buckets per (rate, quota): a key's limits are its row's. ponytail: in memory, like the address buckets (one API
# process); the daily quota is a bucket refilled over 24 h, so it resets with the process, not at midnight.
_minute: dict[int, TokenBuckets] = {}
_day: dict[int, TokenBuckets] = {}


def _take(key: dict[str, Any], cost: int) -> float:
    """0 when the key may make the request now, else the seconds to wait."""
    rate, quota = int(key["rate_per_minute"]), int(key["daily_quota"])
    minute = _minute.setdefault(rate, TokenBuckets(rate, rate / 60))
    day = _day.setdefault(quota, TokenBuckets(quota, quota / 86400))
    ok, wait = minute.take(str(key["id"]), cost)
    if not ok:
        return wait
    ok, wait = day.take(str(key["id"]), cost)
    return 0.0 if ok else wait


def _refuse(status: int, error: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": error, "message": message}, status_code=status,
                        headers={"Cache-Control": "no-store", **(headers or {})})


async def dispatch(request: Request, call_next, raw: str, address_buckets: TokenBuckets, peer: str):
    """A request that presents a key, from `hardening.RateLimit`: the key decides the limits and what may be read."""
    if not settings().api_keys_open:
        return _refuse(401, "api_keys_closed", "API keys are not open")
    key = await run_in_threadpool(authenticate, raw) if raw else None
    if key is None:
        address_buckets.take(client_key(peer), FAILED_COST)
        return _refuse(401, "invalid_key", "the key is unknown, revoked or expired",
                       {"WWW-Authenticate": 'Bearer error="invalid_token"'})
    path = request.url.path
    scope = scope_of(path)
    if request.method != "GET" or scope is None:
        return _refuse(403, "not_available", "a key reads /v1/opportunities, one notice and its versions; GET only")
    if scope not in key["scopes"]:
        return _refuse(403, "out_of_scope", f"this key has no '{scope}' scope")
    params = parse_qsl(request.scope.get("query_string", b"").decode("latin-1"), keep_blank_values=True)
    allowed = settings().api_key_sources
    asked = [s.strip() for k, v in params if k == "source" for s in v.split(",") if s.strip()]
    if any(s not in allowed for s in asked):
        return _refuse(403, "source_not_licensed", "a key reads these sources only: " + ", ".join(allowed))
    wait = _take(key, request_cost(path, dict(params)))
    if wait:
        return _refuse(429, "rate_limited", "the key's rate limit or daily quota is spent",
                       {"Retry-After": str(max(1, math.ceil(wait)))})
    # The licence filter, as the routes' own parameter: the answer and the list cache both key on it.
    request.scope["query_string"] = urlencode(
        [(k, v) for k, v in params if k != "source"] + [("source", ",".join(asked or allowed))]).encode("latin-1")
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"     # an answer for one licensee, never a shared cache's
    response.headers["Vary"] = "Authorization"
    return response


# ------------------------------------------------------------------ management (the account side, internal)
router = APIRouter(prefix="/v1/account/keys", dependencies=[Depends(accounts.internal_only), Depends(no_store)])


class KeyIn(_Body):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    scopes: list[Literal["tenders", "archive"]] = Field(min_length=1, max_length=len(SCOPES))
    password: str = Field(max_length=1024)


class PasswordIn(_Body):
    password: str = Field(max_length=1024)


def _key_out(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(r["id"]), "name": r["name"], "prefix": r["prefix"], "scopes": list(r["scopes"]),
            "ratePerMinute": r["rate_per_minute"], "dailyQuota": r["daily_quota"], "createdAt": r["created_at"],
            "expiresAt": r["expires_at"], "lastUsedAt": r["last_used_at"], "revokedAt": r["revoked_at"],
            "requestsToday": r.get("requests_today") or 0}


def owned_keys(conn, owner_id: Any) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT k.*, (SELECT u.requests FROM api_key_usage u WHERE u.key_id = k.id AND u.day = current_date) "
        "AS requests_today FROM api_key k WHERE k.owner_id = %s ORDER BY k.created_at DESC LIMIT 50",
        (owner_id,)).fetchall()


def _fresh_sign_in(conn, user: dict[str, Any], password: str, ip: str) -> None:
    """K2: the password again, under the sign-in delay. An account made before passwords has none to give."""
    if user["password_hash"] is None:
        raise AccountError(403, "password_required", "set a password first (Forgot your password)")
    _require_password(conn, user, password, ip)


@router.get("")
def list_keys(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    events = conn.execute(
        "SELECT e.event, e.at, k.name, k.prefix FROM api_key_event e JOIN api_key k ON k.id = e.key_id "
        "WHERE e.owner_id = %s ORDER BY e.at DESC, e.id DESC LIMIT 20", (user["id"],)).fetchall()
    return {"open": settings().api_keys_open, "sources": list(settings().api_key_sources), "scopes": list(SCOPES),
            "maxKeys": MAX_KEYS, "keys": [_key_out(r) for r in owned_keys(conn, user["id"])],
            "events": [{"event": e["event"], "at": e["at"], "name": e["name"], "prefix": e["prefix"]} for e in events]}


@router.post("", status_code=201)
def create_key(body: KeyIn, conn=Depends(get_conn), user=Depends(current),
               x_dg_client_ip: str | None = Header(None)) -> dict[str, Any]:
    """The key, once. It is not stored and cannot be shown again."""
    if not settings().api_keys_open:
        raise AccountError(403, "api_keys_closed", "API keys are not open")
    _fresh_sign_in(conn, user, body.password, _client_ip(x_dg_client_ip))
    name = " ".join(body.name.split())
    if not name:
        raise AccountError(422, "invalid", "a name is required")
    active = conn.execute("SELECT count(*) AS n FROM api_key WHERE owner_id = %s AND revoked_at IS NULL "
                          "AND expires_at > now()", (user["id"],)).fetchone()["n"]
    if active >= MAX_KEYS:
        raise AccountError(409, "too_many_keys", f"at most {MAX_KEYS} keys: revoke one first")
    raw, prefix = new_key()
    row = conn.execute(
        "INSERT INTO api_key (owner_id, name, prefix, key_hash, scopes, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, now() + %s::interval) RETURNING *",
        (user["id"], name, prefix, _hash(raw), sorted(set(body.scopes)), KEY_TTL)).fetchone()
    conn.execute("INSERT INTO api_key_event (key_id, owner_id, event) VALUES (%s, %s, 'created')",
                 (row["id"], user["id"]))
    _audit("api_key_created", user["id"], key=prefix)
    return {**_key_out(row), "key": raw}


@router.post("/{key_id}/revoke")
def revoke_key(key_id: str, body: PasswordIn, conn=Depends(get_conn), user=Depends(current),
               x_dg_client_ip: str | None = Header(None)) -> dict[str, Any]:
    if not _UUID.match(key_id):
        raise AccountError(404, "not_found", "no such key")
    _fresh_sign_in(conn, user, body.password, _client_ip(x_dg_client_ip))
    row = conn.execute("UPDATE api_key SET revoked_at = now() WHERE id = %s AND owner_id = %s "
                       "AND revoked_at IS NULL RETURNING *", (key_id, user["id"])).fetchone()
    if not row:
        raise AccountError(404, "not_found", "no such key")
    conn.execute("INSERT INTO api_key_event (key_id, owner_id, event) VALUES (%s, %s, 'revoked')",
                 (row["id"], user["id"]))
    _audit("api_key_revoked", user["id"], key=row["prefix"])
    return _key_out(row)


def export_rows(conn, owner_id: Any) -> list[dict[str, Any]]:
    """For the account's data export: what is held about each key, never its hash."""
    usage = {(str(r["key_id"]), r["day"]): r["requests"] for r in conn.execute(
        "SELECT u.key_id, u.day, u.requests FROM api_key_usage u JOIN api_key k ON k.id = u.key_id "
        "WHERE k.owner_id = %s AND u.day > %s", (owner_id, date.today() - timedelta(days=400))).fetchall()}
    return [{**{k: v for k, v in _key_out(r).items() if k != "requestsToday"},
             "requestsByDay": {d.isoformat(): n for (kid, d), n in sorted(usage.items()) if kid == str(r["id"])}}
            for r in owned_keys(conn, owner_id)]
