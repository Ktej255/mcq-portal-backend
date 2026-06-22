"""Handwritten-image OCR upload endpoint for the Optional Subjects Platform
(Task 9.3 — Phase 1E, R9.1 / R9.3 / R20.1).

Exposes a single auth-gated route that turns an uploaded handwritten-answer
image into text the student can drop into the ``AnswerWorkspace`` (Task 9.1).
The route is mounted under ``/api/v1/optional`` and is auth-gated at the package
router level.

Route:

* ``POST /ocr``
    Accepts an uploaded image (multipart ``image`` field) plus an optional
    ``subject`` slug. Runs the image through the shared :class:`OcrProvider`
    abstraction (``get_ocr_provider().extract(...)``) and returns the normalised
    ``{text, confidence, blocks}`` extraction via ``StandardResponse`` (R9.1).
    The returned text is the exact text that, once the student accepts it, feeds
    the draft that will be evaluated (R9.1). Evaluation itself is Task 9.4 — this
    route only produces the OCR text; it never grades.

Confidence gating (R9.3 / R20.1 / design Property 7): the response carries the
gating ``threshold`` (``OCR_CONFIDENCE_THRESHOLD``) and a ``low_confidence``
boolean (``confidence < threshold``). When ``low_confidence`` is True the UI
must inform the student and offer a fallback (review/correct the extracted text,
type instead, or re-upload) before the text fills the answer — the backend never
decides a shaky OCR result is "good enough" silently.

Provider abstraction (R20.1): this endpoint depends only on the
:class:`OcrProvider` interface via :func:`get_ocr_provider`. The deterministic
mock is the default in dev/test (no model, offline, reproducible); a configured
Gemini-Vision backend (env ``OPTIONAL_OCR_PROVIDER=gemini-vision``) powers real
handwriting OCR in production by routing the image through the shared inference
gateway. There is exactly one OCR path — this route reuses the same abstraction
the recall/import pipelines use; it adds no second one.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.providers import (
    OcrProvider,
    OcrNotConfiguredError,
    get_ocr_provider,
)
from app.api.v1.optional.schemas import (
    OCR_CONFIDENCE_THRESHOLD,
    HandwritingOcrOut,
    OcrBlockOut,
)

router = APIRouter()

# Guard rail: reject implausibly large uploads early so a stray request can't
# exhaust memory. A scanned/photographed answer page is comfortably under 15 MB.
_MAX_IMAGE_BYTES = 15 * 1024 * 1024


def get_ocr_provider_dep() -> OcrProvider:
    """FastAPI dependency wrapper around the env-driven OCR factory.

    Wrapping the factory in a dependency keeps the route depending only on the
    :class:`OcrProvider` interface and lets tests inject a deterministic
    provider (e.g. a forced low-confidence stub) via ``dependency_overrides``
    without touching global env.
    """
    return get_ocr_provider()


@router.post("/ocr")
async def extract_handwriting(
    image: UploadFile = File(..., description="Uploaded handwritten-answer image"),
    subject: Optional[str] = Form(
        default=None, description="Optional subject slug the answer belongs to"
    ),
    provider: OcrProvider = Depends(get_ocr_provider_dep),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Extract handwritten text from an uploaded image via ``OcrProvider`` (R9.1).

    Returns the extracted text plus the confidence-gating signal (``threshold`` +
    ``low_confidence``) the UI uses to honour the low-confidence fallback
    contract (R9.3 / R20.1). The extracted text is what feeds the evaluated draft
    once accepted (R9.1); evaluation is Task 9.4.
    """
    raw = await image.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No image was provided to read.",
        )
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image is too large to process.",
        )

    try:
        result = provider.extract(raw, mime_type=image.content_type)
    except OcrNotConfiguredError as exc:
        # The selected backend isn't operational in this environment. Fail
        # loudly and clearly (R20.1) rather than returning a bad/silent OCR
        # result the student might unknowingly submit. The UI offers the
        # manual-type / re-upload fallback.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    low_confidence = result.confidence < OCR_CONFIDENCE_THRESHOLD

    data = HandwritingOcrOut(
        text=result.text,
        confidence=result.confidence,
        threshold=OCR_CONFIDENCE_THRESHOLD,
        low_confidence=low_confidence,
        provider=result.provider,
        blocks=[
            OcrBlockOut(text=block.text, confidence=block.confidence, bbox=block.bbox)
            for block in result.blocks
        ],
    )
    return StandardResponse(
        success=True,
        message="Handwriting extracted",
        data=data,
    )
