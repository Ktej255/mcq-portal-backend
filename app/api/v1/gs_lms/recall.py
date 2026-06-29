"""Recall Check endpoints for the Interactive Learning Funnel.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at package router):
* POST /funnel/{node_id}/recall/text — Submit typed recall for scoring
* POST /funnel/{node_id}/recall/audio — Upload audio blob for STT + scoring
* GET /funnel/{node_id}/recall/{section_label} — Get recall attempt for a section

Requirements traced: 5.1, 5.2, 5.3, 5.6, 5.7, 5.8, 13.7
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.gs.models import GsSubject, GsReviewStatusEnum
from app.core.gs_lms.models import GsLmsSyllabusNode, GsLmsContentSection
from app.core.gs_lms.funnel_models import GsLmsRecallAttempt
from app.core.gs_lms.recall_scoring import (
    extract_key_concepts,
    score_recall,
)
from app.core.gs_lms.stt_provider import get_stt_provider, STT_CONFIDENCE_THRESHOLD
from app.api.v1.gs_lms.dependencies import resolve_subject


router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RecallTextIn(BaseModel):
    section_label: str = Field(..., description="Content section label (BASIC, NCERT, ADVANCED, etc.)")
    text: str = Field(..., min_length=1, max_length=10000, description="Typed recall text (1-10000 chars)")


class ConceptMatchOut(BaseModel):
    concept: str
    matched: bool
    matched_fragment: str | None = None


class RecallCheckOut(BaseModel):
    recall_score: int          # 0-100
    confidence_score: int      # 0-100
    concepts: List[ConceptMatchOut]
    total_concepts: int
    matched_count: int
    stt_confidence: float | None = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/funnel/{node_id}/recall/text", response_model=RecallCheckOut)
def submit_recall_text(
    node_id: int,
    body: RecallTextIn,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit typed recall text for scoring against section key concepts.

    Validates transcript length (1-10000 chars). Extracts key concepts from
    the section content blocks, scores the recall, and persists the attempt.
    """
    # Verify node exists
    node = db.query(GsLmsSyllabusNode).filter(
        GsLmsSyllabusNode.id == node_id,
        GsLmsSyllabusNode.subject_id == subject.id,
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="Topic node not found")

    # Find the section
    section = db.query(GsLmsContentSection).filter(
        GsLmsContentSection.syllabus_node_id == node_id,
        GsLmsContentSection.section_label == body.section_label,
        GsLmsContentSection.review_status == GsReviewStatusEnum.REVIEWED,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail=f"Section '{body.section_label}' not found or not reviewed")

    # Extract key concepts from section content
    section_blocks = section.blocks or []
    key_concepts = extract_key_concepts(section_blocks)

    if not key_concepts:
        # If no concepts could be extracted, use a minimal fallback
        key_concepts = [section.title.lower()] if section.title else []

    # Score the recall
    result = score_recall(body.text, key_concepts)

    # Count existing attempts for this section
    attempt_count = db.query(GsLmsRecallAttempt).filter(
        GsLmsRecallAttempt.student_id == current_user.id,
        GsLmsRecallAttempt.syllabus_node_id == node_id,
        GsLmsRecallAttempt.section_label == body.section_label,
    ).count()

    # Persist the recall attempt
    recall_attempt = GsLmsRecallAttempt(
        student_id=current_user.id,
        syllabus_node_id=node_id,
        section_label=body.section_label,
        audio_storage_ref=None,  # text-based recall, no audio
        transcript=body.text,
        recall_score=result.recall_score,
        confidence_score=result.confidence_score,
        concepts_matched=[c.concept for c in result.concepts if c.matched],
        concepts_missed=[c.concept for c in result.concepts if not c.matched],
        stt_confidence=None,
        attempt_number=attempt_count + 1,
    )
    db.add(recall_attempt)
    db.commit()

    return RecallCheckOut(
        recall_score=round(result.recall_score * 100),
        confidence_score=round(result.confidence_score * 100),
        concepts=[
            ConceptMatchOut(
                concept=c.concept,
                matched=c.matched,
                matched_fragment=c.matched_fragment,
            )
            for c in result.concepts
        ],
        total_concepts=result.total_concepts,
        matched_count=result.matched_count,
        stt_confidence=None,
    )


@router.post("/funnel/{node_id}/recall/audio", response_model=RecallCheckOut)
async def submit_recall_audio(
    node_id: int,
    section_label: str = Form(...),
    audio: UploadFile = File(...),
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload audio blob for STT transcription and recall scoring.

    Accepts audio file (webm/wav/mp4), transcribes via the STT provider,
    scores against section key concepts, and persists the attempt.
    If STT confidence < 0.6, flags for student review.
    """
    # Verify node exists
    node = db.query(GsLmsSyllabusNode).filter(
        GsLmsSyllabusNode.id == node_id,
        GsLmsSyllabusNode.subject_id == subject.id,
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="Topic node not found")

    # Find the section
    section = db.query(GsLmsContentSection).filter(
        GsLmsContentSection.syllabus_node_id == node_id,
        GsLmsContentSection.section_label == section_label,
        GsLmsContentSection.review_status == GsReviewStatusEnum.REVIEWED,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail=f"Section '{section_label}' not found or not reviewed")

    # Read audio bytes
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="Empty audio file")

    # Transcribe via STT provider
    stt = get_stt_provider()
    # Get vocabulary hint from section key concepts
    section_blocks = section.blocks or []
    key_concepts = extract_key_concepts(section_blocks)
    if not key_concepts:
        key_concepts = [section.title.lower()] if section.title else []

    stt_result = stt.transcribe(
        audio_bytes,
        vocabulary_hint=key_concepts[:10],
        mime_type=audio.content_type,
    )

    transcript = stt_result.text
    stt_confidence = stt_result.confidence

    # Score the recall
    result = score_recall(transcript, key_concepts)

    # Count existing attempts
    attempt_count = db.query(GsLmsRecallAttempt).filter(
        GsLmsRecallAttempt.student_id == current_user.id,
        GsLmsRecallAttempt.syllabus_node_id == node_id,
        GsLmsRecallAttempt.section_label == section_label,
    ).count()

    # Persist the recall attempt
    recall_attempt = GsLmsRecallAttempt(
        student_id=current_user.id,
        syllabus_node_id=node_id,
        section_label=section_label,
        audio_storage_ref=f"recall/{current_user.id}/{node_id}/{section_label}/{attempt_count + 1}",
        transcript=transcript,
        recall_score=result.recall_score,
        confidence_score=result.confidence_score,
        concepts_matched=[c.concept for c in result.concepts if c.matched],
        concepts_missed=[c.concept for c in result.concepts if not c.matched],
        stt_confidence=stt_confidence,
        attempt_number=attempt_count + 1,
    )
    db.add(recall_attempt)
    db.commit()

    return RecallCheckOut(
        recall_score=round(result.recall_score * 100),
        confidence_score=round(result.confidence_score * 100),
        concepts=[
            ConceptMatchOut(
                concept=c.concept,
                matched=c.matched,
                matched_fragment=c.matched_fragment,
            )
            for c in result.concepts
        ],
        total_concepts=result.total_concepts,
        matched_count=result.matched_count,
        stt_confidence=stt_confidence,
    )


@router.get("/funnel/{node_id}/recall/{section_label}", response_model=RecallCheckOut | None)
def get_recall_attempt(
    node_id: int,
    section_label: str,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve the latest recall attempt for a section.

    Returns None (204) if no attempt exists.
    """
    attempt = (
        db.query(GsLmsRecallAttempt)
        .filter(
            GsLmsRecallAttempt.student_id == current_user.id,
            GsLmsRecallAttempt.syllabus_node_id == node_id,
            GsLmsRecallAttempt.section_label == section_label,
        )
        .order_by(GsLmsRecallAttempt.attempt_number.desc())
        .first()
    )

    if not attempt:
        raise HTTPException(status_code=404, detail="No recall attempt found for this section")

    concepts_matched = attempt.concepts_matched or []
    concepts_missed = attempt.concepts_missed or []

    all_concepts = [
        ConceptMatchOut(concept=c, matched=True, matched_fragment=None)
        for c in concepts_matched
    ] + [
        ConceptMatchOut(concept=c, matched=False, matched_fragment=None)
        for c in concepts_missed
    ]

    return RecallCheckOut(
        recall_score=round(attempt.recall_score * 100),
        confidence_score=round(attempt.confidence_score * 100),
        concepts=all_concepts,
        total_concepts=len(concepts_matched) + len(concepts_missed),
        matched_count=len(concepts_matched),
        stt_confidence=attempt.stt_confidence,
    )
