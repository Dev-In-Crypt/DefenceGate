"""Durability: replay from raw storage, and backups.

Two independent guarantees. The raw store is the primary one, because the
database is derived from it; a dump is the fast one, and it carries the
observation timeline, which a replay cannot reconstruct.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from dgate import reprocess as rp
from dgate.db import opportunity_from_payload, opportunity_payload
from dgate.normalise import Opportunity
from dgate.ops import backup
from dgate.rawstore import FileRawStore, storage_key

# ------------------------------------------------- payload round trip

def sample() -> Opportunity:
    return Opportunity(
        source_code="es_placsp", native_id="EXP-1", buyer_name_raw="Ministerio",
        title_original="Suministro", country="ES", cpv_codes=["35700000"],
        published_at=date(2026, 9, 7),
        deadline_at=datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc),
        status="open", status_native="PUB",
    )


def test_a_payload_round_trips_exactly():
    """Replay is only faithful if the record that comes back is the one stored."""
    original = sample()
    assert opportunity_from_payload(opportunity_payload(original)) == original


def test_an_older_payload_still_loads():
    """An archive is replayable only if yesterday's payload loads into today's
    code. A field added since must not break a record written before it."""
    payload = opportunity_payload(sample())
    del payload["summary_en"]
    payload["field_from_a_future_version"] = "whatever"
    assert opportunity_from_payload(payload).native_id == "EXP-1"


def test_an_unusable_payload_is_rejected_rather_than_half_loaded():
    with pytest.raises(ValueError, match="missing required fields"):
        opportunity_from_payload({"native_id": "EXP-1"})


# ------------------------------------------------------ replay plumbing

def test_the_key_says_which_source_and_which_day():
    key = storage_key("ted", "550462-2026", date(2026, 9, 7))
    assert rp._source_of(key) == "ted"
    assert rp._day_of(key) == date(2026, 9, 7)


def test_a_malformed_key_has_no_day_rather_than_a_wrong_one():
    assert rp._day_of("ted/not/a/date.json") is None


def test_the_store_can_be_replayed_by_source_and_by_date(tmp_path):
    store = FileRawStore(tmp_path)
    store.put(storage_key("ted", "a", date(2026, 9, 1)), {"x": 1})
    store.put(storage_key("ted", "b", date(2026, 9, 5)), {"x": 2})
    store.put(storage_key("pl_ezam", "c", date(2026, 9, 5)), {"x": 3})

    assert len(list(rp.keys_from_store(store))) == 3
    assert len(list(rp.keys_from_store(store, source="ted"))) == 2
    assert len(list(rp.keys_from_store(store, since=date(2026, 9, 3)))) == 2
    assert len(list(rp.keys_from_store(store, source="ted",
                                       since=date(2026, 9, 3)))) == 1


def test_every_source_can_be_replayed():
    """A source with no mapper cannot be rebuilt, so the archive would come
    back incomplete after a loss. Adding a connector means adding it here."""
    from dgate.migrate import MIGRATIONS_DIR

    declared = set()
    for path in MIGRATIONS_DIR.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        for code in ("ted", "es_placsp", "es_placsp_agg", "pl_ezam"):
            if f"'{code}'" in text:
                declared.add(code)
    replayable = set(rp.MAPPERS) | rp.PASSTHROUGH_SOURCES
    assert declared <= replayable, f"no replay path for {declared - replayable}"


# ------------------------------------------------------------- backups

def _fake_backup(directory: Path, days_ago: int) -> Path:
    taken = datetime.now(timezone.utc) - timedelta(days=days_ago)
    path = directory / f"dgate-{taken.strftime(backup.STAMP)}.sql.gz"
    path.write_bytes(b"not really a dump")
    return path


def test_listing_is_oldest_first_and_ignores_strangers(tmp_path):
    _fake_backup(tmp_path, 1)
    _fake_backup(tmp_path, 10)
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "dgate-nonsense.sql.gz").write_bytes(b"x")

    found = backup.listing(tmp_path)
    assert len(found) == 2
    assert found[0].taken_at < found[1].taken_at


def test_pruning_removes_only_what_is_older_than_the_window(tmp_path):
    old = _fake_backup(tmp_path, 40)
    recent = _fake_backup(tmp_path, 3)
    removed = backup.prune(keep_days=30, directory=tmp_path)
    assert removed == [old]
    assert recent.exists() and not old.exists()


def test_pruning_never_empties_the_directory(tmp_path):
    """A month of downtime must not end with no backup at all."""
    ancient = _fake_backup(tmp_path, 400)
    assert backup.prune(keep_days=30, directory=tmp_path) == []
    assert ancient.exists()


def test_pruning_an_empty_directory_is_not_an_error(tmp_path):
    assert backup.prune(keep_days=30, directory=tmp_path) == []


def test_the_dsn_is_repointed_by_parsing_not_by_replacing():
    """The bug this guards: in `postgresql://dgate:dgate@host/dgate` a naive
    replace of `/dgate` hits the username first, and the restore then connects
    as the wrong user to the wrong database."""
    dsn = "postgresql://dgate:dgate@postgres:5432/dgate"
    assert backup.with_database(dsn, "postgres") == \
        "postgresql://dgate:dgate@postgres:5432/postgres"
    assert backup.with_database(dsn, "scratch_1") == \
        "postgresql://dgate:dgate@postgres:5432/scratch_1"
    assert dsn.replace("/dgate", "/postgres", 1) != backup.with_database(dsn, "postgres")


def test_a_missing_tool_says_what_to_install():
    with pytest.raises(RuntimeError, match="PostgreSQL client tools"):
        backup._require("definitely-not-a-real-binary")


# ------------------------------------------- shipping a dump off the host

def _dump(directory: Path, days_ago: int, body: bytes = b"not really a dump") -> backup.Backup:
    taken = datetime.now(timezone.utc) - timedelta(days=days_ago)
    path = directory / f"dgate-{taken.strftime(backup.STAMP)}.sql.gz"
    path.write_bytes(body)
    return backup.Backup(path, taken, len(body))


def test_a_dump_is_copied_into_the_store_under_its_own_prefix(tmp_path):
    """Its own prefix because a replay enumerates the store: a 100 MB gzip
    landing in that walk would be read as a notice."""
    store = FileRawStore(tmp_path / "store")
    dump = _dump(tmp_path, 0)
    key = backup.ship(dump, store)
    assert key == f"backups/{dump.path.name}"
    assert store.size(key) == dump.bytes
    assert list(store.list()) == []      # the payload replay sees nothing new


def test_a_short_upload_is_an_error_not_a_backup(tmp_path):
    """Object storage accepts a truncated upload as a perfectly good object.
    The size check is all that stands between that and a backup discovered to
    be useless on the day it is needed."""
    class _Truncating(FileRawStore):
        def put_file(self, key, path, content_type="application/octet-stream"):
            target = self._path(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes()[:3])
            return key

    with pytest.raises(RuntimeError, match="not the dump"):
        backup.ship(_dump(tmp_path, 0), _Truncating(tmp_path / "store"))


def test_shipped_dumps_are_listed_oldest_first_and_strangers_ignored(tmp_path):
    store = FileRawStore(tmp_path / "store")
    for days in (10, 1, 5):
        backup.ship(_dump(tmp_path, days), store)
    store.put_file("backups/notes.sql.gz", _dump(tmp_path, 0).path)
    store.put_file("backups/dgate-nonsense.sql.gz", _dump(tmp_path, 0).path)
    listed = backup.offsite_listing(store)
    assert [taken.date() for _, taken in listed] == sorted(taken.date() for _, taken in listed)
    assert len(listed) == 3


def test_shipped_dumps_are_pruned_on_the_same_window_as_local_ones(tmp_path):
    store = FileRawStore(tmp_path / "store")
    old = backup.ship(_dump(tmp_path, 40), store)
    recent = backup.ship(_dump(tmp_path, 3), store)
    removed = backup.prune_offsite(keep_days=30, store=store)
    assert removed == [old]
    assert store.size(recent) is not None


def test_pruning_never_empties_the_store(tmp_path):
    """A year of downtime must not end with nothing off the host."""
    store = FileRawStore(tmp_path / "store")
    ancient = backup.ship(_dump(tmp_path, 400), store)
    assert backup.prune_offsite(keep_days=30, store=store) == []
    assert store.size(ancient) is not None


def test_the_newest_shipped_dump_can_be_brought_back(tmp_path):
    """What the weekly check restores: the copy a disaster would reach for."""
    store = FileRawStore(tmp_path / "store")
    backup.ship(_dump(tmp_path, 4, b"older dump"), store)
    newest = _dump(tmp_path, 0, b"the newest dump")
    backup.ship(newest, store)
    fetched = backup.fetch_offsite(tmp_path / "restore", store)
    assert fetched.path.read_bytes() == b"the newest dump"
    assert fetched.path.name == newest.path.name


def test_the_host_keeps_fewer_dumps_than_the_store(monkeypatch):
    """One 40 GB disk holds both the database and the dumps of it. At the size
    the archive reaches with the TED history, thirty dumps on the host would
    fill it; thirty in the store cost pennies."""
    from dgate import config

    config.reset_cache()
    try:
        settings = config.settings()
        assert settings.backup_keep_days_local == 7
        assert settings.backup_keep_days == 30
        assert settings.backup_keep_days_local < settings.backup_keep_days
    finally:
        config.reset_cache()


def test_local_retention_can_be_shortened_without_touching_the_store(monkeypatch):
    from dgate import config

    monkeypatch.setenv("DGATE_BACKUP_KEEP_DAYS_LOCAL", "2")
    config.reset_cache()
    try:
        assert config.settings().backup_keep_days_local == 2
        assert config.settings().backup_keep_days == 30
    finally:
        config.reset_cache()


# -------------------------------- the disaster path has to see bundles

def test_replay_from_the_store_finds_payloads_written_as_bundles(tmp_path):
    """The database gone, the store the only copy: a replay that enumerated only
    one-object-per-notice keys would rebuild none of the 2.09 million notices of
    the TED history written as bundles, and say nothing about it."""
    from dgate.rawstore import bundle_key, record_key

    store = FileRawStore(tmp_path)
    store.put(storage_key("ted", "plain", date(2026, 9, 10)), {"n": "plain"})
    bundle = bundle_key("ted", date(2024, 4, 17))
    store.put_records(bundle, [{"n": 0}, {"n": 1}, {"n": 2}])

    keys = list(rp.keys_from_store(store, "ted"))
    assert record_key(bundle, 0) in keys and record_key(bundle, 2) in keys
    assert len(keys) == 4
    assert [store.get(k)["n"] for k in keys if "#" in k] == [0, 1, 2]


def test_a_date_filter_applies_to_bundles_as_to_plain_objects(tmp_path):
    from dgate.rawstore import bundle_key

    store = FileRawStore(tmp_path)
    store.put_records(bundle_key("ted", date(2024, 4, 17)), [{"n": 0}])
    store.put_records(bundle_key("ted", date(2024, 4, 18)), [{"n": 1}])
    keys = list(rp.keys_from_store(store, "ted", since=date(2024, 4, 18)))
    assert keys == [f"{bundle_key('ted', date(2024, 4, 18))}#0"]
