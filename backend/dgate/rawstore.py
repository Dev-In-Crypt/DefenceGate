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
import re
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def storage_key(source_code: str, native_id: str, when: date | None = None) -> str:
    """Deterministic key: ``source/YYYY/MM/DD/native_id.json``.

    Partitioned by source and date so a day can be replayed, audited or expired
    on its own. The identifier is sanitised because native identifiers come
    from twenty-seven national systems and some of them contain slashes.
    """
    day = when or date.today()
    safe = _UNSAFE.sub("_", native_id or "unknown")[:200]
    return f"{source_code}/{day.year:04d}/{day.month:02d}/{day.day:02d}/{safe}.json"


class RawStore(ABC):
    """Write-once storage. Nothing here ever overwrites deliberately."""

    @abstractmethod
    def put(self, key: str, payload: Any, content_type: str = "application/json") -> str:
        """Store a payload under ``key`` and return the key."""

    @abstractmethod
    def get(self, key: str) -> Any:
        """Read a payload back, for replay and audit."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

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
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
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

            self._client = boto3.client("s3", **self._client_kwargs)
        return self._client

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


def build_store(backend: str | None = None) -> RawStore:
    """Construct the configured store. Unknown backend fails loudly."""
    cfg = settings()
    backend = (backend or cfg.raw_backend).lower()
    if backend == "fs":
        return FileRawStore(cfg.raw_dir)
    if backend == "s3":
        import os

        return S3RawStore(
            bucket=os.environ.get("DGATE_S3_BUCKET", "dgate-raw"),
            endpoint_url=os.environ.get("DGATE_S3_ENDPOINT") or None,
            aws_access_key_id=os.environ.get("DGATE_S3_ACCESS_KEY") or None,
            aws_secret_access_key=os.environ.get("DGATE_S3_SECRET_KEY") or None,
        )
    raise ValueError(f"unknown raw storage backend: {backend!r}")
