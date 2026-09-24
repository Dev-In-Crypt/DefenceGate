"""Waiting out a rate limiter.

A historical load walks thousands of pages from one address, and the edge in
front of a public portal answers a walk like that with 429 whether or not the
daily quota is anywhere near spent. The French history stopped at its 2,087th
publication day because four attempts over fourteen seconds was all the patience
the retry had; the day itself was fine, and re-running it succeeded.

So the ladder is tested for the two things that decide whether a run survives
such a block: how long it is willing to wait, and whether it believes the far
end when the far end states its own window.
"""

from __future__ import annotations

import httpx
import pytest

from dgate.sources import boamp as fr
from dgate.sources import request_with_retry, retry_after


def _error(status: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/records")
    response = httpx.Response(status, headers=headers or {}, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


class _Portal:
    """Fails with `status` for the first `failures` calls, then answers."""

    def __init__(self, failures: int, status: int = 429,
                 headers: dict[str, str] | None = None):
        self.failures, self.status, self.headers = failures, status, headers
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise _error(self.status, self.headers)
        return "page"


@pytest.fixture()
def slept(monkeypatch) -> list[float]:
    waits: list[float] = []
    monkeypatch.setattr("time.sleep", lambda seconds: waits.append(seconds))
    return waits


def test_the_ladder_doubles_and_stops_at_the_cap(slept):
    """Unbounded doubling would sleep for hours on the last attempt; a cap keeps
    the patience long without letting one page hold a run indefinitely."""
    portal = _Portal(failures=5)
    assert request_with_retry(portal, attempts=8, base_delay=2.0, max_delay=8.0) == "page"
    assert slept == [2.0, 4.0, 8.0, 8.0, 8.0]


def test_the_retry_after_the_portal_states_beats_our_guess(slept):
    portal = _Portal(failures=1, headers={"Retry-After": "45"})
    assert request_with_retry(portal, attempts=3, base_delay=2.0, max_delay=60.0) == "page"
    assert slept == [45.0]


def test_a_retry_after_date_is_read_as_a_delay():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    when = datetime.now(timezone.utc) + timedelta(seconds=90)
    response = httpx.Response(429, headers={"Retry-After": format_datetime(when)})
    seconds = retry_after(response)
    assert seconds is not None and 80 <= seconds <= 95


def test_a_retry_after_is_still_bounded_by_the_cap(slept):
    """A limiter may ask for an hour. Waiting an hour inside one page is how a
    run looks hung; the cap turns it into several shorter waits instead."""
    portal = _Portal(failures=2, headers={"Retry-After": "3600"})
    assert request_with_retry(portal, attempts=4, max_delay=30.0) == "page"
    assert slept == [30.0, 30.0]


def test_no_retry_after_header_leaves_the_ladder_alone(slept):
    portal = _Portal(failures=2, headers={"X-RateLimit-Remaining": "0"})
    assert request_with_retry(portal, attempts=4, base_delay=3.0) == "page"
    assert slept == [3.0, 6.0]


def test_a_refusal_that_is_not_transient_is_not_retried(slept):
    """400 means the query is wrong. Asking again asks the same wrong question."""
    portal = _Portal(failures=1, status=400)
    with pytest.raises(httpx.HTTPStatusError):
        request_with_retry(portal, attempts=4)
    assert portal.calls == 1 and slept == []


def test_the_last_failure_is_raised_not_swallowed(slept):
    portal = _Portal(failures=9)
    with pytest.raises(httpx.HTTPStatusError):
        request_with_retry(portal, attempts=3)
    assert portal.calls == 3


def test_the_french_pages_sit_out_a_two_minute_block(slept):
    """The settings the French connector actually passes, measured against the
    block that stopped the history: four attempts were not enough, so the test
    is on the total patience rather than on the numbers separately."""
    ladder = [min(fr.PAGE_MAX_DELAY, 2.0 * 2 ** i) for i in range(fr.PAGE_ATTEMPTS - 1)]
    assert sum(ladder) >= 120
    assert fr.REQUEST_PAUSE >= 1.0
