"""Content delivery endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms; auth-gated at the package router):
* GET /geography/topics/{node_id}/sections — Sections with lock/unlock state
* POST /geography/topics/{node_id}/sections/{section_id}/complete — Mark section complete

Progressive disclosure logic:
- Only REVIEWED sections are visible to students (review-gate).
- For first-time topic visits, content is blocked until the student has a
  COMPLETED discussion session for that topic (AI Discussion gate).
- If the student already completed discussion (or is returning), they get
  full progressive access.
- Section 1 (BASIC) is always unlocked (if discussion gate passed).
- Section N is unlocked if section N-1 is completed.
- Content blocks are included only for unlocked sections; None for locked.
- When all 4 sections are completed → topic is content-complete.

Requirements traced: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
)
from app.core.gs_lms.student_models import (
    GsLmsStudentSectionProgress,
    GsLmsDiscussionSession,
    GsLmsDiscussionStatusEnum,
)
from app.api.v1.gs_lms.schemas import (
    GsLmsTopicSectionsOut,
    GsLmsContentSectionOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_node_or_404(db: Session, node_id: int) -> GsLmsSyllabusNode:
    """Fetch a syllabus node by ID or raise 404."""
    node = (
        db.query(GsLmsSyllabusNode)
        .filter(GsLmsSyllabusNode.id == node_id)
        .one_or_none()
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )
    return node


def _has_completed_discussion(db: Session, student_id: int, node_id: int) -> bool:
    """Check if the student has a COMPLETED discussion session for this topic.

    Returns True if at least one session with status=COMPLETED exists,
    meaning the AI Discussion gate has been passed.
    """
    session = (
        db.query(GsLmsDiscussionSession)
        .filter(
            GsLmsDiscussionSession.student_id == student_id,
            GsLmsDiscussionSession.syllabus_node_id == node_id,
            GsLmsDiscussionSession.status == GsLmsDiscussionStatusEnum.COMPLETED,
        )
        .first()
    )
    return session is not None


def _get_reviewed_sections(db: Session, node_id: int) -> list[GsLmsContentSection]:
    """Fetch all REVIEWED content sections for a node, ordered by display_order."""
    return (
        db.query(GsLmsContentSection)
        .filter(
            GsLmsContentSection.syllabus_node_id == node_id,
            GsLmsContentSection.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(GsLmsContentSection.display_order)
        .all()
    )


def _get_student_progress(
    db: Session, student_id: int, section_ids: list[int]
) -> dict[int, bool]:
    """Return a mapping of section_id → completed for the student.

    Only sections with a progress record AND completed=True are considered
    completed.
    """
    if not section_ids:
        return {}
    progress_rows = (
        db.query(GsLmsStudentSectionProgress)
        .filter(
            GsLmsStudentSectionProgress.student_id == student_id,
            GsLmsStudentSectionProgress.section_id.in_(section_ids),
        )
        .all()
    )
    return {row.section_id: row.completed for row in progress_rows}


def _compute_lock_states(
    sections: list[GsLmsContentSection],
    progress_map: dict[int, bool],
    discussion_gate_passed: bool,
) -> list[dict[str, Any]]:
    """Compute lock/unlock state for each section.

    Logic:
    - If discussion gate NOT passed: all sections are locked.
    - Section 1 (first by display_order): always unlocked when gate passed.
    - Section N (N>1): unlocked if section N-1 is completed.
    """
    result: list[dict[str, Any]] = []
    for i, section in enumerate(sections):
        completed = progress_map.get(section.id, False)
        if not discussion_gate_passed:
            locked = True
        elif i == 0:
            # First section is always unlocked once gate passed
            locked = False
        else:
            # Unlocked only if previous section is completed
            prev_section = sections[i - 1]
            prev_completed = progress_map.get(prev_section.id, False)
            locked = not prev_completed

        result.append({
            "section": section,
            "locked": locked,
            "completed": completed,
        })
    return result


def _is_topic_completed(progress_map: dict[int, bool], section_ids: list[int]) -> bool:
    """A topic is content-complete when ALL its sections are completed."""
    if not section_ids:
        return False
    return all(progress_map.get(sid, False) for sid in section_ids)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/geography/topics/{node_id}/sections")
def get_topic_sections(
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return all sections for a topic with lock/unlock state per student.

    Progressive disclosure: only unlocked sections include content blocks.
    Discussion gate must be passed before any content is accessible.

    Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.6, 5.1
    """
    node = _get_node_or_404(db, node_id)

    # Fetch reviewed sections only (review-gate: R10.3)
    sections = _get_reviewed_sections(db, node_id)

    # Check AI Discussion gate (R5.1)
    discussion_gate_passed = _has_completed_discussion(
        db, current_user.id, node_id
    )

    # Student progress for these sections
    section_ids = [s.id for s in sections]
    progress_map = _get_student_progress(db, current_user.id, section_ids)

    # Compute lock states
    section_states = _compute_lock_states(sections, progress_map, discussion_gate_passed)

    # Build response
    sections_out: list[GsLmsContentSectionOut] = []
    for state in section_states:
        section: GsLmsContentSection = state["section"]
        locked: bool = state["locked"]
        completed: bool = state["completed"]

        sections_out.append(
            GsLmsContentSectionOut(
                section_id=section.id,
                section_label=section.section_label.value
                if hasattr(section.section_label, "value")
                else str(section.section_label),
                title=section.title,
                display_order=section.display_order,
                locked=locked,
                completed=completed,
                # Content blocks only for unlocked sections
                blocks=section.blocks if not locked else None,
            )
        )

    topic_completed = _is_topic_completed(progress_map, section_ids)

    return StandardResponse(
        success=True,
        message="Topic sections retrieved",
        data=GsLmsTopicSectionsOut(
            node_id=node.id,
            title=node.title,
            discussion_gate_passed=discussion_gate_passed,
            topic_completed=topic_completed,
            sections=sections_out,
        ),
    )


@router.post("/geography/topics/{node_id}/sections/{section_id}/complete")
def complete_section(
    node_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Mark a content section as complete and unlock the next section.

    Enforces:
    - AI Discussion gate must be passed first (R5.1)
    - Section must belong to the given topic
    - Section must be unlocked (progressive order — R2.2)
    - Completing the 4th section marks the topic as content-complete (R2.5)

    Validates: Requirements 2.2, 2.5, 2.6, 5.1
    """
    node = _get_node_or_404(db, node_id)

    # Verify the section exists and belongs to this node
    section = (
        db.query(GsLmsContentSection)
        .filter(
            GsLmsContentSection.id == section_id,
            GsLmsContentSection.syllabus_node_id == node_id,
            GsLmsContentSection.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .one_or_none()
    )
    if section is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found for this topic",
        )

    # Enforce AI Discussion gate (R5.1)
    discussion_gate_passed = _has_completed_discussion(
        db, current_user.id, node_id
    )
    if not discussion_gate_passed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AI Discussion required before content access",
        )

    # Fetch all reviewed sections to check ordering
    all_sections = _get_reviewed_sections(db, node_id)
    section_ids = [s.id for s in all_sections]
    progress_map = _get_student_progress(db, current_user.id, section_ids)

    # Compute current lock states to verify section is unlocked
    section_states = _compute_lock_states(all_sections, progress_map, discussion_gate_passed)

    # Find target section in states
    target_state = None
    for state in section_states:
        if state["section"].id == section_id:
            target_state = state
            break

    if target_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found for this topic",
        )

    if target_state["locked"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Previous section not completed",
        )

    # Already completed? Return success idempotently
    if target_state["completed"]:
        # Re-fetch full state for response
        updated_progress_map = _get_student_progress(db, current_user.id, section_ids)
        topic_completed = _is_topic_completed(updated_progress_map, section_ids)
        return StandardResponse(
            success=True,
            message="Section already completed",
            data=GsLmsTopicSectionsOut(
                node_id=node.id,
                title=node.title,
                discussion_gate_passed=discussion_gate_passed,
                topic_completed=topic_completed,
                sections=_build_sections_response(
                    all_sections, updated_progress_map, discussion_gate_passed
                ),
            ),
        )

    # Mark section as complete
    now = datetime.now(timezone.utc)
    existing_progress = (
        db.query(GsLmsStudentSectionProgress)
        .filter(
            GsLmsStudentSectionProgress.student_id == current_user.id,
            GsLmsStudentSectionProgress.section_id == section_id,
        )
        .one_or_none()
    )

    if existing_progress:
        existing_progress.completed = True
        existing_progress.completed_at = now
    else:
        new_progress = GsLmsStudentSectionProgress(
            student_id=current_user.id,
            section_id=section_id,
            syllabus_node_id=node_id,
            completed=True,
            completed_at=now,
        )
        db.add(new_progress)

    db.commit()

    # Fetch updated state for response
    updated_progress_map = _get_student_progress(db, current_user.id, section_ids)
    topic_completed = _is_topic_completed(updated_progress_map, section_ids)

    return StandardResponse(
        success=True,
        message="Section completed" + ("; topic content-complete" if topic_completed else ""),
        data=GsLmsTopicSectionsOut(
            node_id=node.id,
            title=node.title,
            discussion_gate_passed=discussion_gate_passed,
            topic_completed=topic_completed,
            sections=_build_sections_response(
                all_sections, updated_progress_map, discussion_gate_passed
            ),
        ),
    )


def _build_sections_response(
    sections: list[GsLmsContentSection],
    progress_map: dict[int, bool],
    discussion_gate_passed: bool,
) -> list[GsLmsContentSectionOut]:
    """Build the section list response with updated lock states."""
    section_states = _compute_lock_states(sections, progress_map, discussion_gate_passed)
    sections_out: list[GsLmsContentSectionOut] = []
    for state in section_states:
        section: GsLmsContentSection = state["section"]
        locked: bool = state["locked"]
        completed: bool = state["completed"]
        sections_out.append(
            GsLmsContentSectionOut(
                section_id=section.id,
                section_label=section.section_label.value
                if hasattr(section.section_label, "value")
                else str(section.section_label),
                title=section.title,
                display_order=section.display_order,
                locked=locked,
                completed=completed,
                blocks=section.blocks if not locked else None,
            )
        )
    return sections_out
