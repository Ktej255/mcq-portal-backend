"""SQLAlchemy model for the subject-specific Current-Affairs feature
(Task 17.1 — Phase 2, R11.4 / R19.2).

Current affairs is a **subject-specific feature module** (like Geography's
mapping): it is presented only for subjects whose config enables the
``currentAffairs`` feature (Public Administration today — R11.4). It demonstrates
that the per-subject framework generalizes beyond Geography.

Honesty gate (design Property 8 / R17.2, R17.3): each item carries a
``review_status``; students only ever see ``REVIEWED`` (non-deleted) items.
Draft/seeded current-affairs content stays ``UNREVIEWED`` and gated until a
content author/founder reviews it for accuracy.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules. Table uses the shared
``optional_`` prefix and registers on the shared ``Base``.

Requirements: 11.4, 17.2, 17.3, 19.2
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Date,
    Enum,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin, SoftDeleteMixin
from app.core.optional.models import OptionalReviewStatusEnum


class CurrentAffairsItem(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A subject-specific current-affairs / news item (R11.4).

    ``topic`` is the thematic tag a student filters by (e.g. "Governance",
    "Polity", "Schemes"); ``summary`` is the exam-oriented note; ``source_url``
    points to the authoritative source. Gated by ``review_status`` like all
    student-visible content.
    """

    __tablename__ = "optional_current_affairs"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    title = Column(String, nullable=False)
    topic = Column(String, nullable=True, index=True)
    summary = Column(Text, nullable=True)
    source_url = Column(String, nullable=True)
    published_on = Column(Date, nullable=True, index=True)
    display_order = Column(Integer, default=0, nullable=False)
    review_status = Column(
        Enum(OptionalReviewStatusEnum),
        default=OptionalReviewStatusEnum.UNREVIEWED,
        nullable=False,
        index=True,
    )

    subject = relationship("OptionalSubject")


__all__ = ["CurrentAffairsItem"]
