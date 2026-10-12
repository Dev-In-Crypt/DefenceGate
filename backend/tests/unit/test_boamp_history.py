"""The French history: never faster than one request a second, and a clean stop.

The history stopped on 23 September 2026 at HTTP 429 and was never resumed:
1,534 official defence notices from 17 November 2020 to 20 September 2026 are
missing (finding F14). What was wrong, in order:

- the pause was between the pages of one day, so the first page of the next day
  followed the last page of the previous one at once;
- a 429 that outlasted the ladder ended the run with a traceback, and nothing
  said when it was safe to ask again.

These tests run the real client over httpx's mock transport with a fake clock,
so they cost no time and ask nothing of the source.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from dgate.sources import RateLimited
from dgate.sources import boamp as fr


class _Clock:
    """Stands in for the `time` module as boamp.py sees it."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture()
def clock(monkeypatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(fr, "time", fake)
    monkeypatch.setattr(fr, "_last_request", 0.0)
    # request_with_retry sleeps through the real module; keep it instant.
    monkeypatch.setattr("time.sleep", lambda seconds: fake.slept.append(seconds))
    return fake


def _portal(records_per_day: int, log: list[float], clock: _Clock):
    def handler(request: httpx.Request) -> httpx.Response:
        log.append(clock.now)
        params = request.url.params
        offset, limit = int(params["offset"]), int(params["limit"])
        rows = [{"idweb": f"26-{i}"} for i in range(records_per_day)][offset:offset + limit]
        return httpx.Response(200, json={"total_count": records_per_day, "results": rows})
    return handler


def test_no_two_requests_are_less_than_a_second_apart_even_across_days(clock):
    """Three days of 250 notices: three pages each, a client per day as the
    history does. Nine requests, every gap at least REQUEST_PAUSE."""
    started: list[float] = []
    handler = _portal(250, started, clock)
    for day in (date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18)):
        client = fr._new_client(transport=httpx.MockTransport(handler))
        assert len(list(fr.search(fr.day_query(day), client=client))) == 250
        client.close()
    assert len(started) == 9
    gaps = [b - a for a, b in zip(started, started[1:], strict=False)]
    assert min(gaps) >= fr.REQUEST_PAUSE


def test_a_retried_request_is_paced_like_any_other(clock):
    """The ladder's own waits are longer than a second, but a 500 answered at
    once must not be asked again at once."""
    started: list[float] = []
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        started.append(clock.now)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"total_count": 1, "results": [{"idweb": "26-1"}]})

    client = fr._new_client(transport=httpx.MockTransport(handler))
    assert [r["idweb"] for r in fr.search(fr.day_query(date(2026, 9, 16)), client=client)] == ["26-1"]
    assert started[1] - started[0] >= fr.REQUEST_PAUSE


def test_a_rate_limit_that_outlasts_the_ladder_is_raised_as_rate_limited(clock):
    """With the Retry-After the source stated, after PAGE_ATTEMPTS attempts."""
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "7"})

    client = fr._new_client(transport=httpx.MockTransport(handler))
    with pytest.raises(RateLimited) as stopped:
        list(fr.search(fr.day_query(date(2026, 9, 16)), client=client))
    assert stopped.value.retry_after == 7.0
    assert seen["n"] == fr.PAGE_ATTEMPTS
    # it waited the 7 seconds the source asked for between attempts, not our guess
    assert [s for s in clock.slept if s >= 2][:3] == [7.0, 7.0, 7.0]


def test_the_waits_the_source_states_beat_our_ladder_but_stay_capped(clock):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "3600"})

    client = fr._new_client(transport=httpx.MockTransport(handler))
    with pytest.raises(RateLimited) as stopped:
        list(fr.search(fr.day_query(date(2026, 9, 16)), client=client))
    assert stopped.value.retry_after == 3600.0           # recorded for the marker
    assert max(clock.slept) == fr.PAGE_MAX_DELAY         # but never slept in one go


def test_a_forbidden_burst_is_a_rate_limit_too(clock):
    """The edge answers a burst of requests from one address with 403."""
    client = fr._new_client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(RateLimited):
        list(fr.search(fr.day_query(date(2026, 9, 16)), client=client))


def test_a_server_error_is_not_dressed_up_as_a_rate_limit(clock):
    client = fr._new_client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        list(fr.search(fr.day_query(date(2026, 9, 16)), client=client))


def test_a_query_error_is_raised_at_once(clock):
    """400 means the query is wrong; asking again asks the same wrong thing."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    client = fr._new_client(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        list(fr.search(fr.day_query(date(2026, 9, 16)), client=client))
    assert calls["n"] == 1
