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

import base64
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
        payload_filename: str = "payload.json",
    ) -> StoredObject:
        """Store one payload immutably, with a metadata sidecar. Path looks like
        `<dataset_code>/<utc-timestamp>/payload.json` (filename overridable for
        non-JSON payloads, e.g. `payload.xlsx` for NRB Excel publications)."""
        now = datetime.now(UTC)
        stamp = now.strftime("%Y-%m-%dT%H%M%S_%fZ")  # colon-free: safe on every filesystem
        prefix = f"{dataset_code.strip('/')}/{stamp}"
        payload_path = f"{prefix}/{payload_filename}"
        metadata_path = f"{prefix}/metadata.json"

        # No exists() pre-check: the microsecond-stamped path is unique per call,
        # and put() below already refuses to overwrite (x-upsert:false on Supabase,
        # an explicit raise on the local backend). The pre-check was a wasted
        # round trip on every write — and at full-catalogue scale, thousands of them.
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

    def store_snapshot(
        self,
        dataset_code: str,
        members: list[tuple[str, bytes, str]],
        snapshot_filename: str = "snapshot.json",
    ) -> StoredObject:
        """Archive MANY payloads as ONE immutable object plus a sidecar.

        For a bulk API harvest (e.g. the full ~1,400-indicator World Bank
        catalogue) writing a separate object per member means thousands of
        Storage round trips — pathologically slow on the free tier (~4,000
        uploads took ~3.8 h). One combined snapshot is two uploads instead.

        Each member's UNTOUCHED bytes are preserved verbatim (base64) next to
        its own SHA-256 and source URL, so any single payload is still
        recoverable byte-for-byte and independently verifiable — the raw-first
        guarantee holds, only the object granularity changes. `members` is a
        list of (member_key, payload_bytes, source_url).
        """
        now = datetime.now(UTC)
        stamp = now.strftime("%Y-%m-%dT%H%M%S_%fZ")  # colon-free: safe on every filesystem
        prefix = f"{dataset_code.strip('/')}/{stamp}"
        payload_path = f"{prefix}/{snapshot_filename}"
        metadata_path = f"{prefix}/metadata.json"
        fetched_at = now.isoformat()

        member_body: dict[str, object] = {}
        member_index: dict[str, str] = {}
        for key, payload, source_url in members:
            digest = hashlib.sha256(payload).hexdigest()
            member_body[key] = {
                "source_url": source_url,
                "sha256": digest,
                "size_bytes": len(payload),
                "payload_b64": base64.b64encode(payload).decode("ascii"),
            }
            member_index[key] = digest

        snapshot: dict[str, object] = {
            "archive_of": dataset_code,
            "fetched_at": fetched_at,
            "member_count": len(members),
            "members": member_body,
        }
        snapshot_bytes = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
        archive_sha = hashlib.sha256(snapshot_bytes).hexdigest()

        # The sidecar carries every member's hash, so a trace can verify any one
        # payload without downloading the whole (multi-MB) snapshot.
        metadata: dict[str, object] = {
            "sha256": archive_sha,
            "fetched_at": fetched_at,
            "member_count": len(members),
            "size_bytes": len(snapshot_bytes),
            "payload_path": payload_path,
            "members_sha256": member_index,
        }
        self.backend.put(payload_path, snapshot_bytes, "application/json")
        self.backend.put(
            metadata_path,
            json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"),
            "application/json",
        )
        return StoredObject(
            payload_path=payload_path,
            metadata_path=metadata_path,
            sha256=archive_sha,
            size_bytes=len(snapshot_bytes),
            fetched_at=fetched_at,
            source_url=dataset_code,
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
