"""Source connectors.

Every connector fetches and yields payloads and does nothing else. Parsing that
can differ between sources lives in the connector; everything shared lives in
normalise.py, so that a new source cannot quietly invent its own schema.
"""

import logging

# Identify the client honestly. These are public administration and NATO agency
# endpoints; anonymous scraping traffic is how access gets withdrawn.
USER_AGENT = "dgate/0.1 (+https://github.com/Dev-In-Crypt/DefenceGate)"


def _use_system_trust_store() -> bool:
    """Trust the operating system's certificate store when we can.

    Corporate and cloud networks routinely terminate TLS with their own CA. On
    such a machine every connector fails with CERTIFICATE_VERIFY_FAILED against
    endpoints that are perfectly healthy, which reads as an outage rather than
    a local trust problem. `truststore` hands Python the OS trust store, where
    that CA already lives. Optional: absent, behaviour is unchanged.
    """
    try:
        import truststore
    except ImportError:
        return False
    truststore.inject_into_ssl()
    return True


SYSTEM_TRUST_STORE = _use_system_trust_store()


def retry_after(response) -> float | None:
    """How long the far end asked us to wait, if it said so.

    `Retry-After` carries either a number of seconds or an HTTP date. A rate
    limiter that states its window is telling us exactly what our own guess is
    trying to estimate, so it wins over the backoff ladder.
    """
    raw = (response.headers.get("retry-after") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime

    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    from datetime import datetime, timezone

    now = datetime.now(when.tzinfo or timezone.utc)
    return max(0.0, (when - now).total_seconds())


def request_with_retry(
    send,
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    what: str = "request",
):
    """Call `send()` again when the far end is briefly unwell.

    Public procurement portals return 429 and 5xx under load, and a walk of
    forty pages is long enough to meet one. Abandoning the run then costs a
    whole day of collection for a fault that clears in seconds, and a day of
    the archive cannot be collected twice.

    The ladder doubles and is capped at `max_delay`, so a caller that wants to
    sit out a rate-limit window asks for more attempts rather than for one
    unbounded sleep. `Retry-After` overrides the guess when the response
    carries it.

    Only transient conditions are retried. A 400 means the query is wrong and
    retrying it just asks the same wrong question more times.
    """
    import time as _time

    import httpx as _httpx

    log = logging.getLogger(__name__)
    transient_status = {408, 425, 429, 500, 502, 503, 504}
    last: Exception | None = None

    for attempt in range(1, attempts + 1):
        asked: float | None = None
        try:
            return send()
        except _httpx.HTTPStatusError as exc:
            if exc.response.status_code not in transient_status:
                raise
            last = exc
            detail = f"HTTP {exc.response.status_code}"
            asked = retry_after(exc.response)
        except (_httpx.TransportError, _httpx.TimeoutException) as exc:
            last = exc
            detail = type(exc).__name__

        if attempt == attempts:
            break
        delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
        if asked is not None:
            delay = min(max_delay, asked)
        log.warning("%s failed (%s), attempt %s of %s, retrying in %.0fs",
                    what, detail, attempt, attempts, delay)
        _time.sleep(delay)

    assert last is not None
    raise last
