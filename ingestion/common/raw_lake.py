"""Immutable raw data lake (P1.S7, Blueprint §2.2).

Every pipeline stores the untouched source payload here BEFORE parsing, together
with a sidecar metadata file recording its SHA-256 hash, fetch time (UTC), source
URL, and size. Objects are never overwritten — the lake is append-only — so a
published number can later be traced byte-for-byte back to the exact original.

Two backends:
  - LocalFilesystemBackend  -- writes to a local directory; used by tests so the
                               suite needs no network.
  - SupabaseStorageBackend  -- writes to a private Supabase Storage bucket.

`RawLake.from_env()` builds the Supabase-backed lake from .env (storage keys live
in .env only, never in code).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import requests
from dotenv import load_dotenv

DEFAULT_BUCKET = "raw-lake"


class RawLakeError(Exception):
    """A raw-lake write failed, or would have overwritten existing data."""


@dataclass(frozen=True)
class StoredObject:
    """References to what was stored — fed into releases.raw_file_refs later."""

    payload_path: str
    metadata_path: str
    sha256: str
    size_bytes: int
    fetched_at: str
    source_url: str


class StorageBackend(Protocol):
    def exists(self, path: str) -> bool: ...
    def put(self, path: str, data: bytes, content_type: str) -> None: ...
    def get(self, path: str) -> bytes: ...
    def delete(self, path: str) -> None: ...


class LocalFilesystemBackend:
    """Stores objects under a local directory (used by tests — no network)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _full(self, path: str) -> Path:
        return self.root / path

    def exists(self, path: str) -> bool:
        return self._full(path).exists()

    def put(self, path: str, data: bytes, content_type: str) -> None:
        full = self._full(path)
        if full.exists():
            raise RawLakeError(f"refusing to overwrite existing object: {path}")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    def get(self, path: str) -> bytes:
        return self._full(path).read_bytes()

    def delete(self, path: str) -> None:
        full = self._full(path)
        if full.exists():
            full.unlink()


class SupabaseStorageBackend:
    """Stores objects in a private Supabase Storage bucket via its REST API."""

    def __init__(self, url: str, service_key: str, bucket: str) -> None:
        self._base = url.rstrip("/") + "/storage/v1"
        self._key = service_key
        self.bucket = bucket

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._key}", "apikey": self._key}
        if extra:
            headers.update(extra)
        return headers

    def _object_url(self, path: str) -> str:
        return f"{self._base}/object/{self.bucket}/{path}"

    def exists(self, path: str) -> bool:
        resp = requests.get(self._object_url(path), headers=self._headers(), timeout=30)
        return resp.ok

    def put(self, path: str, data: bytes, content_type: str) -> None:
        resp = requests.post(
            self._object_url(path),
            data=data,
            headers=self._headers({"Content-Type": content_type, "x-upsert": "false"}),
            timeout=60,
        )
        if not resp.ok:
            if resp.status_code in (400, 409) and "exist" in resp.text.lower():
                raise RawLakeError(f"refusing to overwrite existing object: {path}")
            raise RawLakeError(f"upload failed ({resp.status_code}): {resp.text}")

    def get(self, path: str) -> bytes:
        resp = requests.get(self._object_url(path), headers=self._headers(), timeout=30)
        if not resp.ok:
            raise RawLakeError(f"download failed ({resp.status_code}): {resp.text}")
        return resp.content

    def delete(self, path: str) -> None:
        requests.delete(self._object_url(path), headers=self._headers(), timeout=30)


class RawLake:
    def __init__(self, backend: StorageBackend) -> None:
        self.backend = backend

    def store(
        self,
        dataset_code: str,
        payload: bytes,
        source_url: str,
        content_type: str = "application/json",
    ) -> StoredObject:
        """Store one payload immutably, with a metadata sidecar. Path looks like
        `<dataset_code>/<utc-timestamp>/payload.json`."""
        now = datetime.now(UTC)
        stamp = now.strftime("%Y-%m-%dT%H%M%S_%fZ")  # colon-free: safe on every filesystem
        prefix = f"{dataset_code.strip('/')}/{stamp}"
        payload_path = f"{prefix}/payload.json"
        metadata_path = f"{prefix}/metadata.json"

        if self.backend.exists(payload_path):
            raise RawLakeError(f"refusing to overwrite existing object: {payload_path}")

        sha256 = hashlib.sha256(payload).hexdigest()
        fetched_at = now.isoformat()
        metadata: dict[str, object] = {
            "sha256": sha256,
            "fetched_at": fetched_at,
            "source_url": source_url,
            "size_bytes": len(payload),
            "payload_path": payload_path,
        }
        # Payload first, then its sidecar — both refuse to overwrite.
        self.backend.put(payload_path, payload, content_type)
        self.backend.put(
            metadata_path,
            json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"),
            "application/json",
        )
        return StoredObject(
            payload_path=payload_path,
            metadata_path=metadata_path,
            sha256=sha256,
            size_bytes=len(payload),
            fetched_at=fetched_at,
            source_url=source_url,
        )

    @classmethod
    def from_env(cls) -> RawLake:
        load_dotenv()
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        bucket = os.environ.get("STORAGE_BUCKET", DEFAULT_BUCKET).strip() or DEFAULT_BUCKET
        if not url or not key:
            raise RawLakeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env to use the raw lake."
            )
        return cls(SupabaseStorageBackend(url, key, bucket))
