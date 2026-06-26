"""Spaced revisit endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at the package router):
* GET /revisits/due — Return today's due revisits for the current student
* POST /revisits/{revisit_id}/complete — Mark a revisit as completed

Requirements traced: 4.2, 4.4
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsSubject
from app.core.gs_lms.models import GsLmsSyllabusNode
from app.core.gs_lms.student_models import GsLmsRevisitSchedule
from app.api.v1.gs_lms.dependencies import resolve_subject

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class GsLmsRevisitItemOut(BaseModel):
    """A single revisit item due for review."""

    id: int
    syllabus_node_id: int
    title: str
    due_date: str  # ISO date (YYYY-MM-DD)
    revisit_type: str  # "day_3" | "day_7" | "day_21"
    overdue: bool


class GsLmsRevisitDueOut(BaseModel):
    """Response for the due revisits endpoint."""

    total: int
    revisits: list[GsLmsRevisitItemOut] = []


class GsLmsRevisitCompleteOut(BaseModel):
    """Response after marking a revisit as completed."""

    id: int
    syllabus_node_id: int
    revisit_type: str
    completed: bool
    completed_at: str  # ISO 8601


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/revisits/due")
def get_due_revisits(
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return today's due revisits for the current student.

    Queries GsLmsRevisitSchedule where:
    - student_id = current_user.id
    - due_date <= today
    - completed = False

    Ordered by due_date ASC (oldest first).

    Validates: Requirements 4.2, 4.5
    """
    today = date.today()

    revisits = (
        db.query(GsLmsRevisitSchedule)
        .filter(
            GsLmsRevisitSchedule.student_id == current_user.id,
            GsLmsRevisitSchedule.due_date <= today,
            GsLmsRevisitSchedule.completed == False,
        )
        .order_by(GsLmsRevisitSchedule.due_date.asc())
        .all()
    )

    # Build response items, joining node title
    items: list[GsLmsRevisitItemOut] = []
    for revisit in revisits:
        # Fetch the syllabus node title
        node = (
            db.query(GsLmsSyllabusNode)
            .filter(GsLmsSyllabusNode.id == revisit.syllabus_node_id)
            .one_or_none()
        )
        title = node.title if node else "Unknown Topic"

        items.append(
            GsLmsRevisitItemOut(
                id=revisit.id,
                syllabus_node_id=revisit.syllabus_node_id,
                title=title,
                due_date=revisit.due_date.isoformat(),
                revisit_type=revisit.revisit_type,
                overdue=revisit.due_date < today,
            )
        )

    return StandardResponse(
        success=True,
        message="Due revisits retrieved",
        data=GsLmsRevisitDueOut(
            total=len(items),
            revisits=items,
        ),
    )


@router.post("/revisits/{revisit_id}/complete")
def complete_revisit(
    revisit_id: int,
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Mark a revisit as completed.

    Finds the revisit by ID, verifies ownership (student_id matches),
    sets completed = True and completed_at = now().

    Returns 404 if not found or not owned by the current user.

    Validates: Requirements 4.4
    """
    revisit = (
        db.query(GsLmsRevisitSchedule)
        .filter(
            GsLmsRevisitSchedule.id == revisit_id,
            GsLmsRevisitSchedule.student_id == current_user.id,
        )
        .one_or_none()
    )

    if revisit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revisit not found",
        )

    now = datetime.now(timezone.utc)
    revisit.completed = True
    revisit.completed_at = now
    db.commit()

    return StandardResponse(
        success=True,
        message="Revisit marked as completed",
        data=GsLmsRevisitCompleteOut(
            id=revisit.id,
            syllabus_node_id=revisit.syllabus_node_id,
            revisit_type=revisit.revisit_type,
            completed=True,
            completed_at=now.isoformat(),
        ),
    )
