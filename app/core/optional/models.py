"""SQLAlchemy models for the UPSC Optional Subjects Platform — canonical
content/syllabus domain (design "Data Models" section).

These models are intentionally isolated from the GS Geography experience at
``/upsc/geography`` (Requirement 2 / design Property 9): nothing here imports
from or references GS Geography modules.

They register on the shared declarative ``Base`` (``app.db.session.Base``) so
that a single Alembic ``target_metadata`` continues to cover the whole schema.
Table names are namespaced with an ``optional_`` prefix to avoid collisions
with the existing MCQ domain (e.g. the pre-existing ``subjects`` table). The
canonical "Subject" entity from the design is implemented as
``OptionalSubject`` for the same reason.

Covers entities: Subject (OptionalSubject), Paper, Section, SyllabusNode,
ContentUnit, Diagram, SourceRef, Pyq, HiddenTopic.

Requirements: 3.1, 4.2, 4.3, 5.2, 12.1, 17.1, 17.4
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
)
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.db.governance import InstitutionalAuditMixin, SoftDeleteMixin


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SyllabusNodeTypeEnum(str, enum.Enum):
    """Kind of node within the weighted Syllabus_Tree (design entity notes)."""
    PAPER = "PAPER"
    SECTION = "SECTION"
    TOPIC = "TOPIC"
    SUBTOPIC = "SUBTOPIC"


class OptionalReviewStatusEnum(str, enum.Enum):
    """Content review state used to gate student display (R17.2, R17.3).

    "Not yet authored" is the absence of a REVIEWED ContentUnit; an authored
    but unreviewed unit is never shown to students (design Property 8).
    """
    UNREVIEWED = "UNREVIEWED"
    IN_REVIEW = "IN_REVIEW"
    REVIEWED = "REVIEWED"


class PaperLabelEnum(str, enum.Enum):
    """The two papers of a UPSC optional subject (R3.1)."""
    PAPER_I = "PAPER_I"
    PAPER_II = "PAPER_II"


class SectionLabelEnum(str, enum.Enum):
    """Sections within Paper I (R3.2)."""
    SECTION_A = "SECTION_A"
    SECTION_B = "SECTION_B"


# ---------------------------------------------------------------------------
# Subject / Paper / Section structure (R3)
# ---------------------------------------------------------------------------

class OptionalSubject(Base, InstitutionalAuditMixin):
    """A UPSC optional subject (one of 25). Canonical "Subject" entity.

    Named ``OptionalSubject`` to avoid colliding with the pre-existing MCQ
    ``Subject``/``subjects`` table on the shared metadata.
    """
    __tablename__ = "optional_subjects"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    # Per-subject framework config (papers/sections shape, enabled feature
    # modules, content availability) — Phase 2 readiness (R11, R19).
    config = Column(JSON, nullable=True)
    # Whether the subject meets the "complete" definition (R3.4, R3.5).
    is_complete = Column(Boolean, default=False, nullable=False)
    completeness_status = Column(JSON, nullable=True)

    papers = relationship(
        "Paper", back_populates="subject", cascade="all, delete-orphan"
    )
    pyqs = relationship("Pyq", back_populates="subject")


class Paper(Base, InstitutionalAuditMixin):
    """Paper I or Paper II of an optional subject (R3.1)."""
    __tablename__ = "optional_papers"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    label = Column(Enum(PaperLabelEnum), nullable=False)
    name = Column(String, nullable=False)  # human label e.g. "Paper I"
    display_order = Column(Integer, default=0, nullable=False)

    subject = relationship("OptionalSubject", back_populates="papers")
    sections = relationship(
        "Section", back_populates="paper", cascade="all, delete-orphan"
    )


class Section(Base, InstitutionalAuditMixin):
    """Section A or Section B within a Paper (R3.2, R3.3).

    Paper II is typically modelled as a single (default) section so that the
    Syllabus_Tree always hangs beneath a section uniformly.
    """
    __tablename__ = "optional_sections"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(
        Integer, ForeignKey("optional_papers.id"), nullable=False, index=True
    )
    label = Column(Enum(SectionLabelEnum), nullable=True)
    name = Column(String, nullable=False)  # human label e.g. "Section A"
    display_order = Column(Integer, default=0, nullable=False)

    paper = relationship("Paper", back_populates="sections")
    syllabus_nodes = relationship(
        "SyllabusNode", back_populates="section", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Weighted Syllabus_Tree (R12.1) — self-referencing tree
# ---------------------------------------------------------------------------

class SyllabusNode(Base, InstitutionalAuditMixin):
    """Self-referencing weighted syllabus tree node (design entity notes).

    Carries ``weight`` (basis for gap %), ``display_order``, ``node_type`` and
    ``review_status``. Children of a node refine the printed syllabus into
    topics/subtopics. ``official_phrasing`` preserves the exact printed
    syllabus wording surfaced per segment (R4.5).
    """
    __tablename__ = "optional_syllabus_nodes"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(
        Integer, ForeignKey("optional_sections.id"), nullable=True, index=True
    )
    parent_id = Column(
        Integer, ForeignKey("optional_syllabus_nodes.id"), nullable=True, index=True
    )
    title = Column(String, nullable=False)
    official_phrasing = Column(Text, nullable=True)
    node_type = Column(
        Enum(SyllabusNodeTypeEnum), default=SyllabusNodeTypeEnum.TOPIC, nullable=False
    )
    # Weight used to compute coverage / gap percentage (R12.1, R12.4).
    weight = Column(Float, default=0.0, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)
    review_status = Column(
        Enum(OptionalReviewStatusEnum),
        default=OptionalReviewStatusEnum.UNREVIEWED,
        nullable=False,
    )

    section = relationship("Section", back_populates="syllabus_nodes")
    parent = relationship(
        "SyllabusNode", remote_side=[id], back_populates="children"
    )
    children = relationship(
        "SyllabusNode", back_populates="parent", cascade="all, delete-orphan"
    )
    content_units = relationship(
        "ContentUnit", back_populates="syllabus_node", cascade="all, delete-orphan"
    )
    pyqs = relationship("Pyq", back_populates="topic_node")
    hidden_topics = relationship(
        "HiddenTopic", back_populates="syllabus_node", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Content units, diagrams, sources (R5, R17)
# ---------------------------------------------------------------------------

class ContentUnit(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """Deep-notes content for a syllabus node (R5.2).

    ``blocks`` holds the typed content blocks (para/points/callout/diagram)
    mirroring the existing ``geographyOptionalTypes.ts`` model. ``authored``
    and ``review_status`` make the design's "honest not-yet-authored" and
    review-gating behaviour representable (R5.4, R17.2, R17.3, Property 8).
    """
    __tablename__ = "optional_content_units"

    id = Column(Integer, primary_key=True, index=True)
    syllabus_node_id = Column(
        Integer, ForeignKey("optional_syllabus_nodes.id"), nullable=False, index=True
    )
    title = Column(String, nullable=True)
    # Typed content blocks: list of {type: para|points|callout|diagram, ...}
    blocks = Column(JSON, nullable=True)
    # Examiner keywords surfaced in the Read layer (R5.2).
    exam_keywords = Column(JSON, nullable=True)
    # Answer-language phrasing lines (R5.2).
    answer_language = Column(JSON, nullable=True)
    # Hidden topics authored inline with the unit (mirrors source TS model);
    # the normalized HiddenTopic table is the queryable, syllabus-filed form.
    hidden_topics = Column(JSON, nullable=True)
    # Honest authoring/review flags (R5.4, R17.2, R17.3).
    authored = Column(Boolean, default=False, nullable=False)
    review_status = Column(
        Enum(OptionalReviewStatusEnum),
        default=OptionalReviewStatusEnum.UNREVIEWED,
        nullable=False,
        index=True,
    )
    reviewed_at = Column(DateTime, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)

    syllabus_node = relationship("SyllabusNode", back_populates="content_units")
    diagrams = relationship(
        "Diagram", back_populates="content_unit", cascade="all, delete-orphan"
    )
    source_refs = relationship(
        "SourceRef", back_populates="content_unit", cascade="all, delete-orphan"
    )


class Diagram(Base, InstitutionalAuditMixin):
    """A diagram referenced by a stable ``diagram_id`` render-key.

    The 11 hand-drawn SVGs remain frontend React components; this row carries
    the stable id used to render them within the Read layer (R5.3, R18.2).
    """
    __tablename__ = "optional_diagrams"

    id = Column(Integer, primary_key=True, index=True)
    content_unit_id = Column(
        Integer, ForeignKey("optional_content_units.id"), nullable=True, index=True
    )
    # Stable render-key matching the frontend SVG component (e.g. "geo_d01").
    diagram_id = Column(String, index=True, nullable=False)
    title = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)

    content_unit = relationship("ContentUnit", back_populates="diagrams")


class SourceRef(Base, InstitutionalAuditMixin):
    """An authoritative source backing content accuracy (R17.1, R17.4)."""
    __tablename__ = "optional_source_refs"

    id = Column(Integer, primary_key=True, index=True)
    content_unit_id = Column(
        Integer, ForeignKey("optional_content_units.id"), nullable=True, index=True
    )
    title = Column(String, nullable=False)
    citation = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    source_type = Column(String, nullable=True)  # e.g. OFFICIAL_SYLLABUS, STANDARD_TEXT

    content_unit = relationship("ContentUnit", back_populates="source_refs")
    pyqs = relationship("Pyq", back_populates="source_ref")
    hidden_topics = relationship("HiddenTopic", back_populates="source_ref")


# ---------------------------------------------------------------------------
# PYQ corpus + hidden topics (R4, R6)
# ---------------------------------------------------------------------------

class Pyq(Base, InstitutionalAuditMixin, SoftDeleteMixin):
    """A previous-year question mapped to the syllabus tree (R4.2, R6).

    Carries ``year``/``paper``/``section`` for filtering, a link to the
    syllabus ``topic_node``, a ``beyond_syllabus`` flag (R4.3), and a source
    reference.
    """
    __tablename__ = "optional_pyqs"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("optional_subjects.id"), nullable=False, index=True
    )
    paper_id = Column(
        Integer, ForeignKey("optional_papers.id"), nullable=True, index=True
    )
    section_id = Column(
        Integer, ForeignKey("optional_sections.id"), nullable=True, index=True
    )
    topic_node_id = Column(
        Integer, ForeignKey("optional_syllabus_nodes.id"), nullable=True, index=True
    )
    source_ref_id = Column(
        Integer, ForeignKey("optional_source_refs.id"), nullable=True, index=True
    )
    year = Column(Integer, nullable=False, index=True)
    # Denormalized labels for fast year/paper/section sorting & filtering (R6).
    paper_label = Column(Enum(PaperLabelEnum), nullable=True, index=True)
    section_label = Column(Enum(SectionLabelEnum), nullable=True, index=True)
    question_text = Column(Text, nullable=False)
    marks = Column(Integer, nullable=True)
    # Theme appeared beyond the printed syllabus (R4.3).
    beyond_syllabus = Column(Boolean, default=False, nullable=False, index=True)
    # Review/honesty gate for PYQ rows (R17.2, R17.3, design Property 8).
    # Mirrors ContentUnit.review_status so the PYQ read API (task 7.2) can gate
    # unreviewed/draft questions exactly like content. Nullable so the column
    # can be added to an existing table without a backfill; the application
    # default and the seeder both stamp UNREVIEWED for new draft rows.
    review_status = Column(
        Enum(OptionalReviewStatusEnum),
        default=OptionalReviewStatusEnum.UNREVIEWED,
        nullable=True,
        index=True,
    )

    subject = relationship("OptionalSubject", back_populates="pyqs")
    paper = relationship("Paper")
    section = relationship("Section")
    topic_node = relationship("SyllabusNode", back_populates="pyqs")
    source_ref = relationship("SourceRef", back_populates="pyqs")


class HiddenTopic(Base, InstitutionalAuditMixin):
    """A theme asked beyond the printed syllabus, filed under a SyllabusNode
    with a rationale (R4.3)."""
    __tablename__ = "optional_hidden_topics"

    id = Column(Integer, primary_key=True, index=True)
    syllabus_node_id = Column(
        Integer, ForeignKey("optional_syllabus_nodes.id"), nullable=False, index=True
    )
    source_ref_id = Column(
        Integer, ForeignKey("optional_source_refs.id"), nullable=True, index=True
    )
    title = Column(String, nullable=False)
    rationale = Column(Text, nullable=True)

    syllabus_node = relationship("SyllabusNode", back_populates="hidden_topics")
    source_ref = relationship("SourceRef", back_populates="hidden_topics")


__all__ = [
    "SyllabusNodeTypeEnum",
    "OptionalReviewStatusEnum",
    "PaperLabelEnum",
    "SectionLabelEnum",
    "OptionalSubject",
    "Paper",
    "Section",
    "SyllabusNode",
    "ContentUnit",
    "Diagram",
    "SourceRef",
    "Pyq",
    "HiddenTopic",
]
