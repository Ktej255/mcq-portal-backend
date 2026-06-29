"""Object-storage abstraction for uploaded answer-sheet images.

Provides a :class:`MediaStore` protocol with a local-filesystem implementation
(dev) and an S3-style implementation (prod). References are SERVER-authored and
images are reachable only through access-controlled application routes — never a
public URL (Requirement 11.2 / 17.4).
"""
from app.core.storage.media_store import (
    InMemoryMediaStore,
    LocalMediaStore,
    MediaRef,
    MediaStore,
    MediaStoreError,
)

__all__ = [
    "MediaStore",
    "MediaRef",
    "MediaStoreError",
    "LocalMediaStore",
    "InMemoryMediaStore",
]
