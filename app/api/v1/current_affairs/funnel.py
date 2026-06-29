"""CA Funnel endpoints — per-item learning funnel + MCQ submission.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 14.4
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.current_affairs.ca_models import CAItem, CAStudentProgress
from app.core.current_affairs.ca_funnel_adapter import (
    get_ca_funnel_state,
    complete_ca_funnel_step,
    get_ca_mcqs,
    get_ca_mains_questions,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CAFunnelStateOut(BaseModel):
    item_id: int
    current_step: int
    completed_steps: List[int]
    video_available: bool
    is_completed: bool
    started_at: str | None
    last_activity_at: str | None


class CompleteStepIn(BaseModel):
    step: int = Field(..., ge=1, le=5)


class CAMcqOut(BaseModel):
    id: int
    question_text: str
    question_type: str
    options: list
    display_order: int


class CAMcqAnswerIn(BaseModel):
    answers: dict  # {question_id: chosen_answer}


class CAMcqResultOut(BaseModel):
    total_questions: int
    correct_count: int
    score: float
    attempts: list


class CAMainsQuestionOut(BaseModel):
    id: int
    question_text: str
    gs_paper: str
    marks: int
    word_limit: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/items/{item_id}/funnel/state", response_model=CAFunnelStateOut)
def get_funnel_state(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get or initialize funnel state for a CA item."""
    item = db.query(CAItem).filter(
        CAItem.id == item_id,
        CAItem.review_status == "PUBLISHED",
        CAItem.is_deleted == False,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    state = get_ca_funnel_state(db, current_user.id, item_id)

    return CAFunnelStateOut(
        item_id=item_id,
        current_step=state.current_step,
        completed_steps=sorted(state.completed_steps),
        video_available=state.video_available,
        is_completed=state.is_completed,
        started_at=state.started_at.isoformat() if state.started_at else None,
        last_activity_at=state.last_activity_at.isoformat() if state.last_activity_at else None,
    )


@router.post("/items/{item_id}/funnel/complete-step", response_model=CAFunnelStateOut)
def complete_step(
    item_id: int,
    body: CompleteStepIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a CA funnel step as complete. Idempotent for already-completed steps."""
    item = db.query(CAItem).filter(
        CAItem.id == item_id,
        CAItem.review_status == "PUBLISHED",
        CAItem.is_deleted == False,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        state = complete_ca_funnel_step(db, current_user.id, item_id, body.step)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return CAFunnelStateOut(
        item_id=item_id,
        current_step=state.current_step,
        completed_steps=sorted(state.completed_steps),
        video_available=state.video_available,
        is_completed=state.is_completed,
        started_at=state.started_at.isoformat() if state.started_at else None,
        last_activity_at=state.last_activity_at.isoformat() if state.last_activity_at else None,
    )


@router.get("/items/{item_id}/mcqs", response_model=List[CAMcqOut])
def get_mcqs(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get MCQs attached to a CA item (up to 10)."""
    mcqs = get_ca_mcqs(db, item_id)
    return [
        CAMcqOut(
            id=m.id,
            question_text=m.question_text,
            question_type=m.question_type,
            options=m.options or [],
            display_order=m.display_order,
        )
        for m in mcqs
    ]


@router.post("/items/{item_id}/mcqs/submit", response_model=CAMcqResultOut)
def submit_mcqs(
    item_id: int,
    body: CAMcqAnswerIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit MCQ answers for a CA item. All-or-nothing scoring."""
    mcqs = get_ca_mcqs(db, item_id)
    if not mcqs:
        raise HTTPException(status_code=404, detail="No MCQs for this item")

    mcq_map = {m.id: m for m in mcqs}
    attempts = []
    correct_count = 0

    for qid_str, chosen in body.answers.items():
        qid = int(qid_str)
        mcq = mcq_map.get(qid)
        if not mcq:
            continue
        is_correct = chosen.strip().upper() == mcq.correct_answer.strip().upper()
        if is_correct:
            correct_count += 1
        attempts.append({
            "question_id": qid,
            "chosen_answer": chosen,
            "correct_answer": mcq.correct_answer,
            "is_correct": is_correct,
            "question_type": mcq.question_type,
            "explanation": mcq.explanation,
        })

    total = len(attempts)
    score = (correct_count / total * 100) if total > 0 else 0

    # Update student progress with MCQ score
    progress = db.query(CAStudentProgress).filter(
        CAStudentProgress.student_id == current_user.id,
        CAStudentProgress.ca_item_id == item_id,
    ).first()
    if progress:
        progress.mcq_score = score / 100
        progress.mcq_attempts = attempts
        progress.last_activity_at = datetime.now(timezone.utc)
    db.commit()

    return CAMcqResultOut(
        total_questions=total,
        correct_count=correct_count,
        score=round(score, 1),
        attempts=attempts,
    )


@router.get("/items/{item_id}/mains", response_model=List[CAMainsQuestionOut])
def get_mains_questions(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get Mains questions attached to a CA item (up to 3)."""
    questions = get_ca_mains_questions(db, item_id)
    return [
        CAMainsQuestionOut(
            id=q.id,
            question_text=q.question_text,
            gs_paper=q.gs_paper,
            marks=q.marks,
            word_limit=q.word_limit,
        )
        for q in questions
    ]
