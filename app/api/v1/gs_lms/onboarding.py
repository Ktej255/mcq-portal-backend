"""Onboarding endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms; auth-gated at the package router):
* GET /geography/onboarding/status — Current onboarding state
* POST /geography/onboarding/complete — Mark onboarding done

Design Component 9 (Onboarding Service) — three steps:
  1. Welcome + method explanation
  2. Bandwidth selection
  3. First topic assignment

Completion is persisted so returning students skip directly to learning
position (Requirement 9.5).

Requirements traced: 9.1, 9.2, 9.3, 9.4, 9.5
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
from app.core.gs_lms.models import GsLmsSyllabusNode, GsLmsNodeTypeEnum
from app.core.gs_lms.student_models import GsLmsOnboardingStatus
from app.api.v1.gs_lms.schemas import (
    GsLmsOnboardingStatusOut,
    GsLmsOnboardingCompleteIn,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_onboarding_record(
    db: Session, student_id: int
) -> GsLmsOnboardingStatus | None:
    """Retrieve the onboarding record for a student, or None."""
    return (
        db.query(GsLmsOnboardingStatus)
        .filter(GsLmsOnboardingStatus.student_id == student_id)
        .one_or_none()
    )


def _get_first_reviewed_leaf(db: Session) -> GsLmsSyllabusNode | None:
    """Find the first REVIEWED leaf node in the syllabus tree by display_order.

    This serves as the default first topic for onboarding when the student
    doesn't specify one.
    """
    return (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.node_type == GsLmsNodeTypeEnum.LEAF_TOPIC,
            GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(GsLmsSyllabusNode.display_order, GsLmsSyllabusNode.id)
        .first()
    )


def _build_status_out(
    record: GsLmsOnboardingStatus | None, db: Session
) -> GsLmsOnboardingStatusOut:
    """Build the onboarding status response from a DB record (or None)."""
    if record is None:
        return GsLmsOnboardingStatusOut(
            completed=False,
            completed_at=None,
            bandwidth_selected=None,
            first_topic_id=None,
            first_topic_title=None,
        )

    first_topic_title: str | None = None
    if record.first_topic_id is not None:
        node = (
            db.query(GsLmsSyllabusNode)
            .filter(GsLmsSyllabusNode.id == record.first_topic_id)
            .one_or_none()
        )
        if node is not None:
            first_topic_title = node.title

    completed_at_str: str | None = None
    if record.completed_at is not None:
        completed_at_str = record.completed_at.isoformat()

    return GsLmsOnboardingStatusOut(
        completed=record.completed,
        completed_at=completed_at_str,
        bandwidth_selected=record.bandwidth_selected,
        first_topic_id=record.first_topic_id,
        first_topic_title=first_topic_title,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/geography/onboarding/status")
def get_onboarding_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the current onboarding state for the authenticated student.

    If the student has never started onboarding, returns completed=False
    with no bandwidth or first topic set.
    """
    record = _get_onboarding_record(db, current_user.id)
    data = _build_status_out(record, db)

    return StandardResponse(
        success=True,
        message="Onboarding status retrieved",
        data=data,
    )


@router.post("/geography/onboarding/complete")
def complete_onboarding(
    payload: GsLmsOnboardingCompleteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Mark onboarding as complete with bandwidth selection and first topic.

    Accepts the student's bandwidth choice and an optional first_topic_id.
    If first_topic_id is not provided, defaults to the first REVIEWED leaf
    node in the syllabus tree (by display_order).

    Idempotent: if already completed, returns success without modification.

    Requirements: 9.1, 9.2, 9.3, 9.5
    """
    record = _get_onboarding_record(db, current_user.id)

    # Idempotent: already completed → return current state
    if record is not None and record.completed:
        data = _build_status_out(record, db)
        return StandardResponse(
            success=True,
            message="Onboarding already completed",
            data=data,
        )

    # Resolve the first topic
    first_topic_id = payload.first_topic_id
    if first_topic_id is not None:
        # Validate that the specified topic exists and is a REVIEWED leaf
        topic = (
            db.query(GsLmsSyllabusNode)
            .filter(
                GsLmsSyllabusNode.id == first_topic_id,
                GsLmsSyllabusNode.node_type == GsLmsNodeTypeEnum.LEAF_TOPIC,
                GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
            )
            .one_or_none()
        )
        if topic is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Specified first topic not found or not a reviewed leaf topic",
            )
    else:
        # Default to the first reviewed leaf node
        default_topic = _get_first_reviewed_leaf(db)
        first_topic_id = default_topic.id if default_topic else None

    now = datetime.now(timezone.utc)

    if record is None:
        # Create new onboarding record
        record = GsLmsOnboardingStatus(
            student_id=current_user.id,
            completed=True,
            completed_at=now,
            bandwidth_selected=payload.bandwidth,
            first_topic_id=first_topic_id,
        )
        db.add(record)
    else:
        # Update existing record (was created but not completed)
        record.completed = True
        record.completed_at = now
        record.bandwidth_selected = payload.bandwidth
        record.first_topic_id = first_topic_id

    db.commit()
    db.refresh(record)

    data = _build_status_out(record, db)
    return StandardResponse(
        success=True,
        message="Onboarding completed successfully",
        data=data,
    )
