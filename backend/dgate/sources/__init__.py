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


def request_with_retry(
    send,
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
    what: str = "request",
):
    """Call `send()` again when the far end is briefly unwell.

    Public procurement portals return 429 and 5xx under load, and a walk of
    forty pages is long enough to meet one. Abandoning the run then costs a
    whole day of collection for a fault that clears in seconds, and a day of
    the archive cannot be collected twice.

    Only transient conditions are retried. A 400 means the query is wrong and
    retrying it just asks the same wrong question more times.
    """
    import time as _time

    import httpx as _httpx

    log = logging.getLogger(__name__)
    transient_status = {408, 425, 429, 500, 502, 503, 504}
    last: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return send()
        except _httpx.HTTPStatusError as exc:
            if exc.response.status_code not in transient_status:
                raise
            last = exc
            detail = f"HTTP {exc.response.status_code}"
        except (_httpx.TransportError, _httpx.TimeoutException) as exc:
            last = exc
            detail = type(exc).__name__

        if attempt == attempts:
            break
        delay = base_delay * (2 ** (attempt - 1))
        log.warning("%s failed (%s), attempt %s of %s, retrying in %.0fs",
                    what, detail, attempt, attempts, delay)
        _time.sleep(delay)

    assert last is not None
    raise last
