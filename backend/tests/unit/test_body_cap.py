"""The response-body ceiling is applied while a body is read, not after it is in memory."""

from __future__ import annotations

import gzip

import httpx
import pytest

from dgate import sources
from dgate.sources import ResponseTooLarge, new_client


@pytest.fixture(autouse=True)
def small_ceiling(monkeypatch):
    monkeypatch.setattr(sources, "MAX_BODY_BYTES", 1_000)


def _client(handler):
    return new_client(transport=httpx.MockTransport(handler))


def test_a_body_under_the_ceiling_reads_normally():
    with _client(lambda r: httpx.Response(200, json={"a": 1})) as c:
        assert c.get("https://example.test/").json() == {"a": 1}


def test_a_declared_length_over_the_ceiling_is_refused_before_the_body_is_read():
    read = []

    def handler(request):
        def body():
            read.append(True)
            yield b"x" * 5_000
        return httpx.Response(200, headers={"content-length": "5000"}, stream=_Stream(body))

    with _client(handler) as c, pytest.raises(ResponseTooLarge):
        c.get("https://example.test/")
    assert read == []


def test_an_undeclared_length_is_counted_as_it_arrives_and_cut_off():
    pulled = []

    def handler(request):
        def body():
            for _ in range(100):
                pulled.append(1)
                yield b"x" * 100
        return httpx.Response(200, stream=_Stream(body))

    with _client(handler) as c, pytest.raises(ResponseTooLarge):
        c.get("https://example.test/")
    assert len(pulled) < 100        # stopped part-way, not after reading all of it


def test_a_compressed_body_is_counted_decoded():
    bomb = gzip.compress(b"0" * 100_000)          # a few hundred bytes on the wire
    assert len(bomb) < 1_000

    def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, content=bomb)

    with _client(handler) as c, pytest.raises(ResponseTooLarge):
        c.get("https://example.test/")


class _Stream(httpx.SyncByteStream):
    def __init__(self, make):
        self._make = make

    def __iter__(self):
        return iter(self._make())
