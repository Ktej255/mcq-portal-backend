"""PYQ (Previous Year Questions) endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms; auth-gated at the package router):
* GET /geography/topics/{node_id}/pyqs — PYQs for topic (filterable by exam_type)
* POST /geography/pyqs/{id}/reveal — Reveal answer for a PYQ

Design properties enforced:
* Property 8 (PYQ answer gating): answer_text and explanation omitted until
  explicitly revealed by the student.
* Property 19 (review-gate): only REVIEWED PYQs are visible to students.

Requirements traced: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 10.3
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsPyq,
    GsLmsExamTypeEnum,
)
from app.core.gs_lms.student_models import GsLmsPyqReveal
from app.api.v1.gs_lms.schemas import GsLmsPyqOut, GsLmsPyqListOut

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_reviewed_node(db: Session, node_id: int) -> GsLmsSyllabusNode:
    """Retrieve a REVIEWED syllabus node or raise 404."""
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
    return node


def _get_revealed_pyq_ids(db: Session, student_id: int, pyq_ids: list[int]) -> set[int]:
    """Get set of PYQ IDs that the student has revealed."""
    if not pyq_ids:
        return set()
    rows = (
        db.query(GsLmsPyqReveal.pyq_id)
        .filter(
            GsLmsPyqReveal.student_id == student_id,
            GsLmsPyqReveal.pyq_id.in_(pyq_ids),
        )
        .all()
    )
    return {row[0] for row in rows}


def _pyq_to_out(pyq: GsLmsPyq, revealed: bool) -> GsLmsPyqOut:
    """Convert a GsLmsPyq model to an output schema.

    When not revealed, answer_text and explanation are omitted (Property 8).
    """
    exam_type_val = pyq.exam_type.value if hasattr(pyq.exam_type, "value") else str(pyq.exam_type)
    question_type_val = (
        pyq.question_type.value if pyq.question_type and hasattr(pyq.question_type, "value")
        else (str(pyq.question_type) if pyq.question_type else None)
    )

    return GsLmsPyqOut(
        id=pyq.id,
        year=pyq.year,
        exam_type=exam_type_val,
        question_text=pyq.question_text,
        question_type=question_type_val,
        marks=pyq.marks,
        answer_text=pyq.answer_text if revealed else None,
        explanation=pyq.explanation if revealed else None,
        revealed=revealed,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/geography/topics/{node_id}/pyqs")
def get_topic_pyqs(
    node_id: int,
    exam_type: Optional[str] = Query(
        None,
        description="Filter by exam type: PRELIMS or MAINS",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return PYQs for a topic, optionally filtered by exam type.

    Only REVIEWED PYQs are visible to students (Property 19 / Requirement 10.3).
    Answer and explanation are hidden until explicitly revealed (Property 8).

    Empty-state handling (Requirements 3.6, 3.7):
    - If no REVIEWED PYQs exist and unreviewed PYQs exist → "under review" message
    - If no PYQs exist at all → empty list with "no PYQs available" message
    """
    node = _get_reviewed_node(db, node_id)

    # Validate exam_type if provided
    if exam_type is not None:
        exam_type_upper = exam_type.upper()
        if exam_type_upper not in ("PRELIMS", "MAINS"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="exam_type must be PRELIMS or MAINS",
            )
    else:
        exam_type_upper = None

    # Query REVIEWED PYQs for this node
    query = db.query(GsLmsPyq).filter(
        GsLmsPyq.syllabus_node_id == node_id,
        GsLmsPyq.review_status == GsReviewStatusEnum.REVIEWED,
    )
    if exam_type_upper:
        query = query.filter(GsLmsPyq.exam_type == GsLmsExamTypeEnum(exam_type_upper))

    reviewed_pyqs = query.order_by(GsLmsPyq.year.desc(), GsLmsPyq.id).all()

    # Check for empty-state messaging
    message = "PYQs retrieved"
    if not reviewed_pyqs:
        # Check if there are ANY PYQs (including unreviewed) for this topic
        unreviewed_filter = db.query(GsLmsPyq).filter(
            GsLmsPyq.syllabus_node_id == node_id,
        )
        if exam_type_upper:
            unreviewed_filter = unreviewed_filter.filter(
                GsLmsPyq.exam_type == GsLmsExamTypeEnum(exam_type_upper)
            )
        total_pyqs_count = unreviewed_filter.count()

        if total_pyqs_count > 0:
            # Unreviewed PYQs exist but none are reviewed yet (R3.7)
            message = "Questions are currently under review"
        else:
            # No PYQs at all for this topic (R3.6)
            message = "No PYQs available yet for this topic"

    # Build revealed set for the student
    pyq_ids = [p.id for p in reviewed_pyqs]
    revealed_ids = _get_revealed_pyq_ids(db, current_user.id, pyq_ids)

    # Build output list
    pyqs_out = [
        _pyq_to_out(pyq, revealed=(pyq.id in revealed_ids))
        for pyq in reviewed_pyqs
    ]

    data = GsLmsPyqListOut(
        node_id=node.id,
        title=node.title,
        exam_type_filter=exam_type_upper,
        total=len(pyqs_out),
        pyqs=pyqs_out,
    )

    return StandardResponse(
        success=True,
        message=message,
        data=data,
    )


@router.post("/geography/pyqs/{pyq_id}/reveal")
def reveal_pyq(
    pyq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Reveal the answer for a PYQ (persists reveal event).

    Only works for REVIEWED PYQs. Once revealed, answer_text and explanation
    are visible in subsequent GET responses for this student.

    If already revealed, returns the PYQ with revealed=True without error.
    """
    # Verify PYQ exists and is REVIEWED
    pyq = (
        db.query(GsLmsPyq)
        .filter(
            GsLmsPyq.id == pyq_id,
            GsLmsPyq.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .one_or_none()
    )
    if pyq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PYQ not found",
        )

    # Check if already revealed
    existing_reveal = (
        db.query(GsLmsPyqReveal)
        .filter(
            GsLmsPyqReveal.student_id == current_user.id,
            GsLmsPyqReveal.pyq_id == pyq_id,
        )
        .one_or_none()
    )

    if not existing_reveal:
        # Persist reveal event
        reveal = GsLmsPyqReveal(
            student_id=current_user.id,
            pyq_id=pyq_id,
        )
        db.add(reveal)
        db.commit()

    # Return the PYQ with answer revealed
    pyq_out = _pyq_to_out(pyq, revealed=True)

    return StandardResponse(
        success=True,
        message="PYQ answer revealed",
        data=pyq_out,
    )
