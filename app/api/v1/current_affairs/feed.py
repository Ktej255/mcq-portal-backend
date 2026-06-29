"""CA Feed endpoints — daily items with filters, search, and pagination.

Requirements: 6.1, 6.2, 6.3, 6.4, 14.4, 14.6
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.current_affairs.ca_engine import (
    get_ca_feed,
    get_ca_item_detail,
    get_daily_count,
    CAItemFilters,
)
from app.core.current_affairs.ca_models import CAStudentProgress

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CAItemCardOut(BaseModel):
    id: int
    title: str
    publish_date: str
    subject: str
    gs_paper: str
    exam_relevance: str
    source_authority: str
    relevance_score: int
    has_video: bool
    is_completed: bool
    thread_titles: List[str] = []


class CAFeedOut(BaseModel):
    items: List[CAItemCardOut]
    total_count: int
    today_count: int
    page: int
    page_size: int


class CAItemDetailOut(BaseModel):
    id: int
    title: str
    publish_date: str
    subject: str
    secondary_subjects: List[str]
    gs_paper: str
    exam_relevance: str
    video_url: str | None
    content_blocks: list
    upsc_statement_frames: dict | None
    so_what_analysis: dict | None
    source_authority: str
    relevance_score: int
    threads: List[dict] = []
    syllabus_links: List[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/feed", response_model=CAFeedOut)
def get_feed(
    subject: Optional[str] = Query(None),
    gs_paper: Optional[str] = Query(None),
    exam_relevance: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    thread_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("publish_date"),
    page: int = Query(1, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get paginated CA feed with filters. Only PUBLISHED items."""
    filters = CAItemFilters(
        subject=subject,
        gs_paper=gs_paper,
        exam_relevance=exam_relevance,
        date_from=date.fromisoformat(date_from) if date_from else None,
        date_to=date.fromisoformat(date_to) if date_to else None,
        thread_id=thread_id,
        search_query=search,
        sort_by=sort_by,
        page=page,
        page_size=20,
    )

    items, total = get_ca_feed(db, current_user.id, filters)
    today_count = get_daily_count(db, date.today())

    # Annotate with completion status
    completed_ids = set(
        row[0] for row in
        db.query(CAStudentProgress.ca_item_id)
        .filter(
            CAStudentProgress.student_id == current_user.id,
            CAStudentProgress.is_completed == True,
        ).all()
    )

    result_items = []
    for item in items:
        thread_titles = [
            assoc.thread.title
            for assoc in (item.thread_associations or [])
            if assoc.thread
        ]
        result_items.append(CAItemCardOut(
            id=item.id,
            title=item.title,
            publish_date=item.publish_date.isoformat(),
            subject=item.subject,
            gs_paper=item.gs_paper,
            exam_relevance=item.exam_relevance,
            source_authority=item.source_authority,
            relevance_score=item.relevance_score,
            has_video=bool(item.video_url),
            is_completed=item.id in completed_ids,
            thread_titles=thread_titles,
        ))

    return CAFeedOut(
        items=result_items,
        total_count=total,
        today_count=today_count,
        page=page,
        page_size=20,
    )


@router.get("/feed/today-count")
def get_today_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get count of today's published items."""
    return {"count": get_daily_count(db, date.today())}


@router.get("/items/{item_id}", response_model=CAItemDetailOut)
def get_item_detail(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full CA item detail. 404 if not found or not PUBLISHED."""
    item = get_ca_item_detail(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    threads = [
        {"id": assoc.thread.id, "title": assoc.thread.title}
        for assoc in (item.thread_associations or [])
        if assoc.thread
    ]
    syllabus_links = [
        {"node_id": link.syllabus_node_id, "link_type": link.link_type}
        for link in (item.syllabus_links or [])
    ]

    return CAItemDetailOut(
        id=item.id,
        title=item.title,
        publish_date=item.publish_date.isoformat(),
        subject=item.subject,
        secondary_subjects=item.secondary_subjects or [],
        gs_paper=item.gs_paper,
        exam_relevance=item.exam_relevance,
        video_url=item.video_url,
        content_blocks=item.content_blocks or [],
        upsc_statement_frames=item.upsc_statement_frames,
        so_what_analysis=item.so_what_analysis,
        source_authority=item.source_authority,
        relevance_score=item.relevance_score,
        threads=threads,
        syllabus_links=syllabus_links,
    )


@router.get("/search")
def search_items(
    q: str = Query(..., min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search CA items by query (title match)."""
    filters = CAItemFilters(search_query=q, page_size=20)
    items, _ = get_ca_feed(db, current_user.id, filters)

    return [
        {"id": item.id, "title": item.title, "publish_date": item.publish_date.isoformat(), "subject": item.subject}
        for item in items
    ]
