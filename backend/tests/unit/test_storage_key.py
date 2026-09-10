"""The key is what makes the store write-once.

Neither backend refuses to overwrite; both will happily replace an object. The
guarantee holds only because two different payloads can never be handed the
same key. Without the content hash in it, a notice observed twice in one day
wrote twice to one key and the earlier payload was gone -- silently, because
overwriting is not an error.

That is not a corner case. PLACSP publishes one feed entry per modification,
which *is* its version history, so the same notice appearing several times in a
day is the normal shape of the source. Measured on 10 September 2026, one day's
ingest destroyed 11,496 distinct payloads this way.
"""

from __future__ import annotations

from datetime import date

from dgate.rawstore import FileRawStore, storage_key


def test_two_payloads_of_one_notice_get_two_keys():
    day = date(2026, 9, 10)
    first = storage_key("es_placsp", "ES-12345", day, content_hash="aaaa" * 16)
    second = storage_key("es_placsp", "ES-12345", day, content_hash="bbbb" * 16)
    assert first != second


def test_the_same_payload_keeps_the_same_key():
    """Re-running an ingest must not cost a second object for identical bytes."""
    day = date(2026, 9, 10)
    h = "c" * 64
    assert (storage_key("ted", "N-1", day, content_hash=h)
            == storage_key("ted", "N-1", day, content_hash=h))


def test_the_key_stays_partitioned_by_source_and_day():
    key = storage_key("ted", "N-1", date(2026, 9, 10), content_hash="d" * 64)
    assert key.startswith("ted/2026/09/10/")
    assert key.endswith(".json")


def test_a_key_without_a_hash_is_still_produced():
    """Objects written before this was understood keep their keys and stay readable."""
    key = storage_key("ted", "N-1", date(2026, 9, 10))
    assert key == "ted/2026/09/10/N-1.json"


def test_identifiers_with_slashes_do_not_escape_the_partition():
    key = storage_key("es_placsp", "../../etc/passwd", date(2026, 9, 10),
                      content_hash="e" * 64)
    assert key.startswith("es_placsp/2026/09/10/")
    assert "/etc/" not in key


def test_two_versions_seen_the_same_day_both_survive_in_the_store(tmp_path):
    """The end-to-end property: nothing is lost to an overwrite."""
    store = FileRawStore(tmp_path)
    day = date(2026, 9, 10)
    v1, v2 = {"value": 100}, {"value": 200}
    k1 = store.put(storage_key("es_placsp", "ES-1", day, content_hash="a" * 64), v1)
    k2 = store.put(storage_key("es_placsp", "ES-1", day, content_hash="b" * 64), v2)
    assert store.get(k1) == v1
    assert store.get(k2) == v2
    assert len(list(store.list("es_placsp"))) == 2


def test_listing_reports_when_each_object_was_written(tmp_path):
    """A rebuild replays in observation order, which key order cannot supply."""
    import os
    import time

    store = FileRawStore(tmp_path)
    day = date(2026, 9, 10)
    # 'z' sorts after 'a', so key order and write order disagree on purpose.
    late = store.put(storage_key("ted", "N-1", day, content_hash="z" * 64), {"v": 1})
    time.sleep(0.02)
    early = store.put(storage_key("ted", "N-1", day, content_hash="a" * 64), {"v": 2})
    os.utime(tmp_path / late, (1_000_000, 1_000_000))
    os.utime(tmp_path / early, (2_000_000, 2_000_000))

    by_time = [k for k, _ in sorted(store.listing("ted"), key=lambda kv: kv[1])]
    assert by_time == [late, early], "listing must order by write time, not by key"
