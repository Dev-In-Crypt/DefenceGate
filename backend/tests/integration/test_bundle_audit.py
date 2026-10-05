"""Every bundled index row must point at its own payload.

The failure this exists for is silent: a record addressed one line off returns
the wrong notice for the right key, and nothing complains.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import config, db
from dgate.ops import bundle_audit
from dgate.rawstore import FileRawStore, bundle_key, record_key
from dgate.sources import ted

pytestmark = pytest.mark.integration


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield FileRawStore(tmp_path / "raw")
    config.reset_cache()


def _land_bundle(conn, store, payloads, day=date(2026, 9, 17)):
    key = bundle_key("ted", day)
    store.put_records(key, payloads)
    src = db.source_id(conn, "ted")
    for line, payload in enumerate(payloads):
        db.record_raw(conn, src, f"n{line}", ted.content_hash(payload), record_key(key, line))
    conn.commit()
    return key


def test_a_correct_bundle_reports_nothing(conn, store):
    _land_bundle(conn, store, [{"notice-identifier": [f"{i}"]} for i in range(5)])
    report = bundle_audit.audit("ted", store=store)
    assert (report.bundles, report.rows, report.misplaced) == (1, 5, 0)


def test_a_row_pointing_at_the_wrong_line_is_found(conn, store):
    key = _land_bundle(conn, store, [{"notice-identifier": [f"{i}"]} for i in range(5)])
    conn.execute("UPDATE raw_ingest SET storage_key = %s WHERE storage_key = %s",
                 (record_key(key, 4), record_key(key, 1)))
    conn.commit()
    report = bundle_audit.audit("ted", store=store)
    assert report.misplaced == 1 and report.repaired == 0


def test_repair_puts_the_row_back_on_its_own_payload(conn, store):
    """Repair is by content hash, so it works whatever shifted the line."""
    key = _land_bundle(conn, store, [{"notice-identifier": [f"{i}"]} for i in range(5)])
    conn.execute("UPDATE raw_ingest SET storage_key = %s WHERE storage_key = %s",
                 (record_key(key, 4), record_key(key, 1)))
    conn.commit()
    report = bundle_audit.audit("ted", repair=True, store=store)
    assert report.repaired == 1
    rows = conn.execute("SELECT storage_key, content_hash FROM raw_ingest ORDER BY id").fetchall()
    assert all(ted.content_hash(store.get(r["storage_key"])) == r["content_hash"] for r in rows)


def test_a_payload_that_is_not_in_the_bundle_at_all_is_reported_not_guessed(conn, store):
    key = _land_bundle(conn, store, [{"notice-identifier": ["0"]}])
    src = db.source_id(conn, "ted")
    db.record_raw(conn, src, "ghost", "0" * 64, record_key(key, 7))
    conn.commit()
    report = bundle_audit.audit("ted", repair=True, store=store)
    assert report.repaired == 0
    assert report.unresolved == [record_key(key, 7)]


def test_a_notice_carrying_a_unicode_line_separator_is_addressed_correctly(conn, store):
    """The bug this was written for: U+2028 inside a notice used to shift every
    record after it by one line."""
    payloads = [{"notice-identifier": ["0"]},
                {"notice-identifier": ["1"], "notice-title": {"fra": "ligne\u2028suivante"}},
                {"notice-identifier": ["2"]}]
    _land_bundle(conn, store, payloads)
    report = bundle_audit.audit("ted", store=store)
    assert report.misplaced == 0
    rows = conn.execute("SELECT storage_key FROM raw_ingest ORDER BY id").fetchall()
    assert [store.get(r["storage_key"])["notice-identifier"][0] for r in rows] == ["0", "1", "2"]



def _payloads(n: int, tag: str = "") -> list[dict]:
    return [{"notice-identifier": [f"{tag}{i}"]} for i in range(n)]


def test_the_audit_reads_the_index_once_not_once_per_bundle(conn, store, monkeypatch):
    """One query per bundle was a sequential scan of the whole table each time, and
    with two audits running they saturated the host for hours. The audit hands
    every bundle its rows from a single ordered pass."""
    seen: list[int] = []
    real = bundle_audit.audit_bundle

    def spy(conn_, store_, source, bundle, **kw):
        assert kw["rows"] is not None, "the bundle's rows must come from the single pass"
        seen.append(len(kw["rows"]))
        return real(conn_, store_, source, bundle, **kw)

    monkeypatch.setattr(bundle_audit, "audit_bundle", spy)
    _land_bundle(conn, store, _payloads(3, "a"), day=date(2026, 10, 5))
    _land_bundle(conn, store, _payloads(5, "b"), day=date(2026, 10, 6))
    report = bundle_audit.audit("ted", store=store)
    assert (report.bundles, report.rows, report.misplaced) == (2, 8, 0)
    assert sorted(seen) == [3, 5]


def test_a_limit_stops_the_stream_after_that_many_bundles(conn, store):
    for day in (5, 6, 7):
        _land_bundle(conn, store, _payloads(2, f"d{day}"), day=date(2026, 10, day))
    assert bundle_audit.audit("ted", store=store, limit=2).bundles == 2


def test_rows_of_one_bundle_stay_together_whatever_the_database_locale(conn, store):
    """Bundles named so that a locale-aware sort would interleave them: punctuation
    is ignored at the first comparison under en_US, so `bundle-0000.jsonl.gz#1`
    could land between the rows of `bundle0000.jsonl.gz#...`. Byte order cannot."""
    src = db.source_id(conn, "ted")
    for name in ("a/bundle-0000.jsonl.gz", "a/bundle0000.jsonl.gz", "a/bundle-0000x.jsonl.gz"):
        store.put_records(name, _payloads(3, name))
        for line, payload in enumerate(_payloads(3, name)):
            db.record_raw(conn, src, f"{name}{line}", ted.content_hash(payload),
                          record_key(name, line))
    conn.commit()
    groups = {bundle: len(rows) for bundle, rows in bundle_audit.rows_by_bundle("ted")}
    assert groups == {"a/bundle-0000.jsonl.gz": 3, "a/bundle0000.jsonl.gz": 3,
                      "a/bundle-0000x.jsonl.gz": 3}


def test_repair_works_while_the_index_is_being_streamed(conn, store):
    """The stream holds a named cursor, which a commit closes. Repair commits, so
    it must be on a different connection from the stream."""
    key = _land_bundle(conn, store, _payloads(5))
    conn.execute("UPDATE raw_ingest SET storage_key = %s WHERE storage_key = %s",
                 (record_key(key, 4), record_key(key, 1)))
    conn.commit()
    report = bundle_audit.audit("ted", store=store, repair=True)
    assert (report.misplaced, report.repaired) == (1, 1)
    assert bundle_audit.audit("ted", store=store).misplaced == 0
