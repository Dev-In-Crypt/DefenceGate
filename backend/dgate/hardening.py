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

# What a request costs, in tokens. The archive and the entity-resolution oracle
# are the two things worth scraping, and the slug list is the whole catalogue.
HEAVY_PATHS = {"/v1/organisations/resolve": 5, "/v1/funding/slugs": 20}


def request_cost(path: str, params: dict[str, str]) -> int:
    if path.endswith("/versions"):
        return 5
    if path in HEAVY_PATHS:
        return HEAVY_PATHS[path]
    for key in ("limit", "pageSize"):
        try:
            if int(params.get(key, "0")) >= 100:
                return 3
        except ValueError:
            pass
    return 1


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


class RateLimit(BaseHTTPMiddleware):
    def __init__(self, app: Any, buckets: TokenBuckets | None = None) -> None:
        super().__init__(app)
        self.buckets = buckets or TokenBuckets()

    async def dispatch(self, request: Request, call_next):
        from .config import settings

        peer = request.client.host if request.client else "unknown"
        if peer in LOCAL_PEERS or not settings().rate_limit:
            return await call_next(request)
        cost = request_cost(request.url.path, dict(request.query_params))
        allowed, wait = self.buckets.take(peer, cost)
        if not allowed:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": str(max(1, math.ceil(wait)))})
        return await call_next(request)


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
