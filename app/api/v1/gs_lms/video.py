"""Video watch tracking endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at the package router):
* POST /topics/{node_id}/video/watched — Mark video as watched
* GET /topics/{node_id}/video/status — Get video watch status

Requirements traced: 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsSubject
from app.core.gs_lms.models import GsLmsSyllabusNode
from app.core.gs_lms.student_models import GsLmsVideoWatch
from app.api.v1.gs_lms.dependencies import resolve_subject

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------


class VideoWatchedIn(BaseModel):
    """Optional body when marking a video as watched."""

    model_config = {"extra": "forbid"}

    duration_seconds: Optional[float] = None


class VideoWatchedOut(BaseModel):
    """Response after marking a video as watched."""

    watched: bool
    watched_at: str  # ISO 8601


class VideoStatusOut(BaseModel):
    """Video watch status for the current student."""

    watched: bool
    watched_at: Optional[str] = None  # ISO 8601
    duration_seconds: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_node_or_404(db: Session, node_id: int) -> GsLmsSyllabusNode:
    """Fetch a syllabus node by ID or raise 404."""
    node = (
        db.query(GsLmsSyllabusNode)
        .filter(GsLmsSyllabusNode.id == node_id)
        .one_or_none()
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )
    return node


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/topics/{node_id}/video/watched")
def mark_video_watched(
    node_id: int,
    body: Optional[VideoWatchedIn] = None,
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Mark a topic's video as watched for the current student.

    Creates or updates the GsLmsVideoWatch record (upsert on the unique
    constraint student_id + syllabus_node_id).

    Validates: Requirements 1.3, 1.5
    """
    _get_node_or_404(db, node_id)

    now = datetime.now(timezone.utc)
    duration = body.duration_seconds if body else None

    # Upsert: check for existing watch record
    existing = (
        db.query(GsLmsVideoWatch)
        .filter(
            GsLmsVideoWatch.student_id == current_user.id,
            GsLmsVideoWatch.syllabus_node_id == node_id,
        )
        .one_or_none()
    )

    if existing:
        # Update existing record
        existing.watched_at = now
        if duration is not None:
            existing.watch_duration_seconds = duration
    else:
        # Create new record
        watch = GsLmsVideoWatch(
            student_id=current_user.id,
            syllabus_node_id=node_id,
            watched_at=now,
            watch_duration_seconds=duration,
        )
        db.add(watch)

    db.commit()

    return StandardResponse(
        success=True,
        message="Video marked as watched",
        data=VideoWatchedOut(
            watched=True,
            watched_at=now.isoformat(),
        ),
    )


@router.get("/topics/{node_id}/video/status")
def get_video_status(
    node_id: int,
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Get video watch status for the current student.

    Validates: Requirements 1.4
    """
    _get_node_or_404(db, node_id)

    watch = (
        db.query(GsLmsVideoWatch)
        .filter(
            GsLmsVideoWatch.student_id == current_user.id,
            GsLmsVideoWatch.syllabus_node_id == node_id,
        )
        .one_or_none()
    )

    if watch:
        return StandardResponse(
            success=True,
            message="Video watch status retrieved",
            data=VideoStatusOut(
                watched=True,
                watched_at=watch.watched_at.isoformat() if watch.watched_at else None,
                duration_seconds=watch.watch_duration_seconds,
            ),
        )

    return StandardResponse(
        success=True,
        message="Video watch status retrieved",
        data=VideoStatusOut(
            watched=False,
            watched_at=None,
            duration_seconds=None,
        ),
    )
