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

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any, Iterator

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
    def get(self, key: str) -> Any:
        """Read a payload back, for replay and audit."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove one object. Only ever used for probe objects.

        Ingested payloads are never deleted: the store is the archive's
        insurance, and an insurance policy with a delete path is a liability.
        """

    @abstractmethod
    def listing(self, prefix: str = "") -> Iterator[tuple[str, float]]:
        """Every key under a prefix with the time it was written.

        Needed because a notice can now have several payloads in one day, and a
        rebuild has to replay them in the order they were observed or it will
        number the versions wrongly. Key order cannot carry that: the part that
        distinguishes them is a content hash, which sorts arbitrarily.
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

    def get(self, key: str) -> Any:
        raw = self._path(key).read_bytes()
        return json.loads(raw.decode("utf-8"))

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

    def listing(self, prefix: str = "") -> Iterator[tuple[str, float]]:
        base = Path(os.path.normpath(self.root / prefix)) if prefix else self.root
        if not base.exists():
            return
        for path in sorted(base.rglob("*.json")):
            yield path.relative_to(self.root).as_posix(), path.stat().st_mtime


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
            options.setdefault("config", Config(
                max_pool_connections=max(settings().raw_write_workers + 4, 10)))
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
        self.client.put_object(Bucket=self.bucket, Key=key,
                               Body=self.serialise(payload), ContentType=content_type)
        return key

    def get(self, key: str) -> Any:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))

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

    def list(self, prefix: str = "") -> Iterator[str]:
        for key, _ in self.listing(prefix):
            yield key

    def listing(self, prefix: str = "") -> Iterator[tuple[str, float]]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(".json"):
                    yield obj["Key"], obj["LastModified"].timestamp()


def build_store(backend: str | None = None) -> RawStore:
    """Construct the configured store. Unknown backend fails loudly."""
    cfg = settings()
    backend = (backend or cfg.raw_backend).lower()
    if backend == "fs":
        return FileRawStore(cfg.raw_dir)
    if backend == "s3":
        return S3RawStore(bucket=cfg.s3_bucket, **cfg.s3_settings())
    raise ValueError(f"unknown raw storage backend: {backend!r}")


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
