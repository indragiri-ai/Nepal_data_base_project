"""Tests for the raw data lake (P1.S7). Uses the local backend — no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.common.raw_lake import LocalFilesystemBackend, RawLake, RawLakeError


def test_store_writes_payload_and_metadata(tmp_path: Path) -> None:
    lake = RawLake(LocalFilesystemBackend(tmp_path))
    payload = b'{"hello": "world"}'

    obj = lake.store("worldbank/wdi", payload, "https://example.test/data")

    # the payload is stored byte-for-byte
    assert (tmp_path / obj.payload_path).read_bytes() == payload
    assert obj.size_bytes == len(payload)
    assert len(obj.sha256) == 64  # sha-256 hex digest

    # the sidecar metadata records hash, source, and size
    meta = json.loads((tmp_path / obj.metadata_path).read_text(encoding="utf-8"))
    assert meta["sha256"] == obj.sha256
    assert meta["source_url"] == "https://example.test/data"
    assert meta["size_bytes"] == len(payload)


def test_backend_never_overwrites(tmp_path: Path) -> None:
    backend = LocalFilesystemBackend(tmp_path)
    backend.put("a/b/payload.json", b"first", "application/json")
    with pytest.raises(RawLakeError):
        backend.put("a/b/payload.json", b"second", "application/json")
