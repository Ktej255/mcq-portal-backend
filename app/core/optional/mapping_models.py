"""SQLAlchemy models for the Geography Mapping module (Task 10 — R10).

The mapping subsystem is a **subject-specific feature** (R10.4 / R11.3): it is
presented only for subjects that define map-based features (Geography today).
Two entities:

* :class:`MapLocation` — a place a student must be able to identify on the map,
  with the short UPSC-style "what to know" detail shown when it is clicked
  (R10.3), filed under a feature ``category`` (river / plateau / plain / …).
* :class:`MapQuestion` — a previous-year map-based question, organized
  ``category``-wise across years (R10.1, R10.2), optionally linked to a
  :class:`MapLocation`.

Honesty gate (design Property 8 / R17.2, R17.3): both carry a ``review_status``;
students are only ever shown ``REVIEWED`` (and non-deleted) rows. Draft/seeded
mapping content stays ``UNREVIEWED`` and is gated until a content author/founder
reviews it for UPSC accuracy.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules. Tables use the shared
``optional_`` prefix and register on the shared ``Base``.

Requirements: 10.1, 10.2, 10.3, 10.4, 11.3, 17.2, 17.3
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    Enum,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin, SoftDeleteMixin
from app.core.optional.models import OptionalReviewStatusEnum


class MapLocation(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A map location a student must know, with clickable UPSC-style detail.

    ``category`` is the feature class it is filed under (river / plateau /
    plain / peak / pass / lake / …, an open set — R10.2). ``detail`` is the
    3–4 line "what a student must know" text surfaced on click (R10.3).
    ``latitude``/``longitude`` are optional (a future interactive map can use
    them; the list view does not require them).
    """

    __tablename__ = "optional_map_locations"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    name = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    detail = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    authored = Column(Boolean, default=False, nullable=False)
    review_status = Column(
        Enum(OptionalReviewStatusEnum),
        default=OptionalReviewStatusEnum.UNREVIEWED,
        nullable=False,
        index=True,
    )

    subject = relationship("OptionalSubject")
    questions = relationship("MapQuestion", back_populates="location")


class MapQuestion(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A previous-year map-based question, filed category-wise (R10.1/R10.2).

    Gated by ``review_status`` exactly like PYQs/content (design Property 8):
    only ``REVIEWED`` questions are student-visible.
    """

    __tablename__ = "optional_map_questions"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    location_id = Column(
        Integer, ForeignKey("optional_map_locations.id"), nullable=True, index=True
    )
    year = Column(Integer, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    marks = Column(Integer, nullable=True)
    beyond_syllabus = Column(Boolean, default=False, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    review_status = Column(
        Enum(OptionalReviewStatusEnum),
        default=OptionalReviewStatusEnum.UNREVIEWED,
        nullable=False,
        index=True,
    )

    subject = relationship("OptionalSubject")
    location = relationship("MapLocation", back_populates="questions")


__all__ = ["MapLocation", "MapQuestion"]
