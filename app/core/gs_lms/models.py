"""SQLAlchemy models for the GS LMS Platform — canonical content/syllabus
domain (design "Data Models" section).

These models are intentionally isolated from the Optional Subjects platform at
``app.core.optional`` (design Key Decision 3: Domain isolation). Nothing here
imports from or references Optional modules.

They register on the shared declarative ``Base`` (``app.db.session.Base``) so
that a single Alembic ``target_metadata`` continues to cover the whole schema.
Table names are namespaced with a ``gs_lms_`` prefix. The syllabus tree mirrors
the Optional ``SyllabusNode`` pattern: self-referencing, weighted, review-gated.

Covers entities: GsLmsSyllabusNode, GsLmsContentSection, GsLmsPyq,
GsLmsMcqQuestion, and supporting enums.

Requirements: 1.4, 10.1, 10.4, 11.4
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Float,
    ForeignKey,
    Enum,
    JSON,
    DateTime,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin, SoftDeleteMixin
from app.core.gs.models import GsReviewStatusEnum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GsLmsNodeTypeEnum(str, enum.Enum):
    """Kind of node within the GS LMS syllabus tree."""
    MEGA_TOPIC = "MEGA_TOPIC"
    SUB_TOPIC = "SUB_TOPIC"
    LEAF_TOPIC = "LEAF_TOPIC"


class GsLmsExamTypeEnum(str, enum.Enum):
    """Exam type for Previous Year Questions."""
    PRELIMS = "PRELIMS"
    MAINS = "MAINS"


class GsLmsQuestionTypeEnum(str, enum.Enum):
    """Classification of MCQ/PYQ question patterns UPSC has historically used."""
    STATEMENT_BASED = "STATEMENT_BASED"
    MATCH_THE_FOLLOWING = "MATCH_THE_FOLLOWING"
    ASSERTION_REASON = "ASSERTION_REASON"
    MAP_BASED = "MAP_BASED"
    CAUSE_EFFECT = "CAUSE_EFFECT"
    CHRONOLOGICAL = "CHRONOLOGICAL"
    FACTUAL = "FACTUAL"


class GsLmsSectionLabelEnum(str, enum.Enum):
    """The five progressive-disclosure content sections per topic."""
    BASIC = "BASIC"
    ADVANCED = "ADVANCED"
    NCERT_LEVEL = "NCERT_LEVEL"
    CURRENT_AFFAIRS = "CURRENT_AFFAIRS"
    EXAMINER_TRAPS = "EXAMINER_TRAPS"


class GsLmsPaperEnum(str, enum.Enum):
    """GS Mains paper a question belongs to (R9.1)."""
    GS1 = "GS1"
    GS2 = "GS2"
    GS3 = "GS3"
    GS4 = "GS4"


class GsLmsAnswerModeEnum(str, enum.Enum):
    """How the student composed a descriptive answer (R10, R11)."""
    TYPED = "TYPED"
    HANDWRITTEN = "HANDWRITTEN"


class GsLmsAnswerAttemptStatusEnum(str, enum.Enum):
    """Lifecycle of a GS answer attempt through the evaluation pipeline."""
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Syllabus Tree (self-referencing weighted tree)
# ---------------------------------------------------------------------------

class GsLmsSyllabusNode(Base, InstitutionalAuditMixin):
    """Self-referencing weighted syllabus tree for GS Geography LMS.

    Mirrors the Optional ``SyllabusNode`` pattern: weighted nodes, display
    ordering, review-gated visibility, and a self-referencing parent chain.
    Bridges to existing ``GsDayLesson`` records via ``day_lesson_id`` FK on
    leaf nodes.
    """
    __tablename__ = "gs_lms_syllabus_nodes"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("gs_subjects.id"), nullable=False, index=True
    )
    parent_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=True, index=True
    )
    # Bridge to existing day-lesson system (Requirement 11.2).
    day_lesson_id = Column(
        Integer, ForeignKey("gs_day_lessons.id"), nullable=True, index=True
    )
    title = Column(String, nullable=False)
    node_type = Column(
        Enum(GsLmsNodeTypeEnum), nullable=False
    )
    # Weight used for coverage/gap calculation.
    weight = Column(Float, default=0.0, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    # Metadata justifying the chosen topic ordering (R1.2, R1.5).
    ordering_justification = Column(Text, nullable=True)
    # URL of the video lecture associated with this node (Phase 1 video integration).
    video_url = Column(Text, nullable=True)
    # JSON array of concept strings for concept-level discussion scoring (Phase 2).
    # e.g. ["plate tectonics", "continental drift", "seafloor spreading"]
    concept_checklist = Column(JSON, nullable=True)
    review_status = Column(
        Enum(GsReviewStatusEnum),
        default=GsReviewStatusEnum.UNREVIEWED,
        nullable=False,
    )

    # Relationships
    subject = relationship("GsSubject")
    parent = relationship(
        "GsLmsSyllabusNode", remote_side=[id], back_populates="children"
    )
    children = relationship(
        "GsLmsSyllabusNode", back_populates="parent", cascade="all, delete-orphan"
    )
    day_lesson = relationship("GsDayLesson")
    content_sections = relationship(
        "GsLmsContentSection",
        back_populates="syllabus_node",
        cascade="all, delete-orphan",
        order_by="GsLmsContentSection.display_order",
    )
    pyqs = relationship(
        "GsLmsPyq",
        back_populates="syllabus_node",
        cascade="all, delete-orphan",
    )
    mcq_questions = relationship(
        "GsLmsMcqQuestion",
        back_populates="syllabus_node",
        cascade="all, delete-orphan",
        order_by="GsLmsMcqQuestion.display_order",
    )


# ---------------------------------------------------------------------------
# Content Sections (progressive disclosure)
# ---------------------------------------------------------------------------

class GsLmsContentSection(Base, InstitutionalAuditMixin):
    """One of 4 progressive-disclosure sections per topic.

    Each leaf-level syllabus node has exactly four content sections:
    BASIC → ADVANCED → NCERT_LEVEL → EXAMINER_TRAPS, enforced by
    display_order (1-4).
    """
    __tablename__ = "gs_lms_content_sections"

    id = Column(Integer, primary_key=True, index=True)
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    section_label = Column(
        Enum(GsLmsSectionLabelEnum), nullable=False
    )
    title = Column(String, nullable=False)
    # Typed content blocks: [{type, content, ...}]
    blocks = Column(JSON, nullable=True)
    # 1-4, enforces section sequence.
    display_order = Column(Integer, nullable=False)
    review_status = Column(
        Enum(GsReviewStatusEnum),
        default=GsReviewStatusEnum.UNREVIEWED,
        nullable=False,
    )
    authored = Column(Boolean, default=False, nullable=False)

    # Relationships
    syllabus_node = relationship(
        "GsLmsSyllabusNode", back_populates="content_sections"
    )


# ---------------------------------------------------------------------------
# Previous Year Questions
# ---------------------------------------------------------------------------

class GsLmsPyq(Base, InstitutionalAuditMixin):
    """Previous Year Question for GS Geography (Prelims or Mains).

    Carries year, exam_type, question text, answer/explanation (revealed
    separately per student), and review-gate status.
    """
    __tablename__ = "gs_lms_pyqs"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("gs_subjects.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    exam_type = Column(Enum(GsLmsExamTypeEnum), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    # GS Mains paper discriminator (GS1–GS4); nullable (Prelims/free-form). R9.1
    gs_paper = Column(Enum(GsLmsPaperEnum), nullable=True, index=True)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    # Marks (relevant for Mains questions).
    marks = Column(Integer, nullable=True)
    question_type = Column(Enum(GsLmsQuestionTypeEnum), nullable=True)
    review_status = Column(
        Enum(GsReviewStatusEnum),
        default=GsReviewStatusEnum.UNREVIEWED,
        nullable=False,
        index=True,
    )

    # Relationships
    subject = relationship("GsSubject")
    syllabus_node = relationship("GsLmsSyllabusNode", back_populates="pyqs")


# ---------------------------------------------------------------------------
# MCQ Practice Questions
# ---------------------------------------------------------------------------

class GsLmsMcqQuestion(Base, InstitutionalAuditMixin):
    """MCQ practice question for sequential practice sessions.

    Each question belongs to a syllabus node and carries options (A-D),
    correct answer, explanation, question type classification, and
    display ordering for sequential presentation.
    """
    __tablename__ = "gs_lms_mcq_questions"

    id = Column(Integer, primary_key=True, index=True)
    syllabus_node_id = Column(
        Integer, ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False, index=True
    )
    question_text = Column(Text, nullable=False)
    # Options: [{label: "A", text: "..."}, ...]
    options = Column(JSON, nullable=False)
    correct_option = Column(String, nullable=False)  # "A", "B", "C", "D"
    explanation = Column(Text, nullable=True)
    question_type = Column(
        Enum(GsLmsQuestionTypeEnum), nullable=False
    )
    display_order = Column(Integer, default=0, nullable=False)
    review_status = Column(
        Enum(GsReviewStatusEnum),
        default=GsReviewStatusEnum.UNREVIEWED,
        nullable=False,
        index=True,
    )

    # Relationships
    syllabus_node = relationship(
        "GsLmsSyllabusNode", back_populates="mcq_questions"
    )


# ---------------------------------------------------------------------------
# Answer writing + evaluation (Mains descriptive answers)
# ---------------------------------------------------------------------------

class GsLmsAnswerAttempt(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A student's descriptive (Mains) answer attempt for a GS PYQ/practice
    question (R10, R11, R14).

    Mirrors the Optional ``AnswerAttempt`` shape with a ``gs_lms_`` prefix and
    FKs into the GS domain. Supports typed and handwritten (image) composition;
    handwritten drafts carry the confidence-gate fields (``ocr_confidence`` /
    ``review_acknowledged``). Ownership is scoped by ``student_id`` (R17).
    """
    __tablename__ = "gs_lms_answer_attempts"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Linked PYQ (nullable for free-form practice questions — R9.5).
    pyq_id = Column(
        Integer, ForeignKey("gs_lms_pyqs.id"), nullable=True, index=True
    )
    gs_paper = Column(Enum(GsLmsPaperEnum), nullable=True, index=True)
    # Denormalized prompt text (free-form practice or snapshot of the PYQ).
    question_text = Column(Text, nullable=True)
    # Marking scheme context (R7, R8).
    max_marks = Column(Integer, nullable=True)

    mode = Column(Enum(GsLmsAnswerModeEnum), nullable=False)
    status = Column(
        Enum(GsLmsAnswerAttemptStatusEnum),
        default=GsLmsAnswerAttemptStatusEnum.DRAFT,
        nullable=False,
        index=True,
    )

    # The full answer text fed to the evaluator (typed, or OCR/assembled).
    raw_text = Column(Text, nullable=True)
    # Provider confidence for handwritten OCR + the review-ack gate (R14).
    ocr_confidence = Column(Float, nullable=True)
    review_acknowledged = Column(Boolean, default=False, nullable=False)

    # Length-bias bookkeeping (R8.4).
    word_count = Column(Integer, nullable=True)
    word_limit = Column(Integer, nullable=True)

    # Provider/usage + cache bookkeeping (R18).
    provider_key = Column(String, nullable=True)
    token_usage = Column(Integer, nullable=True)
    content_hash = Column(String, nullable=True, index=True)

    # Relationships
    student = relationship("User")
    pyq = relationship("GsLmsPyq")
    images = relationship(
        "GsLmsAnswerSheetImage",
        back_populates="attempt",
        cascade="all, delete-orphan",
        order_by="GsLmsAnswerSheetImage.page_order",
    )
    report = relationship(
        "GsLmsEvaluationReport",
        back_populates="attempt",
        uselist=False,
        cascade="all, delete-orphan",
    )


class GsLmsAnswerSheetImage(Base, InstitutionalAuditMixin):
    """One uploaded page of a handwritten answer (R11, R12, R17).

    One row per page so pages can be ordered, re-ordered, audited, and
    vision-graded. ``media_ref`` is a SERVER-authored object-storage key (never
    client-supplied — R11.2). Ownership is scoped by ``student_id`` (R17.3).
    """
    __tablename__ = "gs_lms_answer_sheet_images"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(
        Integer, ForeignKey("gs_lms_answer_attempts.id"), nullable=False, index=True
    )
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Server-authored MediaStore key (R11.2).
    media_ref = Column(String, nullable=False)
    # Ascending assembly order (R12.1/R12.2).
    page_order = Column(Integer, nullable=False)
    content_type = Column(String, nullable=True)
    uploaded_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    attempt = relationship("GsLmsAnswerAttempt", back_populates="images")
    student = relationship("User")


class GsLmsEvaluationReport(Base, InstitutionalAuditMixin):
    """A complete evaluation report, 1:1 with a GsLmsAnswerAttempt (R7, R13, R16).

    Preserves the report-completeness honesty invariant (``incomplete_sections``;
    empty => complete) and adds marks-normalized scoring, factual-accuracy +
    value-addition payloads, and the human-override audit columns (R16).
    """
    __tablename__ = "gs_lms_evaluation_reports"

    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(
        Integer,
        ForeignKey("gs_lms_answer_attempts.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    sections = Column(JSON, nullable=True)
    incomplete_sections = Column(JSON, default=list, nullable=False)
    overall_score = Column(Float, nullable=True)
    # Marks-normalized scoring (R7).
    marks_awarded = Column(Float, nullable=True)
    max_marks = Column(Integer, nullable=True)
    # Factual-accuracy + value-addition payloads (R7.5/R7.6, R13.3).
    factual_accuracy = Column(JSON, nullable=True)
    value_addition = Column(JSON, nullable=True)
    # Human-in-the-loop override + audit (R16). ``original_report`` preserves
    # the machine output unchanged when an evaluator overrides it.
    original_report = Column(JSON, nullable=True)
    overridden_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    overridden_at = Column(DateTime, nullable=True)

    attempt = relationship("GsLmsAnswerAttempt", back_populates="report")

    @property
    def is_complete(self) -> bool:
        """A report is complete only when no sections are missing (Property 6)."""
        return not (self.incomplete_sections or [])


__all__ = [
    # Enums
    "GsLmsNodeTypeEnum",
    "GsLmsExamTypeEnum",
    "GsLmsQuestionTypeEnum",
    "GsLmsSectionLabelEnum",
    "GsLmsPaperEnum",
    "GsLmsAnswerModeEnum",
    "GsLmsAnswerAttemptStatusEnum",
    # Models
    "GsLmsSyllabusNode",
    "GsLmsContentSection",
    "GsLmsPyq",
    "GsLmsMcqQuestion",
    "GsLmsAnswerAttempt",
    "GsLmsAnswerSheetImage",
    "GsLmsEvaluationReport",
]
