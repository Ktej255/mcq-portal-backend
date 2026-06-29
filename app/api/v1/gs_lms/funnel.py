"""Funnel Progress endpoints for the Interactive Learning Funnel.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at package router):
* GET /funnel/{node_id}/state — Get current funnel state for a topic
* POST /funnel/{node_id}/complete-step — Mark a step as complete
* POST /funnel/{node_id}/reading-time — Submit reading time for a section

Requirements traced: 1.4, 1.6, 3.3, 3.5, 13.2, 13.7
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.gs.models import GsSubject
from app.core.gs_lms.models import GsLmsSyllabusNode
from app.core.gs_lms.funnel_models import GsLmsReadingTime
from app.core.gs_lms.funnel_engine import (
    get_funnel_state,
    complete_step,
    StepNotReachableError,
    StepAlreadyCompletedError,
    TOTAL_STEPS,
)
from app.api.v1.gs_lms.dependencies import resolve_subject


router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FunnelStateOut(BaseModel):
    node_id: int
    current_step: int
    completed_steps: List[int]
    started_at: str | None
    last_activity_at: str | None

    class Config:
        from_attributes = True


class CompleteStepIn(BaseModel):
    step: int = Field(..., ge=1, le=14, description="Step number to mark complete (1-14)")


class ReadingTimeIn(BaseModel):
    section_id: int = Field(..., description="Content section ID")
    duration_seconds: int = Field(..., ge=1, le=7200, description="Reading time in seconds (1-7200)")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/funnel/{node_id}/state", response_model=FunnelStateOut)
def get_funnel_state_endpoint(
    node_id: int,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current funnel progress state for a student on a topic."""
    # Verify node exists
    node = db.query(GsLmsSyllabusNode).filter(
        GsLmsSyllabusNode.id == node_id,
        GsLmsSyllabusNode.subject_id == subject.id,
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="Topic node not found")

    state = get_funnel_state(db, current_user.id, node_id)

    return FunnelStateOut(
        node_id=node_id,
        current_step=min(state.current_step, TOTAL_STEPS),
        completed_steps=sorted(state.completed_steps),
        started_at=state.started_at.isoformat() if state.started_at else None,
        last_activity_at=state.last_activity_at.isoformat() if state.last_activity_at else None,
    )


@router.post("/funnel/{node_id}/complete-step", response_model=FunnelStateOut)
def complete_funnel_step(
    node_id: int,
    body: CompleteStepIn,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a funnel step as complete and advance to the next step.

    The step must be the current active step — out-of-order completions
    are rejected with 409.
    """
    # Verify node exists
    node = db.query(GsLmsSyllabusNode).filter(
        GsLmsSyllabusNode.id == node_id,
        GsLmsSyllabusNode.subject_id == subject.id,
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="Topic node not found")

    try:
        state = complete_step(db, current_user.id, node_id, body.step)
        db.commit()
    except StepNotReachableError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except StepAlreadyCompletedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return FunnelStateOut(
        node_id=node_id,
        current_step=min(state.current_step, TOTAL_STEPS),
        completed_steps=sorted(state.completed_steps),
        started_at=state.started_at.isoformat() if state.started_at else None,
        last_activity_at=state.last_activity_at.isoformat() if state.last_activity_at else None,
    )


@router.post("/funnel/{node_id}/reading-time", status_code=204)
def submit_reading_time(
    node_id: int,
    body: ReadingTimeIn,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit accumulated reading time for a content section.

    Validates duration is between 1 and 7200 seconds. Adds to cumulative
    total (capped at 7200). Creates or updates the reading time record.
    """
    # Validate section belongs to the node
    from app.core.gs_lms.models import GsLmsContentSection
    section = db.query(GsLmsContentSection).filter(
        GsLmsContentSection.id == body.section_id,
        GsLmsContentSection.syllabus_node_id == node_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found for this topic")

    # Find or create reading time record
    existing = db.query(GsLmsReadingTime).filter(
        GsLmsReadingTime.student_id == current_user.id,
        GsLmsReadingTime.section_id == body.section_id,
    ).first()

    now = datetime.now(timezone.utc)

    if existing:
        # Add to cumulative total, capped at 7200
        new_total = min(7200, existing.duration_seconds + body.duration_seconds)
        existing.duration_seconds = new_total
        existing.last_updated_at = now
    else:
        reading_time = GsLmsReadingTime(
            student_id=current_user.id,
            syllabus_node_id=node_id,
            section_id=body.section_id,
            duration_seconds=min(7200, body.duration_seconds),
            last_updated_at=now,
        )
        db.add(reading_time)

    db.commit()
