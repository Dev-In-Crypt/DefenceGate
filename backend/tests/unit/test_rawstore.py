"""Raw payload storage (plan task M0-07)."""

from datetime import date

import pytest

from dgate import config
from dgate.rawstore import (
    FileRawStore,
    RawStore,
    build_store,
    bundle_key,
    record_key,
    split_record_key,
    storage_key,
)


def test_key_is_partitioned_by_source_and_date():
    assert storage_key("ted", "00512345-2026", date(2026, 9, 7)) == \
        "ted/2026/09/07/00512345-2026.json"


def test_key_sanitises_identifiers_that_contain_separators():
    key = storage_key("es_placsp", "EXP/2026 001", date(2026, 1, 2))
    assert key == "es_placsp/2026/01/02/EXP_2026_001.json"
    assert ".." not in key


def test_serialisation_is_stable_across_key_order():
    """Identical content must produce identical bytes, or replay sees a change."""
    a = RawStore.serialise({"x": 1, "y": [2, 3]})
    b = RawStore.serialise({"y": [2, 3], "x": 1})
    assert a == b


def test_round_trip_on_the_filesystem(tmp_path):
    store = FileRawStore(tmp_path)
    key = storage_key("ted", "abc", date(2026, 9, 7))
    assert not store.exists(key)
    store.put(key, {"notice-identifier": "abc", "value": 42})
    assert store.exists(key)
    assert store.get(key) == {"notice-identifier": "abc", "value": 42}
    assert (tmp_path / "ted" / "2026" / "09" / "07" / "abc.json").is_file()


def test_key_cannot_escape_the_store_root(tmp_path):
    store = FileRawStore(tmp_path)
    with pytest.raises(ValueError):
        store.put("../../etc/passwd.json", {"x": 1})


def test_build_store_follows_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path))
    config.reset_cache()
    try:
        store = build_store()
        assert isinstance(store, FileRawStore)
        assert store.root == tmp_path
    finally:
        config.reset_cache()


def test_unknown_backend_fails_loudly():
    with pytest.raises(ValueError):
        build_store("carrier-pigeon")


# ------------------------------------------------ backend selection

def test_the_s3_backend_is_built_from_configuration(monkeypatch):
    from dgate.rawstore import S3RawStore

    monkeypatch.setenv("DGATE_RAW_BACKEND", "s3")
    monkeypatch.setenv("DGATE_S3_BUCKET", "somewhere")
    monkeypatch.setenv("DGATE_S3_ENDPOINT", "https://example.test")
    monkeypatch.setenv("DGATE_S3_ACCESS_KEY", "key")
    monkeypatch.setenv("DGATE_S3_SECRET_KEY", "secret")
    config.reset_cache()
    try:
        store = build_store()
        assert isinstance(store, S3RawStore)
        assert store.bucket == "somewhere"
        assert store._client_kwargs["endpoint_url"] == "https://example.test"
    finally:
        config.reset_cache()


def test_credentials_left_empty_are_not_passed_as_none(monkeypatch):
    """Unset credentials must fall through to the instance role, not override
    it with None, which is how a deployment supplies them without a file."""
    monkeypatch.setenv("DGATE_RAW_BACKEND", "s3")
    monkeypatch.delenv("DGATE_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("DGATE_S3_SECRET_KEY", raising=False)
    monkeypatch.delenv("DGATE_S3_ENDPOINT", raising=False)
    config.reset_cache()
    try:
        options = config.settings().s3_settings()
        assert "aws_access_key_id" not in options
        assert "endpoint_url" not in options
        assert options["region_name"] == "auto"
    finally:
        config.reset_cache()


def test_deleting_is_available_for_probes_only(tmp_path):
    """The check writes a probe and must be able to remove it. Ingested
    payloads are never deleted; that is why this is the only caller."""
    store = FileRawStore(tmp_path)
    key = storage_key("ted", "probe", date(2026, 9, 8))
    store.put(key, {"probe": True})
    assert store.delete(key) is True
    assert store.delete(key) is False, "deleting what is not there is not an error"
    assert not store.exists(key)


def test_the_check_writes_reads_and_cleans_up(tmp_path, monkeypatch):
    from dgate.ops.rawstore_cli import check, count

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(tmp_path))
    config.reset_cache()
    try:
        message = check()
        assert "wrote, read and deleted" in message
        assert count() == {}, "the probe must not be left behind"
    finally:
        config.reset_cache()


def test_copying_between_stores_skips_what_is_already_there(tmp_path, monkeypatch):
    from dgate.ops.rawstore_cli import copy_from

    origin = tmp_path / "origin"
    target = tmp_path / "target"
    source_store = FileRawStore(origin)
    for i in range(3):
        source_store.put(storage_key("ted", f"n{i}", date(2026, 9, 8)), {"i": i})

    monkeypatch.setenv("DGATE_RAW_BACKEND", "fs")
    monkeypatch.setenv("DGATE_RAW_DIR", str(target))
    config.reset_cache()
    try:
        assert copy_from(origin) == 3
        assert copy_from(origin) == 0, "a second copy must move nothing"
        assert len(list(FileRawStore(target).list())) == 3
    finally:
        config.reset_cache()


# ------------------------------------------------------------ bundles

def test_a_day_of_payloads_is_one_object_not_thousands(tmp_path):
    """Object storage bills for writes, not bytes: the TED history cost $4.50
    per million notices in write operations and pennies in storage."""
    store = FileRawStore(tmp_path)
    key = bundle_key("ted", date(2019, 6, 3))
    written = store.put_records(key, [{"n": i} for i in range(1000)])
    assert written == 1000
    assert list(store.listing(suffix=".gz")) != []
    assert len(list(store.list())) == 0          # no per-notice objects at all
    assert (tmp_path / "ted" / "2019" / "06" / "03" / "bundle-0000.jsonl.gz").is_file()


def test_a_bundled_payload_is_addressed_by_line_and_reads_back_exactly(tmp_path):
    store = FileRawStore(tmp_path)
    key = bundle_key("ted", date(2019, 6, 3))
    store.put_records(key, [{"n": i, "t": f"notice {i}"} for i in range(5)])
    assert store.get(record_key(key, 3)) == {"n": 3, "t": "notice 3"}
    assert store.get(record_key(key, 0)) == {"n": 0, "t": "notice 0"}


def test_a_plain_key_still_reads_the_way_it_always_did(tmp_path):
    """Five million objects are already written one at a time. Both shapes have
    to live in one store and one index."""
    store = FileRawStore(tmp_path)
    key = storage_key("ted", "abc", date(2026, 9, 7))
    store.put(key, {"x": 1})
    assert store.get(key) == {"x": 1}
    assert split_record_key(key) == (key, None)


def test_the_key_says_where_the_payload_is(tmp_path):
    bundle = bundle_key("ted", date(2019, 6, 3))
    assert split_record_key(record_key(bundle, 42)) == (bundle, 42)
    assert split_record_key("ted/2019/06/03/x.json") == ("ted/2019/06/03/x.json", None)


def test_the_same_payloads_produce_the_same_bytes(tmp_path):
    """A rewritten bundle must not look changed to anything comparing objects,
    which gzip's timestamp header would do on its own."""
    store = FileRawStore(tmp_path)
    a, b = bundle_key("ted", date(2019, 6, 3)), bundle_key("ted", date(2019, 6, 4))
    payloads = [{"n": 1}, {"n": 2}]
    store.put_records(a, payloads)
    store.put_records(b, payloads)
    assert store._read(a) == store._read(b)


def test_reading_a_second_line_does_not_fetch_the_bundle_again(tmp_path):
    """A day is one file of three thousand notices; replay walks it in order."""
    store = FileRawStore(tmp_path)
    key = bundle_key("ted", date(2019, 6, 3))
    store.put_records(key, [{"n": i} for i in range(3)])
    reads = []
    original = store._read

    def counted(k):
        reads.append(k)
        return original(k)

    store._read = counted
    assert [store.get(record_key(key, i))["n"] for i in range(3)] == [0, 1, 2]
    assert reads == [key]
