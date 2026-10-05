"""Raw payload storage.

The ordering rule of the whole pipeline is: land the raw payload first,
normalise second. This module is the "land" step. Everything downstream is
reproducible from what is written here, so a parser fix can be replayed over
history without refetching a single byte from a source that may have changed
or removed the notice in the meantime.

Two backends: the local filesystem for development, S3-compatible object
storage (Cloudflare R2) for production. Both take and return the same key, so
`raw_ingest.storage_key` means the same thing everywhere.

Access note: raw payloads still contain the personal-data fields that
`strip_personal_data()` removes downstream. This store is therefore private,
never served, and never indexed.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import os
import posixpath
import queue
import re
import shutil
import stat as stat_module
import threading
import time
import uuid
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .config import settings

log = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def storage_key(source_code: str, native_id: str, when: date | None = None,
                content_hash: str | None = None) -> str:
    """Deterministic key: ``source/YYYY/MM/DD/native_id-hash.json``.

    Partitioned by source and date so a day can be replayed, audited or expired
    on its own. The identifier is sanitised because native identifiers come
    from twenty-seven national systems and some of them contain slashes.

    The content hash is part of the key, and has to be. Without it a notice
    observed twice in one day wrote twice to one key and the earlier payload was
    gone -- silently, because overwriting is not an error. That is not a corner
    case: PLACSP publishes one feed entry per modification, which *is* its
    version history, so the same notice appearing several times a day is the
    normal shape of the source. Measured on 10 September 2026, a single day's
    ingest destroyed 11,496 distinct payloads this way, in the store the whole
    durability guarantee rests on.

    With the hash in the key, an identical payload maps to the identical key, so
    re-running an ingest stays idempotent and costs no extra objects, while a
    payload that differs by a byte gets its own object and survives. A key
    without a hash is still valid and still readable; those are the objects
    written before this was understood.
    """
    day = when or date.today()
    safe = _UNSAFE.sub("_", native_id or "unknown")[:200]
    prefix = f"{source_code}/{day.year:04d}/{day.month:02d}/{day.day:02d}/{safe}"
    if content_hash:
        # Twelve hex characters. Collisions within one notice-day are the only
        # ones that could matter, and at that scale this is far past sufficient.
        return f"{prefix}-{content_hash[:12]}.json"
    return f"{prefix}.json"


# ---------------------------------------------------------------- bundles
#
# One object per notice is the clearest shape and, past a few million notices,
# the expensive one: object storage bills for writes, not bytes. Loading the TED
# history that way cost 4.5 dollars per million notices in write operations and
# nothing worth measuring in storage. A day of one source, written as one
# gzipped file of JSON lines, is a single write instead of thousands, and
# compresses about ten to one.
#
# The key of a bundled payload carries where it is: `<bundle key>#<line>`. That
# keeps `raw_ingest.storage_key` a single self-describing string, so the two
# shapes can live in one store and one index -- which they must, because the
# archive already holds five million objects written one at a time and rewriting
# them is a decision of its own.

# Parts, numbered from zero, because one day of one source is not guaranteed to
# stay small: a busy TED day is 3,600 notices and 40 MB held in memory before
# the write, and a source that changes its habits must not turn that into a
# number nobody chose.
BUNDLE_EXTENSION = ".jsonl.gz"
# One record per line, and this is the only thing that ends a record.
RECORD_SEPARATOR = chr(10)
BUNDLE_PART = "bundle-{part:04d}" + BUNDLE_EXTENSION


def bundle_key(source_code: str, day: date, part: int = 0) -> str:
    return (f"{source_code}/{day.year:04d}/{day.month:02d}/{day.day:02d}/"
            + BUNDLE_PART.format(part=part))


def record_key(bundle: str, line: int) -> str:
    return f"{bundle}#{line}"


def split_record_key(key: str) -> tuple[str, int | None]:
    """Split `bundle#line` into its parts. A plain key keeps its `None`."""
    bundle, sep, line = key.partition("#")
    if not sep:
        return key, None
    try:
        return bundle, int(line)
    except ValueError:
        return key, None


# ------------------------------------------------------------- the fuse
#
# Object storage has no spending cap: Cloudflare's budget alerts say afterwards
# what was spent, they do not stop it. On 16 and 17 September 2026 a load wrote
# 4.9 million objects in two days and cost 22 dollars before anyone was told.
# So the store counts its own writes per day and refuses past a limit. Every
# path that writes goes through here; a run that trips it fails, and a failed
# run alerts.
#
# Per process, deliberately simple: the incident was one long-running process,
# and the ordinary day needs about a hundred and fifty writes against the
# default of twenty thousand.

class StoreWriteLimit(RuntimeError):
    """Raised instead of writing past the configured daily limit."""


_writes_lock = threading.Lock()
_writes: dict[date, int] = {}


def charge_write(n: int = 1, *, today: date | None = None) -> None:
    limit = settings().store_write_limit
    if limit <= 0:
        return
    day = today or date.today()
    with _writes_lock:
        done = _writes.get(day, 0)
        if done + n > limit:
            raise StoreWriteLimit(
                f"object store write limit reached: {done} writes today, limit {limit} "
                f"(DGATE_STORE_WRITE_LIMIT); refusing rather than spending")
        if day not in _writes:
            _writes.clear()          # a new day: yesterday's count no longer matters
        _writes[day] = done + n


def writes_today(today: date | None = None) -> int:
    with _writes_lock:
        return _writes.get(today or date.today(), 0)


class RawStore(ABC):
    """Write-once storage.

    Write-once is a property of the *key*, not of the backend: both backends
    will happily overwrite. It holds only because `storage_key` includes the
    content hash, so two different payloads can never be handed the same key.
    Anything that constructs a key by another route gives that up.
    """

    @abstractmethod
    def put(self, key: str, payload: Any, content_type: str = "application/json") -> str:
        """Store a payload under ``key`` and return the key."""

    @abstractmethod
    def _read(self, key: str) -> bytes:
        """Read one object's bytes. The only read subclasses have to implement."""
        raise NotImplementedError

    def get(self, key: str) -> Any:
        """Read a payload back, for replay and audit.

        Handles both shapes of key: a plain object, and one line of a bundle.
        The last bundle read is kept, because replay walks keys in order and a
        day's three thousand notices live in one file -- without it, each of
        them would fetch and decompress the same megabytes again.
        """
        bundle, line = split_record_key(key)
        if line is None:
            return json.loads(self._read(bundle).decode("utf-8"))
        return json.loads(self._bundle_lines(bundle)[line])

    def _bundle_lines(self, key: str) -> list[str]:
        with self._bundle_lock:
            if self._bundle_cache is not None and self._bundle_cache[0] == key:
                return self._bundle_cache[1]
        raw = gzip.decompress(self._read(key)).decode("utf-8")
        # Split on the record separator itself, never with splitlines().
        # Python counts more than the newline as a line boundary -- U+2028,
        # U+2029, the vertical tab, the form feed, the next-line control --
        # while json.dumps(ensure_ascii=False) leaves every one of them in
        # the text of a notice. A French notice carrying U+2028 made a
        # 5,000-record bundle report 5,001 lines on 23 September 2026;
        # compaction's line-count check caught it, and every record after
        # it would otherwise have been addressed one line off.
        lines = raw.split(RECORD_SEPARATOR)
        if lines and lines[-1] == "":
            lines.pop()          # the separator written after the last record
        with self._bundle_lock:
            self._bundle_cache = (key, lines)
        return lines

    def put_records(self, key: str, payloads: Iterable[Any]) -> int:
        """Write many payloads as one gzipped object of JSON lines.

        One write instead of thousands. Returns how many lines were written, so
        the caller can check the count it recorded against the count it stored.
        """
        buffer = io.BytesIO()
        written = 0
        # mtime=0: the same payloads must produce the same bytes, or a rewritten
        # bundle looks changed to anything comparing objects.
        with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as out:
            for payload in payloads:
                out.write(self.serialise(payload))
                out.write(RECORD_SEPARATOR.encode("utf-8"))
                written += 1
        self.put(key, buffer.getvalue(), content_type="application/gzip")
        return written

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    def delete_many(self, keys: list[str]) -> int:
        """Delete objects that compaction has copied into a verified bundle.

        The one sanctioned way ingested payloads leave the store: after their
        bytes are in a bundle that has been read back and checked record by
        record, and after every index row that pointed at them points into the
        bundle instead. Backends override this to batch; deletes are free on R2,
        but a million round trips are not free in time.
        """
        return sum(1 for key in keys if self.delete(key))

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove one object. Only ever used for probe objects.

        Ingested payloads are never deleted: the store is the archive's
        insurance, and an insurance policy with a delete path is a liability.
        """

    @abstractmethod
    def listing(self, prefix: str = "", suffix: str = ".json") -> Iterator[tuple[str, float]]:
        """Every key under a prefix with the time it was written.

        Needed because a notice can now have several payloads in one day, and a
        rebuild has to replay them in the order they were observed or it will
        number the versions wrongly. Key order cannot carry that: the part that
        distinguishes them is a content hash, which sorts arbitrarily.

        `suffix` exists because the bucket now holds more than payloads: the
        nightly dumps are shipped here too, and a replay that swept them in
        would try to parse a 100 MB gzip as a notice.
        """
        raise NotImplementedError

    @abstractmethod
    def put_file(self, key: str, path: Path, content_type: str = "application/octet-stream") -> str:
        """Upload a file by streaming it, without reading it into memory.

        `put()` serialises a payload that is already in memory, which is right
        for a notice and wrong for a database dump: a dump is a hundred times
        the size of this process's usual footprint.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch(self, key: str, dest: Path) -> Path:
        """Download one object to a local path, streaming it likewise."""
        raise NotImplementedError

    @abstractmethod
    def size(self, key: str) -> int | None:
        """Bytes stored under a key, or None if it is not there.

        An upload that returns without error is not evidence; a size that
        matches the local file is.
        """
        raise NotImplementedError

    @abstractmethod
    def list(self, prefix: str = "") -> Iterator[str]:
        """Every key under a prefix, oldest first.

        This is what makes the store an insurance policy rather than a cache.
        `raw_ingest` indexes these keys, but that table lives in the database:
        if the database is lost, the index goes with it. Enumerating the store
        itself is the only path that survives losing everything except the
        payloads, which is exactly the disaster this exists for.
        """
        raise NotImplementedError

    _bundle_cache: tuple[str, list[str]] | None = None

    @property
    def _bundle_lock(self) -> threading.Lock:
        lock = self.__dict__.get("_bundle_lock_instance")
        if lock is None:
            lock = self.__dict__["_bundle_lock_instance"] = threading.Lock()
        return lock

    @staticmethod
    def serialise(payload: Any) -> bytes:
        # sort_keys so that an identical payload produces identical bytes:
        # key ordering must never look like a change.
        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload)
        if isinstance(payload, str):
            return payload.encode("utf-8")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          default=str).encode("utf-8")


class FileRawStore(RawStore):
    """Local filesystem. Development, and a fallback if object storage is down."""

    def __init__(self, root: Path | str) -> None:
        # Resolved once. Resolving per call was both a syscall per write and a
        # correctness bug: see _path.
        self.root = Path(os.path.abspath(root))

    def _path(self, key: str) -> Path:
        r"""Full path for a key, refusing any key that would escape the root.

        The containment check is textual on purpose. `Path.resolve()` asks the
        filesystem, and on Windows it answers differently depending on whether
        the path exists yet: a key under a directory not yet created comes back
        in the extended-length `\?\C:\...` form while the existing root comes
        back as plain `C:\...`, so the comparison fails and a perfectly good key
        is rejected. Every date directory is new once, which made this the first
        write of each day, and concurrent writers creating that directory made
        it intermittent on top.

        normpath collapses `..` without consulting the filesystem, which is
        exactly what this guards against -- a malformed native_id reaching
        storage_key -- and it gives the same answer on every thread and in
        every state of the disk.
        """
        path = Path(os.path.normpath(self.root / key))
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"key escapes the store root: {key}")
        return path

    def put(self, key: str, payload: Any, content_type: str = "application/json") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.serialise(payload))
        return key

    def _read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def list(self, prefix: str = "") -> Iterator[str]:
        for key, _ in self.listing(prefix):
            yield key

    def listing(self, prefix: str = "", suffix: str = ".json") -> Iterator[tuple[str, float]]:
        base = Path(os.path.normpath(self.root / prefix)) if prefix else self.root
        if not base.exists():
            return
        for path in sorted(base.rglob(f"*{suffix}")):
            yield path.relative_to(self.root).as_posix(), path.stat().st_mtime

    def put_file(self, key: str, path: Path,
                 content_type: str = "application/octet-stream") -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        return key

    def fetch(self, key: str, dest: Path) -> Path:
        source = self._path(key)
        if not source.is_file():
            raise FileNotFoundError(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        return dest

    def size(self, key: str) -> int | None:
        path = self._path(key)
        return path.stat().st_size if path.is_file() else None


class S3RawStore(RawStore):
    """S3-compatible object storage (Cloudflare R2 in production)."""

    def __init__(self, bucket: str, client: Any = None, **client_kwargs: Any) -> None:
        self.bucket = bucket
        self._client = client
        self._client_kwargs = client_kwargs

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3  # imported lazily: development does not need it
            from botocore.config import Config

            # botocore pools ten connections by default, and BufferedWriter runs
            # sixteen threads. The overflow was discarded and reopened, paying a
            # fresh TLS handshake per write and giving back part of what the
            # concurrency bought. The pool has to be at least as wide as the
            # writers, so it is derived from the same setting.
            options = dict(self._client_kwargs)
            #
            # Retries: botocore's default gives up within seconds, which is fine
            # for one request and fatal for a backfill that runs for hours. On
            # 13 September 2026 a brief DNS outage made R2 unresolvable and
            # killed the Polish backfill 106,600 rows into its resumed run.
            # Standard mode backs off exponentially up to 20 s between tries,
            # so ten attempts ride out a couple of minutes of network trouble.
            options.setdefault("config", Config(
                max_pool_connections=max(settings().raw_write_workers + 4, 10),
                retries={"mode": "standard", "max_attempts": 10},
                connect_timeout=10, read_timeout=60))
            self._client = boto3.client("s3", **options)
        return self._client

    def ensure_bucket(self) -> bool:
        """Create the bucket if it is absent. Explicit, never on a write path.

        A store that creates its own bucket on first use will happily write a
        year of payloads into a typo, and nobody notices until the day the
        archive is needed.
        """
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
            return False
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
            log.info("created bucket %s", self.bucket)
            return True

    def put(self, key: str, payload: Any, content_type: str = "application/json") -> str:
        charge_write()
        self.client.put_object(Bucket=self.bucket, Key=key,
                               Body=self.serialise(payload), ContentType=content_type)
        return key

    def _read(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete_many(self, keys: list[str]) -> int:
        deleted = 0
        for start in range(0, len(keys), 1000):   # the API's limit per request
            batch = keys[start:start + 1000]
            response = self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
            errors = response.get("Errors") or []
            if errors:
                raise RuntimeError(f"{len(errors)} objects not deleted, first: {errors[0]}")
            deleted += len(batch)
        return deleted

    def list(self, prefix: str = "") -> Iterator[str]:
        for key, _ in self.listing(prefix):
            yield key

    def listing(self, prefix: str = "", suffix: str = ".json") -> Iterator[tuple[str, float]]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(suffix):
                    yield obj["Key"], obj["LastModified"].timestamp()

    def put_file(self, key: str, path: Path,
                 content_type: str = "application/octet-stream") -> str:
        charge_write()
        self.client.upload_file(str(path), self.bucket, key,
                                ExtraArgs={"ContentType": content_type})
        return key

    def fetch(self, key: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(dest))
        return dest

    def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            return int(self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"])
        except ClientError:
            return None


class SftpRawStore(RawStore):
    """A directory on an SSH host: a Hetzner Storage Box.

    Why a store of its own and not the filesystem store on a mount. The box
    speaks SSH and nothing else -- SMB and WebDAV are off, and S3 was never on
    offer -- so the choices were a FUSE mount, which needs `sshfs` installed on
    the production host and wedges every container reading it when the link
    drops, or a client inside the process, which needs nothing on the host and
    can say what it is doing when the network misbehaves. This is the second.

    Three properties it has to keep that a plain `open()` would not:

    * **A write is whole or absent.** Bytes go to a `.part-` name, are checked
      against the length that was meant, and only then renamed into place. A
      connection that dies mid-write leaves a stray `.part-` file, never a
      truncated bundle under a key the index will trust.
    * **A dropped connection is retried on a new one.** SFTP sessions die
      silently when idle or when the box restarts; the pooled connection is
      discarded and the operation repeated, with a pause that grows.
    * **The box is shared and its connection limit is small.** Hetzner caps
      simultaneous sessions per box, and a second project writes to the same
      box, so the pool is a handful of connections however many threads ask.

    `root` is relative to the login directory. With a Hetzner sub-account the
    login directory *is* the project's directory, which is what keeps this
    project out of the other one's files: the key cannot name a path above it.
    """

    ATTEMPTS = 4

    def __init__(self, root: str, connect: Callable[[], Any], connections: int = 4) -> None:
        cleaned = posixpath.normpath(root.strip().strip("/")) if root.strip("/ ") else ""
        if cleaned.startswith(".."):
            raise ValueError(f"sftp root escapes the login directory: {root!r}")
        self.root = "" if cleaned == "." else cleaned
        self._connect = connect
        self._pool: queue.LifoQueue[Any] = queue.LifoQueue()
        self._slots = threading.BoundedSemaphore(connections)
        self._made: set[str] = set()
        self._made_lock = threading.Lock()

    # ------------------------------------------------------------ plumbing

    @staticmethod
    def _is_transport(exc: BaseException) -> bool:
        """A failure of the connection, as opposed to of the request.

        A missing file, a refused path and an existing directory are answers
        from a healthy server and must reach the caller; repeating them on a new
        connection only repeats the answer. Everything else -- EOF, a reset, a
        timeout, paramiko's own SSHException -- says the session is gone.
        """
        if isinstance(exc, (FileNotFoundError, PermissionError, FileExistsError,
                            IsADirectoryError, NotADirectoryError)):
            return False
        return isinstance(exc, (EOFError, OSError)) or \
            type(exc).__module__.startswith("paramiko")

    @staticmethod
    def _close(sftp: Any) -> None:
        for closer in (getattr(sftp, "close", None),
                       getattr(getattr(sftp, "_ssh", None), "close", None)):
            try:
                if closer:
                    closer()
            except Exception:
                pass

    def _do(self, operation: Callable[[Any], Any]) -> Any:
        last: BaseException | None = None
        for attempt in range(self.ATTEMPTS):
            self._slots.acquire()
            sftp = None
            try:
                try:
                    sftp = self._pool.get_nowait()
                except queue.Empty:
                    sftp = self._connect()
                result = operation(sftp)
                self._pool.put(sftp)
                return result
            except Exception as exc:
                if not self._is_transport(exc):
                    if sftp is not None:
                        self._pool.put(sftp)
                    raise
                last = exc
                if sftp is not None:
                    self._close(sftp)
                log.warning("sftp: %s: %s (attempt %s of %s)",
                            type(exc).__name__, exc, attempt + 1, self.ATTEMPTS)
            finally:
                self._slots.release()
            if attempt < self.ATTEMPTS - 1:
                time.sleep(min(2 ** attempt, 20))
        assert last is not None
        raise last

    def _path(self, key: str) -> str:
        """Full path for a key, refusing any key that would leave the root.

        Textual, for the reason FileRawStore's is: it must give the same answer
        whether or not the directory exists yet.
        """
        path = posixpath.normpath(posixpath.join(self.root, key))
        if self.root:
            inside = path.startswith(self.root + "/")
        else:
            inside = not (path.startswith("/") or path.startswith(".."))
        if not inside:
            raise ValueError(f"key escapes the store root: {key}")
        return path

    def _mkdirs(self, sftp: Any, directory: str) -> None:
        built = ""
        for part in [p for p in directory.split("/") if p]:
            built = f"{built}/{part}" if built else part
            with self._made_lock:
                if built in self._made:
                    continue
            try:
                sftp.stat(built)
            except FileNotFoundError:
                try:
                    sftp.mkdir(built)
                except OSError:
                    sftp.stat(built)        # another writer made it first
            with self._made_lock:
                self._made.add(built)

    def _replace(self, sftp: Any, part: str, path: str) -> None:
        """Move a finished `.part-` file over its final name."""
        try:
            sftp.posix_rename(part, path)
            return
        except OSError:
            pass                            # no posix-rename here, or the target exists
        try:
            sftp.remove(path)
        except FileNotFoundError:
            pass
        sftp.rename(part, path)

    @staticmethod
    def _part(path: str) -> str:
        return f"{path}.part-{uuid.uuid4().hex[:8]}"

    # -------------------------------------------------------------- the API

    def put(self, key: str, payload: Any, content_type: str = "application/json") -> str:
        path, data = self._path(key), self.serialise(payload)

        def write(sftp: Any) -> None:
            self._mkdirs(sftp, posixpath.dirname(path))
            part = self._part(path)
            try:
                with sftp.open(part, "wb") as handle:
                    handle.set_pipelined(True)
                    handle.write(data)
                if sftp.stat(part).st_size != len(data):
                    raise EOFError(f"{part} holds fewer bytes than were written")
                self._replace(sftp, part, path)
            except BaseException:
                try:
                    sftp.remove(part)
                except Exception:
                    pass
                raise

        self._do(write)
        return key

    def _read(self, key: str) -> bytes:
        path = self._path(key)

        def read(sftp: Any) -> bytes:
            with sftp.open(path, "rb") as handle:
                handle.prefetch()
                return handle.read()

        return self._do(read)

    def exists(self, key: str) -> bool:
        return self.size(key) is not None

    def size(self, key: str) -> int | None:
        path = self._path(key)

        def stat(sftp: Any) -> int | None:
            try:
                attrs = sftp.stat(path)
            except FileNotFoundError:
                return None
            return attrs.st_size if stat_module.S_ISREG(attrs.st_mode) else None

        return self._do(stat)

    def delete(self, key: str) -> bool:
        path = self._path(key)

        def remove(sftp: Any) -> bool:
            try:
                sftp.remove(path)
            except FileNotFoundError:
                return False
            return True

        return self._do(remove)

    def list(self, prefix: str = "") -> Iterator[str]:
        for key, _ in self.listing(prefix):
            yield key

    def listing(self, prefix: str = "", suffix: str = ".json") -> Iterator[tuple[str, float]]:
        base = self._path(prefix) if prefix else self.root
        strip = len(self.root) + 1 if self.root else 0

        def walk(sftp: Any) -> list[tuple[str, float]]:
            found: list[tuple[str, float]] = []
            stack = [base]
            while stack:
                directory = stack.pop()
                try:
                    entries = sftp.listdir_attr(directory or ".")
                except FileNotFoundError:
                    continue
                for entry in entries:
                    full = f"{directory}/{entry.filename}" if directory else entry.filename
                    if stat_module.S_ISDIR(entry.st_mode):
                        stack.append(full)
                    elif full.endswith(suffix):
                        found.append((full[strip:], float(entry.st_mtime)))
            return sorted(found)

        yield from self._do(walk)

    def put_file(self, key: str, path: Path,
                 content_type: str = "application/octet-stream") -> str:
        target, local = self._path(key), Path(path)

        def upload(sftp: Any) -> None:
            self._mkdirs(sftp, posixpath.dirname(target))
            part = self._part(target)
            try:
                sftp.put(str(local), part, confirm=True)     # confirm: size must match
                self._replace(sftp, part, target)
            except BaseException:
                try:
                    sftp.remove(part)
                except Exception:
                    pass
                raise

        self._do(upload)
        return key

    def fetch(self, key: str, dest: Path) -> Path:
        source = self._path(key)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")

        def download(sftp: Any) -> None:
            sftp.get(source, str(part))

        try:
            self._do(download)
            os.replace(part, dest)
        finally:
            part.unlink(missing_ok=True)
        return dest


def sftp_connector(host: str, port: int, user: str, key_file: str,
                   known_hosts: str) -> Callable[[], Any]:
    """A function that opens one authenticated SFTP session.

    The host key is checked against `known_hosts` and an unknown host is
    refused, not trusted on first use: this connection carries the whole
    archive, and the first connection is exactly when a man in the middle would
    have to act.
    """
    def connect() -> Any:
        import paramiko

        client = paramiko.SSHClient()
        client.load_host_keys(known_hosts)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(host, port=port, username=user,
                       key_filename=key_file, look_for_keys=False, allow_agent=False,
                       timeout=30, banner_timeout=30, auth_timeout=30)
        transport = client.get_transport()
        if transport is not None:
            transport.set_keepalive(30)
        sftp = client.open_sftp()
        sftp._ssh = client          # keeps the SSH session alive as long as the SFTP one
        return sftp

    return connect


def build_store(backend: str | None = None) -> RawStore:
    """Construct the configured store. Unknown backend fails loudly."""
    cfg = settings()
    backend = (backend or cfg.raw_backend).lower()
    if backend == "fs":
        return FileRawStore(cfg.raw_dir)
    if backend == "s3":
        return S3RawStore(bucket=cfg.s3_bucket, **cfg.s3_settings())
    if backend == "sftp":
        missing = [name for name, value in (
            ("DGATE_SFTP_HOST", cfg.sftp_host), ("DGATE_SFTP_USER", cfg.sftp_user),
            ("DGATE_SFTP_KEY_FILE", cfg.sftp_key_file),
            ("DGATE_SFTP_KNOWN_HOSTS", cfg.sftp_known_hosts)) if not value]
        if missing:
            # Loud, and before anything is written: a store pointed at nothing
            # that fell back to the container's own disk would keep reporting
            # success, which is the failure that hides itself.
            raise ValueError(f"the sftp backend needs {', '.join(missing)}")
        return SftpRawStore(
            cfg.sftp_root,
            sftp_connector(cfg.sftp_host, cfg.sftp_port, cfg.sftp_user,
                           cfg.sftp_key_file, cfg.sftp_known_hosts),
            connections=cfg.sftp_connections)
    raise ValueError(f"unknown raw storage backend: {backend!r}")


class BundleWriter:
    """Collect a run's payloads and land them as bundles, one per checkpoint.

    A drop-in for BufferedWriter where it matters for cost: the same `put()`
    that returns a key at once and the same `drain()` that must return before
    anything pointing at those keys is committed. The difference is what a
    drain writes. BufferedWriter wrote one object per payload -- about 25,000
    writes on an ordinary day, most of them Spain re-reading pages it had read
    the day before, and enough to leave the free tier after a couple of
    restarts. This writes one object per checkpoint: a hundred or so a day.

    Each run gets its own name, so two runs on one day, or a retry, can never
    write over each other's bundles.
    """

    def __init__(self, store: RawStore, source_code: str, *, day: date | None = None,
                 tag: str | None = None) -> None:
        import uuid
        from datetime import datetime, timezone

        self._store = store
        self._day = day or date.today()
        self._tag = tag or (datetime.now(timezone.utc).strftime("%H%M%S")
                            + "-" + uuid.uuid4().hex[:6])
        self._source = source_code
        self._part = 0
        self._buffer: list[bytes] = []

    def _current(self) -> str:
        d = self._day
        return (f"{self._source}/{d.year:04d}/{d.month:02d}/{d.day:02d}/"
                f"run-{self._tag}-{self._part:04d}{BUNDLE_EXTENSION}")

    def put(self, key: str, payload: Any,
            content_type: str = "application/json") -> str:
        """Queue a payload; return where it will be once drained.

        `key` is the one-object key a BufferedWriter would have used. It is
        ignored: the address is a line of this run's current bundle.
        """
        # Serialise now, for the reason BufferedWriter does: the caller may
        # mutate the payload after this returns.
        self._buffer.append(self._store.serialise(payload))
        return record_key(self._current(), len(self._buffer) - 1)

    def drain(self) -> int:
        """Write the pending bundle, then start a new one. Returns records written."""
        if not self._buffer:
            return 0
        pending, self._buffer = self._buffer, []
        key = self._current()
        # Already serialised: `serialise` passes bytes through unchanged.
        stored = self._store.put_records(key, pending)
        if stored != len(pending):
            raise RuntimeError(f"bundle {key} holds {stored} records, not {len(pending)}")
        self._part += 1
        return stored

    def close(self) -> None:
        self.drain()

    def __enter__(self) -> "BundleWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.close()
        # On failure the pending lines are dropped with the rows that pointed
        # at them, which the caller rolls back: neither half survives alone.


class BufferedWriter:
    """Write raw payloads concurrently, and know when they have all landed.

    A raw payload is one small HTTPS round trip to object storage. Measured
    against Cloudflare R2 from this deployment: 530 ms each, which caps
    ingestion at under two records a second. PLACSP alone publishes tens of
    thousands of notices a day, so a sequential daily run could not finish
    inside a day, and it never once did. Sixteen concurrent writers measured
    23.5 a second on the same link -- the latency is round trips, not
    bandwidth, so overlapping them is the entire fix.

    The ordering rule survives, at batch granularity rather than per record:
    `drain()` blocks until every outstanding payload is stored and re-raises
    the first failure, and the pipeline drains before it commits. So a
    committed `raw_ingest` row always has its object in the store.

    The other direction is deliberately left open. If the process dies between
    a write and its commit, the store holds objects the index does not list --
    which is harmless, because the store is the source of truth and
    `reprocess --from-store` reads the bucket rather than the index. The
    reverse, an index pointing at objects that were never written, is the one
    that would quietly break replay, and draining before commit is what rules
    it out.
    """

    def __init__(self, store: RawStore, workers: int = 16) -> None:
        self._store = store
        self._workers = max(1, workers)
        self._pool: Any = None
        self._pending: list[Any] = []

    def _ensure_pool(self) -> Any:
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor

            self._pool = ThreadPoolExecutor(max_workers=self._workers,
                                            thread_name_prefix="rawstore")
        return self._pool

    def put(self, key: str, payload: Any,
            content_type: str = "application/json") -> str:
        """Queue a payload and return its key at once.

        The key is known before the write completes, so the caller can record
        it immediately; what the caller must not do is commit that record
        before `drain()` has returned.
        """
        if self._workers == 1:
            return self._store.put(key, payload, content_type)
        # Serialise on this thread: the payload may be mutated after this
        # returns, and a writer thread reading it later would store whatever
        # it had become rather than what was fetched.
        body = self._store.serialise(payload)
        self._pending.append(
            self._ensure_pool().submit(self._store.put, key, body, content_type))
        return key

    def drain(self) -> int:
        """Block until every queued write has landed. Re-raise the first failure."""
        pending, self._pending = self._pending, []
        error: BaseException | None = None
        for future in pending:
            try:
                future.result()
            except BaseException as exc:  # noqa: BLE001 - reported after all settle
                error = error or exc
        if error is not None:
            raise error
        return len(pending)

    def close(self) -> None:
        try:
            self.drain()
        finally:
            if self._pool is not None:
                self._pool.shutdown(wait=True)
                self._pool = None

    def __enter__(self) -> "BufferedWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.close()
        else:
            # The run is already failing; do not mask its exception with ours.
            if self._pool is not None:
                self._pool.shutdown(wait=False)
                self._pool = None
