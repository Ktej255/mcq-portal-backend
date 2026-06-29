"""SQLAlchemy models for the Daily Current Affairs Platform.

All tables use the `ca_` prefix. Domain isolation: nothing here imports from
`app.core.optional`. Models register on the shared declarative `Base`.

Requirements: 14.1, 14.2, 14.3, 14.5, 14.6
"""

from __future__ import annotations

from datetime import datetime, date, timezone

from sqlalchemy import (
    Column,
    Index,
    Integer,
    Float,
    String,
    Text,
    Boolean,
    DateTime,
    Date,
    JSON,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin, SoftDeleteMixin


# ---------------------------------------------------------------------------
# CA_Items — Core current affairs content
# ---------------------------------------------------------------------------

class CAItem(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A single current affairs item with all structured content."""
    __tablename__ = "ca_items"
    __table_args__ = (
        Index("ix_ca_items_publish_date", "publish_date"),
        Index("ix_ca_items_subject", "subject"),
        Index("ix_ca_items_review_status", "review_status"),
        CheckConstraint(
            "relevance_score >= 1 AND relevance_score <= 5",
            name="ck_ca_items_relevance_range"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    publish_date = Column(Date, nullable=False)
    subject = Column(String(30), nullable=False)
    secondary_subjects = Column(JSON, default=list)
    gs_paper = Column(String(5), nullable=False)
    exam_relevance = Column(String(10), nullable=False)
    video_url = Column(String(500), nullable=True)
    content_blocks = Column(JSON, nullable=False, default=list)
    upsc_statement_frames = Column(JSON, nullable=True)
    so_what_analysis = Column(JSON, nullable=True)
    source_authority = Column(String(15), nullable=False, default="standard")
    relevance_score = Column(Integer, nullable=False, default=3)
    review_status = Column(String(15), nullable=False, default="DRAFT")

    # Relationships
    mcqs = relationship("CAMcq", back_populates="ca_item", cascade="all, delete-orphan")
    mains_questions = relationship("CAMainsQuestion", back_populates="ca_item", cascade="all, delete-orphan")
    thread_associations = relationship("CAThreadItem", back_populates="ca_item")
    syllabus_links = relationship("CASyllabusLink", back_populates="ca_item", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# CA_Threads — Chronological topic groupings
# ---------------------------------------------------------------------------

class CAThread(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A chronological grouping of related CA items tracking topic evolution."""
    __tablename__ = "ca_threads"
    __table_args__ = (
        Index("ix_ca_threads_subject", "primary_subject"),
        Index("ix_ca_threads_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    primary_subject = Column(String(30), nullable=False)
    status = Column(String(15), nullable=False, default="active")
    direction = Column(String(20), nullable=True)
    start_date = Column(Date, nullable=False)

    # Relationships
    item_associations = relationship(
        "CAThreadItem", back_populates="thread",
        cascade="all, delete-orphan",
        order_by="CAThreadItem.sequence_order"
    )


# ---------------------------------------------------------------------------
# CA_Thread_Items — Junction table (many-to-many with metadata)
# ---------------------------------------------------------------------------

class CAThreadItem(Base, InstitutionalAuditMixin):
    """Junction: CA item membership in a thread with sequence and causality."""
    __tablename__ = "ca_thread_items"
    __table_args__ = (
        UniqueConstraint("thread_id", "item_id", name="uq_ca_thread_item"),
        CheckConstraint("sequence_order >= 1", name="ck_ca_thread_item_seq"),
    )

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("ca_threads.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=False, index=True)
    sequence_order = Column(Integer, nullable=False)
    causality_direction = Column(String(15), nullable=True)
    causality_target_item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=True)

    # Relationships
    thread = relationship("CAThread", back_populates="item_associations")
    ca_item = relationship("CAItem", foreign_keys=[item_id], back_populates="thread_associations")
    causality_target = relationship("CAItem", foreign_keys=[causality_target_item_id])


# ---------------------------------------------------------------------------
# CA_MCQs — MCQ questions attached to CA items
# ---------------------------------------------------------------------------

class CAMcq(Base, InstitutionalAuditMixin):
    """MCQ question attached to a CA item (max 10 per item)."""
    __tablename__ = "ca_mcqs"

    id = Column(Integer, primary_key=True, index=True)
    ca_item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(30), nullable=False)
    options = Column(JSON, nullable=False)
    correct_answer = Column(String(5), nullable=False)
    explanation = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=1)

    # Relationships
    ca_item = relationship("CAItem", back_populates="mcqs")


# ---------------------------------------------------------------------------
# CA_Mains_Questions — Mains questions attached to CA items
# ---------------------------------------------------------------------------

class CAMainsQuestion(Base, InstitutionalAuditMixin):
    """Mains practice question attached to a CA item (max 3 per item)."""
    __tablename__ = "ca_mains_questions"

    id = Column(Integer, primary_key=True, index=True)
    ca_item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    gs_paper = Column(String(5), nullable=False)
    marks = Column(Integer, nullable=False)
    word_limit = Column(Integer, nullable=False)
    model_answer = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=1)

    # Relationships
    ca_item = relationship("CAItem", back_populates="mains_questions")


# ---------------------------------------------------------------------------
# CA_Student_Progress — Per-student, per-item funnel progress
# ---------------------------------------------------------------------------

class CAStudentProgress(Base, InstitutionalAuditMixin):
    """Student's funnel progress and completion for a CA item."""
    __tablename__ = "ca_student_progress"
    __table_args__ = (
        UniqueConstraint("student_id", "ca_item_id", name="uq_ca_student_progress"),
        CheckConstraint(
            "current_step >= 1 AND current_step <= 5",
            name="ck_ca_progress_step_range"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ca_item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=False, index=True)
    current_step = Column(Integer, nullable=False, default=1)
    completed_steps = Column(JSON, default=list)
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    mcq_score = Column(Float, nullable=True)
    mcq_attempts = Column(JSON, nullable=True)
    mains_attempted = Column(Boolean, default=False)
    mains_score = Column(Float, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_activity_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    student = relationship("User")
    ca_item = relationship("CAItem")


# ---------------------------------------------------------------------------
# CA_Syllabus_Links — Bidirectional CA ↔ Syllabus node links
# ---------------------------------------------------------------------------

class CASyllabusLink(Base, InstitutionalAuditMixin):
    """Link between a CA item and a GS LMS syllabus node (max 3 per item)."""
    __tablename__ = "ca_syllabus_links"
    __table_args__ = (
        UniqueConstraint("ca_item_id", "syllabus_node_id", name="uq_ca_syllabus_link"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ca_item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=False, index=True)
    syllabus_node_id = Column(Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True)
    link_type = Column(String(20), nullable=False, default="primary")

    # Relationships
    ca_item = relationship("CAItem", back_populates="syllabus_links")


# ---------------------------------------------------------------------------
# CA_Causality_Links — Directional impact connections between items
# ---------------------------------------------------------------------------

class CACausalityLink(Base, InstitutionalAuditMixin):
    """Directional causality link between two CA items."""
    __tablename__ = "ca_causality_links"
    __table_args__ = (
        UniqueConstraint("source_item_id", "target_item_id", name="uq_ca_causality"),
        CheckConstraint("source_item_id != target_item_id", name="ck_ca_causality_no_self"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=False, index=True)
    target_item_id = Column(Integer, ForeignKey("ca_items.id"), nullable=False, index=True)
    impact_type = Column(String(100), nullable=False)
    impact_description = Column(Text, nullable=True)
    source_gs_paper = Column(String(5), nullable=True)
    target_gs_paper = Column(String(5), nullable=True)

    # Relationships
    source_item = relationship("CAItem", foreign_keys=[source_item_id])
    target_item = relationship("CAItem", foreign_keys=[target_item_id])


# ---------------------------------------------------------------------------
# CA_Revision_Schedules — Spaced repetition for CA
# ---------------------------------------------------------------------------

class CARevisionSchedule(Base, InstitutionalAuditMixin):
    """CA-specific spaced repetition schedule entries."""
    __tablename__ = "ca_revision_schedules"
    __table_args__ = (
        Index("ix_ca_revision_student_due", "student_id", "due_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quiz_type = Column(String(15), nullable=False)
    due_date = Column(Date, nullable=False)
    mcq_count = Column(Integer, nullable=False)
    source_item_ids = Column(JSON, nullable=False)
    score = Column(Float, nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    student = relationship("User")


# ---------------------------------------------------------------------------
# CA_Audit_Log — Admin content change tracking
# ---------------------------------------------------------------------------

class CAAuditLog(Base):
    """Audit trail for all admin content changes."""
    __tablename__ = "ca_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(30), nullable=False)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)
    changes = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    admin = relationship("User")


# ---------------------------------------------------------------------------
# CA_Monthly_Compilations — Generated monthly digests
# ---------------------------------------------------------------------------

class CAMonthlyCompilation(Base, InstitutionalAuditMixin):
    """Monthly compilation of CA items for offline revision."""
    __tablename__ = "ca_monthly_compilations"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(Date, nullable=False, unique=True)
    title = Column(String(200), nullable=False)
    total_items = Column(Integer, nullable=False)
    sections = Column(JSON, nullable=False)
    review_status = Column(String(15), nullable=False, default="DRAFT")
    pdf_storage_ref = Column(String(500), nullable=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "CAItem",
    "CAThread",
    "CAThreadItem",
    "CAMcq",
    "CAMainsQuestion",
    "CAStudentProgress",
    "CASyllabusLink",
    "CACausalityLink",
    "CARevisionSchedule",
    "CAAuditLog",
    "CAMonthlyCompilation",
]
