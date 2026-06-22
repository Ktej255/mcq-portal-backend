"""Interactive Recall-LMS endpoints for the Optional Subjects Platform
(Task 12 — Phase 1H, R13 / R14 / R20).

The record → transcribe → concept-match → score → adaptive-hint loop that
measures what a student actually recalled from a video segment (not what they
watched). Mounted under ``/api/v1/optional`` and auth-gated at the package
router level.

Routes:

* ``GET /{slug}/segments``
    The subject's ordered video segments (R13.1). The concept checklist is not
    exposed — only ``concept_count`` — so recall isn't given away. An empty list
    is the honest "no recall lessons authored yet" state.

* ``POST /segments/{segment_id}/recall``  (multipart ``audio``)
    Start a recall session for the segment: transcribe the spoken response
    (STT), concept-match it, score it, persist the first turn, and return the
    explainable result + an adaptive Socratic hint when below 100% (R13.2–R13.5,
    R14.1–R14.5).

* ``POST /recall/{session_id}/respond``  (multipart ``audio``)
    A follow-up turn answering a hint: transcribe, match, and update the
    cumulative score — only newly recalled concepts raise it (R14.3/R14.7,
    Property 3). Ownership-checked against the requesting student.

* ``GET /recall/{session_id}``
    The session's current state + ordered turns (reload-on-return, R15).

Determinism + anti-gaming (Properties 4/5): matching runs at low temperature /
deterministic mock; verbatim echoes of the segment script never earn recall.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import OptionalSubject
from app.core.optional.student_models import (
    VideoSegment,
    ConceptPoint,
    RecallSession,
    RecallTurn,
    RecallSessionStatusEnum,
)
from app.core.optional.providers import (
    SttProvider,
    SttNotConfiguredError,
    get_stt_provider,
    RecallProvider,
    get_recall_provider,
)
from app.core.optional.recall import score_classifications, missed_concepts
from app.api.v1.optional.schemas import (
    STT_CONFIDENCE_THRESHOLD,
    RecallSegmentOut,
    RecallSegmentListOut,
    RecallMatchedConceptOut,
    RecallTurnResultOut,
    RecallSessionStateOut,
)

router = APIRouter()

_MAX_AUDIO_BYTES = 25 * 1024 * 1024


def get_recall_stt_provider_dep() -> SttProvider:
    """STT provider dependency for recall (test-overridable)."""
    return get_stt_provider()


def get_recall_provider_dep() -> RecallProvider:
    """Recall matcher/hinter dependency (test-overridable)."""
    return get_recall_provider()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_subject_or_404(db: Session, slug: str) -> OptionalSubject:
    subject = (
        db.query(OptionalSubject).filter(OptionalSubject.slug == slug).one_or_none()
    )
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optional subject '{slug}' not found",
        )
    return subject


def _get_segment_or_404(db: Session, segment_id: int) -> VideoSegment:
    segment = (
        db.query(VideoSegment).filter(VideoSegment.id == segment_id).one_or_none()
    )
    if segment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video segment {segment_id} not found",
        )
    return segment


def _checklist(segment: VideoSegment) -> List[dict]:
    """The segment's concept checklist as ``[{concept, weight}]`` (R14.1)."""
    points = sorted(segment.concept_points, key=lambda c: (c.display_order, c.id))
    return [{"concept": p.text, "weight": float(p.weight or 0.0)} for p in points]


def _all_session_classifications(session: RecallSession) -> List[dict]:
    """Union of every turn's credited concepts → cumulative scoring input.

    Each stored turn's ``matched_concepts`` is a list of ``{concept, status,
    evidence}``; feeding the union to :func:`score_classifications` yields the
    cumulative (monotonic) session score (Property 3).
    """
    out: List[dict] = []
    for turn in session.turns:
        for m in turn.matched_concepts or []:
            if isinstance(m, dict) and m.get("concept"):
                out.append(m)
    return out


def _read_audio_sync(upload: UploadFile) -> bytes:
    raw = upload.file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio was provided.",
        )
    if len(raw) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio clip is too large.",
        )
    return raw


def _transcribe(
    stt: SttProvider,
    audio: bytes,
    subject_name: Optional[str],
    mime_type: Optional[str] = None,
) -> tuple[str, float]:
    hint = [t for t in (subject_name or "").split() if t] or None
    try:
        result = stt.transcribe(audio, vocabulary_hint=hint, mime_type=mime_type)
    except SttNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return result.text, result.confidence


def _segment_subject_name(db: Session, segment: VideoSegment) -> Optional[str]:
    subject = (
        db.query(OptionalSubject)
        .filter(OptionalSubject.id == segment.subject_id)
        .one_or_none()
    )
    return subject.name if subject else None


def _persist_turn_and_score(
    db: Session,
    *,
    session: RecallSession,
    segment: VideoSegment,
    recall: RecallProvider,
    transcript: str,
    stt_confidence: float,
    audio_ref: Optional[str] = None,
) -> RecallTurnResultOut:
    """Match this turn, persist it, recompute cumulative score, build the result."""
    checklist = _checklist(segment)

    # Classify THIS turn's transcript against the checklist (anti-gaming via the
    # segment script — Property 5).
    match = recall.match(transcript, checklist, segment_script=segment.script)
    this_turn = score_classifications(checklist, match.concepts)

    # Cumulative: union this turn's credited concepts with all prior turns'.
    prior = _all_session_classifications(session)
    cumulative_input = prior + [
        {"concept": m["concept"], "status": m["status"], "evidence": m.get("evidence", "")}
        for m in this_turn.matched
    ]
    cumulative = score_classifications(checklist, cumulative_input)

    turn_order = len(session.turns) + 1

    # Adaptive Socratic hint toward a still-missing concept (R14.2/R14.4).
    hint_text: Optional[str] = None
    hint_target: Optional[str] = None
    if not cumulative.is_complete:
        still_missing = missed_concepts(checklist, cumulative_input)
        if still_missing:
            prior_responses = [t.transcript or "" for t in session.turns] + [transcript]
            hint_obj = recall.hint(still_missing, prior_responses)
            hint_text = hint_obj.hint
            hint_target = hint_obj.target_concept

    turn = RecallTurn(
        session_id=session.id,
        turn_order=turn_order,
        audio_ref=audio_ref,
        transcript=transcript,
        matched_concepts=cumulative.matched,
        missed_concepts=cumulative.missed,
        recall_score=cumulative.score,
        hint_given=hint_text,
    )
    db.add(turn)

    session.recall_score = cumulative.score
    if cumulative.is_complete:
        session.status = RecallSessionStatusEnum.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
    db.flush()

    return RecallTurnResultOut(
        session_id=session.id,
        turn_order=turn_order,
        transcript=transcript,
        stt_confidence=stt_confidence,
        stt_low_confidence=stt_confidence < STT_CONFIDENCE_THRESHOLD,
        recall_score=cumulative.score,
        recall_percent=cumulative.percent,
        matched=[
            RecallMatchedConceptOut(
                concept=m["concept"], status=m["status"], evidence=m.get("evidence", "")
            )
            for m in cumulative.matched
        ],
        missed=cumulative.missed,
        hint=hint_text,
        hint_target=hint_target,
        complete=cumulative.is_complete,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/{slug}/segments")
def list_segments(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """List the subject's ordered recall video segments (R13.1)."""
    subject = _get_subject_or_404(db, slug)
    segments = (
        db.query(VideoSegment)
        .filter(VideoSegment.subject_id == subject.id)
        .order_by(VideoSegment.segment_order.asc(), VideoSegment.id.asc())
        .all()
    )
    out = [
        RecallSegmentOut(
            segment_id=s.id,
            subject_id=s.subject_id,
            title=s.title,
            segment_order=s.segment_order,
            video_ref=s.video_ref,
            duration_seconds=s.duration_seconds,
            concept_count=len(s.concept_points),
        )
        for s in segments
    ]
    return StandardResponse(
        success=True,
        message="Segments retrieved",
        data=RecallSegmentListOut(
            slug=subject.slug, name=subject.name, total=len(out), segments=out
        ),
    )


@router.post("/segments/{segment_id}/recall")
def start_recall(
    segment_id: int,
    audio: UploadFile = File(..., description="Recorded spoken recall"),
    db: Session = Depends(get_db),
    stt: SttProvider = Depends(get_recall_stt_provider_dep),
    recall: RecallProvider = Depends(get_recall_provider_dep),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Start a recall session for a segment and score the first turn (R13/R14)."""
    segment = _get_segment_or_404(db, segment_id)
    if not segment.concept_points:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This segment has no concept checklist authored yet.",
        )

    raw = _read_audio_sync(audio)
    transcript, confidence = _transcribe(
        stt, raw, _segment_subject_name(db, segment), audio.content_type
    )

    session = RecallSession(
        student_id=current_user.id,
        video_segment_id=segment.id,
        status=RecallSessionStatusEnum.IN_PROGRESS,
        recall_score=0.0,
    )
    db.add(session)
    db.flush()

    result = _persist_turn_and_score(
        db,
        session=session,
        segment=segment,
        recall=recall,
        transcript=transcript,
        stt_confidence=confidence,
    )
    db.commit()
    return StandardResponse(success=True, message="Recall scored", data=result)


@router.post("/recall/{session_id}/respond")
def respond_recall(
    session_id: int,
    audio: UploadFile = File(..., description="Recorded response to the hint"),
    db: Session = Depends(get_db),
    stt: SttProvider = Depends(get_recall_stt_provider_dep),
    recall: RecallProvider = Depends(get_recall_provider_dep),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Append a follow-up recall turn; only new content raises the score (R14.3)."""
    session = (
        db.query(RecallSession)
        .filter(
            RecallSession.id == session_id,
            RecallSession.student_id == current_user.id,  # ownership (P10)
        )
        .one_or_none()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recall session {session_id} not found",
        )
    segment = _get_segment_or_404(db, session.video_segment_id)

    raw = _read_audio_sync(audio)
    transcript, confidence = _transcribe(
        stt, raw, _segment_subject_name(db, segment), audio.content_type
    )

    result = _persist_turn_and_score(
        db,
        session=session,
        segment=segment,
        recall=recall,
        transcript=transcript,
        stt_confidence=confidence,
    )
    db.commit()
    return StandardResponse(success=True, message="Recall updated", data=result)


@router.get("/recall/{session_id}")
def get_recall_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return a recall session's state + ordered turns (reload-on-return, R15)."""
    session = (
        db.query(RecallSession)
        .filter(
            RecallSession.id == session_id,
            RecallSession.student_id == current_user.id,  # ownership (P10)
        )
        .one_or_none()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recall session {session_id} not found",
        )

    turns_out: List[RecallTurnResultOut] = []
    for turn in sorted(session.turns, key=lambda t: (t.turn_order, t.id)):
        score = float(turn.recall_score or 0.0)
        turns_out.append(
            RecallTurnResultOut(
                session_id=session.id,
                turn_order=turn.turn_order,
                transcript=turn.transcript or "",
                stt_confidence=0.0,
                stt_low_confidence=False,
                recall_score=score,
                recall_percent=round(score * 100.0, 4),
                matched=[
                    RecallMatchedConceptOut(
                        concept=m.get("concept", ""),
                        status=m.get("status", ""),
                        evidence=m.get("evidence", ""),
                    )
                    for m in (turn.matched_concepts or [])
                    if isinstance(m, dict)
                ],
                missed=list(turn.missed_concepts or []),
                hint=turn.hint_given,
                hint_target=None,
                complete=score >= 1.0,
            )
        )

    state = RecallSessionStateOut(
        session_id=session.id,
        segment_id=session.video_segment_id,
        status=session.status.value
        if hasattr(session.status, "value")
        else str(session.status),
        recall_score=float(session.recall_score or 0.0),
        recall_percent=round(float(session.recall_score or 0.0) * 100.0, 4),
        turns=turns_out,
    )
    return StandardResponse(success=True, message="Recall session retrieved", data=state)
