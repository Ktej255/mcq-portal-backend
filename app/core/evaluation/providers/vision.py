"""Vision-grading helpers for the evaluation core (R13).

When the active model supports vision, answer-sheet images are attached to the
inference request so diagrams/maps are graded directly (R13.1). When the active
model does NOT support vision, callers should instead merge a textual
description of any detected diagram into the answer content (R13.2); this module
exposes the predicate and the attach helper so the engine stays declarative.

Subject-neutral.
"""
from __future__ import annotations

from typing import List

from app.core.inference.contracts import InferenceRequest
from app.core.evaluation.providers.config import ProviderConfig


def should_use_vision(config: ProviderConfig, images: List[bytes]) -> bool:
    """True when there are images AND the configured model supports vision."""
    return bool(images) and config.supports_vision


def apply_vision(
    request: InferenceRequest,
    images: List[bytes],
    config: ProviderConfig,
    *,
    mime_type: str = "image/png",
) -> InferenceRequest:
    """Attach the first answer-sheet page to ``request`` for direct grading.

    The shared :class:`InferenceRequest` carries a single image; the first page
    is attached and the assembled OCR text (already in the prompt) covers the
    remaining pages. Returns the same request for chaining.
    """
    if should_use_vision(config, images):
        request.image = images[0]
        request.image_mime_type = mime_type
    return request


__all__ = ["should_use_vision", "apply_vision"]
