"""The SFTP store: the Hetzner Storage Box as the archive's home.

There is no SFTP server in the unit suite, so the sessions here are a thin fake
over a temporary directory that can fail the way a real box does: a connection
that dies mid-write, one that has silently gone away while idle, a write that
lands short. Those are what the store exists to survive, and each has a test.
What the fake cannot show -- the host key check, the real box's rename
behaviour -- is exercised once against the box itself when the store is wired
in, and recorded in docs/RUNBOOK.md.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from dgate import config
from dgate.rawstore import SftpRawStore, build_store


class _Box:
    """The remote directory, plus switches for how it misbehaves."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.connects = 0
        self.live = 0
        self.peak = 0
        self.sessions: list[_Session] = []
        self.die_on_write = 0          # next N writes fail with a reset
        self.truncate_writes = False   # writes land one byte short
        self.no_posix_rename = False
        self.lock = threading.Lock()

    def connect(self) -> _Session:
        with self.lock:
            self.connects += 1
            self.live += 1
            self.peak = max(self.peak, self.live)
            session = _Session(self)
            self.sessions.append(session)
            return session

    def kill_all_sessions(self) -> None:
        """What an idle timeout or a box restart does: the pooled sessions are
        still in the pool and every call on them fails."""
        for session in self.sessions:
            session.dead = True

    def where(self, remote: str) -> Path:
        return self.root / remote


class _File:
    def __init__(self, box: _Box, handle) -> None:
        self._box, self._handle = box, handle

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._handle.close()

    def set_pipelined(self, flag: bool) -> None:
        pass

    def prefetch(self) -> None:
        pass

    def read(self) -> bytes:
        return self._handle.read()

    def write(self, data: bytes) -> None:
        if self._box.die_on_write:
            self._box.die_on_write -= 1
            self._handle.write(data[: len(data) // 2])      # half of it arrived
            raise EOFError("connection reset by peer")
        self._handle.write(data[:-1] if self._box.truncate_writes else data)


class _Session:
    def __init__(self, box: _Box) -> None:
        self.box, self.dead, self.closed = box, False, False

    def _alive(self) -> None:
        if self.dead or self.closed:
            raise EOFError("socket is closed")

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            with self.box.lock:
                self.box.live -= 1

    def stat(self, remote):
        self._alive()
        return os.stat(self.box.where(remote))

    def mkdir(self, remote):
        self._alive()
        os.mkdir(self.box.where(remote))

    def open(self, remote, mode):
        self._alive()
        return _File(self.box, open(self.box.where(remote), mode))

    def remove(self, remote):
        self._alive()
        os.remove(self.box.where(remote))

    def posix_rename(self, old, new):
        self._alive()
        if self.box.no_posix_rename:
            raise OSError("operation unsupported")
        os.replace(self.box.where(old), self.box.where(new))

    def rename(self, old, new):
        self._alive()
        if self.box.where(new).exists():
            raise OSError("failure")            # SFTP v3: no overwrite on rename
        os.rename(self.box.where(old), self.box.where(new))

    def listdir_attr(self, remote):
        self._alive()
        out = []
        for entry in os.scandir(self.box.where(remote)):
            info = entry.stat()
            out.append(SimpleNamespace(filename=entry.name, st_mode=info.st_mode,
                                       st_size=info.st_size, st_mtime=info.st_mtime))
        return out

    def put(self, local, remote, confirm=True):
        self._alive()
        shutil.copyfile(local, self.box.where(remote))
        if self.box.truncate_writes:
            with open(self.box.where(remote), "r+b") as handle:
                handle.truncate(os.path.getsize(local) - 1)
        if confirm and os.path.getsize(local) != os.path.getsize(self.box.where(remote)):
            raise OSError("size mismatch in put!")

    def get(self, remote, local):
        self._alive()
        shutil.copyfile(self.box.where(remote), local)


@pytest.fixture
def box(tmp_path):
    (tmp_path / "box").mkdir()
    return _Box(tmp_path / "box")


@pytest.fixture
def store(box, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    return SftpRawStore("store", box.connect, connections=4)


# ------------------------------------------------------------- round trips

def test_a_payload_round_trips_and_can_be_deleted(store):
    store.put("ted/2026/10/05/a.json", {"b": 2, "a": [1, "x"]})
    assert store.get("ted/2026/10/05/a.json") == {"a": [1, "x"], "b": 2}
    assert store.exists("ted/2026/10/05/a.json")
    assert store.size("ted/2026/10/05/a.json") > 0
    assert store.delete("ted/2026/10/05/a.json") is True
    assert not store.exists("ted/2026/10/05/a.json")
    assert store.delete("ted/2026/10/05/a.json") is False


def test_a_bundled_record_is_read_by_line_and_a_line_separator_survives(store):
    """The same rule as every other store: a record is `<bundle>#<line>`, and
    U+2028 inside a notice must not shift the index."""
    payloads = [{"n": 0}, {"n": 1, "t": "a b"}, {"n": 2}]
    store.put_records("ted/2026/10/05/bundle-0000.jsonl.gz", payloads)
    assert [store.get(f"ted/2026/10/05/bundle-0000.jsonl.gz#{i}") for i in range(3)] \
        == payloads


def test_a_key_that_would_leave_the_root_is_refused(store, box):
    for key in ("../outside.json", "ted/../../outside.json", "/etc/passwd"):
        with pytest.raises(ValueError, match="escapes"):
            store.put(key, {"x": 1})
    assert not (box.root / "outside.json").exists()
    assert not (box.root.parent / "outside.json").exists()


def test_a_root_above_the_login_directory_is_refused(box):
    with pytest.raises(ValueError, match="escapes"):
        SftpRawStore("../elsewhere", box.connect)


def test_rewriting_a_key_replaces_it_with_or_without_posix_rename(store, box):
    """A history re-run rewrites the same bundle. SFTP v3 rename refuses to
    overwrite, so the store has to cope on a server without posix-rename."""
    store.put("ted/a.json", {"v": 1})
    store.put("ted/a.json", {"v": 2})
    assert store.get("ted/a.json") == {"v": 2}
    box.no_posix_rename = True
    store.put("ted/a.json", {"v": 3})
    assert store.get("ted/a.json") == {"v": 3}


# ----------------------------------------------------------------- listing

def test_listing_returns_relative_keys_by_prefix_and_suffix(store, tmp_path):
    store.put("ted/2026/10/05/a.json", {"x": 1})
    store.put("ted/2026/10/06/b.json", {"x": 2})
    store.put("fr_boamp/2026/10/05/c.json", {"x": 3})
    store.put_records("ted/2026/10/05/bundle-0000.jsonl.gz", [{"x": 4}])
    dump = tmp_path / "dump.sql.gz"
    dump.write_bytes(b"dump")
    store.put_file("backups/dump.sql.gz", dump)

    assert [k for k, _ in store.listing("ted")] == [
        "ted/2026/10/05/a.json", "ted/2026/10/06/b.json"]
    assert [k for k, _ in store.listing("", suffix=".jsonl.gz")] == [
        "ted/2026/10/05/bundle-0000.jsonl.gz"]
    assert list(store.list("backups")) == []                 # .json only, by default
    assert [k for k, _ in store.listing("backups", suffix=".gz")] == ["backups/dump.sql.gz"]
    assert all(isinstance(t, float) for _, t in store.listing("ted"))
    assert list(store.listing("nothing/here")) == []


# ---------------------------------------------------------- a write is whole

def test_a_connection_that_dies_mid_write_leaves_no_key_and_no_stray_file(store, box):
    """The failure the `.part-` name exists for. Half the bytes arrived; the key
    must not exist, or the index would trust a truncated bundle."""
    box.die_on_write = 99
    with pytest.raises(EOFError):
        store.put("ted/2026/10/05/bundle-0000.jsonl.gz", {"x": "y" * 1000})
    assert not store.exists("ted/2026/10/05/bundle-0000.jsonl.gz")
    stray = [p.name for p in (box.root / "store/ted/2026/10/05").iterdir()]
    assert stray == [], stray


def test_a_write_that_lands_one_byte_short_is_refused(store, box):
    box.truncate_writes = True
    with pytest.raises(EOFError, match="fewer bytes"):
        store.put("ted/a.json", {"x": "y" * 100})
    assert not store.exists("ted/a.json")
    assert [p.name for p in (box.root / "store/ted").iterdir()] == []


def test_a_write_that_fails_once_is_simply_retried(store, box):
    box.die_on_write = 1
    store.put("ted/a.json", {"x": 1})
    assert store.get("ted/a.json") == {"x": 1}
    assert [p.name for p in (box.root / "store/ted").iterdir()] == ["a.json"]


def test_a_file_upload_is_confirmed_by_size(store, box, tmp_path):
    local = tmp_path / "dump.sql.gz"
    local.write_bytes(b"x" * 5000)
    store.put_file("backups/dump.sql.gz", local)
    assert store.size("backups/dump.sql.gz") == 5000

    box.truncate_writes = True
    with pytest.raises(OSError, match="size mismatch"):
        store.put_file("backups/short.sql.gz", local)
    assert store.size("backups/short.sql.gz") is None
    assert [p.name for p in (box.root / "store/backups").iterdir()] == ["dump.sql.gz"]


def test_a_fetch_lands_whole_or_not_at_all(store, tmp_path):
    store.put("ted/a.json", {"x": 1})
    out = store.fetch("ted/a.json", tmp_path / "out" / "a.json")
    assert out.read_bytes() == store.serialise({"x": 1})
    assert not list((tmp_path / "out").glob("*.part"))
    with pytest.raises(FileNotFoundError):
        store.fetch("ted/missing.json", tmp_path / "out" / "m.json")
    assert not list((tmp_path / "out").glob("*.part"))


# -------------------------------------------------------------- connections

def test_a_session_that_went_away_while_idle_is_replaced(store, box):
    """Pooled sessions die silently. The first call on a dead one must fall
    through to a fresh connection, not surface to the caller."""
    store.put("ted/a.json", {"x": 1})
    assert box.connects == 1
    box.kill_all_sessions()
    assert store.get("ted/a.json") == {"x": 1}
    assert box.connects == 2
    assert box.live == 1                      # the dead one was closed, not leaked


def test_a_missing_file_is_an_answer_not_a_reason_to_reconnect(store, box, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", slept.append)
    with pytest.raises(FileNotFoundError):
        store.get("ted/missing.json")
    assert box.connects == 1 and slept == []


def test_a_box_that_never_answers_fails_after_a_bounded_number_of_tries(box, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr("time.sleep", slept.append)

    def refuse():
        box.connects += 1
        raise ConnectionRefusedError("box is down")

    store = SftpRawStore("store", refuse)
    with pytest.raises(ConnectionRefusedError):
        store.put("ted/a.json", {"x": 1})
    assert box.connects == SftpRawStore.ATTEMPTS
    assert slept == [1, 2, 4]               # no pause after the last attempt


def test_the_pool_never_opens_more_sessions_than_it_was_allowed(store, box):
    """The box is shared and capped per account. Sixteen writer threads must
    still look like four connections from the other side."""
    errors: list[BaseException] = []

    def work(n: int) -> None:
        try:
            for i in range(10):
                store.put(f"ted/{n}/{i}.json", {"n": n, "i": i})
        except BaseException as exc:                    # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert box.peak <= 4 and box.connects <= 4
    assert len(list(store.list("ted"))) == 160


def test_what_counts_as_a_dropped_connection():
    transport = SftpRawStore._is_transport
    assert transport(EOFError("eof"))
    assert transport(ConnectionResetError("reset"))
    assert transport(OSError("socket is closed"))
    paramiko_style = type("SSHException", (Exception,), {"__module__": "paramiko.ssh_exception"})
    assert transport(paramiko_style("channel closed"))
    # answers from a healthy server, which a new connection would only repeat
    assert not transport(FileNotFoundError("missing"))
    assert not transport(PermissionError("denied"))
    assert not transport(ValueError("a programming error"))


# ------------------------------------------------------------ configuration

def test_the_backend_refuses_to_start_without_its_settings(monkeypatch):
    for name in ("HOST", "USER", "KEY_FILE", "KNOWN_HOSTS"):
        monkeypatch.delenv(f"DGATE_SFTP_{name}", raising=False)
    config.reset_cache()
    try:
        with pytest.raises(ValueError) as caught:
            build_store("sftp")
        for name in ("DGATE_SFTP_HOST", "DGATE_SFTP_USER", "DGATE_SFTP_KEY_FILE",
                     "DGATE_SFTP_KNOWN_HOSTS"):
            assert name in str(caught.value)
    finally:
        config.reset_cache()


def test_the_backend_is_built_from_configuration_without_connecting(monkeypatch):
    monkeypatch.setenv("DGATE_RAW_BACKEND", "sftp")
    monkeypatch.setenv("DGATE_SFTP_HOST", "u1.example.test")
    monkeypatch.setenv("DGATE_SFTP_USER", "u1-sub1")
    monkeypatch.setenv("DGATE_SFTP_KEY_FILE", "/run/secrets/box_key")
    monkeypatch.setenv("DGATE_SFTP_KNOWN_HOSTS", "/run/secrets/known_hosts")
    monkeypatch.setenv("DGATE_SFTP_ROOT", "store")
    config.reset_cache()
    try:
        built = build_store()
        assert isinstance(built, SftpRawStore) and built.root == "store"
        assert config.settings().sftp_port == 23 and config.settings().sftp_connections == 4
    finally:
        config.reset_cache()
