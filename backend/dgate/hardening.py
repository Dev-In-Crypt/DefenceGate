"""What stands between the public API and one badly behaved client.

Three things, all in-process so nothing new has to be installed or run:

  - a per-address token bucket, so a single client cannot take the database or
    download the archive at machine speed;
  - security headers on every response, so a response is never sniffed into
    something it is not or framed by another site;
  - error shapes that say "your request was wrong" or "try later", never a stack
    or a driver message.

The bucket is held in memory, which is correct only while the API runs as one
process (it does). Behind more than one worker it would need a shared store.
"""

from __future__ import annotations

import hmac
import ipaddress
import math
import threading
import time
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# 120 requests a minute sustained, with a burst of the same size. A page of the
# funding hub is one or two requests; a person never meets this.
CAPACITY = 120.0
REFILL_PER_SECOND = 2.0

# Peers that are the container itself: health checks and operators using
# `docker exec`. Everything arriving through the proxy carries the client's own
# address (uvicorn is started with --proxy-headers).
LOCAL_PEERS = {"127.0.0.1", "::1", "localhost"}

# The site's own server rendering reaches the API from inside the compose network, with
# no client address of its own: all of it would share one bucket, so a single busy
# minute of visitors would be refused as if they were one abusive client. Peers on a
# private address (never anyone from the internet: Caddy puts the visitor's address in
# front) get a bucket sized for the whole site instead.
INTERNAL_FACTOR = 20.0


# The visit counter's calls (`/v1/internal/hit` and `/v1/internal/hits`) are not charged.
UNCHARGED_PREFIX = "/v1/internal/hit"


def is_internal(peer: str) -> bool:
    try:
        return ipaddress.ip_address(peer).is_private
    except ValueError:
        return False


def client_key(address: str) -> str:
    """The bucket key of an address: an IPv6 client is its /64 (what one subscriber is
    handed, 2^64 addresses), a mapped IPv4 address is the IPv4 one, and a string that is
    not an address is itself. Without this one subscriber had 2^64 fresh buckets
    (internal audit H4, 14 October 2026)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


# What a request costs, in tokens. The archive and the entity-resolution oracle
# are the two things worth scraping, and the slug list is the whole catalogue.
HEAVY_PATHS = {"/v1/organisations/resolve": 5, "/v1/funding/slugs": 20,
               "/v1/tenders/slugs": 20, "/v1/buyers/slugs": 20}

# Lists whose cost depends on their shape: each page evaluates the filtered set, and a
# text search is a sequential scan of every notice (0.7 s), `status=all` and `scope=all`
# drop the selective predicates (3.6-5.4 s a page), and a deep page sorts all that comes
# before it. Measured 14 October 2026: a request of 4-5 s cost one token, the same as a
# page of 0.3 s, so 120 a minute from one address held nine of the API's thirty
# connections.
SHAPED_LISTS = {"/v1/tenders", "/v1/opportunities"}
MAX_COST = 30


def _int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0


def request_cost(path: str, params: dict[str, str]) -> int:
    if path.endswith("/versions"):
        return 5
    if path in HEAVY_PATHS:
        return HEAVY_PATHS[path]
    if path == "/v1/buyers" or (path.startswith("/v1/buyers/") and path.endswith("/profile")):
        # The buyer list re-aggregates the whole table; a profile is 0.2-0.5 s uncached.
        return 5 + (3 if (params.get("q") or "").strip() else 0)
    # The change feed reads the archive's last 14 days and every page of it computes them
    # (its answer is kept five minutes): dearer than a plain page, as a list of its own.
    cost = 3 if path == "/v1/changes" else 1
    for key in ("limit", "pageSize"):
        if _int(params.get(key)) >= 100:
            cost = max(cost, 3)
    if path in SHAPED_LISTS:
        if (params.get("q") or "").strip():
            cost += 5
        if params.get("status") == "all":
            cost += 3
        if params.get("scope") == "all":
            cost += 3
        size = _int(params.get("pageSize")) or _int(params.get("limit")) or 20
        depth = _int(params.get("offset")) or max(0, _int(params.get("page")) - 1) * size
        cost += min(10, depth // 1000)
    return min(cost, MAX_COST)


class TokenBuckets:
    def __init__(self, capacity: float = CAPACITY, refill: float = REFILL_PER_SECOND,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity, self.refill, self.clock = capacity, refill, clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str, cost: float) -> tuple[bool, float]:
        """(allowed, seconds to wait when not)."""
        now = self.clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill)
            if tokens >= cost:
                self._buckets[key] = (tokens - cost, now)
                allowed, wait = True, 0.0
            else:
                self._buckets[key] = (tokens, now)
                allowed = False
                wait = min(3600.0, (cost - tokens) / self.refill) if self.refill > 0 else 3600.0
            if len(self._buckets) > 20_000:
                # A flood of distinct addresses must not become a memory leak:
                # forget the ones that have been idle long enough to be full again.
                horizon = now - self.capacity / self.refill
                self._buckets = {k: v for k, v in self._buckets.items() if v[1] > horizon}
        return allowed, wait


def _forwarded_client(request: Request) -> str | None:
    """The visitor's address as the site's server states it, or None."""
    from .config import settings

    value = request.headers.get("x-dg-client-ip")
    if not value or len(value) > 45:
        return None
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return None
    if ip.is_private or ip.is_loopback:
        return None                  # the site's own address is not a visitor
    secret = settings().internal_secret
    if secret:
        given = request.headers.get("x-dg-internal") or ""
        if not hmac.compare_digest(given.encode("utf-8"), secret.encode("utf-8")):
            return None
    return str(ip)


class RateLimit(BaseHTTPMiddleware):
    def __init__(self, app: Any, buckets: TokenBuckets | None = None) -> None:
        super().__init__(app)
        self.buckets = buckets or TokenBuckets()
        self.internal = TokenBuckets(CAPACITY * INTERNAL_FACTOR, REFILL_PER_SECOND * INTERNAL_FACTOR)

    async def dispatch(self, request: Request, call_next):
        from .config import settings

        peer = request.client.host if request.client else "unknown"
        if peer in LOCAL_PEERS or not settings().rate_limit:
            return await call_next(request)
        internal = is_internal(peer)
        if internal:
            # The site's own server forwards the visitor's address (it is the first
            # `X-Forwarded-For` entry Caddy set, which the visitor cannot choose) so that a
            # page view is charged to the visitor and not to the site's one big bucket
            # (external audit X-2). Accepted only from a peer on the private network, and
            # only with the shared secret when one is set: a request that came through
            # Caddy has its client's public address as `peer` and never reaches here.
            forwarded = _forwarded_client(request)
            if forwarded is not None:
                peer, internal = forwarded, False
        if request.url.path.startswith(UNCHARGED_PREFIX):
            # The site's own visit counter: it is aggregated and flushed by the site every
            # few seconds, and charging it to the one bucket every page render shares let
            # the counter's traffic starve the pages (review of 12 October 2026, H1).
            return await call_next(request)
        cost = request_cost(request.url.path, dict(request.query_params))
        buckets = self.internal if internal else self.buckets
        allowed, wait = buckets.take(client_key(peer), cost)
        if not allowed:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": str(max(1, math.ceil(wait)))})
        return await call_next(request)


# The account API and the counter take small JSON bodies. 16 KiB, counted on the bytes that
# actually arrive: a chunked body has no Content-Length to look at.
BODY_MAX = 16 * 1024
BODY_LIMITED_PREFIXES = ("/v1/account", "/v1/internal")


class _TooLarge(Exception):
    pass


class BodyLimit:
    """Refuses a request body over BODY_MAX with 413 on the account and counter routes. Reads
    at most BODY_MAX + 1 bytes of it: a declared length over the limit is refused without
    reading, and one that is absent or false is counted as the chunks arrive. FastAPI turns
    any error raised while it parses a body into a 400, so the 413 is sent from here at the
    moment the limit is crossed and whatever the application then says is dropped."""

    def __init__(self, app: Any, limit: int = BODY_MAX) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(BODY_LIMITED_PREFIXES):
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            await self._refuse(scope, receive, send)
            return
        seen = 0
        refused = False

        async def limited():
            nonlocal seen, refused
            message = await receive()
            if message["type"] == "http.request" and not refused:
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    refused = True
                    await self._refuse(scope, receive, send)
                    raise _TooLarge
            return message

        async def guarded(message) -> None:
            if not refused:
                await send(message)

        try:
            await self.app(scope, limited, guarded)
        except _TooLarge:
            pass

    @staticmethod
    async def _refuse(scope, receive, send) -> None:
        response = JSONResponse({"error": "too_large", "message": "request body too large"},
                                status_code=413)
        await response(scope, receive, send)


class SecurityHeaders(BaseHTTPMiddleware):
    """The API returns JSON only: nothing in a response is ever meant to be
    rendered, framed or executed, so the policy says exactly that."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        if "cache-control" not in response.headers:
            ok = request.method == "GET" and 200 <= response.status_code < 300
            response.headers["Cache-Control"] = "public, max-age=60" if ok else "no-store"
        return response
