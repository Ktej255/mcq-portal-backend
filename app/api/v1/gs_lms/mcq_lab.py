"""MCQ Lab endpoints for the Interactive Learning Funnel.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at package router):
* GET /funnel/{node_id}/mcq-lab/questions — Get 15 MCQ Lab questions
* POST /funnel/{node_id}/mcq-lab/submit — Submit all 15 answers (bulk)
* GET /funnel/{node_id}/mcq-lab/result — Get latest MCQ Lab result

Requirements traced: 6.1, 6.2, 6.4, 6.5, 6.6, 6.7, 7.1, 7.2, 14.4
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.gs.models import GsSubject, GsReviewStatusEnum
from app.core.gs_lms.models import GsLmsSyllabusNode, GsLmsMcqQuestion
from app.core.gs_lms.funnel_models import (
    GsLmsMcqLabSession,
    GsLmsMcqLabAttempt,
    GsLmsWeaknessPattern,
)
from app.core.gs_lms.mcq_lab_scoring import (
    REQUIRED_TYPE_DISTRIBUTION,
    TOTAL_MCQ_LAB_QUESTIONS,
    create_attempt,
    score_mcq_lab,
    WEAKNESS_THRESHOLD,
    WEAKNESS_MIN_ATTEMPTS,
)
from app.api.v1.gs_lms.dependencies import resolve_subject


router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class McqLabOptionOut(BaseModel):
    label: str
    text: str


class McqLabQuestionOut(BaseModel):
    question_id: int
    question_type: str
    question_text: str
    statements: List[str] = []
    options: List[McqLabOptionOut]
    display_order: int


class McqLabAnswerIn(BaseModel):
    question_id: int
    chosen_answer: str
    time_taken_seconds: float | None = None


class McqLabSubmitIn(BaseModel):
    answers: List[McqLabAnswerIn] = Field(..., min_length=15, max_length=15)


class McqLabAttemptOut(BaseModel):
    question_id: int
    chosen_answer: str
    correct_answer: str
    is_correct: bool
    question_type: str
    explanation: str | None = None


class McqLabTypeBreakdownOut(BaseModel):
    question_type: str
    total: int
    correct: int
    accuracy: float


class McqLabResultOut(BaseModel):
    total_questions: int
    correct_count: int
    score: float  # 0-100 percentage
    attempts: List[McqLabAttemptOut]
    type_breakdown: List[McqLabTypeBreakdownOut]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/funnel/{node_id}/mcq-lab/questions", response_model=List[McqLabQuestionOut])
def get_mcq_lab_questions(
    node_id: int,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get 15 MCQ Lab questions for a topic with required type distribution.

    Selects questions per REQUIRED_TYPE_DISTRIBUTION (7 UPSC types, total 15).
    Only REVIEWED questions are included. Shuffles for random presentation order.
    """
    node = db.query(GsLmsSyllabusNode).filter(
        GsLmsSyllabusNode.id == node_id,
        GsLmsSyllabusNode.subject_id == subject.id,
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="Topic node not found")

    # Get all reviewed questions for this topic
    all_questions = (
        db.query(GsLmsMcqQuestion)
        .filter(
            GsLmsMcqQuestion.syllabus_node_id == node_id,
            GsLmsMcqQuestion.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .all()
    )

    # Group by question type
    by_type: Dict[str, list] = {}
    for q in all_questions:
        qtype = q.question_type.value if hasattr(q.question_type, 'value') else str(q.question_type)
        by_type.setdefault(qtype, []).append(q)

    # Select per distribution
    selected: list = []
    overflow: list = []

    for required_type, count in REQUIRED_TYPE_DISTRIBUTION.items():
        available = by_type.get(required_type, [])
        if len(available) >= count:
            selected.extend(random.sample(available, count))
        else:
            selected.extend(available)
            # Track deficit
            deficit = count - len(available)
            overflow.append(deficit)

    # Fill any deficit from types with excess
    if len(selected) < TOTAL_MCQ_LAB_QUESTIONS:
        remaining_needed = TOTAL_MCQ_LAB_QUESTIONS - len(selected)
        selected_ids = {q.id for q in selected}
        extras = [q for q in all_questions if q.id not in selected_ids]
        random.shuffle(extras)
        selected.extend(extras[:remaining_needed])

    # Shuffle final selection
    random.shuffle(selected)

    return [
        McqLabQuestionOut(
            question_id=q.id,
            question_type=q.question_type.value if hasattr(q.question_type, 'value') else str(q.question_type),
            question_text=q.question_text,
            statements=[],  # Statements extracted from question_text if needed
            options=[McqLabOptionOut(label=opt["label"], text=opt["text"]) for opt in (q.options or [])],
            display_order=idx + 1,
        )
        for idx, q in enumerate(selected)
    ]


@router.post("/funnel/{node_id}/mcq-lab/submit", response_model=McqLabResultOut)
def submit_mcq_lab(
    node_id: int,
    body: McqLabSubmitIn,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit all 15 MCQ Lab answers in bulk.

    Validates all 15 answers are present, scores with all-or-nothing model,
    updates weakness pattern, and persists session + attempts.
    """
    node = db.query(GsLmsSyllabusNode).filter(
        GsLmsSyllabusNode.id == node_id,
        GsLmsSyllabusNode.subject_id == subject.id,
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="Topic node not found")

    if len(body.answers) != TOTAL_MCQ_LAB_QUESTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Expected {TOTAL_MCQ_LAB_QUESTIONS} answers, got {len(body.answers)}"
        )

    # Fetch questions to validate and get correct answers
    question_ids = [a.question_id for a in body.answers]
    questions = db.query(GsLmsMcqQuestion).filter(
        GsLmsMcqQuestion.id.in_(question_ids)
    ).all()
    question_map = {q.id: q for q in questions}

    if len(question_map) != len(question_ids):
        raise HTTPException(status_code=422, detail="Some question IDs are invalid")

    # Create attempts with all-or-nothing scoring
    attempts = []
    for answer in body.answers:
        question = question_map[answer.question_id]
        qtype = question.question_type.value if hasattr(question.question_type, 'value') else str(question.question_type)
        attempt = create_attempt(
            question_id=answer.question_id,
            question_type=qtype,
            chosen_answer=answer.chosen_answer,
            correct_answer=question.correct_option,
            time_taken_seconds=answer.time_taken_seconds,
        )
        attempts.append(attempt)

    # Score the session
    result = score_mcq_lab(attempts)
    now = datetime.now(timezone.utc)

    # Persist session
    session = GsLmsMcqLabSession(
        student_id=current_user.id,
        syllabus_node_id=node_id,
        total_questions=result.total_questions,
        correct_count=result.correct_count,
        score=result.score,
        submitted_at=now,
    )
    db.add(session)
    db.flush()

    # Persist individual attempts
    for attempt in result.attempts:
        db_attempt = GsLmsMcqLabAttempt(
            session_id=session.id,
            question_id=attempt.question_id,
            question_type=attempt.question_type,
            chosen_answer=attempt.chosen_answer,
            correct_answer=attempt.correct_answer,
            is_correct=attempt.is_correct,
            time_taken_seconds=attempt.time_taken_seconds,
        )
        db.add(db_attempt)

    # Update weakness patterns (same transaction)
    for breakdown in result.type_breakdown:
        pattern = db.query(GsLmsWeaknessPattern).filter(
            GsLmsWeaknessPattern.student_id == current_user.id,
            GsLmsWeaknessPattern.question_type == breakdown.question_type,
        ).first()

        if pattern:
            pattern.total_attempts += breakdown.total
            pattern.correct_count += breakdown.correct
            pattern.accuracy = pattern.correct_count / pattern.total_attempts if pattern.total_attempts > 0 else 0.0
            pattern.is_weak = (
                pattern.accuracy < WEAKNESS_THRESHOLD
                and pattern.total_attempts >= WEAKNESS_MIN_ATTEMPTS
            )
            pattern.last_updated_at = now
        else:
            accuracy = breakdown.correct / breakdown.total if breakdown.total > 0 else 0.0
            pattern = GsLmsWeaknessPattern(
                student_id=current_user.id,
                question_type=breakdown.question_type,
                total_attempts=breakdown.total,
                correct_count=breakdown.correct,
                accuracy=accuracy,
                is_weak=(accuracy < WEAKNESS_THRESHOLD and breakdown.total >= WEAKNESS_MIN_ATTEMPTS),
                last_updated_at=now,
            )
            db.add(pattern)

    db.commit()

    # Build response
    return McqLabResultOut(
        total_questions=result.total_questions,
        correct_count=result.correct_count,
        score=round(result.score * 100, 1),
        attempts=[
            McqLabAttemptOut(
                question_id=a.question_id,
                chosen_answer=a.chosen_answer,
                correct_answer=a.correct_answer,
                is_correct=a.is_correct,
                question_type=a.question_type,
                explanation=question_map.get(a.question_id, None) and question_map[a.question_id].explanation,
            )
            for a in result.attempts
        ],
        type_breakdown=[
            McqLabTypeBreakdownOut(
                question_type=tb.question_type,
                total=tb.total,
                correct=tb.correct,
                accuracy=round(tb.accuracy * 100, 1),
            )
            for tb in result.type_breakdown
        ],
    )


@router.get("/funnel/{node_id}/mcq-lab/result", response_model=McqLabResultOut | None)
def get_mcq_lab_result(
    node_id: int,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the latest MCQ Lab result for a topic."""
    session = (
        db.query(GsLmsMcqLabSession)
        .filter(
            GsLmsMcqLabSession.student_id == current_user.id,
            GsLmsMcqLabSession.syllabus_node_id == node_id,
            GsLmsMcqLabSession.submitted_at.isnot(None),
        )
        .order_by(GsLmsMcqLabSession.submitted_at.desc())
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="No MCQ Lab result found")

    # Load attempts
    attempts = (
        db.query(GsLmsMcqLabAttempt)
        .filter(GsLmsMcqLabAttempt.session_id == session.id)
        .all()
    )

    # Fetch questions for explanations
    question_ids = [a.question_id for a in attempts]
    questions = db.query(GsLmsMcqQuestion).filter(
        GsLmsMcqQuestion.id.in_(question_ids)
    ).all()
    question_map = {q.id: q for q in questions}

    # Compute type breakdown
    type_stats: Dict[str, tuple[int, int]] = {}
    for a in attempts:
        correct, total = type_stats.get(a.question_type, (0, 0))
        total += 1
        if a.is_correct:
            correct += 1
        type_stats[a.question_type] = (correct, total)

    return McqLabResultOut(
        total_questions=session.total_questions,
        correct_count=session.correct_count or 0,
        score=round((session.score or 0) * 100, 1),
        attempts=[
            McqLabAttemptOut(
                question_id=a.question_id,
                chosen_answer=a.chosen_answer,
                correct_answer=a.correct_answer,
                is_correct=a.is_correct,
                question_type=a.question_type,
                explanation=question_map.get(a.question_id) and question_map[a.question_id].explanation,
            )
            for a in attempts
        ],
        type_breakdown=[
            McqLabTypeBreakdownOut(
                question_type=qtype,
                total=total,
                correct=correct,
                accuracy=round((correct / total * 100) if total > 0 else 0, 1),
            )
            for qtype, (correct, total) in sorted(type_stats.items())
        ],
    )
