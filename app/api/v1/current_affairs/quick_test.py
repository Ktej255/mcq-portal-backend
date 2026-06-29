"""CA Quick Test endpoints — "Test Anytime" feature.

Students can trigger on-demand quizzes at any time:
- Test today's CA
- Test this week's CA
- Test by subject
- Test random mix

Requirements: Enhancement 3 (Test Anytime)
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.current_affairs.ca_models import CAItem, CAMcq

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class QuickTestMcqOut(BaseModel):
    id: int
    question_text: str
    question_type: str
    options: list
    item_title: str
    item_date: str


class QuickTestOut(BaseModel):
    quiz_label: str
    mcqs: List[QuickTestMcqOut]
    total_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/quick-test", response_model=QuickTestOut)
def get_quick_test(
    scope: str = Query("today", regex="^(today|this_week|this_month|subject)$"),
    subject: Optional[str] = Query(None),
    count: int = Query(10, ge=5, le=30),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate an on-demand quiz from CA items.

    Scopes:
    - today: MCQs from today's published items
    - this_week: MCQs from the last 7 days
    - this_month: MCQs from the last 30 days
    - subject: MCQs filtered by subject (requires subject param)
    """
    today = date.today()

    # Build item filter based on scope
    item_query = db.query(CAItem).filter(
        CAItem.review_status == "PUBLISHED",
        CAItem.is_deleted == False,
    )

    if scope == "today":
        item_query = item_query.filter(CAItem.publish_date == today)
        label = "Today's Current Affairs"
    elif scope == "this_week":
        week_ago = today - timedelta(days=7)
        item_query = item_query.filter(CAItem.publish_date >= week_ago)
        label = "This Week's Current Affairs"
    elif scope == "this_month":
        month_ago = today - timedelta(days=30)
        item_query = item_query.filter(CAItem.publish_date >= month_ago)
        label = "Last 30 Days"
    elif scope == "subject":
        if not subject:
            raise HTTPException(status_code=422, detail="subject parameter required for scope=subject")
        item_query = item_query.filter(CAItem.subject == subject)
        label = f"{subject.replace('-', ' ').title()} Current Affairs"
    else:
        label = "Quick Test"

    # Get item IDs
    item_ids = [row[0] for row in item_query.with_entities(CAItem.id).all()]

    if not item_ids:
        return QuickTestOut(quiz_label=label, mcqs=[], total_count=0)

    # Get MCQs from those items
    mcqs = db.query(CAMcq).filter(CAMcq.ca_item_id.in_(item_ids)).all()

    if not mcqs:
        return QuickTestOut(quiz_label=label, mcqs=[], total_count=0)

    # Random sample up to count
    selected = random.sample(mcqs, min(count, len(mcqs)))

    # Build response with item context
    item_map = {
        row.id: row for row in
        db.query(CAItem).filter(CAItem.id.in_([m.ca_item_id for m in selected])).all()
    }

    result_mcqs = [
        QuickTestMcqOut(
            id=m.id,
            question_text=m.question_text,
            question_type=m.question_type,
            options=m.options or [],
            item_title=item_map.get(m.ca_item_id, CAItem()).title or "",
            item_date=item_map.get(m.ca_item_id, CAItem()).publish_date.isoformat() if item_map.get(m.ca_item_id) else "",
        )
        for m in selected
    ]

    return QuickTestOut(
        quiz_label=label,
        mcqs=result_mcqs,
        total_count=len(result_mcqs),
    )
