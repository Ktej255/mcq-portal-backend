"""MCQ Practice endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms; auth-gated at the package router):
* POST /geography/practice/start — Create a practice session for a topic
* POST /geography/practice/{session_id}/answer — Record answer for current question
* POST /geography/practice/{session_id}/skip — Skip current question
* POST /geography/practice/{session_id}/submit — Finalize and score session

Design properties enforced:
* Property 10 (Sequential MCQ access control): only the current question is
  exposed; advance only after answer/skip.
* Property 11 (MCQ scoring and per-type accuracy): total_score and per-type
  accuracy computed on submission.
* Property 19 (review-gate): only REVIEWED MCQ questions are presented.

Requirements traced: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsMcqQuestion,
)
from app.core.gs_lms.student_models import (
    GsLmsPracticeSession,
    GsLmsPracticeAttempt,
    GsLmsPracticeSessionStatusEnum,
)
from app.core.gs_lms.mcq_scoring import (
    Attempt,
    compute_score,
    compute_type_accuracy,
)
from app.core.gs_lms.coverage import create_gap_snapshot
from app.api.v1.gs_lms.schemas import (
    GsLmsPracticeStartIn,
    GsLmsPracticeSessionOut,
    GsLmsPracticeAnswerIn,
    GsLmsPracticeResultOut,
    GsLmsMcqQuestionOut,
    GsLmsMcqOptionOut,
    GsLmsQuestionTypeAccuracyOut,
    GsLmsPracticeAttemptResultOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session_owned_by(
    db: Session, session_id: int, student_id: int
) -> GsLmsPracticeSession:
    """Retrieve a practice session owned by the student, or raise 404."""
    session = (
        db.query(GsLmsPracticeSession)
        .filter(
            GsLmsPracticeSession.id == session_id,
            GsLmsPracticeSession.student_id == student_id,
        )
        .one_or_none()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return session


def _get_questions_for_session(
    db: Session, syllabus_node_id: int
) -> list[GsLmsMcqQuestion]:
    """Get all REVIEWED MCQ questions for a topic in display order."""
    return (
        db.query(GsLmsMcqQuestion)
        .filter(
            GsLmsMcqQuestion.syllabus_node_id == syllabus_node_id,
            GsLmsMcqQuestion.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(GsLmsMcqQuestion.display_order)
        .all()
    )


def _question_to_out(question: GsLmsMcqQuestion) -> GsLmsMcqQuestionOut:
    """Convert a GsLmsMcqQuestion model to the output schema."""
    question_type_val = (
        question.question_type.value
        if hasattr(question.question_type, "value")
        else str(question.question_type)
    )
    options = question.options or []
    options_out = [
        GsLmsMcqOptionOut(label=opt["label"], text=opt["text"])
        for opt in options
    ]
    return GsLmsMcqQuestionOut(
        question_id=question.id,
        question_text=question.question_text,
        question_type=question_type_val,
        options=options_out,
        display_order=question.display_order,
    )


def _build_session_out(
    session: GsLmsPracticeSession,
    current_question: GsLmsMcqQuestion | None,
) -> GsLmsPracticeSessionOut:
    """Build the session output schema including the current question if any."""
    status_val = (
        session.status.value
        if hasattr(session.status, "value")
        else str(session.status)
    )
    current_q_out = _question_to_out(current_question) if current_question else None
    return GsLmsPracticeSessionOut(
        session_id=session.id,
        syllabus_node_id=session.syllabus_node_id,
        status=status_val,
        total_questions=session.total_questions,
        current_index=session.current_index,
        current_question=current_q_out,
        started_at=session.started_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/geography/practice/start")
def start_practice_session(
    body: GsLmsPracticeStartIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Create a practice session for a topic.

    Queries all REVIEWED MCQ questions for the specified syllabus node,
    creates a GsLmsPracticeSession, and returns the session state with
    the first question exposed.

    Raises 404 if the syllabus node doesn't exist or isn't REVIEWED.
    Raises 422 if no REVIEWED MCQ questions exist for the topic.
    """
    # Validate the syllabus node
    node = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.id == body.syllabus_node_id,
            GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .one_or_none()
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )

    # Get REVIEWED questions for the topic
    questions = _get_questions_for_session(db, body.syllabus_node_id)
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No MCQ questions available for this topic",
        )

    # Create session
    practice_session = GsLmsPracticeSession(
        student_id=current_user.id,
        syllabus_node_id=body.syllabus_node_id,
        status=GsLmsPracticeSessionStatusEnum.IN_PROGRESS,
        total_questions=len(questions),
        current_index=0,
    )
    db.add(practice_session)
    db.commit()
    db.refresh(practice_session)

    # Build output with first question
    first_question = questions[0]
    session_out = _build_session_out(practice_session, first_question)

    return StandardResponse(
        success=True,
        message="Practice session started",
        data=session_out,
    )


@router.post("/geography/practice/{session_id}/answer")
def answer_question(
    session_id: int,
    body: GsLmsPracticeAnswerIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Record the answer for the current question in a practice session.

    Validates session ownership and sequential access (Property 10).
    Records the attempt, checks correctness, and advances the session.

    Raises 404 if session not found or not owned by student.
    Raises 409 if session is already SUBMITTED.
    Raises 422 if session is already COMPLETED (all questions traversed).
    """
    practice_session = _get_session_owned_by(db, session_id, current_user.id)

    # Check session status
    if practice_session.status == GsLmsPracticeSessionStatusEnum.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already submitted",
        )

    if practice_session.status == GsLmsPracticeSessionStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All questions have been answered. Please submit the session.",
        )

    # Get the current question
    questions = _get_questions_for_session(db, practice_session.syllabus_node_id)
    current_index = practice_session.current_index

    if current_index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All questions have been answered. Please submit the session.",
        )

    current_question = questions[current_index]

    # Check correctness
    is_correct = body.chosen_answer.upper() == current_question.correct_option.upper()

    # Determine question type
    question_type = current_question.question_type

    # Record the attempt
    attempt = GsLmsPracticeAttempt(
        session_id=practice_session.id,
        question_id=current_question.id,
        student_id=current_user.id,
        chosen_answer=body.chosen_answer,
        is_correct=is_correct,
        time_taken_seconds=body.time_taken_seconds,
        question_type=question_type,
    )
    db.add(attempt)

    # Advance session
    practice_session.current_index += 1

    # If all questions traversed, mark COMPLETED
    if practice_session.current_index >= practice_session.total_questions:
        practice_session.status = GsLmsPracticeSessionStatusEnum.COMPLETED

    db.commit()
    db.refresh(practice_session)

    # Build attempt result
    question_type_val = (
        question_type.value if hasattr(question_type, "value") else str(question_type)
    )
    attempt_result = GsLmsPracticeAttemptResultOut(
        question_id=current_question.id,
        chosen_answer=body.chosen_answer,
        correct_answer=current_question.correct_option,
        is_correct=is_correct,
        question_type=question_type_val,
        explanation=current_question.explanation,
        time_taken_seconds=body.time_taken_seconds,
    )

    # Build session output with next question (if any)
    next_question = None
    if practice_session.current_index < len(questions):
        next_question = questions[practice_session.current_index]

    session_out = _build_session_out(practice_session, next_question)

    return StandardResponse(
        success=True,
        message="Answer recorded",
        data={
            "session": session_out.model_dump(),
            "attempt_result": attempt_result.model_dump(),
        },
    )


@router.post("/geography/practice/{session_id}/skip")
def skip_question(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Skip the current question in a practice session.

    Similar to answer but sets chosen_answer=None, is_correct=None.
    Validates session ownership and sequential access (Property 10).

    Raises 404 if session not found or not owned by student.
    Raises 409 if session is already SUBMITTED.
    Raises 422 if session is already COMPLETED.
    """
    practice_session = _get_session_owned_by(db, session_id, current_user.id)

    # Check session status
    if practice_session.status == GsLmsPracticeSessionStatusEnum.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already submitted",
        )

    if practice_session.status == GsLmsPracticeSessionStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All questions have been answered. Please submit the session.",
        )

    # Get the current question
    questions = _get_questions_for_session(db, practice_session.syllabus_node_id)
    current_index = practice_session.current_index

    if current_index >= len(questions):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All questions have been answered. Please submit the session.",
        )

    current_question = questions[current_index]

    # Determine question type
    question_type = current_question.question_type

    # Record skip attempt (chosen_answer=None, is_correct=None)
    attempt = GsLmsPracticeAttempt(
        session_id=practice_session.id,
        question_id=current_question.id,
        student_id=current_user.id,
        chosen_answer=None,
        is_correct=None,
        time_taken_seconds=None,
        question_type=question_type,
    )
    db.add(attempt)

    # Advance session
    practice_session.current_index += 1

    # If all questions traversed, mark COMPLETED
    if practice_session.current_index >= practice_session.total_questions:
        practice_session.status = GsLmsPracticeSessionStatusEnum.COMPLETED

    db.commit()
    db.refresh(practice_session)

    # Build session output with next question (if any)
    next_question = None
    if practice_session.current_index < len(questions):
        next_question = questions[practice_session.current_index]

    session_out = _build_session_out(practice_session, next_question)

    return StandardResponse(
        success=True,
        message="Question skipped",
        data=session_out,
    )


@router.post("/geography/practice/{session_id}/submit")
def submit_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Finalize and score a completed practice session.

    Only works if session status is COMPLETED (all questions traversed).
    Scores the session using the mcq_scoring engine, returns results with
    per-type accuracy breakdown.

    Raises 404 if session not found or not owned by student.
    Raises 409 if session already SUBMITTED.
    Raises 422 if not all questions have been answered/skipped yet.
    """
    practice_session = _get_session_owned_by(db, session_id, current_user.id)

    # Check session status
    if practice_session.status == GsLmsPracticeSessionStatusEnum.SUBMITTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session already submitted",
        )

    if practice_session.status == GsLmsPracticeSessionStatusEnum.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Not all questions have been answered or skipped",
        )

    # Get all attempts for this session
    attempts_db = (
        db.query(GsLmsPracticeAttempt)
        .filter(GsLmsPracticeAttempt.session_id == practice_session.id)
        .all()
    )

    # Get questions for explanation data
    questions = _get_questions_for_session(db, practice_session.syllabus_node_id)
    question_map = {q.id: q for q in questions}

    # Convert DB attempts to scoring DTOs
    scoring_attempts = []
    for a in attempts_db:
        question = question_map.get(a.question_id)
        correct_answer = question.correct_option if question else ""
        q_type = a.question_type
        scoring_attempts.append(
            Attempt(
                question_id=a.question_id,
                question_type=q_type,
                chosen_answer=a.chosen_answer,
                correct_answer=correct_answer,
                is_correct=a.is_correct,
                time_taken_seconds=a.time_taken_seconds,
            )
        )

    # Compute scores using the scoring engine
    score = compute_score(scoring_attempts)
    type_accuracies = compute_type_accuracy(scoring_attempts)

    # Mark session as SUBMITTED
    now = datetime.now(timezone.utc)
    practice_session.status = GsLmsPracticeSessionStatusEnum.SUBMITTED
    practice_session.submitted_at = now
    db.commit()
    db.refresh(practice_session)

    # Update gap profile after practice submission (R6.5)
    create_gap_snapshot(db, current_user.id)
    db.commit()

    # Build attempt results output
    attempts_out = []
    for a in attempts_db:
        question = question_map.get(a.question_id)
        q_type_val = (
            a.question_type.value
            if a.question_type and hasattr(a.question_type, "value")
            else str(a.question_type) if a.question_type else ""
        )
        attempts_out.append(
            GsLmsPracticeAttemptResultOut(
                question_id=a.question_id,
                chosen_answer=a.chosen_answer,
                correct_answer=question.correct_option if question else "",
                is_correct=a.is_correct,
                question_type=q_type_val,
                explanation=question.explanation if question else None,
                time_taken_seconds=a.time_taken_seconds,
            )
        )

    # Build type accuracy output
    type_accuracy_out = [
        GsLmsQuestionTypeAccuracyOut(
            question_type=ta.question_type.value,
            total=ta.total,
            correct=ta.correct,
            accuracy=ta.accuracy,
        )
        for ta in type_accuracies
    ]

    correct_count = sum(1 for a in attempts_db if a.is_correct is True)

    result = GsLmsPracticeResultOut(
        session_id=practice_session.id,
        total_questions=practice_session.total_questions,
        correct_count=correct_count,
        score=score,
        attempts=attempts_out,
        type_accuracy=type_accuracy_out,
        submitted_at=now.isoformat(),
    )

    return StandardResponse(
        success=True,
        message="Session submitted and scored",
        data=result,
    )
