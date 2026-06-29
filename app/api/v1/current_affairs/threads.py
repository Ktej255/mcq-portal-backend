"""CA Thread endpoints — thread retrieval and consolidation views.

Requirements: 3.3, 3.4, 12.1, 12.2, 12.3, 12.4, 12.5, 14.4
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.current_affairs.ca_models import (
    CAThread,
    CAThreadItem,
    CAItem,
    CAStudentProgress,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ThreadSummaryOut(BaseModel):
    id: int
    title: str
    primary_subject: str
    status: str
    direction: str | None
    item_count: int
    start_date: str


class ThreadItemOut(BaseModel):
    id: int
    title: str
    publish_date: str
    sequence_order: int
    causality_direction: str | None
    is_completed: bool


class ThreadConsolidationOut(BaseModel):
    id: int
    title: str
    description: str | None
    direction: str | None
    primary_subject: str
    items: List[ThreadItemOut]
    coverage: dict
    related_threads: List[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/threads", response_model=List[ThreadSummaryOut])
def get_threads_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List active threads with summary info."""
    threads = (
        db.query(CAThread)
        .filter(CAThread.is_deleted == False)
        .order_by(CAThread.start_date.desc())
        .all()
    )

    result = []
    for thread in threads:
        item_count = (
            db.query(CAThreadItem)
            .filter(CAThreadItem.thread_id == thread.id)
            .join(CAItem, CAThreadItem.item_id == CAItem.id)
            .filter(CAItem.review_status == "PUBLISHED", CAItem.is_deleted == False)
            .count()
        )
        if item_count > 0:
            result.append(ThreadSummaryOut(
                id=thread.id,
                title=thread.title,
                primary_subject=thread.primary_subject,
                status=thread.status,
                direction=thread.direction,
                item_count=item_count,
                start_date=thread.start_date.isoformat(),
            ))

    return result


@router.get("/threads/{thread_id}/consolidation", response_model=ThreadConsolidationOut)
def get_thread_consolidation(
    thread_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get thread consolidation view with all items chronologically."""
    thread = db.query(CAThread).filter(
        CAThread.id == thread_id,
        CAThread.is_deleted == False,
    ).first()

    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Get all PUBLISHED items in this thread
    associations = (
        db.query(CAThreadItem)
        .filter(CAThreadItem.thread_id == thread_id)
        .join(CAItem, CAThreadItem.item_id == CAItem.id)
        .filter(CAItem.review_status == "PUBLISHED", CAItem.is_deleted == False)
        .order_by(CAThreadItem.sequence_order)
        .all()
    )

    # Get completion status
    item_ids = [a.item_id for a in associations]
    completed_ids = set(
        row[0] for row in
        db.query(CAStudentProgress.ca_item_id)
        .filter(
            CAStudentProgress.student_id == current_user.id,
            CAStudentProgress.ca_item_id.in_(item_ids),
            CAStudentProgress.is_completed == True,
        ).all()
    ) if item_ids else set()

    items = []
    for assoc in associations:
        ca_item = assoc.ca_item
        items.append(ThreadItemOut(
            id=ca_item.id,
            title=ca_item.title,
            publish_date=ca_item.publish_date.isoformat(),
            sequence_order=assoc.sequence_order,
            causality_direction=assoc.causality_direction,
            is_completed=ca_item.id in completed_ids,
        ))

    coverage = {
        "total_items": len(items),
        "completed": len(completed_ids),
        "mcqs_attempted": 0,
    }

    return ThreadConsolidationOut(
        id=thread.id,
        title=thread.title,
        description=thread.description,
        direction=thread.direction,
        primary_subject=thread.primary_subject,
        items=items,
        coverage=coverage,
        related_threads=[],
    )
