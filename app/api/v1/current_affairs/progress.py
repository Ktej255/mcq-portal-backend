"""CA Progress and Analytics endpoints — streak, coverage, missed items.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 14.4
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.current_affairs.ca_models import CAItem, CAStudentProgress

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CAStreakOut(BaseModel):
    current_streak: int
    longest_streak: int
    last_activity_date: str | None


class CACoverageOut(BaseModel):
    subject: str
    total_available: int
    completed: int
    percentage: float


class CAAnalyticsOut(BaseModel):
    streak: CAStreakOut
    coverage_by_subject: List[CACoverageOut]
    overall_coverage_percent: float
    missed_items_count: int
    total_items_available: int
    total_items_completed: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/analytics", response_model=CAAnalyticsOut)
def get_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get comprehensive CA analytics for the student."""
    today = date.today()

    # Total available PUBLISHED items
    total_available = db.query(func.count(CAItem.id)).filter(
        CAItem.review_status == "PUBLISHED",
        CAItem.is_deleted == False,
    ).scalar() or 0

    # Total completed by this student
    total_completed = db.query(func.count(CAStudentProgress.id)).filter(
        CAStudentProgress.student_id == current_user.id,
        CAStudentProgress.is_completed == True,
    ).scalar() or 0

    # Coverage by subject
    subjects = ["geography", "economy", "polity", "environment", "science-tech", "history", "disaster-mgmt", "internal-security"]
    coverage_by_subject = []
    for subj in subjects:
        avail = db.query(func.count(CAItem.id)).filter(
            CAItem.subject == subj,
            CAItem.review_status == "PUBLISHED",
            CAItem.is_deleted == False,
        ).scalar() or 0

        completed = db.query(func.count(CAStudentProgress.id)).filter(
            CAStudentProgress.student_id == current_user.id,
            CAStudentProgress.is_completed == True,
        ).join(CAItem, CAStudentProgress.ca_item_id == CAItem.id).filter(
            CAItem.subject == subj,
        ).scalar() or 0

        coverage_by_subject.append(CACoverageOut(
            subject=subj,
            total_available=avail,
            completed=completed,
            percentage=round((completed / avail * 100) if avail > 0 else 0, 1),
        ))

    overall_pct = round((total_completed / total_available * 100) if total_available > 0 else 0, 1)

    # Missed items (PUBLISHED, publish_date < today - 3 days, not completed)
    cutoff = today - timedelta(days=3)
    completed_ids = set(
        row[0] for row in
        db.query(CAStudentProgress.ca_item_id)
        .filter(CAStudentProgress.student_id == current_user.id, CAStudentProgress.is_completed == True)
        .all()
    )
    missed_count = db.query(func.count(CAItem.id)).filter(
        CAItem.review_status == "PUBLISHED",
        CAItem.is_deleted == False,
        CAItem.publish_date < cutoff,
        ~CAItem.id.in_(completed_ids) if completed_ids else CAItem.id > 0,
    ).scalar() or 0

    # Streak
    streak = _compute_streak(db, current_user.id, today)

    return CAAnalyticsOut(
        streak=streak,
        coverage_by_subject=coverage_by_subject,
        overall_coverage_percent=overall_pct,
        missed_items_count=missed_count,
        total_items_available=total_available,
        total_items_completed=total_completed,
    )


@router.get("/streak", response_model=CAStreakOut)
def get_streak(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current CA streak."""
    return _compute_streak(db, current_user.id, date.today())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_streak(db: Session, student_id: int, today: date) -> CAStreakOut:
    """Compute current and longest CA streak for a student."""
    # Get all distinct completion dates
    completion_dates = sorted(set(
        row[0].date() if hasattr(row[0], 'date') else row[0]
        for row in
        db.query(CAStudentProgress.completed_at)
        .filter(
            CAStudentProgress.student_id == student_id,
            CAStudentProgress.is_completed == True,
            CAStudentProgress.completed_at.isnot(None),
        ).all()
        if row[0]
    ), reverse=True)

    if not completion_dates:
        return CAStreakOut(current_streak=0, longest_streak=0, last_activity_date=None)

    last_activity = completion_dates[0]

    # Current streak (consecutive days ending at today or yesterday)
    current_streak = 0
    check_date = today
    if last_activity < today - timedelta(days=1):
        current_streak = 0
    else:
        if last_activity == today or last_activity == today - timedelta(days=1):
            check_date = last_activity
            date_set = set(completion_dates)
            while check_date in date_set:
                current_streak += 1
                check_date -= timedelta(days=1)

    # Longest streak
    longest = 0
    current_run = 1
    for i in range(1, len(completion_dates)):
        if completion_dates[i - 1] - completion_dates[i] == timedelta(days=1):
            current_run += 1
        else:
            longest = max(longest, current_run)
            current_run = 1
    longest = max(longest, current_run, current_streak)

    return CAStreakOut(
        current_streak=current_streak,
        longest_streak=longest,
        last_activity_date=last_activity.isoformat(),
    )
