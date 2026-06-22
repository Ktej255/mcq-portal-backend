"""Content read endpoints for the Optional Subjects Platform (Task 6.1).

These endpoints make the Read layer **backend-served**: the frontend
``ReadView`` fetches the syllabus tree and per-topic deep-notes content from
here instead of reading the legacy frontend TypeScript modules (which are
deleted in a later gated task — 6.4).

Routes (mounted under ``/api/v1/optional``; auth-gated at the package router):

* ``GET /{slug}/syllabus-tree``
    The subject's papers → sections → topics → subtopics tree. Each node
    carries its ``review_status`` and an ``authored`` honesty flag.

* ``GET /{slug}/topics/{node_id}/content``
    A syllabus node's reviewed/authored ``ContentUnit`` (typed ``blocks``,
    ``exam_keywords``, ``answer_language``, ``hidden_topics``) plus its
    ``Diagram`` rows, recursively including child subtopics.

Honesty gate (design Property 8 / R5.4, R17.2, R17.3): a node is only reported
as ``authored`` — and its ``content`` only populated — when it has a
``ContentUnit`` that is BOTH ``authored=True`` AND ``review_status==REVIEWED``
and not soft-deleted. Otherwise ``authored`` is ``False`` and ``content`` is
``None`` so the UI shows an honest "not yet authored" state rather than
treating empty-as-complete.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import (
    OptionalSubject,
    Paper,
    Section,
    SyllabusNode,
    ContentUnit,
    Diagram,
    OptionalReviewStatusEnum,
)
from app.api.v1.optional.schemas import (
    SyllabusNodeOut,
    SyllabusSectionOut,
    SyllabusPaperOut,
    SyllabusTreeOut,
    DiagramOut,
    ContentUnitOut,
    NodeContentOut,
    SyllabusTrendPointOut,
    SyllabusHiddenTopicOut,
    SyllabusSegmentAnalysisOut,
    SyllabusAnalysisOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Honesty gate helpers (design Property 8 / R5.4)
# ---------------------------------------------------------------------------

def _reviewed_authored_unit(node: SyllabusNode) -> Optional[ContentUnit]:
    """Return the node's first reviewed+authored, non-deleted ContentUnit.

    This is the single source of truth for the honesty gate: content is only
    ever surfaced to students when it is genuinely authored AND reviewed.
    Returns ``None`` when no such unit exists (i.e. "not yet authored").
    """
    candidates = [
        cu
        for cu in node.content_units
        if cu.authored
        and cu.review_status == OptionalReviewStatusEnum.REVIEWED
        and not getattr(cu, "is_deleted", False)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda cu: (cu.display_order, cu.id))
    return candidates[0]


def _is_authored(node: SyllabusNode) -> bool:
    return _reviewed_authored_unit(node) is not None


def _diagram_out(diagram: Diagram) -> DiagramOut:
    return DiagramOut(
        diagram_id=diagram.diagram_id,
        title=diagram.title,
        caption=diagram.caption,
        display_order=diagram.display_order,
    )


def _content_unit_out(unit: ContentUnit) -> ContentUnitOut:
    diagrams = sorted(unit.diagrams, key=lambda d: (d.display_order, d.id))
    return ContentUnitOut(
        id=unit.id,
        title=unit.title,
        blocks=unit.blocks,
        exam_keywords=unit.exam_keywords,
        answer_language=unit.answer_language,
        hidden_topics=unit.hidden_topics,
        review_status=unit.review_status.value
        if hasattr(unit.review_status, "value")
        else str(unit.review_status),
        display_order=unit.display_order,
        diagrams=[_diagram_out(d) for d in diagrams],
    )


def _review_status_value(node: SyllabusNode) -> str:
    rs = node.review_status
    return rs.value if hasattr(rs, "value") else str(rs)


def _node_type_value(node: SyllabusNode) -> str:
    nt = node.node_type
    return nt.value if hasattr(nt, "value") else str(nt)


# ---------------------------------------------------------------------------
# Syllabus tree builders
# ---------------------------------------------------------------------------

def _syllabus_node_out(node: SyllabusNode) -> SyllabusNodeOut:
    children = sorted(node.children, key=lambda n: (n.display_order, n.id))
    return SyllabusNodeOut(
        node_id=node.id,
        title=node.title,
        node_type=_node_type_value(node),
        review_status=_review_status_value(node),
        authored=_is_authored(node),
        weight=node.weight,
        display_order=node.display_order,
        official_phrasing=node.official_phrasing,
        children=[_syllabus_node_out(c) for c in children],
    )


def _node_content_out(node: SyllabusNode, *, include_children: bool = True) -> NodeContentOut:
    unit = _reviewed_authored_unit(node)
    children_out: list[NodeContentOut] = []
    if include_children:
        children = sorted(node.children, key=lambda n: (n.display_order, n.id))
        children_out = [_node_content_out(c) for c in children]
    return NodeContentOut(
        node_id=node.id,
        title=node.title,
        node_type=_node_type_value(node),
        review_status=_review_status_value(node),
        official_phrasing=node.official_phrasing,
        authored=unit is not None,
        content=_content_unit_out(unit) if unit is not None else None,
        children=children_out,
    )


def _get_subject_or_404(db: Session, slug: str) -> OptionalSubject:
    subject = (
        db.query(OptionalSubject)
        .filter(OptionalSubject.slug == slug)
        .one_or_none()
    )
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optional subject '{slug}' not found",
        )
    return subject


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/{slug}/syllabus-tree")
def get_syllabus_tree(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's full syllabus tree with honesty flags (R5.1)."""
    subject = _get_subject_or_404(db, slug)

    papers_out: list[SyllabusPaperOut] = []
    papers = sorted(subject.papers, key=lambda p: (p.display_order, p.id))
    for paper in papers:
        sections_out: list[SyllabusSectionOut] = []
        sections = sorted(paper.sections, key=lambda s: (s.display_order, s.id))
        for section in sections:
            # Top-level syllabus nodes (TOPIC) hang directly off a section;
            # subtopics are nested as children and rendered recursively.
            top_nodes = sorted(
                [n for n in section.syllabus_nodes if n.parent_id is None],
                key=lambda n: (n.display_order, n.id),
            )
            sections_out.append(
                SyllabusSectionOut(
                    section_id=section.id,
                    label=section.label.value
                    if section.label is not None and hasattr(section.label, "value")
                    else (str(section.label) if section.label is not None else None),
                    name=section.name,
                    display_order=section.display_order,
                    nodes=[_syllabus_node_out(n) for n in top_nodes],
                )
            )
        papers_out.append(
            SyllabusPaperOut(
                paper_id=paper.id,
                label=paper.label.value
                if hasattr(paper.label, "value")
                else str(paper.label),
                name=paper.name,
                display_order=paper.display_order,
                sections=sections_out,
            )
        )

    tree = SyllabusTreeOut(slug=subject.slug, name=subject.name, papers=papers_out)
    return StandardResponse(
        success=True,
        message="Syllabus tree retrieved",
        data=tree,
    )


@router.get("/{slug}/topics/{node_id}/content")
def get_topic_content(
    slug: str,
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return a syllabus node's reviewed content + child subtopics (R5.2).

    Applies the honesty gate (design Property 8): only reviewed+authored
    content is returned; not-yet-authored nodes are flagged, never faked.
    """
    subject = _get_subject_or_404(db, slug)

    node = (
        db.query(SyllabusNode)
        .filter(SyllabusNode.id == node_id)
        .one_or_none()
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Syllabus node {node_id} not found",
        )

    # Guard: the node must belong to the requested subject (isolation + safety).
    if not _node_belongs_to_subject(db, node, subject.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Syllabus node {node_id} does not belong to subject '{slug}'",
        )

    data = _node_content_out(node, include_children=True)
    return StandardResponse(
        success=True,
        message="Topic content retrieved",
        data=data,
    )


def _node_belongs_to_subject(db: Session, node: SyllabusNode, subject_id: int) -> bool:
    """Walk up to the owning section/paper/subject to confirm ownership."""
    current = node
    # Climb to the top-level (section-attached) ancestor.
    guard = 0
    while current.section_id is None and current.parent_id is not None and guard < 100:
        parent = (
            db.query(SyllabusNode)
            .filter(SyllabusNode.id == current.parent_id)
            .one_or_none()
        )
        if parent is None:
            break
        current = parent
        guard += 1

    if current.section_id is None:
        return False

    section = db.query(Section).filter(Section.id == current.section_id).one_or_none()
    if section is None:
        return False
    paper = db.query(Paper).filter(Paper.id == section.paper_id).one_or_none()
    if paper is None:
        return False
    return paper.subject_id == subject_id


# ---------------------------------------------------------------------------
# Per-segment syllabus analysis (Task 7.4 — R4.4 / R4.5)
# ---------------------------------------------------------------------------

def _overview_blocks(unit: ContentUnit) -> dict[str, Any]:
    """Return the topic-overview ``blocks`` payload as a dict (or empty).

    Topic nodes carry a ``kind == "topic-overview"`` ContentUnit whose
    ``blocks.syllabus`` holds the three-layer payload (official / trendSays /
    hiddenTopics). Subtopic units use a different shape, so we only read the
    overview shape here.
    """
    blocks = unit.blocks
    if isinstance(blocks, dict) and blocks.get("kind") == "topic-overview":
        return blocks
    return {}


def _official_lines(node: SyllabusNode, overview: dict[str, Any]) -> list[str]:
    """The "Official says" layer — official printed syllabus phrasing (R4.5).

    Prefers the structured ``syllabus.official`` list from the overview block;
    falls back to splitting the node's ``official_phrasing`` (newline-joined at
    import time) so an official layer is always surfaced when present.
    """
    syllabus = overview.get("syllabus") if isinstance(overview, dict) else None
    if isinstance(syllabus, dict):
        official = syllabus.get("official")
        if isinstance(official, list) and official:
            return [str(line) for line in official]
    if node.official_phrasing:
        return [ln for ln in node.official_phrasing.split("\n") if ln.strip()]
    return []


def _trend_points(overview: dict[str, Any]) -> list[SyllabusTrendPointOut]:
    """The "Trend says" layer — theme + insight + frequency (R4.5).

    This is the question-trend layer surfaced from the overview block's
    ``syllabus.trendSays`` (the layer previously missing in the UI).
    """
    syllabus = overview.get("syllabus") if isinstance(overview, dict) else None
    out: list[SyllabusTrendPointOut] = []
    if isinstance(syllabus, dict):
        trends = syllabus.get("trendSays")
        if isinstance(trends, list):
            for t in trends:
                if not isinstance(t, dict):
                    continue
                out.append(
                    SyllabusTrendPointOut(
                        theme=str(t.get("theme", "")),
                        insight=str(t.get("insight", "")),
                        frequency=str(t.get("frequency", "")),
                    )
                )
    return out


def _hidden_topics(unit: ContentUnit, overview: dict[str, Any]) -> list[SyllabusHiddenTopicOut]:
    """The "Hidden topics" layer — themes beyond the printed syllabus (R4.5).

    Prefers the unit's own ``hidden_topics`` column; falls back to the overview
    block's ``syllabus.hiddenTopics``. Each entry carries the theme + rationale.
    """
    source: Any = unit.hidden_topics
    if not isinstance(source, list) or not source:
        syllabus = overview.get("syllabus") if isinstance(overview, dict) else None
        source = syllabus.get("hiddenTopics") if isinstance(syllabus, dict) else None
    out: list[SyllabusHiddenTopicOut] = []
    if isinstance(source, list):
        for ht in source:
            if not isinstance(ht, dict):
                continue
            out.append(
                SyllabusHiddenTopicOut(
                    topic=str(ht.get("topic", "")),
                    why=str(ht.get("why", "")),
                )
            )
    return out


@router.get("/{slug}/syllabus-analysis")
def get_syllabus_analysis(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's per-segment three-layer syllabus analysis (R4.4/R4.5).

    For every **reviewed+authored** syllabus TOPIC segment, surfaces the three
    layers a student sees when opening that segment:

    * "Official says"  — the official printed syllabus phrasing.
    * "Trend says"     — the question trend (theme + insight + frequency).
    * "Hidden topics"  — themes asked beyond the printed syllabus, with rationale.

    Convenience over per-node ``/topics/{id}/content`` fan-out: one call returns
    every segment's analysis so the frontend ``SyllabusView`` stays a single,
    clean fetch. Segments are ordered by syllabus position (paper → section →
    topic) so the UI can group them (R4.4).

    Honesty gate (design Property 8 / R17.3): only segments with a
    reviewed+authored overview unit are returned; unreviewed/draft segments are
    gated out, and an empty ``segments`` list is the honest "nothing authored
    yet" signal.
    """
    subject = _get_subject_or_404(db, slug)

    segments: list[SyllabusSegmentAnalysisOut] = []
    papers = sorted(subject.papers, key=lambda p: (p.display_order, p.id))
    for paper in papers:
        paper_label = paper.label.value if hasattr(paper.label, "value") else str(paper.label)
        sections = sorted(paper.sections, key=lambda s: (s.display_order, s.id))
        for section in sections:
            section_label = (
                section.label.value
                if section.label is not None and hasattr(section.label, "value")
                else (str(section.label) if section.label is not None else None)
            )
            top_nodes = sorted(
                [n for n in section.syllabus_nodes if n.parent_id is None],
                key=lambda n: (n.display_order, n.id),
            )
            for node in top_nodes:
                unit = _reviewed_authored_unit(node)
                if unit is None:
                    # Honesty gate: skip unreviewed/unauthored segments.
                    continue
                overview = _overview_blocks(unit)
                segments.append(
                    SyllabusSegmentAnalysisOut(
                        node_id=node.id,
                        title=node.title,
                        node_type=_node_type_value(node),
                        paper_label=paper_label,
                        paper_name=paper.name,
                        section_label=section_label,
                        section_name=section.name,
                        official=_official_lines(node, overview),
                        trend_says=_trend_points(overview),
                        hidden_topics=_hidden_topics(unit, overview),
                    )
                )

    data = SyllabusAnalysisOut(
        slug=subject.slug,
        name=subject.name,
        segment_count=len(segments),
        segments=segments,
    )
    return StandardResponse(
        success=True,
        message="Syllabus analysis retrieved",
        data=data,
    )
