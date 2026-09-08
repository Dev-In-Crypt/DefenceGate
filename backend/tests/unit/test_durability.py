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
