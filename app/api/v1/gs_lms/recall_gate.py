"""Day-start recall gate endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at package router):
* GET  /recall-gate       — Check if yesterday's topic needs recall before today
* POST /recall-gate/clear — Clear today's recall gate after successful recall

The recall gate ensures spaced repetition by requiring a lightweight recall of
yesterday's (or most recently completed) topic before new content unlocks.

Requirements traced: 5.1, 5.2, 5.4
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsSubject
from app.core.gs_lms.models import GsLmsSyllabusNode, GsLmsNodeTypeEnum
from app.core.gs_lms.student_models import (
    GsLmsStudentSectionProgress,
    GsLmsRevisitSchedule,
)
from app.api.v1.gs_lms.dependencies import resolve_subject

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RecallGateOut(BaseModel):
    recall_needed: bool
    topic_id: Optional[int] = None
    topic_title: Optional[str] = None
    concepts: Optional[list[str]] = None


class RecallGateClearIn(BaseModel):
    topic_id: int


class RecallGateClearOut(BaseModel):
    cleared: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECTIONS_PER_LEAF = 4


def _find_most_recently_completed_topic(
    db: Session, student_id: int, subject_id: int
) -> Optional[GsLmsSyllabusNode]:
    """Find the student's most recently completed topic for this subject.

    A topic is considered completed when all 4 sections have been marked
    complete. We find the topic whose last section was completed most recently.
    """
    from sqlalchemy import and_

    # Subquery: for each syllabus_node_id, count completed sections and find
    # the latest completed_at timestamp.
    completion_info = (
        db.query(
            GsLmsStudentSectionProgress.syllabus_node_id,
            func.count(GsLmsStudentSectionProgress.id).label("completed_count"),
            func.max(GsLmsStudentSectionProgress.completed_at).label("last_completed"),
        )
        .filter(
            GsLmsStudentSectionProgress.student_id == student_id,
            GsLmsStudentSectionProgress.completed == True,  # noqa: E712
        )
        .group_by(GsLmsStudentSectionProgress.syllabus_node_id)
        .subquery()
    )

    # Join with syllabus nodes to filter by subject and get only fully
    # completed topics (4 sections done).
    result = (
        db.query(GsLmsSyllabusNode)
        .join(
            completion_info,
            and_(
                GsLmsSyllabusNode.id == completion_info.c.syllabus_node_id,
                completion_info.c.completed_count >= _SECTIONS_PER_LEAF,
            ),
        )
        .filter(
            GsLmsSyllabusNode.subject_id == subject_id,
            GsLmsSyllabusNode.node_type == GsLmsNodeTypeEnum.LEAF_TOPIC,
        )
        .order_by(completion_info.c.last_completed.desc())
        .first()
    )

    return result


def _was_completed_within_24h(
    db: Session, student_id: int, node_id: int
) -> bool:
    """Check if the topic was completed within the last 24 hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    latest_completion = (
        db.query(func.max(GsLmsStudentSectionProgress.completed_at))
        .filter(
            GsLmsStudentSectionProgress.student_id == student_id,
            GsLmsStudentSectionProgress.syllabus_node_id == node_id,
            GsLmsStudentSectionProgress.completed == True,  # noqa: E712
        )
        .scalar()
    )

    if latest_completion is None:
        return False

    # Handle both naive and aware datetimes
    if latest_completion.tzinfo is None:
        latest_completion = latest_completion.replace(tzinfo=timezone.utc)

    return latest_completion >= cutoff


def _has_recall_done_today(
    db: Session, student_id: int, node_id: int
) -> bool:
    """Check if the student already cleared the recall gate for this topic today."""
    today = date.today()

    existing = (
        db.query(GsLmsRevisitSchedule)
        .filter(
            GsLmsRevisitSchedule.student_id == student_id,
            GsLmsRevisitSchedule.syllabus_node_id == node_id,
            GsLmsRevisitSchedule.revisit_type == "day_start",
            GsLmsRevisitSchedule.due_date == today,
            GsLmsRevisitSchedule.completed == True,  # noqa: E712
        )
        .first()
    )

    return existing is not None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/recall-gate")
def check_recall_gate(
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Check if recall is needed before today's content.

    Finds the student's most recently completed topic. If that topic was
    completed within the last 24 hours (yesterday or earlier today) and the
    student has NOT yet done a day-start recall for it today, returns
    recall_needed=true with topic info and first 3 concepts from the checklist.

    Requirements: 5.1, 5.2, 5.5
    """
    topic = _find_most_recently_completed_topic(
        db, current_user.id, subject.id
    )

    # No completed topic exists → no recall needed (Requirement 5.5)
    if topic is None:
        return StandardResponse(
            success=True,
            message="No recall needed",
            data=RecallGateOut(recall_needed=False),
        )

    # Check if it was completed within the last 24 hours
    if not _was_completed_within_24h(db, current_user.id, topic.id):
        return StandardResponse(
            success=True,
            message="No recall needed",
            data=RecallGateOut(recall_needed=False),
        )

    # Check if recall already done today
    if _has_recall_done_today(db, current_user.id, topic.id):
        return StandardResponse(
            success=True,
            message="Recall already completed today",
            data=RecallGateOut(recall_needed=False),
        )

    # Recall is needed — return topic info and first 3 concepts
    concepts = None
    if topic.concept_checklist:
        concepts = topic.concept_checklist[:3]

    return StandardResponse(
        success=True,
        message="Recall needed before today's content",
        data=RecallGateOut(
            recall_needed=True,
            topic_id=topic.id,
            topic_title=topic.title,
            concepts=concepts,
        ),
    )


@router.post("/recall-gate/clear")
def clear_recall_gate(
    body: RecallGateClearIn,
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Clear today's recall gate for a given topic.

    Creates a GsLmsRevisitSchedule record with revisit_type='day_start',
    due_date=today, completed=True, completed_at=now to mark the recall
    as done.

    Requirements: 5.4
    """
    today = date.today()
    now = datetime.now(timezone.utc)

    # Check if already cleared today (idempotent)
    existing = (
        db.query(GsLmsRevisitSchedule)
        .filter(
            GsLmsRevisitSchedule.student_id == current_user.id,
            GsLmsRevisitSchedule.syllabus_node_id == body.topic_id,
            GsLmsRevisitSchedule.revisit_type == "day_start",
            GsLmsRevisitSchedule.due_date == today,
        )
        .first()
    )

    if existing:
        # Update to completed if not already
        if not existing.completed:
            existing.completed = True
            existing.completed_at = now
            db.commit()
    else:
        # Use merge/upsert pattern to avoid unique constraint violations:
        # Delete any prior day_start record for this topic (from previous days)
        # and insert a fresh one for today.
        db.query(GsLmsRevisitSchedule).filter(
            GsLmsRevisitSchedule.student_id == current_user.id,
            GsLmsRevisitSchedule.syllabus_node_id == body.topic_id,
            GsLmsRevisitSchedule.revisit_type == "day_start",
        ).delete(synchronize_session=False)

        # Create a new day-start recall record for today
        record = GsLmsRevisitSchedule(
            student_id=current_user.id,
            syllabus_node_id=body.topic_id,
            due_date=today,
            revisit_type="day_start",
            completed=True,
            completed_at=now,
        )
        db.add(record)
        db.commit()

    return StandardResponse(
        success=True,
        message="Recall gate cleared",
        data=RecallGateClearOut(cleared=True),
    )
