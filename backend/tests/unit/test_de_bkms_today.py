"""The German feed answers HTTP 400 for today's publication day: that is "not yet", not a failure."""

from datetime import date, timedelta

import httpx

from dgate.sources import de_bkms


def _client(status: int) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status)))


def test_a_400_for_today_means_no_file_yet():
    with _client(400) as c:
        assert de_bkms.open_day(date.today(), client=c) is None


def test_a_400_for_a_past_day_is_still_an_error():
    import pytest
    with _client(400) as c, pytest.raises(httpx.HTTPStatusError):
        de_bkms.open_day(date.today() - timedelta(days=3), client=c, attempts=1)
