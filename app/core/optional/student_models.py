"""SQLAlchemy models for the UPSC Optional Subjects Platform — student
activity domain (design "Data Models" section).

This module complements ``app.core.optional.models`` (the canonical
content/syllabus domain) with the student-facing activity entities:
subject selection, answer attempts + evaluation reports, the segmented
Recall-LMS (video segments, concept checklists, recall sessions/turns), and
progress/coverage tracking.

Design references:
- "Answer-evaluation pipeline" — AnswerAttempt + EvaluationReport fields back
  the typed/spoken/handwritten flow and confidence gating.
- "Recall-LMS loop" — VideoSegment/ConceptPoint/RecallSession/RecallTurn back
  concept-match scoring, adaptive hinting and explainability.
- "Gap/progress" — ProgressEvent + Coverage back weighted coverage.
- Correctness Properties: P3/P4/P5 (recall scoring), P6 (report completeness
  honesty), P10 (ownership).

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.

Every student-owned record carries the student FK (``users.id``) so ownership
can be authorized against the requesting student (design Property 10 / R15.4).
Models register on the shared declarative ``Base`` and use the ``optional_``
table-name prefix, mirroring ``app.core.optional.models``.

Requirements: 1.3, 9.5, 12.2, 13.5, 14.5, 15.1, 15.4
"""

from datetime import datetime, timezone
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Float,
    Enum,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin, SoftDeleteMixin

# Import the content-domain enums so denormalized labels stay consistent with
# the canonical models (single source of truth for paper/section labels).
from app.core.optional.models import PaperLabelEnum, SectionLabelEnum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnswerModeEnum(str, enum.Enum):
    """How the student composed the answer (R8.1, R8.2, R9.1)."""
    TYPED = "TYPED"
    SPOKEN = "SPOKEN"
    HANDWRITTEN = "HANDWRITTEN"


class AnswerAttemptStatusEnum(str, enum.Enum):
    """Lifecycle of an answer attempt through the evaluation pipeline."""
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    EVALUATED = "EVALUATED"
    FAILED = "FAILED"


class RecallSessionStatusEnum(str, enum.Enum):
    """Lifecycle of a recall run over a video segment (R13)."""
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class ProgressEventTypeEnum(str, enum.Enum):
    """Kinds of tracked activity that count toward coverage (R12.2).

    A syllabus node becomes "covered" when one of these is recorded against it
    (design Gap/progress section).
    """
    READ_COMPLETE = "READ_COMPLETE"
    PRACTICE_PASS = "PRACTICE_PASS"
    RECALL_THRESHOLD = "RECALL_THRESHOLD"


# ---------------------------------------------------------------------------
# Subject selection (R1.3)
# ---------------------------------------------------------------------------

class SubjectSelection(Base, InstitutionalAuditMixin):
    """Links a student (user) to a selected OptionalSubject (R1.3).

    A student may change their selection over time; ``is_active`` marks the
    current selection. "One active selection per student" is enforced at the
    application/migration layer (a partial unique index on
    ``(student_id) WHERE is_active``); the history rows are retained for audit.
    """
    __tablename__ = "optional_subject_selections"

    id = Column(Integer, primary_key=True, index=True)
    # Student/user FK for ownership checks (Property 10 / R15.4).
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    selected_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    student = relationship("User")
    subject = relationship("OptionalSubject")


# ---------------------------------------------------------------------------
# Answer writing + evaluation (R8, R9)
# ---------------------------------------------------------------------------

class AnswerAttempt(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A student's answer attempt for a subject/topic (R8, R9).

    Supports the three composition modes (typed/spoken/handwritten). For
    spoken/handwritten input, the source media is retained via
    ``source_media_ref`` (object-storage key) along with the provider
    confidence (``stt_confidence`` / ``ocr_confidence``) that drives the
    low-confidence review/correction gate (design "Confidence gating", P7).
    """
    __tablename__ = "optional_answer_attempts"

    id = Column(Integer, primary_key=True, index=True)
    # Student/user FK for ownership checks (Property 10 / R15.4).
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    # Topic the answer addresses; nullable for free-form attempts.
    topic_node_id = Column(
        Integer, ForeignKey("optional_syllabus_nodes.id"), nullable=True, index=True
    )

    mode = Column(Enum(AnswerModeEnum), nullable=False)
    status = Column(
        Enum(AnswerAttemptStatusEnum),
        default=AnswerAttemptStatusEnum.DRAFT,
        nullable=False,
        index=True,
    )

    # Question being answered (denormalized prompt text for self-contained
    # attempts); optionally links to a PYQ.
    question_text = Column(Text, nullable=True)
    pyq_id = Column(
        Integer, ForeignKey("optional_pyqs.id"), nullable=True, index=True
    )

    # The full answer text fed to the evaluator (post OCR/STT/typing).
    raw_text = Column(Text, nullable=True)
    # Structured typed composition (R8.1) — optional intro/body/conclusion.
    intro_text = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    conclusion_text = Column(Text, nullable=True)

    # Object-storage key for the spoken audio / handwritten image (R8.2, R9.1).
    source_media_ref = Column(String, nullable=True)
    # Provider confidences (nullable: only set for the relevant mode).
    ocr_confidence = Column(Float, nullable=True)
    stt_confidence = Column(Float, nullable=True)

    student = relationship("User")
    subject = relationship("OptionalSubject")
    topic_node = relationship("SyllabusNode")
    pyq = relationship("Pyq")
    report = relationship(
        "EvaluationReport",
        back_populates="attempt",
        uselist=False,
        cascade="all, delete-orphan",
    )


class EvaluationReport(Base, InstitutionalAuditMixin):
    """A complete evaluation report, 1:1 with an AnswerAttempt (R9.2, R9.5).

    ``sections`` holds the fixed set of required report sections as JSON;
    ``incomplete_sections`` lists exactly the sections that could not be
    produced. A report is "complete" only when ``incomplete_sections`` is
    empty — this makes report-completeness honesty representable (design
    Property 6 / R9.4). Persisted and associated with the student (R9.5).
    """
    __tablename__ = "optional_evaluation_reports"

    id = Column(Integer, primary_key=True, index=True)
    # 1:1 with the answer attempt (unique FK).
    attempt_id = Column(
        Integer,
        ForeignKey("optional_answer_attempts.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Denormalized owner for direct ownership filtering (Property 10 / R15.4).
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    # The required report sections, keyed by section name.
    sections = Column(JSON, nullable=True)
    # Sections that could not be produced; empty list => complete (Property 6).
    incomplete_sections = Column(JSON, default=list, nullable=False)
    # Optional overall/parameter scores surfaced to the student.
    overall_score = Column(Float, nullable=True)

    attempt = relationship("AnswerAttempt", back_populates="report")
    student = relationship("User")

    @property
    def is_complete(self) -> bool:
        """A report is complete only when no sections are missing (Property 6).

        Treats a null/empty ``incomplete_sections`` as complete; any listed
        section makes the report incomplete.
        """
        return not (self.incomplete_sections or [])


# ---------------------------------------------------------------------------
# Recall-LMS: segmented video + concept checklist (R13, R14)
# ---------------------------------------------------------------------------

class VideoSegment(Base, InstitutionalAuditMixin):
    """An ordered part of a video lesson for a subject/topic (R13.1).

    Lessons are delivered as ordered segments rather than one continuous file;
    ``segment_order`` defines the sequence. The segment script/transcript is
    retained so anti-gaming checks can reject verbatim echoes (P5).
    """
    __tablename__ = "optional_video_segments"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    # Topic the segment teaches; nullable for subject-level intros.
    topic_node_id = Column(
        Integer, ForeignKey("optional_syllabus_nodes.id"), nullable=True, index=True
    )
    title = Column(String, nullable=False)
    # Ordered position within the lesson (R13.1).
    segment_order = Column(Integer, default=0, nullable=False, index=True)
    video_ref = Column(String, nullable=True)  # object-storage key / URL
    duration_seconds = Column(Integer, nullable=True)
    # Segment script/transcript — basis for anti-gaming verbatim rejection (P5).
    script = Column(Text, nullable=True)

    subject = relationship("OptionalSubject")
    topic_node = relationship("SyllabusNode")
    concept_points = relationship(
        "ConceptPoint",
        back_populates="video_segment",
        cascade="all, delete-orphan",
        order_by="ConceptPoint.display_order",
    )
    recall_sessions = relationship(
        "RecallSession",
        back_populates="video_segment",
        cascade="all, delete-orphan",
    )


class ConceptPoint(Base, InstitutionalAuditMixin):
    """An author-defined concept checklist item for a VideoSegment (R14.1).

    Each concept carries a ``weight``; the weights of a segment's concept
    points sum to 1.0 and form the basis of the recall score
    (``recall_score = Σ weight × match_factor``, design Recall scoring / P3).
    """
    __tablename__ = "optional_concept_points"

    id = Column(Integer, primary_key=True, index=True)
    video_segment_id = Column(
        Integer, ForeignKey("optional_video_segments.id"), nullable=False, index=True
    )
    text = Column(Text, nullable=False)
    # Contribution of this concept to the recall score; weights per segment
    # sum to 1.0 (R14.1, basis of scoring).
    weight = Column(Float, default=0.0, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)

    video_segment = relationship("VideoSegment", back_populates="concept_points")


class RecallSession(Base, InstitutionalAuditMixin):
    """A student's recall run over a VideoSegment (R13).

    Aggregates the ordered turns of the discussion loop and caches the latest
    cumulative ``recall_score`` (0..1) for the session.
    """
    __tablename__ = "optional_recall_sessions"

    id = Column(Integer, primary_key=True, index=True)
    # Student/user FK for ownership checks (Property 10 / R15.4).
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    video_segment_id = Column(
        Integer, ForeignKey("optional_video_segments.id"), nullable=False, index=True
    )
    status = Column(
        Enum(RecallSessionStatusEnum),
        default=RecallSessionStatusEnum.IN_PROGRESS,
        nullable=False,
        index=True,
    )
    # Latest cumulative recall score in [0, 1] (P3).
    recall_score = Column(Float, default=0.0, nullable=False)
    started_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at = Column(DateTime, nullable=True)

    student = relationship("User")
    video_segment = relationship("VideoSegment", back_populates="recall_sessions")
    turns = relationship(
        "RecallTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="RecallTurn.turn_order",
    )


class RecallTurn(Base, InstitutionalAuditMixin):
    """A single turn within a recall session (R13.5, R14.5).

    Stores the recorded audio reference and transcript, the matched/missed
    concepts (the explainability payload, R14.5), the turn's ``recall_score``,
    and any Socratic ``hint_given`` (nullable; only set when score < 100%).
    """
    __tablename__ = "optional_recall_turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("optional_recall_sessions.id"), nullable=False, index=True
    )
    turn_order = Column(Integer, default=0, nullable=False, index=True)

    # Recorded spoken response + transcript (R13.5).
    audio_ref = Column(String, nullable=True)  # object-storage key
    transcript = Column(Text, nullable=True)

    # Explainability: which concepts were recalled vs not (R14.5).
    matched_concepts = Column(JSON, default=list, nullable=False)
    missed_concepts = Column(JSON, default=list, nullable=False)
    # This turn's recall score in [0, 1] (P3).
    recall_score = Column(Float, default=0.0, nullable=False)
    # Adaptive Socratic hint targeting a missed concept; null when none given.
    hint_given = Column(Text, nullable=True)

    session = relationship("RecallSession", back_populates="turns")


# ---------------------------------------------------------------------------
# Progress + coverage (R12)
# ---------------------------------------------------------------------------

class ProgressEvent(Base, InstitutionalAuditMixin):
    """A tracked activity recorded against a syllabus node (R12.2).

    Read completion, practice pass, or recall-threshold events mark a node as
    "covered"; these feed the weighted coverage rollup (design Gap/progress).
    """
    __tablename__ = "optional_progress_events"

    id = Column(Integer, primary_key=True, index=True)
    # Student/user FK for ownership checks (Property 10 / R15.4).
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    syllabus_node_id = Column(
        Integer, ForeignKey("optional_syllabus_nodes.id"), nullable=False, index=True
    )
    event_type = Column(Enum(ProgressEventTypeEnum), nullable=False, index=True)
    # Optional measured value (e.g. recall/practice score) for thresholding.
    value = Column(Float, nullable=True)
    event_metadata = Column(JSON, nullable=True)
    occurred_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    student = relationship("User")
    subject = relationship("OptionalSubject")
    syllabus_node = relationship("SyllabusNode")


class Coverage(Base, InstitutionalAuditMixin):
    """Rolled-up coverage cache per student + subject (R12).

    Caches the covered weight and the derived covered%/remaining% so the gap
    panel reads without recomputing the whole tree. Bounds and exactness
    (``0 ≤ covered% ≤ 100`` and ``covered% + remaining% = 100``) are enforced
    by the computation/property tests (design Property 2).
    """
    __tablename__ = "optional_coverage"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_optional_coverage_student_subject"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Student/user FK for ownership checks (Property 10 / R15.4).
    student_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    # Sum of weights of covered nodes (numerator of covered%).
    covered_weight = Column(Float, default=0.0, nullable=False)
    covered_percent = Column(Float, default=0.0, nullable=False)
    remaining_percent = Column(Float, default=100.0, nullable=False)
    last_computed_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    student = relationship("User")
    subject = relationship("OptionalSubject")


__all__ = [
    # Enums
    "AnswerModeEnum",
    "AnswerAttemptStatusEnum",
    "RecallSessionStatusEnum",
    "ProgressEventTypeEnum",
    # Models
    "SubjectSelection",
    "AnswerAttempt",
    "EvaluationReport",
    "VideoSegment",
    "ConceptPoint",
    "RecallSession",
    "RecallTurn",
    "ProgressEvent",
    "Coverage",
]
