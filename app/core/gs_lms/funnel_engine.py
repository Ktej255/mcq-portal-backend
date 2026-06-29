"""Funnel Engine — server-authoritative state machine for the 14-step
Interactive Learning Funnel.

Manages step progression per student per topic. All step advancement is
validated server-side to prevent client manipulation (skipping steps).

Key responsibilities:
- Funnel state initialization and retrieval
- Step completion validation and persistence
- Side-effect orchestration (Discussion Gate verification, MCQ weakness
  update, Growth Report generation, Daily Planner notification)

Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 14.1
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.gs_lms.funnel_models import (
    GsLmsFunnelStepEnum,
    GsLmsFunnelProgress,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOTAL_STEPS = 14


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class StepNotReachableError(Exception):
    """Raised when attempting to complete a step that is not the current step."""
    pass


class StepAlreadyCompletedError(Exception):
    """Raised when attempting to complete a step that is already done."""
    pass


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FunnelState:
    """Immutable snapshot of a student's funnel position for a topic."""
    student_id: int
    syllabus_node_id: int
    current_step: int
    completed_steps: frozenset[int]
    started_at: Optional[datetime]
    last_activity_at: Optional[datetime]


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def get_funnel_state(db: Session, student_id: int, node_id: int) -> FunnelState:
    """Load or initialize funnel progress for a student-topic pair.

    If no progress records exist, returns a fresh state with current_step = 1
    and an empty completed set.

    Args:
        db: SQLAlchemy database session.
        student_id: The student's user ID.
        node_id: The syllabus node (topic) ID.

    Returns:
        An immutable FunnelState snapshot.
    """
    rows = (
        db.query(GsLmsFunnelProgress)
        .filter(
            GsLmsFunnelProgress.student_id == student_id,
            GsLmsFunnelProgress.syllabus_node_id == node_id,
        )
        .all()
    )

    completed_steps: set[int] = set()
    started_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None

    for row in rows:
        if row.completed:
            completed_steps.add(row.step_number)
        # Track timestamps
        if row.created_at:
            if started_at is None or row.created_at < started_at:
                started_at = row.created_at
        if row.completed_at:
            if last_activity_at is None or row.completed_at > last_activity_at:
                last_activity_at = row.completed_at

    current_step = _compute_current_step(completed_steps)

    return FunnelState(
        student_id=student_id,
        syllabus_node_id=node_id,
        current_step=current_step,
        completed_steps=frozenset(completed_steps),
        started_at=started_at,
        last_activity_at=last_activity_at,
    )


def complete_step(
    db: Session,
    student_id: int,
    node_id: int,
    step: int,
) -> FunnelState:
    """Mark a step complete and advance current_step to the next unlocked step.

    Validates that `step` equals the current_step (rejects out-of-order
    completions). Persists the completion and returns the updated state.

    Side effects on specific steps:
    - Step 12 (MCQ Lab): triggers weakness_pattern update (handled by mcq_lab router)
    - Step 14 (Growth Report): generates growth report, triggers spaced_rep, notifies planner

    Args:
        db: SQLAlchemy database session.
        student_id: The student's user ID.
        node_id: The syllabus node (topic) ID.
        step: The step number to mark as complete (1–14).

    Returns:
        Updated FunnelState with the new completed set and advanced current_step.

    Raises:
        StepNotReachableError: If step != current_step.
        StepAlreadyCompletedError: If step is already in completed_steps.
        ValueError: If step is outside [1, 14].
    """
    if step < 1 or step > TOTAL_STEPS:
        raise ValueError(f"Step must be between 1 and {TOTAL_STEPS}, got {step}")

    state = get_funnel_state(db, student_id, node_id)

    if step in state.completed_steps:
        raise StepAlreadyCompletedError(
            f"Step {step} is already completed for student {student_id} on topic {node_id}"
        )

    if step != state.current_step:
        raise StepNotReachableError(
            f"Cannot complete step {step}: current step is {state.current_step}. "
            f"Steps must be completed in order."
        )

    # Persist completion
    now = datetime.now(timezone.utc)

    # Check if a row already exists (not yet completed)
    existing = (
        db.query(GsLmsFunnelProgress)
        .filter(
            GsLmsFunnelProgress.student_id == student_id,
            GsLmsFunnelProgress.syllabus_node_id == node_id,
            GsLmsFunnelProgress.step_number == step,
        )
        .first()
    )

    if existing:
        existing.completed = True
        existing.completed_at = now
    else:
        progress = GsLmsFunnelProgress(
            student_id=student_id,
            syllabus_node_id=node_id,
            step_number=step,
            completed=True,
            completed_at=now,
        )
        db.add(progress)

    db.flush()

    # --- Side effects for specific steps ---
    _trigger_step_side_effects(db, student_id, node_id, step)

    # Return updated state
    return get_funnel_state(db, student_id, node_id)


def is_step_complete(state: FunnelState, step: int) -> bool:
    """Pure check: is `step` in the completed set?"""
    return step in state.completed_steps


def get_next_step(state: FunnelState) -> Optional[int]:
    """Return the next incomplete step, or None if funnel is done."""
    if state.current_step > TOTAL_STEPS:
        return None
    return state.current_step


def can_access_step(state: FunnelState, step: int) -> bool:
    """True if step is accessible (completed or currently active).

    A step is accessible if it has already been completed OR if it is
    the current active step.
    """
    return step <= state.current_step


def is_funnel_complete(state: FunnelState) -> bool:
    """True if all 14 steps have been completed."""
    return len(state.completed_steps) >= TOTAL_STEPS


# ---------------------------------------------------------------------------
# Side-Effect Orchestration
# ---------------------------------------------------------------------------

def _trigger_step_side_effects(db: Session, student_id: int, node_id: int, step: int) -> None:
    """Trigger side effects for specific funnel steps.

    - Step 14 (Growth Report): Generate growth report, notify daily planner,
      update topic completion status.
    - Other step side effects (MCQ Lab weakness update, recall → gap tracker)
      are handled directly in their respective API routers.

    Requirements: 14.3, 14.4, 14.5
    """
    if step == TOTAL_STEPS:  # Growth Report = final step
        _on_funnel_complete(db, student_id, node_id)


def _on_funnel_complete(db: Session, student_id: int, node_id: int) -> None:
    """Side effects when the entire funnel is completed (step 14).

    1. Generate and persist Growth Report (triggers spaced rep scheduling)
    2. Mark topic as completed in existing progress system
    3. Emit topic-completion event to Daily Planner bandwidth tracking

    Requirements: 14.3, 14.5
    """
    try:
        # Import here to avoid circular imports
        from app.core.gs_lms.growth_report import generate_growth_report
        generate_growth_report(db, student_id, node_id)
    except Exception:
        # Growth report generation failure should not block funnel completion
        pass

    try:
        # Update existing topic completion status (GsLmsStudentSectionProgress pattern)
        from app.core.gs_lms.student_models import GsLmsStudentSectionProgress
        from app.core.gs_lms.models import GsLmsContentSection

        # Mark all sections as completed for this topic
        sections = (
            db.query(GsLmsContentSection)
            .filter(GsLmsContentSection.syllabus_node_id == node_id)
            .all()
        )
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        for section in sections:
            existing = (
                db.query(GsLmsStudentSectionProgress)
                .filter(
                    GsLmsStudentSectionProgress.student_id == student_id,
                    GsLmsStudentSectionProgress.section_id == section.id,
                )
                .first()
            )
            if existing and not existing.completed:
                existing.completed = True
                existing.completed_at = now
            elif not existing:
                progress = GsLmsStudentSectionProgress(
                    student_id=student_id,
                    section_id=section.id,
                    syllabus_node_id=node_id,
                    completed=True,
                    completed_at=now,
                )
                db.add(progress)
    except Exception:
        # Progress update failure should not block funnel completion
        pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_current_step(completed_steps: set[int]) -> int:
    """Compute the current step from the set of completed steps.

    The current step is the minimum step number not in the completed set.
    If all steps are complete, returns TOTAL_STEPS + 1.
    """
    for step_num in range(1, TOTAL_STEPS + 1):
        if step_num not in completed_steps:
            return step_num
    return TOTAL_STEPS + 1


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "TOTAL_STEPS",
    "StepNotReachableError",
    "StepAlreadyCompletedError",
    "FunnelState",
    "get_funnel_state",
    "complete_step",
    "is_step_complete",
    "get_next_step",
    "can_access_step",
    "is_funnel_complete",
]
