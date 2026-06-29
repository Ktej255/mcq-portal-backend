"""CA Engine — core CRUD, filtering, search, and publish-gate enforcement.

Requirements: 1.6, 6.1, 6.2, 6.3, 10.3, 10.6, 11.1, 11.2, 14.4, 14.6
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.core.current_affairs.ca_models import (
    CAItem,
    CAStudentProgress,
    CAAuditLog,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CASubject(StrEnum):
    GEOGRAPHY = "geography"
    ECONOMY = "economy"
    POLITY = "polity"
    ENVIRONMENT = "environment"
    SCIENCE_TECH = "science-tech"
    HISTORY = "history"
    DISASTER_MGMT = "disaster-mgmt"
    INTERNAL_SECURITY = "internal-security"


class GSPaper(StrEnum):
    GS1 = "GS1"
    GS2 = "GS2"
    GS3 = "GS3"
    GS4 = "GS4"


class ExamRelevance(StrEnum):
    PRELIMS = "prelims"
    MAINS = "mains"
    BOTH = "both"


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class SourceAuthority(StrEnum):
    OFFICIAL = "official"
    STANDARD = "standard"
    SECONDARY = "secondary"


# Valid review status transitions
VALID_TRANSITIONS = {
    ReviewStatus.DRAFT: {ReviewStatus.IN_REVIEW},
    ReviewStatus.IN_REVIEW: {ReviewStatus.PUBLISHED, ReviewStatus.DRAFT},
    ReviewStatus.PUBLISHED: {ReviewStatus.ARCHIVED},
    ReviewStatus.ARCHIVED: set(),
}


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CAItemFilters:
    """Filter criteria for CA feed queries."""
    subject: Optional[str] = None
    gs_paper: Optional[str] = None
    exam_relevance: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    thread_id: Optional[int] = None
    search_query: Optional[str] = None
    sort_by: str = "publish_date"
    page: int = 1
    page_size: int = 20


# ---------------------------------------------------------------------------
# Query Functions (Student-facing — publish gate enforced)
# ---------------------------------------------------------------------------

def get_ca_feed(
    db: Session, student_id: int, filters: CAItemFilters
) -> tuple[List[CAItem], int]:
    """Query published CA items with filters and pagination.

    Only returns items with review_status == PUBLISHED and is_deleted == False.
    """
    query = db.query(CAItem).filter(
        CAItem.review_status == ReviewStatus.PUBLISHED,
        CAItem.is_deleted == False,
    )

    # Apply filters
    if filters.subject:
        query = query.filter(CAItem.subject == filters.subject)
    if filters.gs_paper:
        query = query.filter(CAItem.gs_paper == filters.gs_paper)
    if filters.exam_relevance:
        query = query.filter(CAItem.exam_relevance == filters.exam_relevance)
    if filters.date_from:
        query = query.filter(CAItem.publish_date >= filters.date_from)
    if filters.date_to:
        query = query.filter(CAItem.publish_date <= filters.date_to)
    if filters.search_query:
        search = f"%{filters.search_query}%"
        query = query.filter(
            or_(CAItem.title.ilike(search))
        )
    if filters.thread_id:
        from app.core.current_affairs.ca_models import CAThreadItem
        query = query.join(CAThreadItem, CAThreadItem.item_id == CAItem.id).filter(
            CAThreadItem.thread_id == filters.thread_id
        )

    # Count total
    total = query.count()

    # Sort
    if filters.sort_by == "relevance_score":
        query = query.order_by(CAItem.relevance_score.desc(), CAItem.publish_date.desc())
    else:
        query = query.order_by(CAItem.publish_date.desc())

    # Paginate
    offset = (filters.page - 1) * filters.page_size
    items = query.offset(offset).limit(filters.page_size).all()

    return items, total


def get_ca_item_detail(db: Session, item_id: int) -> Optional[CAItem]:
    """Load a full CA item. Returns None if not found or not PUBLISHED."""
    return db.query(CAItem).filter(
        CAItem.id == item_id,
        CAItem.review_status == ReviewStatus.PUBLISHED,
        CAItem.is_deleted == False,
    ).first()


def get_daily_count(db: Session, today: date) -> int:
    """Count of PUBLISHED CA items for today's date."""
    return db.query(func.count(CAItem.id)).filter(
        CAItem.publish_date == today,
        CAItem.review_status == ReviewStatus.PUBLISHED,
        CAItem.is_deleted == False,
    ).scalar() or 0


# ---------------------------------------------------------------------------
# Admin CRUD Functions
# ---------------------------------------------------------------------------

def create_ca_item(db: Session, admin_id: int, payload: dict) -> int:
    """Create a new CA item in DRAFT status. Returns item ID."""
    item = CAItem(
        title=payload["title"],
        publish_date=payload["publish_date"],
        subject=payload["subject"],
        secondary_subjects=payload.get("secondary_subjects", []),
        gs_paper=payload["gs_paper"],
        exam_relevance=payload["exam_relevance"],
        video_url=payload.get("video_url"),
        content_blocks=payload.get("content_blocks", []),
        upsc_statement_frames=payload.get("upsc_statement_frames"),
        so_what_analysis=payload.get("so_what_analysis"),
        source_authority=payload.get("source_authority", "standard"),
        relevance_score=payload.get("relevance_score", 3),
        review_status=ReviewStatus.DRAFT,
    )
    db.add(item)
    db.flush()

    # Audit log
    _log_audit(db, admin_id, "create", "ca_item", item.id)

    return item.id


def update_ca_item(db: Session, admin_id: int, item_id: int, payload: dict) -> None:
    """Update CA item fields. Logs audit trail."""
    item = db.query(CAItem).filter(CAItem.id == item_id).first()
    if not item:
        raise ValueError(f"CA item {item_id} not found")

    changes = {}
    for key, value in payload.items():
        if hasattr(item, key) and getattr(item, key) != value:
            changes[key] = {"old": getattr(item, key), "new": value}
            setattr(item, key, value)

    if changes:
        _log_audit(db, admin_id, "update", "ca_item", item_id, changes)


def update_review_status(
    db: Session, admin_id: int, item_id: int, new_status: str
) -> None:
    """Transition review status with valid transition enforcement."""
    item = db.query(CAItem).filter(CAItem.id == item_id).first()
    if not item:
        raise ValueError(f"CA item {item_id} not found")

    current = ReviewStatus(item.review_status)
    target = ReviewStatus(new_status)

    if target not in VALID_TRANSITIONS.get(current, set()):
        raise ValueError(
            f"Invalid transition: {current.value} → {target.value}. "
            f"Valid targets: {[s.value for s in VALID_TRANSITIONS[current]]}"
        )

    old_status = item.review_status
    item.review_status = target.value
    _log_audit(db, admin_id, "status_change", "ca_item", item_id,
               {"review_status": {"old": old_status, "new": target.value}})


def soft_delete_ca_item(db: Session, admin_id: int, item_id: int) -> None:
    """Soft-delete a CA item."""
    item = db.query(CAItem).filter(CAItem.id == item_id).first()
    if not item:
        raise ValueError(f"CA item {item_id} not found")

    item.soft_delete(db, actor=str(admin_id))
    _log_audit(db, admin_id, "delete", "ca_item", item_id)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _log_audit(
    db: Session, admin_id: int, action: str,
    entity_type: str, entity_id: int, changes: dict = None
) -> None:
    """Persist an audit log entry."""
    entry = CAAuditLog(
        admin_id=admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "CASubject",
    "GSPaper",
    "ExamRelevance",
    "ReviewStatus",
    "SourceAuthority",
    "VALID_TRANSITIONS",
    "CAItemFilters",
    "get_ca_feed",
    "get_ca_item_detail",
    "get_daily_count",
    "create_ca_item",
    "update_ca_item",
    "update_review_status",
    "soft_delete_ca_item",
]
