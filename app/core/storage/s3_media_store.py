"""S3-style MediaStore implementation (prod) — R11.2, R17.4.

Implements the same :class:`MediaStore` protocol as the local store using an
S3-compatible backend (AWS S3, MinIO, etc.). References are server-authored and
reads are authorized to the Owning_Student / Evaluator; objects are returned as
bytes through the application — never via a public URL.

``boto3`` is imported lazily so importing this module never requires the SDK or
credentials in environments that use the local/in-memory store.
"""
from __future__ import annotations

import os

from app.core.storage.media_store import (
    MediaRef,
    MediaStoreError,
    _authorize,
    _mint_key,
)


class S3MediaStore:
    """Stores answer-sheet images in an S3-compatible bucket."""

    def __init__(self, bucket: str | None = None, *, region: str | None = None) -> None:
        self.bucket = bucket or os.environ.get("MEDIA_STORE_S3_BUCKET")
        if not self.bucket:
            raise MediaStoreError(
                "S3MediaStore requires a bucket (set MEDIA_STORE_S3_BUCKET)"
            )
        self.region = region or os.environ.get("AWS_REGION") or "ap-south-1"
        self._client = None

    def _s3(self):
        if self._client is None:
            try:
                import boto3  # lazy import
            except Exception as exc:  # pragma: no cover - env dependent
                raise MediaStoreError(
                    "boto3 is required for S3MediaStore but is not installed"
                ) from exc
            self._client = boto3.client("s3", region_name=self.region)
        return self._client

    def put(
        self,
        data: bytes,
        *,
        content_type: str,
        owner_id: int,
        attempt_id: int,
        page_order: int,
    ) -> MediaRef:
        key = _mint_key(owner_id, attempt_id, page_order)
        try:
            self._s3().put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type or "application/octet-stream",
            )
        except Exception as exc:  # pragma: no cover - network dependent
            raise MediaStoreError(f"failed to store object: {type(exc).__name__}") from exc
        return MediaRef(key=key)

    def open(
        self,
        key: str,
        *,
        requester_id: int,
        is_evaluator: bool,
        owner_id: int,
    ) -> bytes:
        _authorize(requester_id, owner_id, is_evaluator)
        try:
            obj = self._s3().get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except Exception as exc:  # pragma: no cover - network dependent
            raise MediaStoreError(f"object not found or unreadable: {key}") from exc


__all__ = ["S3MediaStore"]
