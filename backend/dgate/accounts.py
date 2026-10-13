"""Accounts: sign-in by e-mail link, profile, saved searches, shortlist, follows, dashboard.

Contract: docs/design/ACCOUNT_CONTRACT.md. Requirements: docs/SECURITY_REQUIREMENTS.md
(A1-A6, O1-O3). Data held: docs/DATA_PROTECTION.md.

The browser never calls this. The site's server (a backend for frontend) does, over the
internal network, with the session in `X-DG-Session`. Consequences that are deliberate:

  - these routes are not in the Caddy allow-list, and a request that carries an `Origin` or
    an `X-Forwarded-For` header (a browser, or something that came through the proxy) is
    refused here as well; once `DGATE_INTERNAL_SECRET` is set the site must also send it
    in `X-DG-Internal`, so the network boundary is not the only control;
  - there is no cookie on this side at all, so there is nothing to forge cross-site (A6);
  - every query on a user-owned table is scoped by the authenticated owner id in SQL (O1);
    a row owned by someone else is a 404, never a 403 and never the row.

Secrets (sign-in tokens, session ids) exist in plain form only in the response that hands
them to the site and in the e-mail; the database holds SHA-256 hashes.
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

from . import db
from .config import settings
from .hardening import BODY_MAX, TokenBuckets
from .ops import mailer
from .ops.notify import notify

log = logging.getLogger("accounts")

# ------------------------------------------------------------------ limits
LINK_TTL = timedelta(minutes=15)
SESSION_ABSOLUTE = timedelta(days=30)
SESSION_IDLE = timedelta(days=7)
LIMIT_PER_ADDRESS = 5          # sign-in links per hour, per address (A3)
LIMIT_PER_IP = 20              # per client IP
LIMIT_GLOBAL = 120             # in total; beyond it the operator is told
MAX_SEARCHES = 10
MAX_SHORTLIST = 500
MAX_FOLLOWS = 100
MAX_COUNTRIES = 20
MAX_BODY = BODY_MAX
MAX_SESSIONS = 10              # per account; signing in beyond it ends the oldest
USER_RATE = 30                 # requests a minute per account on searches and the dashboard
MAX_HITS_PER_BATCH = 200       # of the visit counter
MAX_HIT_COUNT = 10_000         # one key's count in one batch
NOTE_MAX = 500
SEARCH_RESULTS = 100           # how many newest matches are read to count the new ones

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
_BINDER = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
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


def _event_key(kind: str, value: str) -> bytes:
    """Key of a throttle counter: HMAC-SHA256 under a key only the server holds. A plain hash
    of an address or an IP can be reversed by trying candidates; this cannot without the key."""
    cfg = settings()
    key = (cfg.internal_secret or cfg.app_password).encode("utf-8")
    return hmac.new(key, f"{kind}\x00{value}".encode("utf-8"), hashlib.sha256).digest()


def _secret() -> str:
    return secrets.token_urlsafe(32)      # 256 bits, 43 URL-safe characters


def _client_ip(value: str | None) -> str:
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return "unknown"


# ------------------------------------------------------------------ plumbing
def get_conn():
    cfg = settings()
    with db.connect(cfg.app_dsn or cfg.dsn) as conn:
        yield conn


def internal_only(request: Request) -> None:
    """A6, defence in depth: the site's server calls this over the compose network and adds
    neither header. A browser sends `Origin` on a cross-site write; a request that came
    through the proxy carries `X-Forwarded-For`. Either means it is not the site, and so does
    an empty one: presence is tested, not truthiness. With DGATE_INTERNAL_SECRET set the
    site's own header `X-DG-Internal` must match it as well (a second control, not the
    network alone). The size check is a first look at a declared length; BodyLimit counts
    the bytes that really arrive."""
    secret = settings().internal_secret
    if secret:
        given = request.headers.get("x-dg-internal")
        if given is None or not hmac.compare_digest(given.encode("utf-8"), secret.encode("utf-8")):
            raise AccountError(403, "forbidden", "not available from here")
    if request.headers.get("origin") is not None or request.headers.get("x-forwarded-for") is not None:
        raise AccountError(403, "forbidden", "not available from here")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY:
        raise AccountError(413, "too_large", "request body too large")


def no_store(response: Response) -> None:
    """Nothing here is for a shared cache: the API's default for a GET is to be cacheable."""
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(prefix="/v1/account", dependencies=[Depends(internal_only), Depends(no_store)])
internal_router = APIRouter(dependencies=[Depends(internal_only)])


def current(request: Request, conn=Depends(get_conn),
            x_dg_session: str | None = Header(None)) -> dict[str, Any]:
    """The authenticated account and the session it came with, or 401."""
    if not x_dg_session or not _SESSION.match(x_dg_session):
        raise AccountError(401, "unauthenticated", "sign in required")
    row = conn.execute(
        """SELECT s.public_id AS session_id, s.id_hash, u.*
             FROM app_session s JOIN app_user u ON u.id = s.user_id
            WHERE s.id_hash = %s AND s.expires_at > now()
              AND s.last_seen_at > now() - %s::interval""",
        (_hash(x_dg_session), SESSION_IDLE)).fetchone()
    if not row:
        raise AccountError(401, "unauthenticated", "sign in required")
    conn.execute("UPDATE app_session SET last_seen_at = now() "
                 "WHERE id_hash = %s AND last_seen_at < now() - interval '1 minute'",
                 (row["id_hash"],))
    return row


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


class LinkRequest(_Body):
    email: str = Field(max_length=320)
    binder: str


class Verify(_Body):
    token: str
    binder: str


class ProfilePatch(_Body):
    role: Literal["supplier", "prime", "consultant", "grant_writer", "other"] | None = None
    tracks: list[Literal["tenders", "funding"]] | None = Field(None, max_length=2)
    countries: list[str] | None = Field(None, max_length=MAX_COUNTRIES)
    scope: Literal["core", "all"] | None = None
    cadence: Literal["instant", "daily", "weekly", "off"] | None = None


class DeleteAccount(_Body):
    confirm: str = Field(max_length=320)


class SearchIn(_Body):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["tender", "call"]
    filters: dict[str, Any] = Field(default_factory=dict)
    cadence: Literal["instant", "daily", "weekly", "off"] = "daily"


class SearchPatch(_Body):
    name: str | None = Field(None, min_length=1, max_length=80)
    filters: dict[str, Any] | None = None
    cadence: Literal["instant", "daily", "weekly", "off"] | None = None


class ShortlistIn(_Body):
    status: Literal["watching", "evaluating", "bidding", "submitted", "dropped"] = "watching"
    note: str = Field("", max_length=NOTE_MAX)


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
@router.get("/status")
def status() -> JSONResponse:
    return JSONResponse({"open": mailer.can_send()}, headers={"Cache-Control": "public, max-age=60"})


# ------------------------------------------------------------------ sign-in
_last_global_page = 0.0
_page_lock = threading.Lock()


def _recent(conn, kind: str, key: str) -> int:
    """How many accepted requests this key has in the last hour. Read only: a request that
    is refused must leave nothing behind, or an attacker could fill the table and keep a
    victim's counter hot with requests that were never served."""
    return conn.execute(
        "SELECT count(*) AS n FROM app_auth_event WHERE kind = %s AND key_hash = %s "
        "AND at > now() - interval '1 hour'", (kind, _event_key(kind, key))).fetchone()["n"]


def _page_operator(message: str) -> None:
    global _last_global_page
    with _page_lock:
        if time.monotonic() - _last_global_page < 3600:
            return
        _last_global_page = time.monotonic()
    notify(message)


def _send_link(address: str, token: str) -> None:
    link = f"{settings().site_url.rstrip('/')}/auth/verify?token={token}"
    body = (
        "Sign in to DefenceGate\n\n"
        "Open this link in the browser where you asked for it. It works once and expires in "
        "15 minutes:\n\n"
        f"{link}\n\n"
        "If you did not ask for this, ignore this message. Nothing happens unless the link "
        "is opened.\n")
    mailer.send_mail(address, "Your DefenceGate sign-in link", body)


@router.post("/auth/request", status_code=202)
def auth_request(body: LinkRequest, background: BackgroundTasks, conn=Depends(get_conn),
                 x_dg_client_ip: str | None = Header(None)) -> dict[str, bool]:
    if not mailer.can_send():
        raise AccountError(503, "not_open", "sign-in is not open yet")
    try:
        canonical, display = canonical_email(body.email)
    except ValueError:
        raise AccountError(422, "invalid_email", "that does not look like an e-mail address") from None
    if not _BINDER.match(body.binder):
        raise AccountError(422, "invalid_request", "invalid request")

    # Tiny tables, so pruned at the start of every request that gets this far (an index on
    # `at`): what the notice says (about a day) is then true. Committed at once, so a
    # request refused below does not undo it.
    conn.execute("DELETE FROM app_auth_event WHERE at < now() - interval '1 day'")
    conn.execute("DELETE FROM app_login_token WHERE expires_at < now() - interval '1 day'")
    conn.commit()

    # A3. Counts are read first and written only for a request that is accepted. The per-IP
    # and global limits are 429. The per-address limit is the same 202 and nothing is sent or
    # stored: a 429 there would tell a stranger which address is being mailed, and refusing
    # visibly would let anyone lock a person out of signing in by asking for their address.
    ip = _client_ip(x_dg_client_ip)
    total = _recent(conn, "all", "all")
    if total >= LIMIT_GLOBAL:
        _page_operator(f"Sign-in link requests are over {LIMIT_GLOBAL} an hour: possible abuse.")
    if total >= LIMIT_GLOBAL or _recent(conn, "ip", ip) >= LIMIT_PER_IP:
        raise AccountError(429, "rate_limited", "too many requests, try again later",
                           {"Retry-After": "3600"})
    if _recent(conn, "addr", canonical) >= LIMIT_PER_ADDRESS:
        return {"ok": True}
    for kind, value in (("addr", canonical), ("ip", ip), ("all", "all")):
        conn.execute("INSERT INTO app_auth_event (kind, key_hash) VALUES (%s, %s)",
                     (kind, _event_key(kind, value)))

    domain = canonical.rsplit("@", 1)[1]
    disposable = conn.execute(
        "SELECT 1 FROM app_disposable_domain WHERE domain = %s", (domain,)).fetchone() is not None
    token = _secret()
    conn.execute(
        "INSERT INTO app_login_token (token_hash, binder_hash, email_canonical, email_display, expires_at) "
        "VALUES (%s, %s, %s, %s, now() + %s::interval)",
        (_hash(token), _hash(body.binder), canonical, display, LINK_TTL))
    if not disposable:                     # A4: refused quietly, identical answer
        background.add_task(_send_link, display, token)
    return {"ok": True}


@router.post("/auth/verify")
def auth_verify(body: Verify, conn=Depends(get_conn)) -> dict[str, Any]:
    fail = AccountError(400, "invalid_or_expired", "this link is not valid")
    if not _TOKEN.match(body.token) or not _BINDER.match(body.binder):
        raise fail
    row = conn.execute(
        "SELECT token_hash, binder_hash, email_canonical, email_display, expires_at, used_at "
        "FROM app_login_token WHERE token_hash = %s FOR UPDATE", (_hash(body.token),)).fetchone()
    if (not row or row["used_at"] is not None or row["expires_at"] <= datetime.now(timezone.utc)
            or not hmac.compare_digest(bytes(row["binder_hash"]), _hash(body.binder))):
        # A wrong browser does not burn the link: a mail scanner must not be able to
        # use it up on the person's behalf.
        raise fail
    conn.execute("UPDATE app_login_token SET used_at = now() WHERE token_hash = %s", (row["token_hash"],))
    created = conn.execute(
        "INSERT INTO app_user (email_canonical, email_display) VALUES (%s, %s) "
        "ON CONFLICT (email_canonical) DO NOTHING RETURNING id",
        (row["email_canonical"], row["email_display"])).fetchone()
    if created:
        user_id, is_new = created["id"], True
    else:
        user_id = conn.execute("SELECT id FROM app_user WHERE email_canonical = %s",
                               (row["email_canonical"],)).fetchone()["id"]
        is_new = False
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


@router.post("/auth/logout", status_code=204)
def auth_logout(conn=Depends(get_conn), x_dg_session: str | None = Header(None)) -> Response:
    if x_dg_session and _SESSION.match(x_dg_session):
        conn.execute("DELETE FROM app_session WHERE id_hash = %s", (_hash(x_dg_session),))
    return Response(status_code=204)


# ------------------------------------------------------------------ account
def _user_out(u: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(u["id"]), "email": u["email_display"], "createdAt": u["created_at"],
        "profile": {"role": u["role"], "tracks": list(u["tracks"]), "countries": list(u["countries"]),
                    "scope": u["scope"], "cadence": u["cadence"]},
        "onboarded": u["onboarded"], "lastVisitAt": u["last_visit_at"],
    }


@router.get("/me")
def me(user=Depends(current)) -> dict[str, Any]:
    return _user_out(user)


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
    sets, params = [], []
    for key, value in changes.items():
        if value is None and key != "role":
            continue
        sets.append(f"{key} = %s")
        params.append(value)
    if sets:
        conn.execute(f"UPDATE app_user SET {', '.join(sets)} WHERE id = %s", params + [user["id"]])
    row = conn.execute("SELECT * FROM app_user WHERE id = %s", (user["id"],)).fetchone()
    done = bool(row["role"]) and bool(row["tracks"])
    if done != row["onboarded"]:
        conn.execute("UPDATE app_user SET onboarded = %s WHERE id = %s", (done, user["id"]))
        row["onboarded"] = done
    return _user_out(row)


@router.delete("/me", status_code=204)
def delete_me(body: DeleteAccount, conn=Depends(get_conn), user=Depends(current)) -> Response:
    try:
        typed, _ = canonical_email(body.confirm)
    except ValueError:
        raise AccountError(422, "confirmation_mismatch", "type your e-mail address to confirm") from None
    if typed != user["email_canonical"]:
        raise AccountError(422, "confirmation_mismatch", "type your e-mail address to confirm")
    conn.execute("DELETE FROM app_user WHERE id = %s", (user["id"],))   # cascades to everything owned
    return Response(status_code=204)


@router.get("/export")
def export(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    uid = user["id"]
    log.info("account export for %s", uid)          # O3: logged with the account id
    return {
        "exportedAt": datetime.now(timezone.utc),
        "account": _user_out(user),
        "searches": [_search_row(r) for r in conn.execute(
            "SELECT * FROM app_saved_search WHERE owner_id = %s ORDER BY created_at LIMIT %s",
            (uid, MAX_SEARCHES)).fetchall()],
        "shortlist": [{"kind": r["kind"], "ref": r["ref"], "status": r["status"], "note": r["note"],
                       "createdAt": r["created_at"], "updatedAt": r["updated_at"]}
                      for r in conn.execute(
                          "SELECT * FROM app_shortlist WHERE owner_id = %s ORDER BY created_at LIMIT %s",
                          (uid, MAX_SHORTLIST)).fetchall()],
        "follows": [{"kind": r["kind"], "ref": r["ref"], "createdAt": r["created_at"]}
                    for r in conn.execute(
                        "SELECT * FROM app_follow WHERE owner_id = %s ORDER BY created_at LIMIT %s",
                        (uid, MAX_FOLLOWS)).fetchall()],
    }


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
_TENDER_KEYS = {"q", "country", "cpv", "status", "scope", "buyer", "from", "to", "min", "max",
                "currency", "sort"}
_CALL_KEYS = {"q", "programme", "regime", "country", "status", "from", "to", "min", "max",
              "currency", "sort"}
_ENUMS = {
    ("tender", "status"): {"open", "closed", "all"},
    ("tender", "scope"): {"core", "supply", "all"},
    ("tender", "sort"): {"deadline-asc", "published-desc"},
    ("call", "status"): {"open", "forthcoming", "closing-soon", "closed", "all"},
    ("call", "sort"): {"deadline-asc", "deadline-desc", "budget-desc"},
}
_MAX_LEN = {"q": 100, "country": 200, "cpv": 400, "programme": 200, "regime": 100}


def clean_filters(kind: str, filters: dict[str, Any]) -> dict[str, str]:
    """The stored form of a search: only the public list endpoint's own parameters, each
    checked against the rule that endpoint applies, as strings. Anything else is refused."""
    allowed = _TENDER_KEYS if kind == "tender" else _CALL_KEYS
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
        "currency": f.get("currency", "EUR"), "page": 1,
    }
    if kind == "tender":
        base.update(cpv=f.get("cpv"), status=f.get("status", "open"), scope=f.get("scope", "core"),
                    buyer=int(f["buyer"]) if "buyer" in f else None)
    else:
        base.update(programme=f.get("programme"), regime=f.get("regime"),
                    status=f.get("status", "open"))
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
    return item.get("publishedAt") if kind == "tender" else item.get("firstSeenAt")


def run_search(conn, kind: str, filters: dict[str, str], *, full: bool = False) -> dict[str, Any]:
    """The newest SEARCH_RESULTS matches (tenders by publication, calls by deadline) and
    the total, through the same function the public endpoint is. What is cached is what the
    dashboard needs: the total, the first CACHED_ITEMS items, and the date each of all the
    matches was published or first seen (so "new since your last visit" still counts among
    the whole SEARCH_RESULTS). `full=True` is for the digest: every item, not cached."""
    from .funding import list_funding
    from .tenders import list_tenders

    def compute() -> dict[str, Any]:
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
            "cadence": r["cadence"], "createdAt": r["created_at"]}


def _search_out(conn, r: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    out = _search_row(r)
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


@router.get("/searches")
def list_searches(conn=Depends(get_conn), user=Depends(throttled)) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM app_saved_search WHERE owner_id = %s "
                        "ORDER BY created_at DESC LIMIT %s", (user["id"], MAX_SEARCHES)).fetchall()
    return {"items": [_search_out(conn, r, user) for r in rows]}


@router.post("/searches", status_code=201)
def create_search(body: SearchIn, conn=Depends(get_conn), user=Depends(throttled)) -> dict[str, Any]:
    n = conn.execute("SELECT count(*) AS n FROM app_saved_search WHERE owner_id = %s",
                     (user["id"],)).fetchone()["n"]
    if n >= MAX_SEARCHES:
        raise AccountError(409, "limit_reached", f"at most {MAX_SEARCHES} saved searches")
    filters = clean_filters(body.kind, body.filters)
    run_search(conn, body.kind, filters)             # a filter the list endpoint refuses is refused here
    row = conn.execute(
        "INSERT INTO app_saved_search (owner_id, name, kind, filters, cadence) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING *",
        (user["id"], body.name.strip(), body.kind, json.dumps(filters), body.cadence)).fetchone()
    return _search_out(conn, row, user)


@router.patch("/searches/{search_id}")
def patch_search(search_id: str, body: SearchPatch, conn=Depends(get_conn),
                 user=Depends(throttled)) -> dict[str, Any]:
    row = _owned_search(conn, search_id, user)
    name = body.name.strip() if body.name is not None else row["name"]
    cadence = body.cadence if body.cadence is not None else row["cadence"]
    filters = row["filters"]
    if body.filters is not None:
        filters = clean_filters(row["kind"], body.filters)
        run_search(conn, row["kind"], filters)
    row = conn.execute(
        "UPDATE app_saved_search SET name = %s, cadence = %s, filters = %s "
        "WHERE id = %s AND owner_id = %s RETURNING *",
        (name, cadence, json.dumps(filters), search_id, user["id"])).fetchone()
    return _search_out(conn, row, user)


@router.delete("/searches/{search_id}", status_code=204)
def delete_search(search_id: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    _owned_search(conn, search_id, user)
    conn.execute("DELETE FROM app_saved_search WHERE id = %s AND owner_id = %s", (search_id, user["id"]))
    return Response(status_code=204)


# ------------------------------------------------------------------ hydration
def _tenders_by_id(conn, ids: list[int]) -> dict[str, dict[str, Any]]:
    from .tenders import TENDER_SELECT, _present

    if not ids:
        return {}
    rows = conn.execute(f"{TENDER_SELECT} WHERE o.id = ANY(%s) AND o.is_defence", (ids,)).fetchall()
    return {t["id"]: t for t in _present(conn, rows)}


def _calls_by_id(conn, ids: list[int]) -> dict[str, dict[str, Any]]:
    from .funding import SELECT, to_call

    if not ids:
        return {}
    rows = conn.execute(f"{SELECT} WHERE c.id = ANY(%s)", (ids,)).fetchall()
    return {c["id"]: c for c in (to_call(r) for r in rows)}


def _buyers_by_id(conn, ids: list[int]) -> dict[str, dict[str, Any]]:
    from . import api
    from .tenders import AGGREGATE, _buyer, _buyer_names

    if not ids:
        return {}
    agg = AGGREGATE.format(eff=api.EFFECTIVE_STATUS_SQL)
    rows = conn.execute(
        f"""SELECT org.id, org.canonical_name, org.country, org.is_defence_buyer,
                   a.n, a.open_n, a.last_published
              FROM organisation org JOIN ({agg}) a ON a.org_id = org.id
             WHERE org.id = ANY(%s)""", (ids,)).fetchall()
    names = _buyer_names(conn, [r["id"] for r in rows])
    return {str(r["id"]): _buyer(r, names) for r in rows}


PROGRAMME_NAMES = {"EDF": "European Defence Fund", "EDIP": "European Defence Industry Programme",
                   "HORIZON": "Horizon Europe", "DIGITAL": "Digital Europe",
                   "NATIONAL": "National programmes"}


def _programmes(conn) -> dict[str, dict[str, Any]]:
    """Programme chips (EDF, EDIP, HORIZON, DIGITAL, NATIONAL) with their open calls."""
    from .funding import EFFECTIVE_STATUS, programme_of

    rows = conn.execute(
        f"""SELECT p.code, p.name, ({EFFECTIVE_STATUS} = 'open') AS is_open, c.deadline_at
              FROM call c JOIN programme p ON p.id = c.programme_id""").fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        chip = programme_of(r["code"])
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
                    "createdAt": r["created_at"], "updatedAt": r["updated_at"], "item": item})
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
    found = (conn.execute("SELECT 1 FROM opportunity WHERE id = %s AND is_defence", (int(norm),)).fetchone()
             if kind == "tender"
             else conn.execute("SELECT 1 FROM call WHERE id = %s", (int(norm),)).fetchone())
    if not found:
        raise AccountError(404, "not_found", "no such item")
    return norm


@router.get("/shortlist")
def get_shortlist(conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM app_shortlist WHERE owner_id = %s "
                        "ORDER BY updated_at DESC LIMIT %s", (user["id"], MAX_SHORTLIST)).fetchall()
    return {"items": _hydrate_shortlist(conn, rows)}


@router.put("/shortlist/{kind}/{ref}")
def put_shortlist(kind: str, ref: str, body: ShortlistIn, conn=Depends(get_conn),
                  user=Depends(current)) -> dict[str, Any]:
    ref = _check_ref(conn, kind, ref)
    exists = conn.execute("SELECT 1 FROM app_shortlist WHERE owner_id = %s AND kind = %s AND ref = %s",
                          (user["id"], kind, ref)).fetchone()
    if not exists:
        n = conn.execute("SELECT count(*) AS n FROM app_shortlist WHERE owner_id = %s",
                         (user["id"],)).fetchone()["n"]
        if n >= MAX_SHORTLIST:
            raise AccountError(409, "limit_reached", f"at most {MAX_SHORTLIST} shortlisted items")
    note = body.note.replace("\x00", "").strip()
    row = conn.execute(
        """INSERT INTO app_shortlist (owner_id, kind, ref, status, note) VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (owner_id, kind, ref)
           DO UPDATE SET status = EXCLUDED.status, note = EXCLUDED.note, updated_at = now()
           RETURNING *""", (user["id"], kind, ref, body.status, note)).fetchone()
    return _hydrate_shortlist(conn, [row])[0]


@router.delete("/shortlist/{kind}/{ref}", status_code=204)
def delete_shortlist(kind: str, ref: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    ref = _norm_ref(ref) or ""
    gone = conn.execute("DELETE FROM app_shortlist WHERE owner_id = %s AND kind = %s AND ref = %s "
                        "RETURNING 1", (user["id"], kind, ref)).fetchone()
    if not gone:
        raise AccountError(404, "not_found", "not on your shortlist")
    return Response(status_code=204)


# ------------------------------------------------------------------ follows
def _check_follow(conn, kind: str, ref: str) -> str:
    """The normalised reference of an existing buyer or programme, or 404."""
    if kind == "buyer":
        norm = _norm_ref(ref)
        if norm is None or not conn.execute(
                "SELECT 1 FROM organisation WHERE id = %s", (int(norm),)).fetchone():
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
    rows = conn.execute("SELECT * FROM app_follow WHERE owner_id = %s ORDER BY created_at DESC LIMIT %s",
                        (user["id"], MAX_FOLLOWS)).fetchall()
    return {"items": _hydrate_follows(conn, rows)}


@router.put("/follows/{kind}/{ref}")
def put_follow(kind: str, ref: str, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    ref = _check_follow(conn, kind, ref)
    exists = conn.execute("SELECT 1 FROM app_follow WHERE owner_id = %s AND kind = %s AND ref = %s",
                          (user["id"], kind, ref)).fetchone()
    if not exists:
        n = conn.execute("SELECT count(*) AS n FROM app_follow WHERE owner_id = %s",
                         (user["id"],)).fetchone()["n"]
        if n >= MAX_FOLLOWS:
            raise AccountError(409, "limit_reached", f"at most {MAX_FOLLOWS} follows")
    row = conn.execute(
        "INSERT INTO app_follow (owner_id, kind, ref) VALUES (%s, %s, %s) "
        "ON CONFLICT (owner_id, kind, ref) DO UPDATE SET kind = EXCLUDED.kind RETURNING *",
        (user["id"], kind, ref)).fetchone()
    return _hydrate_follows(conn, [row])[0]


@router.delete("/follows/{kind}/{ref}", status_code=204)
def delete_follow(kind: str, ref: str, conn=Depends(get_conn), user=Depends(current)) -> Response:
    if kind != "programme":
        ref = _norm_ref(ref) or ""
    gone = conn.execute("DELETE FROM app_follow WHERE owner_id = %s AND kind = %s AND ref = %s "
                        "RETURNING 1", (user["id"], kind, ref)).fetchone()
    if not gone:
        raise AccountError(404, "not_found", "not followed")
    return Response(status_code=204)


@router.post("/state")
def state(body: StateIn, conn=Depends(get_conn), user=Depends(current)) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for key in body.keys:
        table = "app_shortlist" if key.type == "shortlist" else "app_follow"
        extra = ", status" if key.type == "shortlist" else ""
        ref = key.ref if key.kind == "programme" else (_norm_ref(key.ref) or "")
        row = conn.execute(
            f"SELECT 1 AS saved{extra} FROM {table} WHERE owner_id = %s AND kind = %s AND ref = %s",
            (user["id"], key.kind, ref)).fetchone()
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
        base = f"o.is_defence AND {CORE}"
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

    searches = conn.execute(
        "SELECT * FROM app_saved_search WHERE owner_id = %s ORDER BY created_at DESC LIMIT 6",
        (user["id"],)).fetchall()
    matches, searched_items = [], []
    for s in searches:
        res = run_search(conn, s["kind"], s["filters"])
        fresh = [i for i in res["items"] if _is_new(s["kind"], i, since)]
        matches.append({"search": {"id": str(s["id"]), "name": s["name"], "kind": s["kind"]},
                        "newCount": _new_count(res, since), "totalCount": res["total"],
                        "items": (fresh or res["items"])[:5]})
        searched_items += [(s["kind"], i) for i in res["items"]]

    shortlist_rows = conn.execute(
        "SELECT * FROM app_shortlist WHERE owner_id = %s ORDER BY updated_at DESC LIMIT %s",
        (user["id"], MAX_SHORTLIST)).fetchall()
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
        "SELECT * FROM app_follow WHERE owner_id = %s ORDER BY created_at DESC LIMIT %s",
        (user["id"], MAX_FOLLOWS)).fetchall()
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
                                                WHERE buyer_org_id = ANY(%s) AND is_defence))
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
                 "privacy", "imprint", "pricing", "alerts", "pack", "signin", "app"}
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
