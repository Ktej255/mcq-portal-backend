"""Content delivery endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms/{subject_slug}; auth-gated at the package router):
* GET /topics/{node_id}/sections — Sections with lock/unlock state
* POST /topics/{node_id}/sections/{section_id}/complete — Mark section complete

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

Requirements traced: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1, 9.1, 9.2
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
from app.core.gs.models import GsReviewStatusEnum, GsSubject
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
)
from app.core.gs_lms.student_models import (
    GsLmsStudentSectionProgress,
    GsLmsDiscussionSession,
    GsLmsDiscussionStatusEnum,
    GsLmsVideoWatch,
    GsLmsOnboardingStatus,
)
from app.api.v1.gs_lms.dependencies import resolve_subject
from app.api.v1.gs_lms.schemas import (
    GsLmsTopicSectionsOut,
    GsLmsContentSectionOut,
)
from app.core.gs_lms.revisit import schedule_revisits

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


def _is_topic_completed(
    progress_map: dict[int, bool],
    section_ids: list[int],
    skippable_section_ids: set[int] | None = None,
) -> bool:
    """A topic is content-complete when all non-skippable sections are completed.

    Skippable sections are excluded from the completion requirement — the student
    can still read them, but they don't block topic completion.
    """
    if not section_ids:
        return False
    skip = skippable_section_ids or set()
    required_ids = [sid for sid in section_ids if sid not in skip]
    if not required_ids:
        return False
    return all(progress_map.get(sid, False) for sid in required_ids)


def _get_learner_level(db: Session, student_id: int) -> str:
    """Get the learner level for a student from their onboarding record.

    Defaults to "beginner" if no onboarding record exists.
    """
    onboarding = (
        db.query(GsLmsOnboardingStatus)
        .filter(GsLmsOnboardingStatus.student_id == student_id)
        .one_or_none()
    )
    if onboarding is None:
        return "beginner"
    return onboarding.learner_level or "beginner"


def _get_latest_match_percentage(
    db: Session, student_id: int, node_id: int
) -> float | None:
    """Get the match_percentage from the latest completed discussion session for a topic.

    Returns None if no completed session exists or no match_percentage was recorded.
    """
    session = (
        db.query(GsLmsDiscussionSession)
        .filter(
            GsLmsDiscussionSession.student_id == student_id,
            GsLmsDiscussionSession.syllabus_node_id == node_id,
            GsLmsDiscussionSession.status == GsLmsDiscussionStatusEnum.COMPLETED,
        )
        .order_by(GsLmsDiscussionSession.completed_at.desc())
        .first()
    )
    if session is None:
        return None
    return session.match_percentage


def _compute_skippable_section_labels(
    learner_level: str, match_percentage: float | None
) -> set[str]:
    """Determine which section labels are skippable based on level + match %.

    Rules:
    - Beginner: no sections skipped
    - Intermediate + match > 70%: BASIC is skippable
    - Advanced + match > 90%: BASIC + ADVANCED are skippable
    """
    if learner_level == "intermediate" and match_percentage is not None and match_percentage > 70.0:
        return {"BASIC"}
    elif learner_level == "advanced" and match_percentage is not None and match_percentage > 90.0:
        return {"BASIC", "ADVANCED"}
    return set()


def _compute_skippable_section_ids(
    sections: list[GsLmsContentSection],
    skippable_labels: set[str],
) -> set[int]:
    """Map skippable section labels to their IDs for a given sections list."""
    result: set[int] = set()
    for section in sections:
        label = section.section_label.value if hasattr(section.section_label, "value") else str(section.section_label)
        if label in skippable_labels:
            result.add(section.id)
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/topics/{node_id}/sections")
def get_topic_sections(
    node_id: int,
    subject: GsSubject = Depends(resolve_subject),
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

    # --- Section-skip logic based on learner level + match percentage ---
    learner_level = _get_learner_level(db, current_user.id)
    match_percentage = _get_latest_match_percentage(db, current_user.id, node_id)
    skippable_labels = _compute_skippable_section_labels(learner_level, match_percentage)
    skippable_ids = _compute_skippable_section_ids(sections, skippable_labels)

    # Build response
    sections_out: list[GsLmsContentSectionOut] = []
    for state in section_states:
        section: GsLmsContentSection = state["section"]
        locked: bool = state["locked"]
        completed: bool = state["completed"]
        is_skippable = section.id in skippable_ids

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
                skippable=is_skippable,
                # Content blocks: always include when discussion gate passed
                # (funnel controls access progression, not section locking)
                blocks=section.blocks if discussion_gate_passed else None,
            )
        )

    topic_completed = _is_topic_completed(progress_map, section_ids, skippable_ids)

    # Video data: read video_url from the node and check watch status
    video_url = node.video_url if hasattr(node, "video_url") else None
    watch_record = (
        db.query(GsLmsVideoWatch)
        .filter(
            GsLmsVideoWatch.student_id == current_user.id,
            GsLmsVideoWatch.syllabus_node_id == node_id,
        )
        .one_or_none()
    )
    video_watched = watch_record is not None

    return StandardResponse(
        success=True,
        message="Topic sections retrieved",
        data=GsLmsTopicSectionsOut(
            node_id=node.id,
            title=node.title,
            discussion_gate_passed=discussion_gate_passed,
            topic_completed=topic_completed,
            video_url=video_url,
            video_watched=video_watched,
            learner_level=learner_level,
            sections=sections_out,
        ),
    )


@router.post("/topics/{node_id}/sections/{section_id}/complete")
def complete_section(
    node_id: int,
    section_id: int,
    subject: GsSubject = Depends(resolve_subject),
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

    # Compute skippable sections for this student + topic
    learner_level = _get_learner_level(db, current_user.id)
    match_percentage = _get_latest_match_percentage(db, current_user.id, node_id)
    skippable_labels = _compute_skippable_section_labels(learner_level, match_percentage)
    skippable_ids = _compute_skippable_section_ids(all_sections, skippable_labels)

    # Already completed? Return success idempotently
    if target_state["completed"]:
        # Re-fetch full state for response
        updated_progress_map = _get_student_progress(db, current_user.id, section_ids)
        topic_completed = _is_topic_completed(updated_progress_map, section_ids, skippable_ids)
        return StandardResponse(
            success=True,
            message="Section already completed",
            data=GsLmsTopicSectionsOut(
                node_id=node.id,
                title=node.title,
                discussion_gate_passed=discussion_gate_passed,
                topic_completed=topic_completed,
                learner_level=learner_level,
                sections=_build_sections_response(
                    all_sections, updated_progress_map, discussion_gate_passed, skippable_ids
                ),
            ),
        )

    # Check if topic was already completed BEFORE this section completion
    topic_was_already_completed = _is_topic_completed(progress_map, section_ids, skippable_ids)

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
    topic_completed = _is_topic_completed(updated_progress_map, section_ids, skippable_ids)

    # Auto-schedule revisits if topic just became completed in THIS request
    if topic_completed and not topic_was_already_completed:
        schedule_revisits(db, current_user.id, node_id)
        db.commit()

    return StandardResponse(
        success=True,
        message="Section completed" + ("; topic content-complete" if topic_completed else ""),
        data=GsLmsTopicSectionsOut(
            node_id=node.id,
            title=node.title,
            discussion_gate_passed=discussion_gate_passed,
            topic_completed=topic_completed,
            learner_level=learner_level,
            sections=_build_sections_response(
                all_sections, updated_progress_map, discussion_gate_passed, skippable_ids
            ),
        ),
    )


def _build_sections_response(
    sections: list[GsLmsContentSection],
    progress_map: dict[int, bool],
    discussion_gate_passed: bool,
    skippable_ids: set[int] | None = None,
) -> list[GsLmsContentSectionOut]:
    """Build the section list response with updated lock states.

    Args:
        skippable_ids: Set of section IDs that are skippable based on learner
            level and discussion match percentage. Defaults to empty set.
    """
    skip = skippable_ids or set()
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
                skippable=section.id in skip,
                blocks=section.blocks,
            )
        )
    return sections_out
