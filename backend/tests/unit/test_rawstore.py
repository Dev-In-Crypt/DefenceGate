"""Raw payload storage (plan task M0-07)."""

from datetime import date

import pytest

from dgate import config
from dgate.rawstore import FileRawStore, RawStore, build_store, storage_key


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
