"""Database backups.

Two independent guarantees, and it is worth being clear about which does what.

The raw payload store is the *primary* one: the database is derived from it,
and `dgate.reprocess --from-store` rebuilds the whole serving layer without
touching a source. That protects against losing the database and against a bad
parser, and it works when the sources are down or have deleted the notice.

A dump is the *fast* one. Replaying two hundred thousand payloads takes hours;
restoring a dump takes minutes, and it also carries what a replay cannot
reconstruct: the observation timeline. A version row records *when* we saw a
change, and no amount of replaying tells you that after the fact.

So both exist, and neither is redundant.

A dump on the same host as the database is the weakest of the three: one disk
takes both. So every dump is also shipped to the object store, under its own
prefix, and the weekly restore check reads the shipped copy rather than the
local one -- proving the copy that would actually be used in a disaster.

Encryption and integrity
------------------------
A dump is the whole database, so it is encrypted before it is written, not
after it is shipped. Hybrid scheme, `cryptography` only: a fresh 256-bit data
key per dump, AES-256-GCM over 1 MiB frames, the data key wrapped with
RSA-OAEP(SHA-256) under the PUBLIC key in `DGATE_BACKUP_PUBLIC_KEY`. The private
key is never on this host (`python -m dgate.ops.backup_keys generate` makes the
pair on the owner's machine), so a host compromise yields neither old nor new
dumps. Encrypted dumps are `dgate-<stamp>.sql.gz.enc`; the gzip is inside.

File format ("DGBK" version 1), all integers big-endian:

    magic "DGBK" | version u8 | wrapped-key length u16 | wrapped key |
    nonce prefix (8 random bytes) | frame*

    frame = final u8 | ciphertext length u32 | ciphertext (plaintext + 16 B tag)

Frame i is encrypted under nonce `prefix || i (u32)` with associated data
`sha256(header) || i (u64) || final (u8)`. The index in the AAD makes reordering
and splicing fail authentication; the final marker makes truncation at a frame
boundary fail; the header hash ties every frame to this file's wrapped key.

Beside each dump sits `dgate-<stamp>.manifest.json` (file, size, sha256 of the
encrypted file, created_at, database, schema_migrations, key fingerprint). It is
not secret and it is shipped to the same place. It catches a damaged or swapped
file; it does not authenticate who wrote it (see `verify`).

    python -m dgate.ops.backup                    write a dump, ship it, prune
    python -m dgate.ops.backup --list             what is on disk
    python -m dgate.ops.backup --list-offsite     what is in the object store
    python -m dgate.ops.backup --verify           check the newest dump; restore
                                                  it too where a private key is
                                                  configured

Environment: DGATE_BACKUP_PUBLIC_KEY (PEM path, required to create),
DGATE_BACKUP_ALLOW_PLAINTEXT=1 (dev and tests only), DGATE_BACKUP_PRIVATE_KEY_FILE
(restore-drill machines only), DGATE_BACKUP_DIR, DGATE_ENV.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import hmac
import io
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import settings

log = logging.getLogger("backup")

STAMP = "%Y%m%dT%H%M%SZ"
# The dumps share the payload bucket but not its namespace: a replay enumerates
# the store, and a 100 MB gzip has no business showing up in that walk.
OFFSITE_PREFIX = "backups/"

SUFFIX_ENC = ".sql.gz.enc"
SUFFIX_PLAIN = ".sql.gz"           # legacy dumps, and dev/test with ALLOW_PLAINTEXT
SUFFIXES = (SUFFIX_ENC, SUFFIX_PLAIN)
MANIFEST_SUFFIX = ".manifest.json"

MAGIC = b"DGBK"
FORMAT_VERSION = 1
CHUNK = 1 << 20                    # plaintext bytes per frame
TAG = 16
NONCE_PREFIX = 8
MAX_WRAPPED = 1024                 # an RSA-8192 wrapped key is 1024 bytes
MIN_RSA_BITS = 3072

_OAEP = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


class BackupFormatError(RuntimeError):
    """The file is not an intact DGBK dump, or the key is not its key."""


class UnsafeDump(RuntimeError):
    """The SQL contains something a restore must not hand to psql."""


@dataclass
class Backup:
    path: Path
    taken_at: datetime
    bytes: int

    @property
    def megabytes(self) -> float:
        return self.bytes / 1_000_000

    @property
    def encrypted(self) -> bool:
        return self.path.name.endswith(SUFFIX_ENC)

    @property
    def manifest(self) -> Path:
        return manifest_path(self.path)


def backup_dir() -> Path:
    return Path(os.environ.get("DGATE_BACKUP_DIR", "./backups"))


# ------------------------------------------------------------------ names

def _stem(name: str) -> str | None:
    for suffix in SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return None


def manifest_path(path: Path) -> Path:
    return path.with_name((_stem(path.name) or path.name) + MANIFEST_SUFFIX)


def _stamp(name: str) -> datetime | None:
    """The time a dump file name carries, or None if it is not one of ours."""
    stem = _stem(name)
    if stem is None or not stem.startswith("dgate-"):
        return None
    try:
        return datetime.strptime(stem[len("dgate-"):], STAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ------------------------------------------------------------ connections

def _split_dsn(dsn: str) -> tuple[str, str | None, str]:
    """(dsn without the password, the password, the database name).

    The password goes to libpq through PGPASSWORD; it must never be an argv
    element, because argv is world-readable in /proc and in `ps`.
    """
    if "://" in dsn:
        parsed = urlparse(dsn)
        userinfo, at, hostport = parsed.netloc.rpartition("@")
        user, _, password = userinfo.partition(":")
        query = parse_qsl(parsed.query, keep_blank_values=True)
        from_query = next((v for k, v in query if k == "password"), None)
        query = [(k, v) for k, v in query if k != "password"]
        netloc = f"{user}@{hostport}" if at and user else hostport
        clean = urlunparse(parsed._replace(netloc=netloc, query=urlencode(query)))
        return clean, (unquote(password) if password else from_query), unquote(parsed.path.lstrip("/"))
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    fields = conninfo_to_dict(dsn)
    password = fields.pop("password", None)
    return make_conninfo(**fields), password, str(fields.get("dbname") or "")


def _pg_env(dsn: str) -> dict[str, str]:
    """Pass the password through the environment, never on the command line."""
    env = dict(os.environ)
    password = _split_dsn(dsn)[1]
    if password:
        env["PGPASSWORD"] = password
    return env


def _pg_dsn(dsn: str) -> str:
    """The DSN as it may appear in an argument list: no password in it."""
    return _split_dsn(dsn)[0]


def with_database(dsn: str, database: str) -> str:
    """Point a DSN at a different database, by parsing rather than replacing.

    `dsn.replace("/dgate", "/postgres")` looks equivalent and is not: in
    `postgresql://dgate:dgate@host/dgate` the first match is inside the
    username, so the result connects as the wrong user to the wrong database.
    """
    parsed = urlparse(dsn)
    return urlunparse(parsed._replace(path=f"/{database}"))


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(
            f"{tool} is not on PATH. Install the PostgreSQL client tools, or run "
            f"this inside the postgres container.")
    return path


def _psql_argv(conninfo: str) -> list[str]:
    """psql with no startup file, stopping at the first error. Meta-commands are
    not disabled by psql itself; `filter_dump` is what keeps them out."""
    return [_require("psql"), "--no-psqlrc", "--quiet", "-v", "ON_ERROR_STOP=1", conninfo]


# ------------------------------------------------------------ the format

def load_public_key(path: Path) -> rsa.RSAPublicKey:
    try:
        key = serialization.load_pem_public_key(Path(path).read_bytes())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read the backup public key {path}: {type(exc).__name__}") from None
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < MIN_RSA_BITS:
        raise RuntimeError(f"the backup public key must be RSA of at least {MIN_RSA_BITS} bits")
    return key


def load_private_key(path: Path) -> rsa.RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"cannot read the private key {path}: {type(exc).__name__}") from None
    if not isinstance(key, rsa.RSAPrivateKey):
        raise RuntimeError("the backup private key must be an RSA key")
    return key


def key_fingerprint(public_key: rsa.RSAPublicKey) -> str:
    """SHA-256 of the DER SubjectPublicKeyInfo, as hex."""
    der = public_key.public_bytes(serialization.Encoding.DER,
                                  serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


class _EncryptingWriter:
    """A write-only file object that frames, encrypts and writes what it is given.

    Memory is bounded by one frame: nothing is held beyond `chunk` bytes, so a
    640 MB dump costs the same as a 1 MB one. `close()` writes the final frame
    and must be called, or the file is (deliberately) unreadable as truncated.
    """

    def __init__(self, raw: IO[bytes], public_key: rsa.RSAPublicKey, chunk: int = CHUNK) -> None:
        if not 0 < chunk <= CHUNK:
            raise ValueError("frame size out of range")
        key = AESGCM.generate_key(bit_length=256)
        wrapped = public_key.encrypt(key, _OAEP)
        self._prefix = os.urandom(NONCE_PREFIX)
        header = MAGIC + bytes([FORMAT_VERSION]) + struct.pack(">H", len(wrapped)) + wrapped + self._prefix
        raw.write(header)
        self._raw, self._aes, self._chunk = raw, AESGCM(key), chunk
        self._base = hashlib.sha256(header).digest()
        self._buf = bytearray()
        self._index = 0
        self._closed = False

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("write to a closed backup writer")
        self._buf += data
        while len(self._buf) > self._chunk:     # strictly greater: the last frame is never empty
            self._emit(bytes(self._buf[:self._chunk]), final=0)
            del self._buf[:self._chunk]
        return len(data)

    def flush(self) -> None:
        pass

    def _emit(self, plain: bytes, final: int) -> None:
        if self._index >= 2 ** 32:
            raise BackupFormatError("too many frames for one file")
        nonce = self._prefix + struct.pack(">I", self._index)
        aad = self._base + struct.pack(">QB", self._index, final)
        ciphertext = self._aes.encrypt(nonce, plain, aad)
        self._raw.write(struct.pack(">BI", final, len(ciphertext)))
        self._raw.write(ciphertext)
        self._index += 1

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._emit(bytes(self._buf), final=1)
            self._buf.clear()


def encrypt_stream(src: IO[bytes], dst: IO[bytes], public_key: rsa.RSAPublicKey,
                   chunk: int = CHUNK) -> int:
    """Encrypt `src` into `dst`; returns plaintext bytes."""
    writer = _EncryptingWriter(dst, public_key, chunk)
    total = 0
    while block := src.read(CHUNK):
        total += writer.write(block)
    writer.close()
    return total


def _read_exact(src: IO[bytes], n: int, what: str) -> bytes:
    data = src.read(n)
    if len(data) != n:
        raise BackupFormatError(f"truncated {what}")
    return data


def _read_header(src: IO[bytes]) -> tuple[bytes, bytes, bytes]:
    """(whole header, wrapped key, nonce prefix)."""
    fixed = _read_exact(src, 7, "header")
    if fixed[:4] != MAGIC:
        raise BackupFormatError("not a DGBK backup (bad magic)")
    if fixed[4] != FORMAT_VERSION:
        raise BackupFormatError(f"unsupported backup format version {fixed[4]}")
    (length,) = struct.unpack(">H", fixed[5:7])
    if not 0 < length <= MAX_WRAPPED:
        raise BackupFormatError("implausible wrapped-key length")
    wrapped = _read_exact(src, length, "wrapped key")
    prefix = _read_exact(src, NONCE_PREFIX, "nonce prefix")
    return fixed + wrapped + prefix, wrapped, prefix


def _frames(src: IO[bytes]) -> Iterator[tuple[int, int, bytes]]:
    """Structurally validated (index, final, ciphertext), ending at the final frame.

    Every length is bounded before it is used to read, so a hostile file cannot
    ask for a gigabyte; and the file must end exactly at the final frame.
    """
    index = 0
    while True:
        head = src.read(5)
        if len(head) != 5:
            raise BackupFormatError(f"truncated: no final frame after {index} frames")
        final, length = struct.unpack(">BI", head)
        if final > 1:
            raise BackupFormatError(f"frame {index}: bad final marker")
        if not TAG <= length <= CHUNK + TAG:
            raise BackupFormatError(f"frame {index}: implausible length {length}")
        if index >= 2 ** 32:
            raise BackupFormatError("too many frames")
        yield index, final, _read_exact(src, length, f"frame {index}")
        index += 1
        if final:
            if src.read(1):
                raise BackupFormatError("data after the final frame")
            return


def scan(src: IO[bytes]) -> dict[str, int]:
    """Header and frame structure, without a key. Not authentication: only the
    key can say a frame is genuine, this says the file is whole and parseable."""
    _read_header(src)
    frames = size = 0
    for _, _, ciphertext in _frames(src):
        frames += 1
        size += len(ciphertext) - TAG
    return {"frames": frames, "gzip_bytes": size}


def _plaintext_chunks(src: IO[bytes], private_key: rsa.RSAPrivateKey) -> Iterator[bytes]:
    header, wrapped, prefix = _read_header(src)
    try:
        key = private_key.decrypt(wrapped, _OAEP)
    except ValueError:
        raise BackupFormatError("wrong private key: cannot unwrap the data key") from None
    if len(key) != 32:
        raise BackupFormatError("the unwrapped data key has the wrong length")
    aes, base = AESGCM(key), hashlib.sha256(header).digest()
    for index, final, ciphertext in _frames(src):
        try:
            yield aes.decrypt(prefix + struct.pack(">I", index), ciphertext,
                              base + struct.pack(">QB", index, final))
        except InvalidTag:
            raise BackupFormatError(
                f"frame {index} failed authentication: the file was altered, "
                f"reordered or spliced") from None


def decrypt_stream(src: IO[bytes], dst: IO[bytes], private_key: rsa.RSAPrivateKey) -> int:
    """Decrypt every frame into `dst`, verifying each; returns plaintext bytes."""
    total = 0
    for chunk in _plaintext_chunks(src, private_key):
        dst.write(chunk)
        total += len(chunk)
    return total


class _PlainReader(io.RawIOBase):
    """Presents decrypted frames as a readable file, so gzip can sit on top."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._buf = memoryview(b"")

    def readable(self) -> bool:
        return True

    def readinto(self, target: Any) -> int:
        while not len(self._buf):
            try:
                self._buf = memoryview(next(self._chunks))
            except StopIteration:
                return 0
        n = min(len(target), len(self._buf))
        target[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n


# ---------------------------------------------------------------- manifest

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_manifest(path: Path, final_name: str, taken_at: datetime, database: str,
                    migrations: int | None, fingerprint: str | None) -> Path:
    """Describe the file at `path` as it will be named `final_name`."""
    document = {
        "version": 1,
        "file": final_name,
        "size": path.stat().st_size,
        "sha256": _sha256_file(path),
        "created_at": taken_at.isoformat(),
        "database": database,
        "schema_migrations": migrations,
        "encrypted": fingerprint is not None,
        "key_fingerprint": fingerprint,
    }
    target = manifest_path(path.with_name(final_name))
    partial = target.with_name(target.name + ".partial")
    partial.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(target)
    return target


def check_manifest(path: Path, manifest_file: Path | None = None) -> dict[str, Any]:
    """The manifest of `path`, after proving it describes this exact file.

    Raises rather than returning False: a caller that forgot to look at a
    boolean would carry on and restore a file nobody vouched for.
    """
    manifest_file = manifest_file or manifest_path(path)
    try:
        document = json.loads(manifest_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"manifest {manifest_file.name} is missing; "
                           f"refusing to trust {path.name}") from None
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"manifest {manifest_file.name} is unreadable: "
                           f"{type(exc).__name__}") from None
    if not isinstance(document, dict) or document.get("file") != path.name:
        raise RuntimeError(f"manifest {manifest_file.name} does not describe {path.name}")
    size = path.stat().st_size
    if document.get("size") != size:
        raise RuntimeError(f"{path.name} is {size} bytes, its manifest says {document.get('size')}")
    if not hmac.compare_digest(str(document.get("sha256", "")).lower(), _sha256_file(path)):
        raise RuntimeError(f"{path.name} does not match the sha256 in its manifest")
    return document


# ------------------------------------------------------------------ create

def _production() -> bool:
    return (os.environ.get("DGATE_ENV", "").lower() == "production"
            or os.environ.get("DGATE_RAW_BACKEND", "fs") != "fs")


def _public_key_or_none() -> rsa.RSAPublicKey | None:
    """The key to encrypt under, or None only where plaintext was asked for."""
    key_file = os.environ.get("DGATE_BACKUP_PUBLIC_KEY", "").strip()
    if key_file:
        return load_public_key(Path(key_file))
    if os.environ.get("DGATE_BACKUP_ALLOW_PLAINTEXT") == "1":
        log.warning("DGATE_BACKUP_ALLOW_PLAINTEXT=1: writing an UNENCRYPTED dump")
        return None
    where = "production" if _production() else "this environment"
    raise RuntimeError(
        f"DGATE_BACKUP_PUBLIC_KEY is not set, and a dump is never written in "
        f"plaintext in {where}. Set it to the PEM path of the backup public key "
        f"(DGATE_BACKUP_ALLOW_PLAINTEXT=1 is for local development only).")


def _schema_migrations_count(dsn: str) -> int | None:
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=10) as conn:
            row = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()
            return int(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001 - the count is informational, the dump is not
        log.warning("cannot count schema_migrations for the manifest: %s", type(exc).__name__)
        return None


def create(dsn: str | None = None, directory: Path | None = None) -> Backup:
    """Write one encrypted, compressed dump and its manifest.

    Never overwrites: the name carries the time. Refuses, before touching the
    database, to write plaintext where it was not explicitly allowed.
    """
    dsn = dsn or settings().dsn
    public_key = _public_key_or_none()
    directory = directory or backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    taken_at = datetime.now(timezone.utc)
    name = f"dgate-{taken_at.strftime(STAMP)}{SUFFIX_ENC if public_key else SUFFIX_PLAIN}"
    target = directory / name
    partial = target.with_name(name + ".partial")
    conninfo, _, database = _split_dsn(dsn)
    argv = [_require("pg_dump"), "--no-owner", "--no-privileges", conninfo]

    # Dump to a .partial name and rename on success, so a crash mid-dump cannot
    # leave a truncated file that looks like a usable backup.
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with tempfile.TemporaryFile() as errlog, \
                subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=errlog,
                                 env=_pg_env(dsn)) as proc, \
                os.fdopen(fd, "wb") as raw:
            sink = _EncryptingWriter(raw, public_key) if public_key else None
            assert proc.stdout is not None
            with gzip.GzipFile(filename="", fileobj=sink or raw, mode="wb") as zipped:  # type: ignore[arg-type]
                shutil.copyfileobj(proc.stdout, zipped, CHUNK)
            if sink:
                sink.close()
            raw.flush()
            os.fsync(raw.fileno())
            returncode = proc.wait()
            errlog.seek(0)
            stderr = errlog.read(4000).decode("utf-8", "replace")
        if returncode != 0:
            raise RuntimeError(f"pg_dump failed ({returncode}): {stderr.strip()[:400]}")
        # Manifest first, then the rename: a crash in between leaves a harmless
        # orphan manifest, never a dump that nobody vouches for.
        fingerprint = key_fingerprint(public_key) if public_key else None
        _write_manifest(partial, name, taken_at, database,
                        _schema_migrations_count(dsn), fingerprint)
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    result = Backup(target, taken_at, target.stat().st_size)
    log.info("backup written: %s (%.1f MB, %s)", name, result.megabytes,
             "encrypted" if public_key else "PLAINTEXT")
    return result


# ------------------------------------------------- listing, pruning, ship

def listing(directory: Path | None = None) -> list[Backup]:
    directory = directory or backup_dir()
    if not directory.exists():
        return []
    out: list[Backup] = []
    for path in directory.glob("dgate-*"):
        stamp = _stamp(path.name)
        if stamp is not None and path.is_file():
            out.append(Backup(path, stamp, path.stat().st_size))
    return sorted(out, key=lambda b: (b.taken_at, b.path.name))


def prune(keep_days: int = 30, directory: Path | None = None) -> list[Path]:
    """Delete dumps (and their manifests) older than the retention window,
    always keeping the newest of either kind.

    Keeping the newest unconditionally matters: a month of downtime must not
    end with an empty backup directory.
    """
    backups = listing(directory)
    if not backups:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    removed = []
    for backup in backups[:-1]:
        if backup.taken_at < cutoff:
            backup.path.unlink()
            backup.manifest.unlink(missing_ok=True)
            removed.append(backup.path)
            log.info("pruned %s", backup.path.name)
    return removed


def offsite_key(name: str) -> str:
    return f"{OFFSITE_PREFIX}{name}"


def ship(backup: Backup | None = None, store: Any = None) -> str:
    """Copy one dump and its manifest to the object store and prove they arrived whole.

    Returns the dump's key. A short write is the failure this guards against:
    object storage accepts a truncated upload as a perfectly good object, and the
    size check is the only thing between that and a backup that is discovered to
    be useless on the day it is needed.

    The manifest goes first, so a dump in the store always has its manifest
    there too; and it is checked against the local file before anything leaves.
    """
    from ..rawstore import build_store

    backup = backup or newest()
    if backup is None:
        raise RuntimeError("no backup to ship")
    store = store or build_store()

    if backup.manifest.exists() or backup.encrypted:
        check_manifest(backup.path)          # raises if missing or not this file
        mkey = offsite_key(backup.manifest.name)
        store.put_file(mkey, backup.manifest, content_type="application/json")
        if store.size(mkey) != backup.manifest.stat().st_size:
            raise RuntimeError(f"shipped {backup.manifest.name} is not the manifest")
    else:
        log.warning("%s is a legacy dump without a manifest; shipping it as is", backup.path.name)

    key = offsite_key(backup.path.name)
    store.put_file(key, backup.path, content_type="application/octet-stream")
    stored = store.size(key)
    if stored != backup.bytes:
        raise RuntimeError(
            f"shipped {backup.path.name} is {stored} bytes in the store, "
            f"{backup.bytes} on disk; the copy is not the dump")
    log.info("shipped %s (%.1f MB) to %s", backup.path.name, backup.megabytes, key)
    return key


def offsite_listing(store: Any = None) -> list[tuple[str, datetime]]:
    """Shipped dumps of either kind, oldest first, read from the store itself.

    Deliberately not from a local index: the case this exists for is the host
    being gone, and an index on the lost host answers nothing.
    """
    from ..rawstore import build_store

    store = store or build_store()
    found: dict[str, datetime] = {}
    for suffix in SUFFIXES:
        for key, _ in store.listing(OFFSITE_PREFIX, suffix=suffix):
            stamp = _stamp(key.rsplit("/", 1)[-1])
            if stamp is not None:
                found[key] = stamp
    return sorted(found.items(), key=lambda pair: (pair[1], pair[0]))


def prune_offsite(keep_days: int = 30, store: Any = None) -> list[str]:
    """Same retention as on disk, and the same refusal to delete the last one."""
    from ..rawstore import build_store

    store = store or build_store()
    shipped = offsite_listing(store)
    if not shipped:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    removed = []
    for key, taken_at in shipped[:-1]:
        if taken_at < cutoff:
            store.delete(key)
            store.delete(offsite_key(manifest_path(Path(key)).name))
            removed.append(key)
            log.info("pruned %s from the store", key)
    return removed


def newest(directory: Path | None = None) -> Backup | None:
    found = listing(directory)
    return found[-1] if found else None


def fetch_offsite(dest_dir: Path, store: Any = None) -> Backup:
    """Bring the newest shipped dump, and its manifest, back to disk, as a restore would."""
    from ..rawstore import build_store

    store = store or build_store()
    shipped = offsite_listing(store)
    if not shipped:
        raise RuntimeError("no shipped backup to fetch")
    key, taken_at = shipped[-1]
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = store.fetch(key, dest_dir / key.rsplit("/", 1)[-1])
    mkey = offsite_key(manifest_path(path).name)
    if store.size(mkey) is not None:
        store.fetch(mkey, dest_dir / manifest_path(path).name)
    return Backup(path, taken_at, path.stat().st_size)


# ---------------------------------------------------------- the SQL filter
#
# A dump is replayed by psql, and psql is not a data loader: it runs
# meta-commands (`\! id` is a shell) and the server runs `COPY ... PROGRAM`. The
# shipped file comes from a store other things can write to, so it is checked
# before psql sees any of it. This is a conservative gate, not a sandbox: it
# knows what pg_dump emits and refuses what it does not recognise.

_COPY_WORD = re.compile(rb"copy\b", re.I)
_COPY_START = re.compile(rb"COPY [\w.\"]+(?: \([\w\", ]+\))? FROM stdin;")
_RESTRICT = re.compile(rb"\\(?:restrict|unrestrict) [A-Za-z0-9]+")      # pg_dump >= 17.6
_CONNECT = re.compile(rb"\\connect (\S+)")
_EXTENSION = re.compile(rb"CREATE\s+EXTENSION\b(?:\s+IF\s+NOT\s+EXISTS)?\s+\"?([\w-]+)\"?", re.I)
SAFE_EXTENSIONS = frozenset({"plpgsql", "pg_trgm", "unaccent", "citext", "btree_gin", "btree_gist"})
_ALLOWED_EXACT = frozenset({b"SET standard_conforming_strings = on;"})
_DENY = re.compile(
    rb"\bPROGRAM\b|\bALTER\s+SYSTEM\b|\bpg_(?:read_(?:binary_)?file|ls_dir|stat_file|"
    rb"terminate_backend|reload_conf|file_write)\b|\blo_(?:import|export)\b|\bdblink\b|"
    rb"\bCREATE\s+(?:DATABASE|ROLE|USER|SERVER|FOREIGN|TABLESPACE|LANGUAGE)\b|"
    rb"\bDROP\s+(?:DATABASE|ROLE|USER)\b|"
    rb"\bLANGUAGE\s+'?(?:plpythonu|plpython3u|plperlu|pltclu|c|internal)\b|"
    rb"\bstandard_conforming_strings\b", re.I)
# Tokens the lexer has to see: comments, quotes, dollar quotes, backslash.
_TOKEN = re.compile(rb"--|/\*|'|\"|\\|\$(?:[A-Za-z_\x80-\xff][A-Za-z0-9_\x80-\xff]*)?\$")
_ESTR = re.compile(rb"[\\']")
_BLOCK = re.compile(rb"/\*|\*/")
_IDENT = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$") | frozenset(range(0x80, 0x100))
MAX_SQL_LINE = 1 << 20


class _Lexer:
    """Where psql would be, between lines: inside a quote, a comment, or not."""

    def __init__(self) -> None:
        self.mode = "n"       # n normal, s 'string', e E'string', d "ident", c comment, $ dollar
        self.depth = 0
        self.tag = b""

    def backslash_outside_quotes(self, line: bytes) -> bool:
        pos, n = 0, len(line)
        while pos < n:
            if self.mode == "n":
                m = _TOKEN.search(line, pos)
                if m is None:
                    return False
                tok, start = m.group(), m.start()
                prev = line[start - 1] if start else None
                if tok == b"--":
                    return False                   # the rest of the line is a comment
                if tok == b"\\":
                    return True
                pos = m.end()
                if tok == b"/*":
                    self.mode, self.depth = "c", 1
                elif tok == b'"':
                    self.mode = "d"
                elif tok == b"'":
                    estring = (prev is not None and prev in b"eE"
                               and (start < 2 or line[start - 2] not in _IDENT))
                    self.mode = "e" if estring else "s"
                elif prev is None or prev not in _IDENT:    # `a$b$` is an identifier
                    self.mode, self.tag = "$", tok
            elif self.mode in "sd":
                quote = b"'" if self.mode == "s" else b'"'
                i = line.find(quote, pos)
                if i < 0:
                    return False
                if line[i + 1:i + 2] == quote:
                    pos = i + 2
                else:
                    self.mode, pos = "n", i + 1
            elif self.mode == "e":
                m = _ESTR.search(line, pos)
                if m is None:
                    return False
                if m.group() == b"\\" or line[m.end():m.end() + 1] == b"'":
                    pos = m.end() + 1             # an escape, or a doubled quote
                else:
                    self.mode, pos = "n", m.end()
            elif self.mode == "c":
                m = _BLOCK.search(line, pos)
                if m is None:
                    return False
                self.depth += 1 if m.group() == b"/*" else -1
                pos = m.end()
                if self.depth == 0:
                    self.mode = "n"
            else:                                   # dollar-quoted body
                i = line.find(self.tag, pos)
                if i < 0:
                    return False
                self.mode, pos = "n", i + len(self.tag)
        return False


def filter_dump(src: IO[bytes], allow_connect: tuple[str, ...] = ()) -> Iterator[bytes]:
    """Yield the dump's bytes, or raise UnsafeDump before yielding a bad line.

    Outside COPY data every line is lexed the way psql would: a backslash that is
    not inside a string or comment must be one of the commands pg_dump itself
    writes (`\\restrict`/`\\unrestrict`, and `\\connect` to a database named in
    `allow_connect` -- by default none, because a planted `\\connect dgate`
    would aim the restore at production). COPY blocks are accepted only in the
    exact form pg_dump writes, and a COPY data line is data: only its `\\.`
    terminator is looked at.
    """
    lexer = _Lexer()
    in_copy = False
    mid_line = False            # the previous chunk had no newline: this continues a line
    number = 0
    while True:
        line = src.readline(MAX_SQL_LINE)
        if not line:
            break
        continuation, mid_line = mid_line, not line.endswith(b"\n")
        if not continuation:
            number += 1
        if in_copy:
            if not continuation and line.startswith(b"\\."):
                if line not in (b"\\.\n", b"\\."):
                    raise UnsafeDump(f"line {number}: unusual COPY terminator")
                in_copy = False
            yield line
            continue
        if continuation or mid_line:
            raise UnsafeDump(f"line {number}: a statement line longer than {MAX_SQL_LINE} bytes")
        text = line.strip()
        if lexer.mode == "n" and text.startswith(b"\\"):
            m = _CONNECT.fullmatch(text)
            allowed = _RESTRICT.fullmatch(text) is not None or (
                m is not None and m.group(1).strip(b'"').decode("utf-8", "replace") in allow_connect)
            if not allowed:
                raise UnsafeDump(f"line {number}: psql meta-command {text[:40]!r} is not allowed")
            yield line
            continue
        if lexer.mode == "n" and _COPY_WORD.match(text):
            if not _COPY_START.fullmatch(text):
                raise UnsafeDump(f"line {number}: COPY in a form pg_dump does not write")
            in_copy = True
            yield line
            continue
        if text.startswith(b"--") and lexer.mode == "n":
            yield line
            continue
        if _DENY.search(line) and text not in _ALLOWED_EXACT:
            raise UnsafeDump(f"line {number}: statement not allowed in a restore: {text[:60]!r}")
        ext = _EXTENSION.search(line)
        if ext and ext.group(1).decode().lower() not in SAFE_EXTENSIONS:
            raise UnsafeDump(f"line {number}: extension {ext.group(1).decode()!r} is not allowed")
        if lexer.backslash_outside_quotes(line):
            raise UnsafeDump(f"line {number}: backslash outside a string or comment")
        yield line
    if in_copy:
        raise UnsafeDump("the dump ends inside a COPY block (truncated)")


# ------------------------------------------------------------------ verify

@contextlib.contextmanager
def _decrypted_sql(path: Path, private_key: rsa.RSAPrivateKey) -> Iterator[IO[bytes]]:
    """The decompressed SQL of an encrypted dump, authenticated as it is read."""
    with open(path, "rb") as raw:
        reader = io.BufferedReader(_PlainReader(_plaintext_chunks(raw, private_key)), CHUNK)
        with gzip.GzipFile(fileobj=reader) as stream:
            yield stream  # type: ignore[misc]


def _open_dump(backup: Backup, private_key: rsa.RSAPrivateKey | None
               ) -> Callable[[], AbstractContextManager[IO[bytes]]]:
    """A factory for the decompressed SQL stream of one dump."""
    if not backup.encrypted:
        return lambda: gzip.open(backup.path, "rb")          # type: ignore[return-value]
    assert private_key is not None
    return lambda: _decrypted_sql(backup.path, private_key)


def _restore_and_count(open_dump: Callable[[], AbstractContextManager[IO[bytes]]], dsn: str,
                       expected_migrations: int | None) -> dict[str, int]:
    import psycopg
    from psycopg.rows import dict_row

    scratch = f"dgate_verify_{datetime.now(timezone.utc).strftime('%H%M%S')}"
    admin_dsn = with_database(dsn, "postgres")
    target_dsn = with_database(dsn, scratch)

    # First pass: nothing is executed until the whole dump has passed the filter.
    with open_dump() as src:
        for _ in filter_dump(src, allow_connect=(scratch,)):
            pass

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{scratch}"')
        conn.execute(f'CREATE DATABASE "{scratch}"')
    try:
        # Stream the decompressed bytes through a pipe rather than handing psql
        # the file object: subprocess takes the underlying descriptor, which
        # still points at the compressed file, so psql would be fed gzip.
        with tempfile.TemporaryFile() as errlog, subprocess.Popen(
            _psql_argv(_pg_dsn(target_dsn)),
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errlog,
            env=_pg_env(dsn),
        ) as proc:
            assert proc.stdin is not None
            try:
                with open_dump() as src:
                    for chunk in filter_dump(src, allow_connect=(scratch,)):
                        proc.stdin.write(chunk)
                proc.stdin.close()
            except BrokenPipeError:
                # psql gave up early. Its own message is the useful one, so let
                # the stderr read below surface it instead of this.
                pass
            except BaseException:
                proc.kill()
                raise
            returncode = proc.wait()
            errlog.seek(0)
            stderr = errlog.read(4000).decode("utf-8", "replace")
        if returncode != 0:
            raise RuntimeError(f"restore failed: {stderr.strip()[:400]}")

        counts: dict[str, int] = {}
        with psycopg.connect(target_dsn, row_factory=dict_row) as conn:
            for table in ("opportunity", "opportunity_version", "raw_ingest",
                          "organisation", "organisation_alias", "ingest_run"):
                counts[table] = conn.execute(f"SELECT count(*) n FROM {table}").fetchone()["n"]
            migrations = conn.execute("SELECT count(*) n FROM schema_migrations").fetchone()["n"]
        if expected_migrations is not None and migrations != expected_migrations:
            raise RuntimeError(f"restored database has {migrations} migrations, "
                               f"the manifest says the dump had {expected_migrations}")
        counts["schema_migrations"] = migrations
        return counts
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch}"')


def verify(backup: Backup | None = None, dsn: str | None = None) -> dict[str, int]:
    """Prove a dump is the one that was written, and restore it where possible.

    An unverified backup is a belief, not a backup. In order, and each step
    gates the next:

    (a) the manifest exists and its size and sha256 match the file. Without that
        nothing below runs. Legacy plaintext dumps have no manifest: that is
        reported, and they are restored only through the SQL filter.
    (b) for an encrypted dump, the header is valid and every frame's length
        fields parse, up to a final frame that ends the file. This needs no key.
    (c) where DGATE_BACKUP_PRIVATE_KEY_FILE names the private key (a restore-drill
        machine, never the production host) the dump is decrypted, every frame
        authenticated, filtered, and restored into a scratch database that is
        dropped afterwards.

    Without (c) the result has no table counts: it says only that the shipped
    file is whole. The manifest and the file are both writable by whoever can
    write the store, so (a) detects damage and mix-ups, not a deliberate swap;
    the SQL filter and a restore as a role that is not a superuser cover that.
    """
    backup = backup or newest()
    if backup is None:
        raise RuntimeError("no backup to verify")

    result: dict[str, int] = {}
    manifest: dict[str, Any] | None = None
    if backup.manifest.exists() or backup.encrypted:
        manifest = check_manifest(backup.path)
        result["manifest"] = 1
    else:
        log.warning("%s is a legacy dump with no manifest: its integrity cannot be checked "
                    "and it will be restored only through the SQL filter", backup.path.name)
        result["manifest"] = 0

    private_key: rsa.RSAPrivateKey | None = None
    if backup.encrypted:
        with open(backup.path, "rb") as handle:
            result.update(scan(handle))
        key_file = os.environ.get("DGATE_BACKUP_PRIVATE_KEY_FILE", "").strip()
        if not key_file:
            log.warning("verified manifest, hash and frame structure of %s; NOT restored: "
                        "no private key on this host (set DGATE_BACKUP_PRIVATE_KEY_FILE on "
                        "a restore-drill machine for a full restore)", backup.path.name)
            return result
        private_key = load_private_key(Path(key_file))

    dsn = dsn or settings().dsn
    expected = manifest.get("schema_migrations") if manifest else None
    result.update(_restore_and_count(_open_dump(backup, private_key), dsn,
                                     expected if isinstance(expected, int) else None))
    log.info("verified %s: %s", backup.path.name, result)
    return result


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="dgate-backup")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--list-offsite", action="store_true",
                        help="what has been shipped to the object store")
    parser.add_argument("--verify", action="store_true",
                        help="check the newest dump: manifest, structure, and a restore "
                             "where a private key is configured")
    parser.add_argument("--offsite", action="store_true",
                        help="with --verify: fetch and check the newest shipped copy")
    parser.add_argument("--file", type=Path,
                        help="with --verify: a specific dump file instead of the newest")
    parser.add_argument("--no-ship", action="store_true",
                        help="write the dump but leave it on this host")
    parser.add_argument("--keep-days", type=int, default=30)
    args = parser.parse_args(argv)

    if args.list:
        for backup in listing():
            kind = "enc  " if backup.encrypted else "plain"
            print(f"{backup.path.name}  {kind} {backup.megabytes:8.1f} MB  {backup.taken_at:%Y-%m-%d %H:%M}Z")
        return 0

    if args.list_offsite:
        for key, taken_at in offsite_listing():
            print(f"{key}  {taken_at:%Y-%m-%d %H:%M}Z")
        return 0

    if args.verify:
        if args.offsite:
            with tempfile.TemporaryDirectory(prefix="dgate-verify-") as tmp:
                counts = verify(fetch_offsite(Path(tmp)))
        elif args.file:
            stamp = _stamp(args.file.name) or datetime.now(timezone.utc)
            counts = verify(Backup(args.file, stamp, args.file.stat().st_size))
        else:
            counts = verify()
        print(" ".join(f"{k}={v}" for k, v in counts.items()))
        return 0

    result = create()
    prune(args.keep_days)
    if not args.no_ship:
        ship(result)
        prune_offsite(args.keep_days)
    print(f"{result.path} ({result.megabytes:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
