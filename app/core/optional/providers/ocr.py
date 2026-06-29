"""Re-export shim for the handwriting OCR provider.

The OCR provider moved into the shared evaluation core
(:mod:`app.core.evaluation.providers.ocr`) so both the Optional platform and the
GS LMS can reuse it without cross-domain coupling (behavior-preserving — R19).
This module re-exports it so existing imports keep working unchanged.
"""
from __future__ import annotations

from app.core.evaluation.providers.ocr import (  # noqa: F401  (re-export)
    GeminiVisionOcrProvider,
    MockOcrProvider,
    OcrBlock,
    OcrNotConfiguredError,
    OcrProvider,
    OcrResult,
    get_ocr_provider,
    _PROVIDERS,
)

__all__ = [
    "OcrProvider",
    "OcrResult",
    "OcrBlock",
    "OcrNotConfiguredError",
    "MockOcrProvider",
    "GeminiVisionOcrProvider",
    "get_ocr_provider",
    "_PROVIDERS",
]
