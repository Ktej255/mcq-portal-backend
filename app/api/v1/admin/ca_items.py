"""Admin CA Items — CRUD, status management, bulk import.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 10.1, 10.3, 10.4, 14.7
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_admin
from app.core.current_affairs.ca_engine import (
    create_ca_item,
    update_ca_item,
    update_review_status,
    soft_delete_ca_item,
)
from app.core.current_affairs.ca_models import CAItem, CAMcq, CAMainsQuestion

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MCQCreateIn(BaseModel):
    question_text: str
    question_type: str
    options: list
    correct_answer: str
    explanation: str | None = None
    display_order: int = 1


class MainsCreateIn(BaseModel):
    question_text: str
    gs_paper: str
    marks: int = Field(..., ge=10, le=15)
    word_limit: int = Field(..., ge=150, le=250)
    model_answer: str | None = None
    display_order: int = 1


class CAItemCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    publish_date: str
    subject: str
    secondary_subjects: List[str] = []
    gs_paper: str
    exam_relevance: str
    video_url: str | None = None
    content_blocks: list = []
    upsc_statement_frames: dict | None = None
    so_what_analysis: dict | None = None
    source_authority: str = "standard"
    relevance_score: int = Field(3, ge=1, le=5)
    mcqs: List[MCQCreateIn] = Field(default=[], max_length=10)
    mains_questions: List[MainsCreateIn] = Field(default=[], max_length=3)


class CAItemUpdateIn(BaseModel):
    title: str | None = None
    publish_date: str | None = None
    subject: str | None = None
    secondary_subjects: List[str] | None = None
    gs_paper: str | None = None
    exam_relevance: str | None = None
    video_url: str | None = None
    content_blocks: list | None = None
    upsc_statement_frames: dict | None = None
    so_what_analysis: dict | None = None
    source_authority: str | None = None
    relevance_score: int | None = Field(None, ge=1, le=5)


class StatusChangeIn(BaseModel):
    status: str


class BulkImportIn(BaseModel):
    items: List[CAItemCreateIn]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/items")
def list_items(
    status: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin: list all CA items (any status) with optional filters."""
    query = db.query(CAItem).filter(CAItem.is_deleted == False)
    if status:
        query = query.filter(CAItem.review_status == status)
    if subject:
        query = query.filter(CAItem.subject == subject)

    total = query.count()
    items = query.order_by(CAItem.publish_date.desc()).offset((page - 1) * 50).limit(50).all()

    return {
        "items": [
            {
                "id": i.id, "title": i.title, "publish_date": i.publish_date.isoformat(),
                "subject": i.subject, "gs_paper": i.gs_paper, "review_status": i.review_status,
                "relevance_score": i.relevance_score,
            }
            for i in items
        ],
        "total": total,
        "page": page,
    }


@router.post("/items", status_code=201)
def create_item(
    body: CAItemCreateIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin: create a new CA item with MCQs and Mains questions."""
    if len(body.mcqs) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 MCQs per item")
    if len(body.mains_questions) > 3:
        raise HTTPException(status_code=422, detail="Maximum 3 Mains questions per item")

    payload = body.model_dump(exclude={"mcqs", "mains_questions"})
    payload["publish_date"] = date.fromisoformat(body.publish_date)

    item_id = create_ca_item(db, admin.id, payload)

    # Create MCQs
    for mcq_data in body.mcqs:
        mcq = CAMcq(ca_item_id=item_id, **mcq_data.model_dump())
        db.add(mcq)

    # Create Mains questions
    for mq_data in body.mains_questions:
        mq = CAMainsQuestion(ca_item_id=item_id, **mq_data.model_dump())
        db.add(mq)

    db.commit()
    return {"id": item_id}


@router.put("/items/{item_id}")
def update_item(
    item_id: int,
    body: CAItemUpdateIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin: update CA item fields."""
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if "publish_date" in payload:
        payload["publish_date"] = date.fromisoformat(payload["publish_date"])

    try:
        update_ca_item(db, admin.id, item_id, payload)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "updated"}


@router.patch("/items/{item_id}/status")
def change_status(
    item_id: int,
    body: StatusChangeIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin: transition review status (DRAFT→IN_REVIEW→PUBLISHED→ARCHIVED)."""
    try:
        update_review_status(db, admin.id, item_id, body.status)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"status": body.status}


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin: soft-delete a CA item."""
    try:
        soft_delete_ca_item(db, admin.id, item_id)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "deleted"}


@router.post("/items/bulk-import")
def bulk_import(
    body: BulkImportIn,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin: bulk import CA items. Returns per-item success/failure."""
    results = {"created": 0, "failed": 0, "errors": []}

    for idx, item_data in enumerate(body.items):
        try:
            if len(item_data.mcqs) > 10:
                raise ValueError("Maximum 10 MCQs per item")
            if len(item_data.mains_questions) > 3:
                raise ValueError("Maximum 3 Mains questions per item")

            payload = item_data.model_dump(exclude={"mcqs", "mains_questions"})
            payload["publish_date"] = date.fromisoformat(item_data.publish_date)
            item_id = create_ca_item(db, admin.id, payload)

            for mcq_data in item_data.mcqs:
                db.add(CAMcq(ca_item_id=item_id, **mcq_data.model_dump()))
            for mq_data in item_data.mains_questions:
                db.add(CAMainsQuestion(ca_item_id=item_id, **mq_data.model_dump()))

            results["created"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"index": idx, "message": str(e)})

    db.commit()
    return results
