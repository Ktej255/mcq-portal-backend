"""CA Funnel Adapter — 5-step learning funnel for individual CA items.

Reuses existing funnel infrastructure (discussion engine, MCQ scoring,
evaluation engine) adapted for current affairs context.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional, List

from sqlalchemy.orm import Session

from app.core.current_affairs.ca_models import (
    CAItem,
    CAStudentProgress,
    CAMcq,
    CAMainsQuestion,
)


# ---------------------------------------------------------------------------
# Constants & Enums
# ---------------------------------------------------------------------------

class CAFunnelStep(IntEnum):
    WATCH_VIDEO = 1
    READ_CONTENT = 2
    AI_DISCUSSION = 3
    MCQ_PRACTICE = 4
    MAINS_PRACTICE = 5


# Steps required for completion (Mains is optional)
REQUIRED_STEPS_WITH_VIDEO = frozenset({1, 2, 3, 4})
REQUIRED_STEPS_NO_VIDEO = frozenset({2, 3, 4})

# CA-specific discussion prompts
CA_DISCUSSION_PROMPTS = [
    "What do you think is the UPSC angle for this news item?",
    "Which GS paper does this fall under and why?",
    "What static concept from the syllabus is this connected to?",
    "What are the short-term and long-term implications of this event?",
]


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CAFunnelState:
    """Student's funnel progress for a specific CA item."""
    student_id: int
    ca_item_id: int
    current_step: int
    completed_steps: frozenset[int]
    video_available: bool
    started_at: Optional[datetime]
    last_activity_at: Optional[datetime]
    is_completed: bool


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def get_ca_funnel_state(db: Session, student_id: int, item_id: int) -> CAFunnelState:
    """Load or initialize CA funnel progress for a student-item pair.

    If item has no video_url, automatically marks step 1 as completed
    and sets current_step to 2.
    """
    item = db.query(CAItem).filter(CAItem.id == item_id).first()
    video_available = bool(item and item.video_url)

    progress = db.query(CAStudentProgress).filter(
        CAStudentProgress.student_id == student_id,
        CAStudentProgress.ca_item_id == item_id,
    ).first()

    if progress:
        completed = frozenset(progress.completed_steps or [])
        return CAFunnelState(
            student_id=student_id,
            ca_item_id=item_id,
            current_step=progress.current_step,
            completed_steps=completed,
            video_available=video_available,
            started_at=progress.started_at,
            last_activity_at=progress.last_activity_at,
            is_completed=progress.is_completed,
        )

    # Initialize: auto-skip video if not available
    initial_step = 1 if video_available else 2
    initial_completed: frozenset[int] = frozenset() if video_available else frozenset({1})

    return CAFunnelState(
        student_id=student_id,
        ca_item_id=item_id,
        current_step=initial_step,
        completed_steps=initial_completed,
        video_available=video_available,
        started_at=None,
        last_activity_at=None,
        is_completed=False,
    )


def complete_ca_funnel_step(
    db: Session, student_id: int, item_id: int, step: int
) -> CAFunnelState:
    """Mark a CA funnel step complete and advance to next.

    Step 5 (MAINS_PRACTICE) is optional — skipping it still allows completion.
    On all required steps complete: marks item as completed.
    """
    state = get_ca_funnel_state(db, student_id, item_id)

    if step in state.completed_steps:
        return state  # Idempotent

    if step != state.current_step and step != CAFunnelStep.MAINS_PRACTICE:
        raise ValueError(
            f"Cannot complete step {step}: current step is {state.current_step}"
        )

    now = datetime.now(timezone.utc)
    new_completed = set(state.completed_steps) | {step}

    # Compute next step
    next_step = _compute_next_step(new_completed, state.video_available)

    # Check if all required steps are done
    required = REQUIRED_STEPS_WITH_VIDEO if state.video_available else REQUIRED_STEPS_NO_VIDEO
    is_completed = required.issubset(new_completed)

    # Persist
    progress = db.query(CAStudentProgress).filter(
        CAStudentProgress.student_id == student_id,
        CAStudentProgress.ca_item_id == item_id,
    ).first()

    if progress:
        progress.current_step = next_step
        progress.completed_steps = sorted(new_completed)
        progress.last_activity_at = now
        if is_completed and not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = now
    else:
        progress = CAStudentProgress(
            student_id=student_id,
            ca_item_id=item_id,
            current_step=next_step,
            completed_steps=sorted(new_completed),
            is_completed=is_completed,
            completed_at=now if is_completed else None,
            started_at=now,
            last_activity_at=now,
        )
        db.add(progress)

    db.flush()
    return get_ca_funnel_state(db, student_id, item_id)


def get_ca_discussion_prompts() -> List[str]:
    """Return CA-specific AI discussion prompts."""
    return list(CA_DISCUSSION_PROMPTS)


def get_ca_mcqs(db: Session, item_id: int) -> List[CAMcq]:
    """Load all MCQs attached to a CA item (up to 10)."""
    return (
        db.query(CAMcq)
        .filter(CAMcq.ca_item_id == item_id)
        .order_by(CAMcq.display_order)
        .limit(10)
        .all()
    )


def get_ca_mains_questions(db: Session, item_id: int) -> List[CAMainsQuestion]:
    """Load Mains questions attached to a CA item (up to 3)."""
    return (
        db.query(CAMainsQuestion)
        .filter(CAMainsQuestion.ca_item_id == item_id)
        .order_by(CAMainsQuestion.display_order)
        .limit(3)
        .all()
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_next_step(completed: set[int], video_available: bool) -> int:
    """Compute the next step from completed set."""
    start = 1 if video_available else 2
    for step in range(start, 6):
        if step not in completed:
            return step
    return 5  # All done, stay at 5


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "CAFunnelStep",
    "REQUIRED_STEPS_WITH_VIDEO",
    "REQUIRED_STEPS_NO_VIDEO",
    "CA_DISCUSSION_PROMPTS",
    "CAFunnelState",
    "get_ca_funnel_state",
    "complete_ca_funnel_step",
    "get_ca_discussion_prompts",
    "get_ca_mcqs",
    "get_ca_mains_questions",
]
