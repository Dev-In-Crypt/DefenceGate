"""Compaction deletes ingested payloads, so these tests are about when it must not.

The store is the archive's insurance. The only acceptable deletion is of an
object whose bytes are already in a bundle that was read back and checked, and
that no index row points at any more.
"""

from __future__ import annotations

from datetime import date

import pytest

from dgate import config, db
from dgate.ops import compact_raw as cr
from dgate.rawstore import FileRawStore, bundle_key, storage_key
from dgate.sources import ted

pytestmark = pytest.mark.integration


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path / "raw"))
    config.reset_cache()
    yield FileRawStore(tmp_path / "raw")
    config.reset_cache()


def _land(conn, store, n: int, day=date(2026, 9, 16)) -> list[str]:
    src = db.source_id(conn, "ted")
    keys = []
    for i in range(n):
        payload = {"publication-number": [f"{i:06d}-2024"], "notice-title": {"eng": f"n{i}"}}
        h = ted.content_hash(payload)
        key = storage_key("ted", f"{i:06d}-2024", day, content_hash=h)
        store.put(key, payload)
        db.record_raw(conn, src, f"{i:06d}-2024", h, key)
        keys.append(key)
    conn.commit()
    return keys


def _keys(conn) -> list[str]:
    return [r["storage_key"] for r in conn.execute(
        "SELECT storage_key FROM raw_ingest ORDER BY id").fetchall()]


def test_originals_become_one_verified_bundle_and_are_then_deleted(conn, store):
    originals = _land(conn, store, 7)
    progress = cr.compact("ted", chunk=5, store=store)

    assert progress.chunks == 2 and progress.deleted == 7
    assert all("#" in k for k in _keys(conn))
    assert not any(store.exists(k) for k in originals)
    assert [store.get(k)["notice-title"]["eng"] for k in _keys(conn)] == \
        [f"n{i}" for i in range(7)]
    assert conn.execute("SELECT count(*) n FROM compaction_pending").fetchone()["n"] == 0


def test_a_payload_that_no_longer_matches_its_hash_stops_everything(conn, store):
    """A corrupted original must never be laundered into a bundle and have its
    only other trace deleted."""
    originals = _land(conn, store, 3)
    store.put(originals[1], {"publication-number": ["tampered"]})
    with pytest.raises(RuntimeError, match="no longer matches"):
        cr.compact("ted", chunk=10, store=store)
    assert _keys(conn) == originals
    assert all(store.exists(k) for k in originals)


def test_a_bundle_that_does_not_read_back_right_deletes_nothing(conn, store, monkeypatch):
    originals = _land(conn, store, 3)
    real = store.put_records

    def short(key, payloads):
        return real(key, list(payloads)[:-1])

    monkeypatch.setattr(store, "put_records", short)
    with pytest.raises(RuntimeError, match="holds 2 lines, not 3"):
        cr.compact("ted", chunk=10, store=store)
    assert _keys(conn) == originals
    assert all(store.exists(k) for k in originals)


def test_deletions_interrupted_after_repointing_are_finished_next_run(conn, store, monkeypatch):
    """Rows repointed, originals journaled, process dies before deleting: the
    journal is what stops those objects becoming orphans nobody knows about."""
    originals = _land(conn, store, 3)
    monkeypatch.setattr(store, "delete_many", lambda keys: (_ for _ in ()).throw(
        ConnectionError("gone")))
    with pytest.raises(ConnectionError):
        cr.compact("ted", chunk=10, store=store)
    assert conn.execute("SELECT count(*) n FROM compaction_pending").fetchone()["n"] == 3

    monkeypatch.undo()
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    cr.drain_pending(conn, store)
    assert not any(store.exists(k) for k in originals)
    assert conn.execute("SELECT count(*) n FROM compaction_pending").fetchone()["n"] == 0


def test_a_compacted_bundle_never_overwrites_an_existing_one(conn, store):
    """The history already writes bundle-0000 for each publication day; a
    compaction bundle landing on that name would destroy those records."""
    day = date(2026, 9, 16)
    store.put_records(bundle_key("ted", day), [{"keep": "me"}])
    _land(conn, store, 2, day=day)
    cr.compact("ted", chunk=10, store=store)
    assert store.get(bundle_key("ted", day) + "#0") == {"keep": "me"}


def test_a_source_whose_hash_is_unknown_is_refused_before_anything_is_touched(conn, store):
    """A source added tomorrow may hash its payloads differently. Compaction
    deletes originals, so an unregistered source is refused rather than assumed."""
    with pytest.raises(ValueError, match="refusing"):
        cr.compact("nato_diana", store=store)


def test_the_sources_that_are_registered_all_hash_the_same_way(conn, store):
    """The registry claims Spain and Poland hash as TED does. They do -- the
    Polish connector's own function calls TED's, and the pipeline calls TED's
    directly for the others -- and this is what keeps that claim checked."""
    from dgate.sources import ted

    payload = {"b": 2, "a": [1, "x"]}
    for code in ("pl_atlas", "pl_ezam", "es_placsp", "es_placsp_agg"):
        assert cr.hasher(code)(payload) == ted.content_hash(payload), code


def test_a_dry_run_reads_and_verifies_and_changes_nothing(conn, store):
    originals = _land(conn, store, 3)
    cr.compact("ted", chunk=10, store=store, dry_run=True)
    assert _keys(conn) == originals
    assert all(store.exists(k) for k in originals)


def test_already_compacted_rows_are_not_touched_again(conn, store):
    _land(conn, store, 3)
    cr.compact("ted", chunk=10, store=store)
    first = _keys(conn)
    assert cr.compact("ted", chunk=10, store=store).chunks == 0
    assert _keys(conn) == first


def test_a_duplicate_row_outside_the_chunk_is_repointed_with_it(conn, store):
    """A key carries its payload's content hash, so the same payload landed twice
    shares one key -- the first Polish chunk was 5,000 rows over 4,611 keys.
    Repointing only this chunk's ids leaves the sibling pointing at the original,
    which then cannot be deleted and stops the run. Both rows move, and both
    still read their payload."""
    originals = _land(conn, store, 3)
    src = db.source_id(conn, "ted")
    first = conn.execute(
        "SELECT content_hash FROM raw_ingest ORDER BY id LIMIT 1").fetchone()
    db.record_raw(conn, src, "000000-2024", first["content_hash"], originals[0])
    conn.commit()

    cr.compact("ted", chunk=2, store=store)

    keys = [r["storage_key"] for r in conn.execute(
        "SELECT storage_key FROM raw_ingest WHERE storage_key LIKE %s ORDER BY id",
        (originals[0].rsplit("/", 1)[0] + "%",)).fetchall()]
    assert all("#" in k for k in keys), keys
    assert not store.exists(originals[0])
    assert all(store.get(k) is not None for k in keys)


def test_an_object_a_later_chunk_still_points_at_is_not_deleted(conn, store):
    """The safety property the repointing must not cost: step 4 deletes only what
    nothing references any more."""
    originals = _land(conn, store, 4)
    cr.compact("ted", chunk=2, max_chunks=1, store=store)
    assert not store.exists(originals[0]) and not store.exists(originals[1])
    assert store.exists(originals[2]) and store.exists(originals[3])


def test_a_key_recorded_under_two_hashes_is_left_alone(conn, store):
    """Spain's early keys carried no content hash, so a second version of a notice
    overwrote the first at the same key and the index kept both rows. One of the two
    payloads is already gone; compaction cannot tell which row it is looking at, so
    it skips the key instead of stopping the run or deleting on a guess."""
    originals = _land(conn, store, 3)
    src = db.source_id(conn, "ted")
    db.record_raw(conn, src, "000000-2024", "a" * 64, originals[1])
    conn.commit()

    progress = cr.compact("ted", chunk=10, store=store)

    assert store.exists(originals[1])                       # the ambiguous one survives
    assert not store.exists(originals[0]) and not store.exists(originals[2])
    assert progress.objects == 2


def test_a_read_the_store_throttles_is_waited_out_not_abandoned(conn, store, monkeypatch):
    """R2 answers a chunk of reads on one day prefix with ServiceUnavailable. Half a
    million objects in, that ended the run twice. The read waits and tries again."""
    originals = _land(conn, store, 3)
    real_get = store.get
    failures = {"left": 2}

    def flaky(key):
        if failures["left"] and not key.endswith(".gz") and "#" not in key:
            failures["left"] -= 1
            raise RuntimeError("ServiceUnavailable: Reduce your rate of simultaneous reads")
        return real_get(key)

    monkeypatch.setattr(store, "get", flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)

    cr.compact("ted", chunk=10, store=store)
    assert failures["left"] == 0
    assert all(not store.exists(k) for k in originals)
