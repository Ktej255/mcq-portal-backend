"""SQLAlchemy models for the Interactive Learning Funnel — student activity domain.

Extends the GS LMS platform with tables for funnel step progression, reading
time tracking, speech-based recall checks, MCQ Lab sessions (15-question batch),
weakness pattern aggregation, growth reports, adaptive spaced repetition
schedules, and curated external resources.

Models register on the shared declarative ``Base`` and use the ``gs_lms_``
table-name prefix. Domain isolation: nothing here imports from ``app.core.optional``.

Requirements: 13.1, 13.5
"""

from __future__ import annotations

import enum
from datetime import datetime, date, timezone

from sqlalchemy import (
    Column,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    DateTime,
    Date,
    ForeignKey,
    Enum,
    JSON,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GsLmsFunnelStepEnum(int, enum.Enum):
    """The 14 steps of the Interactive Learning Funnel."""
    DISCUSSION_GATE = 1
    BASIC_CONTENT = 2
    BASIC_RECALL = 3
    NCERT_CONTENT = 4
    NCERT_RECALL = 5
    ADVANCED_CONTENT = 6
    ADVANCED_RECALL = 7
    CURRENT_AFFAIRS_CONTENT = 8
    CURRENT_AFFAIRS_RECALL = 9
    TRAPS_CONTENT = 10
    TRAPS_RECALL = 11
    MCQ_LAB = 12
    MAINS_PRACTICE = 13
    GROWTH_REPORT = 14


# ---------------------------------------------------------------------------
# Funnel Step Progress
# ---------------------------------------------------------------------------

class GsLmsFunnelProgress(Base, InstitutionalAuditMixin):
    """Per-student, per-topic, per-step completion tracking.

    The unique constraint ensures exactly one progress record per student per
    topic per step. The step_number is bounded to [1, 14].
    """
    __tablename__ = "gs_lms_funnel_progress"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "syllabus_node_id", "step_number",
            name="uq_gs_lms_funnel_step"
        ),
        CheckConstraint(
            "step_number >= 1 AND step_number <= 14",
            name="ck_funnel_step_range"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    step_number = Column(Integer, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")


# ---------------------------------------------------------------------------
# Reading Time Records
# ---------------------------------------------------------------------------

class GsLmsReadingTime(Base, InstitutionalAuditMixin):
    """Cumulative reading time per student per content section.

    Duration is capped at 7200 seconds (2 hours). Estimated duration is
    computed from content word count / 200 wpm.
    """
    __tablename__ = "gs_lms_reading_times"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "section_id",
            name="uq_gs_lms_reading_time"
        ),
        CheckConstraint(
            "duration_seconds >= 0 AND duration_seconds <= 7200",
            name="ck_reading_time_range"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    section_id = Column(
        Integer, ForeignKey("gs_lms_content_sections.id"), nullable=False, index=True
    )
    duration_seconds = Column(Integer, default=0, nullable=False)
    estimated_duration_seconds = Column(Integer, nullable=True)
    last_updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")
    section = relationship("GsLmsContentSection")


# ---------------------------------------------------------------------------
# Recall Check Attempts
# ---------------------------------------------------------------------------

class GsLmsRecallAttempt(Base, InstitutionalAuditMixin):
    """Speech-based recall check attempt with transcript and scores.

    Scores are stored as floats in [0.0, 1.0]. The section_label identifies
    which content section was recalled (BASIC, NCERT, ADVANCED, etc.).
    """
    __tablename__ = "gs_lms_recall_attempts"
    __table_args__ = (
        CheckConstraint(
            "recall_score >= 0.0 AND recall_score <= 1.0",
            name="ck_recall_score_range"
        ),
        CheckConstraint(
            "confidence_score >= 0.0 AND confidence_score <= 1.0",
            name="ck_confidence_score_range"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    section_label = Column(String(30), nullable=False)
    audio_storage_ref = Column(String(500), nullable=True)
    transcript = Column(Text, nullable=True)
    recall_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)
    concepts_matched = Column(JSON, nullable=True)
    concepts_missed = Column(JSON, nullable=True)
    stt_confidence = Column(Float, nullable=True)
    attempt_number = Column(Integer, default=1, nullable=False)

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")


# ---------------------------------------------------------------------------
# MCQ Lab Sessions and Attempts
# ---------------------------------------------------------------------------

class GsLmsMcqLabSession(Base, InstitutionalAuditMixin):
    """A 15-question MCQ Lab session (submit-all flow).

    Distinct from existing GsLmsPracticeSession (sequential, one-at-a-time).
    MCQ Lab presents all 15 questions simultaneously and uses bulk submit.
    """
    __tablename__ = "gs_lms_mcq_lab_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    total_questions = Column(Integer, default=15, nullable=False)
    correct_count = Column(Integer, nullable=True)
    score = Column(Float, nullable=True)  # 0.0–1.0
    submitted_at = Column(DateTime, nullable=True)

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")
    attempts = relationship(
        "GsLmsMcqLabAttempt",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class GsLmsMcqLabAttempt(Base, InstitutionalAuditMixin):
    """Individual question attempt within an MCQ Lab session.

    Records chosen answer, correctness (all-or-nothing), time taken, and
    the UPSC question type for weakness pattern computation.
    """
    __tablename__ = "gs_lms_mcq_lab_attempts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("gs_lms_mcq_lab_sessions.id"), nullable=False, index=True
    )
    question_id = Column(
        Integer, ForeignKey("gs_lms_mcq_questions.id"), nullable=False
    )
    question_type = Column(String(30), nullable=False)
    chosen_answer = Column(String(10), nullable=False)
    correct_answer = Column(String(10), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_taken_seconds = Column(Float, nullable=True)

    # Relationships
    session = relationship("GsLmsMcqLabSession", back_populates="attempts")
    question = relationship("GsLmsMcqQuestion")


# ---------------------------------------------------------------------------
# Weakness Patterns (Aggregated)
# ---------------------------------------------------------------------------

class GsLmsWeaknessPattern(Base, InstitutionalAuditMixin):
    """Per-student, per-question-type aggregate accuracy tracking.

    Updated after each MCQ Lab session. Flags question types as weak when
    accuracy < 50% across 3+ attempts; removes flag when accuracy >= 70%
    over the most recent 5 attempts.
    """
    __tablename__ = "gs_lms_weakness_patterns"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "question_type",
            name="uq_gs_lms_weakness"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    question_type = Column(String(30), nullable=False)
    total_attempts = Column(Integer, default=0, nullable=False)
    correct_count = Column(Integer, default=0, nullable=False)
    accuracy = Column(Float, default=0.0, nullable=False)
    is_weak = Column(Boolean, default=False, nullable=False)
    last_updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    student = relationship("User")


# ---------------------------------------------------------------------------
# Growth Reports (Snapshot)
# ---------------------------------------------------------------------------

class GsLmsGrowthReport(Base, InstitutionalAuditMixin):
    """Persisted Growth Report snapshot per student per topic.

    Generated upon funnel completion (step 14). Contains all component
    scores, spaced repetition schedule, weakness identification, and
    historical comparison data.
    """
    __tablename__ = "gs_lms_growth_reports"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    # Per-section metrics: [{section_label, reading_time_seconds, recall_score, confidence_score, is_rushed}]
    section_metrics = Column(JSON, nullable=False)
    mcq_total_score = Column(Float, nullable=False)
    mcq_type_breakdown = Column(JSON, nullable=False)
    mains_score = Column(Float, nullable=True)
    mains_max_marks = Column(Integer, nullable=True)
    next_recall_date = Column(Date, nullable=False)
    recall_interval_days = Column(Integer, nullable=False)
    weaknesses = Column(JSON, nullable=False)
    comparison_data = Column(JSON, nullable=True)
    generated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")


# ---------------------------------------------------------------------------
# Spaced Repetition Schedules (Adaptive)
# ---------------------------------------------------------------------------

class GsLmsSpacedRepSchedule(Base, InstitutionalAuditMixin):
    """Adaptive spaced repetition schedule entries.

    Replaces the fixed Day+3/7/21 pattern in GsLmsRevisitSchedule with
    performance-based intervals that adjust based on recall scores.
    """
    __tablename__ = "gs_lms_spaced_rep_schedules"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "syllabus_node_id", "sequence_number",
            name="uq_gs_lms_spaced_rep"
        ),
        Index(
            "ix_gs_lms_spaced_rep_student_due",
            "student_id", "due_date",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    sequence_number = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    interval_days = Column(Integer, nullable=False)
    recall_score = Column(Float, nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    missed = Column(Boolean, default=False, nullable=False)

    # Relationships
    student = relationship("User")
    syllabus_node = relationship("GsLmsSyllabusNode")


# ---------------------------------------------------------------------------
# External Reading Resources
# ---------------------------------------------------------------------------

class GsLmsExternalResource(Base, InstitutionalAuditMixin):
    """Curated external reading resources per topic per section.

    Only resources with review_status REVIEWED are displayed to students.
    Maximum 5 per section, ordered by display_order.
    """
    __tablename__ = "gs_lms_external_resources"

    id = Column(Integer, primary_key=True, index=True)
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    section_label = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    source_name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    relevance_description = Column(String(150), nullable=True)
    display_order = Column(Integer, default=1, nullable=False)
    review_status = Column(String(20), default="DRAFT", nullable=False)

    # Relationships
    syllabus_node = relationship("GsLmsSyllabusNode")


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "GsLmsFunnelStepEnum",
    # Models
    "GsLmsFunnelProgress",
    "GsLmsReadingTime",
    "GsLmsRecallAttempt",
    "GsLmsMcqLabSession",
    "GsLmsMcqLabAttempt",
    "GsLmsWeaknessPattern",
    "GsLmsGrowthReport",
    "GsLmsSpacedRepSchedule",
    "GsLmsExternalResource",
]
