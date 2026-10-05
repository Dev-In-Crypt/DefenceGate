"""Moving the archive between stores.

While the move is in flight there is one copy of nine million notices, so these
tests are about what a copy is allowed to be called: only an object whose bytes
were read back from the destination and found identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dgate.ops import migrate_store as ms
from dgate.rawstore import FileRawStore


@pytest.fixture
def stores(tmp_path):
    return FileRawStore(tmp_path / "from"), FileRawStore(tmp_path / "to")


def _seed(source: FileRawStore) -> dict[str, bytes]:
    """The shapes the real bucket holds: single objects, bundles, and a dump."""
    objects = {
        "ted/2026/10/05/a.json": b'{"a": 1}',
        "ted/2026/10/05/bundle-0000.jsonl.gz": b"\x1f\x8b" + b"bundle" * 500,
        "es_placsp/2026/09/10/2026_12.json": b'{"early": "key without a hash"}',
        "backups/dgate-20261003T120941Z.sql.gz": b"dump" * 100_000,
    }
    for key, data in objects.items():
        source.put(key, data)
    return objects


def test_everything_is_copied_byte_for_byte(stores, tmp_path):
    source, target = stores
    objects = _seed(source)
    report = ms.migrate(source, target)

    assert (report.copied, report.skipped, len(report.failed)) == (4, 0, 0)
    assert report.bytes_copied == sum(len(d) for d in objects.values())
    for key, data in objects.items():
        assert (tmp_path / "to" / key).read_bytes() == data


def test_the_keys_are_the_same_on_both_sides(stores):
    """The index points at keys, not at a backend. If a key changed in transit the
    index would point at nothing."""
    source, target = stores
    objects = _seed(source)
    ms.migrate(source, target)
    # FileRawStore lists directories too when the suffix is empty; S3 and SFTP do
    # not, and the tool filters them out by asking for a size. Same here.
    files = [k for k, _ in target.listing("", suffix="") if target.size(k) is not None]
    assert sorted(files) == sorted(objects)


def test_a_second_run_copies_nothing_it_already_has(stores):
    source, target = stores
    _seed(source)
    ms.migrate(source, target)
    again = ms.migrate(source, target)
    assert (again.copied, again.skipped, len(again.failed)) == (0, 4, 0)


def test_an_object_added_between_runs_is_picked_up(stores):
    """The cut-over is two runs: a long one while the worker is quiet, and a short
    one after it stops to catch whatever landed in the meantime."""
    source, target = stores
    _seed(source)
    ms.migrate(source, target)
    source.put("ted/2026/10/06/new.json", b'{"late": true}')
    report = ms.migrate(source, target)
    assert (report.copied, report.skipped) == (1, 4)


def test_a_destination_object_of_the_wrong_size_is_replaced(stores, tmp_path):
    """A half-finished earlier attempt must not be mistaken for a finished copy."""
    source, target = stores
    source.put("ted/a.json", b"complete")
    target.put("ted/a.json", b"comp")
    report = ms.migrate(source, target)
    assert report.copied == 1
    assert (tmp_path / "to/ted/a.json").read_bytes() == b"complete"


class _LiesOnReadBack(FileRawStore):
    """A destination that stores something other than what it was sent."""

    def fetch(self, key: str, dest: Path) -> Path:
        super().fetch(key, dest)
        if key.endswith("bundle-0000.jsonl.gz"):
            data = bytearray(dest.read_bytes())
            data[10] ^= 0xFF                           # one flipped byte, same length
            dest.write_bytes(bytes(data))
        return dest


def test_a_copy_that_does_not_read_back_identical_is_not_counted(tmp_path):
    """The check that makes the whole tool worth running. Same length, one byte
    different: size alone would call it a good copy."""
    source = FileRawStore(tmp_path / "from")
    target = _LiesOnReadBack(tmp_path / "to")
    _seed(source)
    report = ms.migrate(source, target)

    assert len(report.failed) == 1
    assert report.failed[0][0] == "ted/2026/10/05/bundle-0000.jsonl.gz"
    assert "not what was sent" in report.failed[0][1]
    assert report.copied == 3                     # the other three were fine and still copied


def test_one_failing_object_does_not_stop_the_others(tmp_path):
    source = FileRawStore(tmp_path / "from")
    target = _LiesOnReadBack(tmp_path / "to")
    _seed(source)
    source.put("zzz/after.json", b'{"last": 1}')   # sorts after the bad one
    report = ms.migrate(source, target)
    assert (tmp_path / "to/zzz/after.json").read_bytes() == b'{"last": 1}'
    assert len(report.failed) == 1


def test_a_dry_run_touches_nothing(stores, tmp_path):
    source, target = stores
    _seed(source)
    report = ms.migrate(source, target, dry_run=True)
    assert report.copied == 4 and report.failed == []
    assert not (tmp_path / "to").exists() or not list((tmp_path / "to").rglob("*.json"))


def test_it_never_deletes_from_either_side(stores, tmp_path):
    source, target = stores
    objects = _seed(source)
    ms.migrate(source, target)
    for key in objects:
        assert (tmp_path / "from" / key).exists()


def test_a_prefix_limits_what_is_copied(stores, tmp_path):
    source, target = stores
    _seed(source)
    report = ms.migrate(source, target, prefix="backups")
    assert report.copied == 1
    assert not (tmp_path / "to/ted").exists()


def test_source_and_destination_must_differ():
    with pytest.raises(SystemExit):
        ms.main(["--from-backend", "s3", "--to-backend", "s3"])
