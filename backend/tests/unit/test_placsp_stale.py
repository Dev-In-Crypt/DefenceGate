"""A PLACSP live feed that stops moving must not be reported as a success.

Dataset 1's head file was last modified on 8 September 2026 and served unchanged
on the 14th. For six days every run re-read the same 19,497 entries, cleared its
floor of 400 -- a floor counts what was read, not what was new -- and reported
success. The publisher's monthly archive was current throughout.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import httpx
import pytest

from dgate import pipeline
from dgate.sources import placsp

from .test_placsp import _entry, _page

NOW = datetime(2026, 9, 14, 7, 9, tzinfo=timezone.utc)


def _run(monkeypatch, newest: datetime | None, now: datetime = NOW):
    calls: list[tuple[str, str | None]] = []
    sent: list[str] = []

    def fake_live(ds, max_pages, observe):
        observe["newest"] = newest
        return iter(())

    def fake_ingest(opps, label, ds, stale_reason=None):
        list(opps)
        calls.append((label, stale_reason() if stale_reason else None))

    monkeypatch.setattr(placsp, "fetch_live", fake_live)
    monkeypatch.setattr(placsp, "fetch_archive", lambda url, ds: iter(()))
    monkeypatch.setattr(pipeline, "_ingest_placsp", fake_ingest)
    monkeypatch.setattr("dgate.ops.notify.notify", lambda text: sent.append(text))
    pipeline.run_placsp_live(datasets=[placsp.MAIN], now=now)
    return calls, sent


def test_a_frozen_feed_is_partial_loud_and_covered_from_the_archive(monkeypatch):
    calls, sent = _run(monkeypatch, datetime(2026, 9, 8, 18, 12, tzinfo=timezone.utc))
    live_label, live_reason = calls[0]
    assert live_label == "es_placsp-live"
    assert live_reason and "stale" in live_reason
    assert [label for label, _ in calls[1:]] == ["es_placsp-202609"]
    assert sent and "stale" in sent[0]


def test_a_fresh_feed_reads_no_archive(monkeypatch):
    calls, sent = _run(monkeypatch, datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc))
    assert calls == [("es_placsp-live", None)]
    assert sent == []


def test_an_empty_feed_counts_as_stale(monkeypatch):
    calls, _ = _run(monkeypatch, None)
    assert calls[0][1] and "stale" in calls[0][1]


def test_early_in_a_month_the_previous_month_is_read_too(monkeypatch):
    early = datetime(2026, 10, 2, 7, 0, tzinfo=timezone.utc)
    calls, _ = _run(monkeypatch, datetime(2026, 9, 28, tzinfo=timezone.utc), now=early)
    assert [label for label, _ in calls[1:]] == ["es_placsp-202609", "es_placsp-202610"]


def test_an_archive_is_handed_on_in_source_order_and_reports_its_newest():
    """An archive is the same chain, newest first; read in file order it
    re-archives history as change, exactly as the live walk did."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a_newer.atom", _page(_entry("EXP-9", "ADJ", "2026-09-08T20:00:00+02:00"), None))
        zf.writestr("b_older.atom", _page(_entry("EXP-9", "PUB", "2026-09-07T10:00:00+02:00"), None))
    body = buf.getvalue()
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=body))
    seen: dict = {}
    with httpx.Client(transport=transport) as client:
        opps = list(placsp.fetch_archive("https://example.test/x_202609.zip", placsp.MAIN,
                                         client=client, observe=seen))
    assert [o.status_native for o in opps] == ["PUB", "ADJ"]
    assert seen["newest"] == datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc)
    assert seen["entries"] == 2


@pytest.mark.parametrize("hours, stale", [(35, False), (37, True)])
def test_the_threshold_is_the_configured_hours(monkeypatch, hours, stale):
    from datetime import timedelta

    calls, _ = _run(monkeypatch, NOW - timedelta(hours=hours))
    assert bool(calls[0][1]) is stale
