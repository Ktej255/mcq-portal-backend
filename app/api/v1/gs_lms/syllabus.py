"""Syllabus tree endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at the package router):
* GET /syllabus — Full tree with per-student completion status
* GET /syllabus/{node_id} — Single node with children

Design properties enforced:
* Property 19 (review-gate): only REVIEWED nodes are returned to students.
* Property 2 (completion accuracy): annotates each node correctly —
  boolean for leaf nodes, percentage for non-leaf nodes.
* Requirement 11.2: bridges to existing GsDayLesson via day_lesson_id FK.

Requirements traced: 1.1, 1.2, 1.3, 1.4, 9.1, 9.2, 10.3, 11.2
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsReviewStatusEnum, GsSubject
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsNodeTypeEnum,
    GsLmsContentSection,
    GsLmsSectionLabelEnum,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress
from app.api.v1.gs_lms.dependencies import resolve_subject
from app.api.v1.gs_lms.schemas import (
    GsLmsSyllabusNodeOut,
    GsLmsSyllabusTreeOut,
)

router = APIRouter()

# The number of progressive-disclosure sections per leaf topic (BASIC,
# ADVANCED, NCERT_LEVEL, EXAMINER_TRAPS).
_SECTIONS_PER_LEAF = 4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_completion_map(db: Session, student_id: int) -> dict[int, int]:
    """Build a mapping of syllabus_node_id → count of completed sections.

    Returns a dict where keys are syllabus node IDs and values are the
    number of sections completed by the student for that node.
    """
    rows = (
        db.query(
            GsLmsStudentSectionProgress.syllabus_node_id,
        )
        .filter(
            GsLmsStudentSectionProgress.student_id == student_id,
            GsLmsStudentSectionProgress.completed == True,  # noqa: E712
        )
        .all()
    )
    completion_counts: dict[int, int] = {}
    for (node_id,) in rows:
        completion_counts[node_id] = completion_counts.get(node_id, 0) + 1
    return completion_counts


def _is_leaf_completed(node_id: int, completion_map: dict[int, int]) -> bool:
    """A leaf topic is completed when all 4 sections are marked complete."""
    return completion_map.get(node_id, 0) >= _SECTIONS_PER_LEAF


def _compute_completion(
    node: GsLmsSyllabusNode,
    children_out: list[GsLmsSyllabusNodeOut],
    completion_map: dict[int, int],
) -> tuple[float | None, bool | None]:
    """Compute completion metrics for a node.

    Returns (completion_percent, completed_bool):
    - For leaf nodes: (None, bool)
    - For non-leaf nodes: (float 0-100, None)
    """
    if node.node_type == GsLmsNodeTypeEnum.LEAF_TOPIC:
        completed = _is_leaf_completed(node.id, completion_map)
        return (None, completed)
    else:
        # Non-leaf: percentage = completed children / total children * 100
        total_children = len(children_out)
        if total_children == 0:
            return (0.0, None)
        completed_children = sum(
            1
            for child in children_out
            if (child.completed is True)
            or (child.completion_percent is not None and child.completion_percent >= 100.0)
        )
        percent = (completed_children / total_children) * 100.0
        return (percent, None)


def _review_status_value(node: GsLmsSyllabusNode) -> str:
    rs = node.review_status
    return rs.value if hasattr(rs, "value") else str(rs)


def _node_type_value(node: GsLmsSyllabusNode) -> str:
    nt = node.node_type
    return nt.value if hasattr(nt, "value") else str(nt)


def _build_node_out(
    node: GsLmsSyllabusNode,
    completion_map: dict[int, int],
) -> GsLmsSyllabusNodeOut:
    """Recursively build a GsLmsSyllabusNodeOut from a reviewed node.

    Only includes children that are also REVIEWED (Property 19).
    """
    # Filter children to only REVIEWED nodes, sorted by display_order.
    reviewed_children = sorted(
        [c for c in node.children if c.review_status == GsReviewStatusEnum.REVIEWED],
        key=lambda n: (n.display_order, n.id),
    )
    children_out = [_build_node_out(c, completion_map) for c in reviewed_children]

    completion_percent, completed = _compute_completion(
        node, children_out, completion_map
    )

    return GsLmsSyllabusNodeOut(
        node_id=node.id,
        title=node.title,
        node_type=_node_type_value(node),
        weight=node.weight,
        display_order=node.display_order,
        review_status=_review_status_value(node),
        completion_percent=completion_percent,
        completed=completed,
        day_lesson_id=node.day_lesson_id,
        ordering_justification=node.ordering_justification,
        children=children_out,
    )


def _count_nodes(nodes: list[GsLmsSyllabusNodeOut]) -> int:
    """Recursively count all nodes in the tree."""
    count = 0
    for node in nodes:
        count += 1
        count += _count_nodes(node.children)
    return count


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/syllabus")
def get_syllabus_tree(
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the full syllabus tree with per-student completion.

    Only REVIEWED nodes are included (Property 19 / Requirement 10.3).
    Each node is annotated with completion status for the requesting student.
    """
    # Query all REVIEWED root nodes (parent_id IS NULL) for this subject.
    root_nodes = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.subject_id == subject.id,
            GsLmsSyllabusNode.parent_id == None,  # noqa: E711
            GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(GsLmsSyllabusNode.display_order, GsLmsSyllabusNode.id)
        .all()
    )

    # Build completion map for this student in one query.
    completion_map = _build_completion_map(db, current_user.id)

    tree = [_build_node_out(node, completion_map) for node in root_nodes]
    total_nodes = _count_nodes(tree)

    data = GsLmsSyllabusTreeOut(
        subject_id=subject.id,
        subject_name=subject.name,
        total_nodes=total_nodes,
        tree=tree,
    )
    return StandardResponse(
        success=True,
        message=f"{subject.name} syllabus tree retrieved",
        data=data,
    )


@router.get("/syllabus/{node_id}")
def get_syllabus_node(
    node_id: int,
    subject: GsSubject = Depends(resolve_subject),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return a single syllabus node with its children.

    Only returns the node if it is REVIEWED (Property 19).
    Children are also filtered to only REVIEWED nodes.
    """
    node = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.id == node_id,
            GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .one_or_none()
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )

    completion_map = _build_completion_map(db, current_user.id)
    data = _build_node_out(node, completion_map)

    return StandardResponse(
        success=True,
        message="Syllabus node retrieved",
        data=data,
    )
