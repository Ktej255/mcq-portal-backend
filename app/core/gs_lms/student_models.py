"""SQLAlchemy models for the GS LMS Platform — student activity domain
(design "Data Models" section).

This module complements ``app.core.gs_lms.models`` (the canonical
content/syllabus domain) with student-facing activity entities: section
progress, AI discussion sessions, MCQ practice sessions/attempts, gap
snapshots, daily plans, replanning events, and onboarding status.

Every student-owned record carries the student FK (``users.id``) so ownership
can be authorized against the requesting student (ownership-scoped queries).
Models register on the shared declarative ``Base`` and use the ``gs_lms_``
table-name prefix, mirroring ``app.core.gs_lms.models``.

Domain isolation: nothing here imports from ``app.core.optional``.

Requirements: 1.4, 10.1, 10.4, 11.4
"""

from __future__ import annotations

from datetime import datetime, date, timezone
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    Date,
    Float,
    ForeignKey,
    Enum,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin
from app.core.gs_lms.models import GsLmsQuestionTypeEnum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GsLmsDiscussionStatusEnum(str, enum.Enum):
    """Lifecycle of an AI discussion session."""
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class GsLmsPracticeSessionStatusEnum(str, enum.Enum):
    """Lifecycle of an MCQ practice session."""
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SUBMITTED = "SUBMITTED"


# ---------------------------------------------------------------------------
# Student Section Progress
# ---------------------------------------------------------------------------

class GsLmsStudentSectionProgress(Base, InstitutionalAuditMixin):
    """Per-student, per-section completion tracking.

    Tracks whether a student has completed each progressive-disclosure section
    of a topic. The unique constraint on (student_id, section_id) ensures
    exactly one progress record per student per section.
    """
    __tablename__ = "gs_lms_student_section_progress"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "section_id",
            name="uq_gs_lms_student_section_progress"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    section_id = Column(
        Integer, ForeignKey("gs_lms_content_sections.id"), nullable=False, index=True
    )
    # Denormalized for fast per-topic queries without joining content_sections.
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    student = relationship("User")
    section = relationship("GsLmsContentSection")
    syllabus_node = relationship("GsLmsSyllabusNode")


# ---------------------------------------------------------------------------
# AI Discussion Sessions
# ---------------------------------------------------------------------------

class GsLmsDiscussionSession(Base, InstitutionalAuditMixin):
    """AI Discussion session before topic content unlock.

    The pre-content recall conversation gates topic access. A session
    transitions through INITIATED → IN_PROGRESS → COMPLETED. Completion
    sets the gate flag that unlocks Topic_Page content.
    """
    __tablename__ = "gs_lms_discussion_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    status = Column(
        Enum(GsLmsDiscussionStatusEnum),
        default=GsLmsDiscussionStatusEnum.INITIATED,
        nullable=False,
        index=True,
    )
    started_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")
    turns = relationship(
        "GsLmsDiscussionTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="GsLmsDiscussionTurn.turn_order",
    )


class GsLmsDiscussionTurn(Base, InstitutionalAuditMixin):
    """One turn in the AI Discussion conversation.

    Each turn stores the role (student or ai), the message content, and the
    ordering within the session.
    """
    __tablename__ = "gs_lms_discussion_turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("gs_lms_discussion_sessions.id"), nullable=False, index=True
    )
    turn_order = Column(Integer, nullable=False, index=True)
    role = Column(String, nullable=False)  # "student" or "ai"
    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    session = relationship("GsLmsDiscussionSession", back_populates="turns")


# ---------------------------------------------------------------------------
# MCQ Practice Sessions and Attempts
# ---------------------------------------------------------------------------

class GsLmsPracticeSession(Base, InstitutionalAuditMixin):
    """A student's MCQ practice session for a topic.

    Tracks sequential progression through questions. The session state
    (current_index) enforces sequential access: only the current question
    is exposed until answered or skipped.
    """
    __tablename__ = "gs_lms_practice_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    status = Column(
        Enum(GsLmsPracticeSessionStatusEnum),
        default=GsLmsPracticeSessionStatusEnum.IN_PROGRESS,
        nullable=False,
        index=True,
    )
    total_questions = Column(Integer, nullable=False)
    # Tracks sequential progression (0-indexed).
    current_index = Column(Integer, default=0, nullable=False)
    started_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    submitted_at = Column(DateTime, nullable=True)

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")
    attempts = relationship(
        "GsLmsPracticeAttempt",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class GsLmsPracticeAttempt(Base, InstitutionalAuditMixin):
    """Individual answer in a practice session.

    Records the student's chosen answer (or None for skipped), correctness,
    time taken, and the question type (denormalized for fast gap queries).
    """
    __tablename__ = "gs_lms_practice_attempts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("gs_lms_practice_sessions.id"), nullable=False, index=True
    )
    question_id = Column(
        Integer, ForeignKey("gs_lms_mcq_questions.id"), nullable=False, index=True
    )
    # Denormalized for fast gap queries without joining sessions.
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    chosen_answer = Column(String, nullable=True)  # None = skipped
    is_correct = Column(Boolean, nullable=True)
    time_taken_seconds = Column(Float, nullable=True)
    # Denormalized from question for fast per-type aggregation.
    question_type = Column(Enum(GsLmsQuestionTypeEnum), nullable=True)

    # Relationships
    session = relationship("GsLmsPracticeSession", back_populates="attempts")
    question = relationship("GsLmsMcqQuestion")
    student = relationship("User")


# ---------------------------------------------------------------------------
# Gap Snapshots
# ---------------------------------------------------------------------------

class GsLmsGapSnapshot(Base, InstitutionalAuditMixin):
    """Point-in-time gap profile for a student.

    Captures overall accuracy, weak topics, weak question types, and
    recommended actions at a specific moment. Timestamped for trend tracking.
    """
    __tablename__ = "gs_lms_gap_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    computed_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    overall_accuracy = Column(Float, nullable=False)
    # [{node_id, title, accuracy}, ...]
    weak_topics = Column(JSON, nullable=True)
    # [{type, accuracy, attempts}, ...]
    weak_question_types = Column(JSON, nullable=True)
    # [{action, target_node_id, reason}, ...]
    recommended_actions = Column(JSON, nullable=True)

    # Relationships
    student = relationship("User")


# ---------------------------------------------------------------------------
# Daily Plans
# ---------------------------------------------------------------------------

class GsLmsDailyPlan(Base, InstitutionalAuditMixin):
    """A student's daily study plan.

    Stores the planned items, actual completions, bandwidth setting, and
    target-met status. Projected completion date computed from remaining
    items and effective bandwidth.
    """
    __tablename__ = "gs_lms_daily_plans"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    plan_date = Column(Date, nullable=False, index=True)
    # Topics/sections committed for this day.
    bandwidth = Column(Integer, nullable=False)
    # [{node_id, type: "section"|"practice"}, ...]
    planned_items = Column(JSON, nullable=True)
    # [{node_id, completed_at}, ...]
    completed_items = Column(JSON, nullable=True)
    is_target_met = Column(Boolean, nullable=True)
    projected_completion_date = Column(Date, nullable=True)

    # Relationships
    student = relationship("User")


# ---------------------------------------------------------------------------
# Replan Events
# ---------------------------------------------------------------------------

class GsLmsReplanEvent(Base, InstitutionalAuditMixin):
    """Record of dynamic replanning triggers.

    Tracks when replanning occurs, the reason (consecutive misses, manual,
    or bandwidth increase), and the before/after bandwidth and projected dates.
    """
    __tablename__ = "gs_lms_replan_events"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    triggered_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    reason = Column(String, nullable=False)  # "consecutive_misses" | "manual" | "bandwidth_increase"
    old_bandwidth = Column(Integer, nullable=False)
    new_bandwidth = Column(Integer, nullable=False)
    old_projected_date = Column(Date, nullable=True)
    new_projected_date = Column(Date, nullable=True)

    # Relationships
    student = relationship("User")


# ---------------------------------------------------------------------------
# Onboarding Status
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PYQ Reveal Tracking
# ---------------------------------------------------------------------------

class GsLmsPyqReveal(Base, InstitutionalAuditMixin):
    """Tracks which PYQs a student has revealed the answer for.

    Once revealed, answer_text and explanation become visible in the PYQ
    response for that student. The unique constraint ensures at most one
    reveal event per student per PYQ.
    """
    __tablename__ = "gs_lms_pyq_reveals"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "pyq_id",
            name="uq_gs_lms_pyq_reveal"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    pyq_id = Column(
        Integer, ForeignKey("gs_lms_pyqs.id"), nullable=False, index=True
    )
    revealed_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    student = relationship("User")
    pyq = relationship("GsLmsPyq")


# ---------------------------------------------------------------------------
# Onboarding Status
# ---------------------------------------------------------------------------

class GsLmsOnboardingStatus(Base, InstitutionalAuditMixin):
    """Onboarding completion tracking per student.

    Persists whether a student has completed the max-3-step onboarding flow,
    their selected bandwidth, and the assigned first topic. Unique per student.
    """
    __tablename__ = "gs_lms_onboarding"
    __table_args__ = (
        UniqueConstraint("student_id", name="uq_gs_lms_onboarding_student"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    bandwidth_selected = Column(Integer, nullable=True)
    first_topic_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=True
    )

    # Relationships
    student = relationship("User")
    first_topic = relationship("GsLmsSyllabusNode")


__all__ = [
    # Enums
    "GsLmsDiscussionStatusEnum",
    "GsLmsPracticeSessionStatusEnum",
    # Models
    "GsLmsStudentSectionProgress",
    "GsLmsDiscussionSession",
    "GsLmsDiscussionTurn",
    "GsLmsPracticeSession",
    "GsLmsPracticeAttempt",
    "GsLmsGapSnapshot",
    "GsLmsDailyPlan",
    "GsLmsReplanEvent",
    "GsLmsPyqReveal",
    "GsLmsOnboardingStatus",
]
