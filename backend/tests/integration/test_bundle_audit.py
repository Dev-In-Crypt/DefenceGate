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
