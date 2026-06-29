"""MediaStore protocol + local/in-memory implementations (R11, R17).

The store MINTS the storage reference server-side (clients never supply it —
R11.2) and authorizes reads to the Owning_Student or an authorized Evaluator
(R17.3). Images are reached only through application routes; no implementation
exposes a public URL (R17.4).

Subject-neutral: imports nothing from GS or Optional domains.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Protocol


class MediaStoreError(RuntimeError):
    """Storage failure (missing object, unauthorized read, backend error)."""


@dataclass(frozen=True)
class MediaRef:
    """A server-authored reference to a stored object."""

    key: str


def _mint_key(owner_id: int, attempt_id: int, page_order: int) -> str:
    """Server-authored, collision-resistant key (never client-supplied)."""
    token = uuid.uuid4().hex
    return f"gslms/{owner_id}/{attempt_id}/{page_order:03d}_{token}"


def _authorize(requester_id: int, owner_id: int, is_evaluator: bool) -> None:
    if requester_id != owner_id and not is_evaluator:
        # Do not leak existence — the API maps this to a 404/403 as appropriate.
        raise MediaStoreError("not authorized to read this object")


class MediaStore(Protocol):
    """Stores and retrieves answer-sheet image bytes."""

    def put(
        self,
        data: bytes,
        *,
        content_type: str,
        owner_id: int,
        attempt_id: int,
        page_order: int,
    ) -> MediaRef: ...

    def open(
        self,
        key: str,
        *,
        requester_id: int,
        is_evaluator: bool,
        owner_id: int,
    ) -> bytes: ...


class InMemoryMediaStore:
    """Process-local store (tests / ephemeral dev)."""

    def __init__(self) -> None:
        self._objects: Dict[str, bytes] = {}

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
        self._objects[key] = bytes(data)
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
        if key not in self._objects:
            raise MediaStoreError(f"object not found: {key}")
        return self._objects[key]


class LocalMediaStore:
    """Local-filesystem store (single-node dev).

    Files are written under ``base_dir`` (env ``MEDIA_STORE_DIR`` or a default
    ``.media_store`` directory). The key encodes owner/attempt/page for
    traceability but reads are authorized explicitly (R17.3).
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(
            base_dir or os.environ.get("MEDIA_STORE_DIR") or ".media_store"
        )

    def _path(self, key: str) -> Path:
        return self.base_dir / key

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
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
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
        path = self._path(key)
        if not path.exists():
            raise MediaStoreError(f"object not found: {key}")
        return path.read_bytes()


__all__ = [
    "MediaStore",
    "MediaRef",
    "MediaStoreError",
    "InMemoryMediaStore",
    "LocalMediaStore",
]
