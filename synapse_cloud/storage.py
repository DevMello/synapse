"""Blob storage seam over Supabase Storage (S3-backed).

Buckets: `traces` (full reasoning traces / artifacts), `artifacts`, `checkpoints`
(opaque E2E-encrypted run-checkpoint payloads the cloud cannot read). In test
mode a fake keeps blobs in memory.
"""
from __future__ import annotations

import abc
from typing import Optional

from .config import get_settings
from .db import service_db

TRACES = "traces"
ARTIFACTS = "artifacts"
CHECKPOINTS = "checkpoints"


class BlobStore(abc.ABC):
    @abc.abstractmethod
    async def put(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload bytes; returns a storage ref ('bucket/key')."""

    @abc.abstractmethod
    async def get(self, bucket: str, key: str) -> bytes:
        ...

    @abc.abstractmethod
    async def signed_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        ...


class FakeBlobStore(BlobStore):
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    async def put(self, bucket, key, data, content_type="application/octet-stream"):
        self.blobs[f"{bucket}/{key}"] = bytes(data)
        return f"{bucket}/{key}"

    async def get(self, bucket, key):
        return self.blobs[f"{bucket}/{key}"]

    async def signed_url(self, bucket, key, expires_in=3600):
        return f"memory://{bucket}/{key}"


class SupabaseBlobStore(BlobStore):
    async def put(self, bucket, key, data, content_type="application/octet-stream"):
        db = await service_db()
        await db.storage.from_(bucket).upload(
            key, bytes(data), {"content-type": content_type, "upsert": "true"}
        )
        return f"{bucket}/{key}"

    async def get(self, bucket, key):
        db = await service_db()
        return await db.storage.from_(bucket).download(key)

    async def signed_url(self, bucket, key, expires_in=3600):
        db = await service_db()
        res = await db.storage.from_(bucket).create_signed_url(key, expires_in)
        return res.get("signedURL") or res.get("signedUrl") or ""


_store: Optional[BlobStore] = None


def get_storage() -> BlobStore:
    global _store
    if _store is None:
        _store = FakeBlobStore() if get_settings().is_test else SupabaseBlobStore()
    return _store


def set_storage(store: BlobStore) -> None:
    global _store
    _store = store
