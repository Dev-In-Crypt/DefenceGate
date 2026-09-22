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
    with pytest.raises(ValueError, match="refusing"):
        cr.compact("es_placsp", store=store)


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


def test_an_object_still_referenced_from_outside_the_chunk_is_not_deleted(conn, store):
    """Rows are repointed by id, one statement per chunk. A row pointing at the
    same object from outside the chunk is not repointed with it -- and the
    object it points at must then survive."""
    originals = _land(conn, store, 3)
    src = db.source_id(conn, "ted")
    h = conn.execute("SELECT content_hash FROM raw_ingest ORDER BY id LIMIT 1").fetchone()
    db.record_raw(conn, src, "000000-2024", h["content_hash"], originals[0])
    conn.commit()

    with pytest.raises(RuntimeError, match="still referenced"):
        cr.compact("ted", chunk=2, store=store)
    assert store.exists(originals[0])
    assert all(store.exists(k) for k in originals)
