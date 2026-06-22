"""Speak-to-fill transcription endpoint for the Optional Subjects Platform
(Task 9.2 — Phase 1E, R8.2 / R8.3 / R8.4 / R20.3).

Exposes a single auth-gated route that turns a spoken answer into text the
student can drop into the ``AnswerWorkspace`` (Task 9.1). The route is mounted
under ``/api/v1/optional`` and is auth-gated at the package router level.

Route:

* ``POST /transcribe``
    Accepts an uploaded audio blob (multipart ``audio`` field) plus an optional
    ``subject`` slug and optional ``vocabulary_hint``. Runs the audio through
    the shared :class:`SttProvider` abstraction
    (``get_stt_provider().transcribe(...)``) and returns the normalised
    ``{text, confidence, segments}`` transcript via ``StandardResponse`` (R8.2).
    The returned transcript is the exact text that, once the student accepts it,
    becomes part of the draft that will be evaluated (R8.3).

Confidence gating (R8.4 / R20.3 / design Property 7): the response carries the
gating ``threshold`` (``STT_CONFIDENCE_THRESHOLD``) and a ``low_confidence``
boolean (``confidence < threshold``). When ``low_confidence`` is True the UI
must route the student through an explicit review/correct step before the
transcript fills the answer segment — the backend never decides the transcript
is "good enough" silently.

Provider abstraction (R8.5 / R20.2): this endpoint depends only on the
``SttProvider`` interface via :func:`get_stt_provider`. The deterministic mock
is the default in dev/test (no model, offline, reproducible); a configured
Whisper backend (env ``OPTIONAL_STT_PROVIDER=whisper``) powers real
transcription in production. There is exactly one STT path — this route reuses
the same abstraction the recall pipeline uses; it adds no second one.

Vocabulary biasing (R20.2): a small per-subject ``vocabulary_hint`` is derived
from the subject name (plus any caller-supplied hint terms) and passed through
to the provider to bias decoding toward domain vocabulary.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import OptionalSubject
from app.core.optional.providers import SttProvider, SttNotConfiguredError, get_stt_provider
from app.api.v1.optional.schemas import (
    STT_CONFIDENCE_THRESHOLD,
    SttSegmentOut,
    TranscriptionOut,
)

router = APIRouter()

# Guard rail: reject implausibly large uploads early so a stray request can't
# exhaust memory. Spoken-answer clips are short; 25 MB is generous headroom.
_MAX_AUDIO_BYTES = 25 * 1024 * 1024


def get_stt_provider_dep() -> SttProvider:
    """FastAPI dependency wrapper around the env-driven STT factory.

    Wrapping the factory in a dependency keeps the route depending only on the
    :class:`SttProvider` interface and lets tests inject a deterministic
    provider (e.g. a forced low-confidence stub) via ``dependency_overrides``
    without touching global env.
    """
    return get_stt_provider()


def _vocabulary_hint(
    db: Session, *, subject_slug: Optional[str], extra: Optional[str]
) -> List[str]:
    """Build a small domain ``vocabulary_hint`` to bias decoding (R20.2).

    Combines, in order: any caller-supplied comma/space separated terms, and a
    few tokens derived from the subject's name when a known ``subject_slug`` is
    given. Kept intentionally small and resilient — an unknown slug simply
    contributes no terms (transcription must never fail just because the hint
    can't be built).
    """
    terms: List[str] = []

    if extra:
        for chunk in extra.replace(",", " ").split():
            term = chunk.strip()
            if term and term not in terms:
                terms.append(term)

    if subject_slug:
        subject = (
            db.query(OptionalSubject)
            .filter(OptionalSubject.slug == subject_slug)
            .one_or_none()
        )
        if subject is not None and subject.name:
            for token in subject.name.split():
                token = token.strip()
                if token and token not in terms:
                    terms.append(token)

    return terms


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(..., description="Recorded spoken-answer audio blob"),
    subject: Optional[str] = Form(
        default=None, description="Optional subject slug for per-subject vocabulary biasing"
    ),
    vocabulary_hint: Optional[str] = Form(
        default=None, description="Optional extra domain terms (comma/space separated)"
    ),
    db: Session = Depends(get_db),
    provider: SttProvider = Depends(get_stt_provider_dep),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Transcribe a spoken answer to text via the shared ``SttProvider`` (R8.2).

    Returns the transcript plus the confidence-gating signal (``threshold`` +
    ``low_confidence``) the UI uses to honour the review/correct contract
    (R8.4 / R20.3). The transcript text is what becomes part of the evaluated
    draft once accepted (R8.3).
    """
    raw = await audio.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio was provided to transcribe.",
        )
    if len(raw) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio clip is too large to transcribe.",
        )

    hint = _vocabulary_hint(db, subject_slug=subject, extra=vocabulary_hint)

    try:
        result = provider.transcribe(
            raw, vocabulary_hint=hint or None, mime_type=audio.content_type
        )
    except SttNotConfiguredError as exc:
        # The selected backend isn't operational in this environment. Fail
        # loudly and clearly (R20.1/R20.3) rather than returning a bad/silent
        # transcript the student might unknowingly submit.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    low_confidence = result.confidence < STT_CONFIDENCE_THRESHOLD

    data = TranscriptionOut(
        text=result.text,
        confidence=result.confidence,
        threshold=STT_CONFIDENCE_THRESHOLD,
        low_confidence=low_confidence,
        provider=result.provider,
        segments=[
            SttSegmentOut(
                text=seg.text,
                start=seg.start,
                end=seg.end,
                confidence=seg.confidence,
            )
            for seg in result.segments
        ],
    )
    return StandardResponse(
        success=True,
        message="Transcription complete",
        data=data,
    )
