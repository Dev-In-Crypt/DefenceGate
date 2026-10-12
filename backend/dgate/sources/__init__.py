"""Source connectors.

Every connector fetches and yields payloads and does nothing else. Parsing that
can differ between sources lives in the connector; everything shared lives in
normalise.py, so that a new source cannot quietly invent its own schema.
"""

import logging
import re

# The largest response body any connector will accept. The biggest real one is the
# EU portal's reference data, 124 MiB; a source sending more than this is not
# sending what we asked for, and the worker has 3.8 GB on a shared host.
MAX_BODY_BYTES = 256 * 1024 * 1024


class ResponseTooLarge(RuntimeError):
    """A response body larger than MAX_BODY_BYTES."""


class RateLimited(RuntimeError):
    """The source refused us for rate (HTTP 429, or the 403 its edge answers a burst
    with) and the retry ladder did not clear it.

    A historical load that meets this stops cleanly and records when it may
    resume; it does not keep asking, and it does not crash. `retry_after` is the
    far end's own statement of its window in seconds, when it made one.
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


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


def _cap_body(response) -> None:
    """Refuse a response body larger than MAX_BODY_BYTES *while it is read*.

    httpx runs response hooks after the headers and before the body is read, so a
    declared length is refused without downloading anything, and a body that does not
    declare one (chunked, or compressed) is counted as it is decoded and cut off the
    moment it passes the ceiling. `request_with_retry` only looked after the whole body
    was already in memory, which is the thing this exists to prevent.

    Not for streamed downloads (`client.stream`): the body is consumed here. No
    connector uses one through a client; the Atlas file is fetched by its own
    `httpx.stream` and is deliberately large.
    """
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        response.close()
        raise ResponseTooLarge(
            f"{response.request.url.host}: declared body of {declared} bytes exceeds "
            f"{MAX_BODY_BYTES}")
    total = 0
    parts: list[bytes] = []
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            response.close()
            raise ResponseTooLarge(
                f"{response.request.url.host}: body passed {MAX_BODY_BYTES} bytes")
        parts.append(chunk)
    # What `Response.read()` would have stored; it returns this instead of reading.
    response._content = b"".join(parts)


def new_client(**kwargs):
    """The one way a connector makes an HTTP client: the same as `httpx.Client`, with
    the body ceiling applied to every response."""
    import httpx

    hooks = kwargs.pop("event_hooks", None) or {}
    hooks = {**hooks, "response": [_cap_body, *hooks.get("response", [])]}
    return httpx.Client(event_hooks=hooks, **kwargs)


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
            response = send()
            body = getattr(response, "content", None)
            if isinstance(body, (bytes, bytearray)) and len(body) > MAX_BODY_BYTES:
                raise ResponseTooLarge(
                    f"{what}: response body of {len(body)} bytes exceeds {MAX_BODY_BYTES}")
            return response
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


MAX_HTML_CHARS = 2_000_000
_BLOCK_OPEN = re.compile(r"<(script|style|nav|header|footer)[^<>]{0,2000}>")
_ANY_TAG = re.compile(r"<[^<>]{1,2000}>")


def html_to_text_markup(markup: str) -> str:
    """Remove script, style, nav, header and footer blocks and every tag, in time
    linear in the page.

    The expressions this replaces (`<(nav)[^>]*>.*?</nav>` and `<[^>]+>`) rescan to
    the end of the page for every opening tag that is never closed, so a page of
    a few hundred thousand unclosed tags held the worker for minutes: `re` does
    not release the GIL. Found by the security review of 12 October 2026.
    """
    markup = markup[:MAX_HTML_CHARS]
    out: list[str] = []
    pos = 0
    no_close: set[str] = set()      # once a tag has no closer after here, none later has
    while True:
        m = _BLOCK_OPEN.search(markup, pos)
        if not m:
            out.append(markup[pos:])
            break
        tag = m.group(1)
        if tag in no_close:
            out.append(markup[pos:m.end()])
            pos = m.end()
            continue
        close = markup.find(f"</{tag}>", m.end())
        if close == -1:
            no_close.add(tag)
            out.append(markup[pos:m.end()])
            pos = m.end()
            continue
        out.append(markup[pos:m.start()])
        out.append(" ")
        pos = close + len(tag) + 3
    return _ANY_TAG.sub(" ", "".join(out))
