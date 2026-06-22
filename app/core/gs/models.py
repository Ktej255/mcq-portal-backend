"""SQLAlchemy models for the GS (General Studies) student domain — canonical
content store (Master Plan A3/B3, GATE-1 = standardize the live loop on the
backend).

These models make FastAPI/Postgres the source of truth for GS *content*
(starting with Geography's 30-day guided-study curriculum), mirroring the
``app.core.optional`` content domain. They register on the shared declarative
``Base`` (``app.db.session.Base``) so a single Alembic ``target_metadata``
covers the whole schema, and use a ``gs_`` table-name prefix to avoid colliding
with the pre-existing MCQ domain and the ``optional_`` tables.

Design notes:
- The GS Geography curriculum is naturally document-shaped (a day lesson is a
  Watch-room scene script + the day's session metadata), so the lesson body is
  preserved faithfully as JSON (``content``) for **no content loss** — the same
  approach the Optional importer uses for its flexible ``ContentUnit.blocks``.
  A few list/scalar fields are promoted to columns so a future read API can
  query them directly (``scenes``, ``subtopics``, ``day_number``).
- Student *progress* already lives on the backend via
  ``StudentSubjectProgress`` (A3, ``GET/PUT /api/v1/student/progress/{slug}``);
  this module owns the *content* half. Student attempts/reports are NOT
  migrated here (gated separately).

Content honesty (Completion Integrity Contract): the importer fabricates no
content — it only stores what the authored frontend modules contain. Authored,
already-shipping GS Geography content is imported as ``REVIEWED``; pass a
different status to gate it behind a review workflow.
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    Enum,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin


class GsReviewStatusEnum(str, enum.Enum):
    """Content review state used to gate student display.

    Mirrors the Optional review semantics (kept as a self-contained GS enum so
    the GS domain does not depend on the Optional package).
    """
    UNREVIEWED = "UNREVIEWED"
    IN_REVIEW = "IN_REVIEW"
    REVIEWED = "REVIEWED"


class GsSubject(Base, InstitutionalAuditMixin):
    """A GS subject (Geography, Environment, Polity, ...). Canonical entity.

    Named ``GsSubject`` to avoid colliding with the pre-existing MCQ
    ``Subject``/``subjects`` table and the ``OptionalSubject`` table on the
    shared metadata.
    """
    __tablename__ = "gs_subjects"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    # Free-form per-subject framework config (weeks, labs, feature flags).
    config = Column(JSON, nullable=True)
    is_complete = Column(Boolean, default=False, nullable=False)
    completeness_status = Column(JSON, nullable=True)

    day_lessons = relationship(
        "GsDayLesson", back_populates="subject", cascade="all, delete-orphan"
    )


class GsDayLesson(Base, InstitutionalAuditMixin):
    """One day of a GS subject's guided-study curriculum.

    For Geography this is one of the 30 ``geographyDay<N>PortalLesson`` Watch
    modules, joined (for days 1..20) with its ``geographySessions`` entry. The
    full authored payload is preserved in ``content`` (``{"session": ...,
    "lesson": {...all module exports...}}``) so the migration loses nothing;
    ``scenes`` and ``subtopics`` are promoted for direct querying.
    """
    __tablename__ = "gs_day_lessons"
    __table_args__ = (
        UniqueConstraint("subject_id", "day_number", name="uq_gs_day_lessons_subject_day"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("gs_subjects.id"), nullable=False, index=True
    )
    # 1-based curriculum/lesson number (the geographyDay<N> file number).
    day_number = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=True)

    # The Watch-lesson title (always present, from the day lesson module).
    title = Column(String, nullable=False)
    # The curriculum/session title (present for days that have a session row).
    session_title = Column(String, nullable=True)

    # True when a ``geographySessions`` entry backs this day (days 1..20 for
    # Geography); False for authored scene-only lessons (e.g. lessons 21..30).
    has_session = Column(Boolean, default=False, nullable=False)

    # Promoted, list-shaped fields a read API serves directly.
    scenes = Column(JSON, nullable=True)
    subtopics = Column(JSON, nullable=True)

    # Full faithful payload for no content loss: {"session": <or null>,
    # "lesson": {<every exported member of the day module>}}.
    content = Column(JSON, nullable=True)

    review_status = Column(
        Enum(GsReviewStatusEnum), default=GsReviewStatusEnum.REVIEWED, nullable=False
    )
    display_order = Column(Integer, default=0, nullable=False)

    subject = relationship("GsSubject", back_populates="day_lessons")


__all__ = ["GsReviewStatusEnum", "GsSubject", "GsDayLesson"]
