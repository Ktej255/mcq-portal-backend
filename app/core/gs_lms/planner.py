"""Daily planner engine for the GS LMS Platform.

This module provides **pure functions** for bandwidth-based daily scheduling
with auto-continue and replanning logic:

* **generate_day_plan** — Pure scheduling: given a syllabus position and
  bandwidth, produces a list of plan items (design Property 16 / Req 7.1, 7.2).
* **find_current_position** — Locates the first uncompleted item in the
  syllabus sequence for a student (Req 7.2).
* **check_replan_needed** — Streak detection: 2 consecutive missed-target days
  trigger auto-replan (design Property 17 / Req 7.4).
* **should_suggest_bandwidth_increase** — Recommends bandwidth increase after
  5 consecutive target hits (Req 7.3).
* **compute_projected_completion** — Projected completion date calculation
  (design Property 18 / Req 7.5).
* **create_daily_plan** — Orchestrates plan creation with DB persistence (Req 7.6).
* **record_replan_event** — Persists replanning triggers (Req 7.6).

The scheduling math is intentionally separated from the ORM/endpoint layer so
that correctness can be validated with pure unit and property tests.

Requirements traced: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional, Sequence

from sqlalchemy import asc
from sqlalchemy.orm import Session

from app.core.gs_lms.models import GsLmsSyllabusNode, GsLmsNodeTypeEnum
from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.student_models import (
    GsLmsDailyPlan,
    GsLmsReplanEvent,
    GsLmsStudentSectionProgress,
)


# ---------------------------------------------------------------------------
# Data transfer objects (pure — no ORM dependency)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanItem:
    """A single item in a daily plan.

    Represents one syllabus node scheduled for study on a given day.
    """

    node_id: int
    title: str
    item_type: str = "section"  # "section" or "practice"


@dataclass(frozen=True)
class DayPlan:
    """The generated day plan with scheduled items and projected completion.

    Invariant (Property 16):
        len(items) == min(bandwidth, remaining_items)
        items start from the given position in syllabus display order.
    """

    items: List[PlanItem] = field(default_factory=list)
    bandwidth: int = 0
    remaining_items: int = 0
    projected_completion: Optional[date] = None


@dataclass(frozen=True)
class PlanHistoryEntry:
    """One day's plan outcome for streak analysis.

    Used by check_replan_needed and should_suggest_bandwidth_increase.
    """

    plan_date: date
    is_target_met: Optional[bool]


# ---------------------------------------------------------------------------
# Pure scheduling functions
# ---------------------------------------------------------------------------


def generate_day_plan(
    syllabus_items: Sequence[PlanItem],
    current_position: int,
    bandwidth: int,
) -> DayPlan:
    """Generate a day plan from position and bandwidth.

    Pure scheduling function: position + bandwidth → day plan items.

    Property 16: The generated day plan contains exactly
    min(bandwidth, remaining_items) items starting from position P
    in syllabus display order.

    Args:
        syllabus_items: Full ordered list of plan-eligible syllabus items.
        current_position: Index into syllabus_items of the first uncompleted item.
        bandwidth: Number of items the student committed to for this day.

    Returns:
        DayPlan with items, bandwidth, remaining count, and projected completion.
    """
    if bandwidth <= 0:
        return DayPlan(
            items=[],
            bandwidth=bandwidth,
            remaining_items=max(0, len(syllabus_items) - current_position),
            projected_completion=None,
        )

    remaining_items = max(0, len(syllabus_items) - current_position)
    count = min(bandwidth, remaining_items)
    items = list(syllabus_items[current_position : current_position + count])

    projected = compute_projected_completion(remaining_items, bandwidth)

    return DayPlan(
        items=items,
        bandwidth=bandwidth,
        remaining_items=remaining_items,
        projected_completion=projected,
    )


def check_replan_needed(plan_history: Sequence[PlanHistoryEntry]) -> bool:
    """Check if dynamic replanning should be triggered.

    Property 17: Replan triggers if and only if the most recent 2 consecutive
    days both have is_target_met = False. A single miss or a miss followed by
    a hit does NOT trigger replanning.

    Args:
        plan_history: Sequence of plan outcomes ordered chronologically
            (oldest first). Only entries with non-None is_target_met are
            considered.

    Returns:
        True if replanning should be triggered, False otherwise.
    """
    # Filter to entries with definitive target status.
    evaluated = [e for e in plan_history if e.is_target_met is not None]

    if len(evaluated) < 2:
        return False

    # Check the last two entries.
    last_two = evaluated[-2:]
    return (
        last_two[0].is_target_met is False
        and last_two[1].is_target_met is False
    )


def should_suggest_bandwidth_increase(
    plan_history: Sequence[PlanHistoryEntry],
) -> bool:
    """Check if a bandwidth increase should be suggested.

    Returns True if the last 5 consecutive evaluated entries all have
    is_target_met = True. This indicates the student is consistently
    hitting targets and could handle a higher workload.

    Requirement 7.3: Consistent target hit suggests bandwidth increase
    after 5 consecutive hits.

    Args:
        plan_history: Sequence of plan outcomes ordered chronologically
            (oldest first). Only entries with non-None is_target_met are
            considered.

    Returns:
        True if bandwidth increase should be suggested.
    """
    evaluated = [e for e in plan_history if e.is_target_met is not None]

    if len(evaluated) < 5:
        return False

    last_five = evaluated[-5:]
    return all(entry.is_target_met is True for entry in last_five)


def compute_projected_completion(
    remaining_items: int,
    bandwidth: int,
    reference_date: Optional[date] = None,
) -> Optional[date]:
    """Compute the projected syllabus completion date.

    Property 18: projected_completion = today + ceil(R / B) days (B > 0).
    If B = 0, no projection is possible (returns None).

    Args:
        remaining_items: Number of items left in the syllabus (R).
        bandwidth: Effective daily bandwidth (B).
        reference_date: The base date for calculation (defaults to today).

    Returns:
        The projected completion date, or None if bandwidth is 0.
    """
    if bandwidth <= 0:
        return None

    if remaining_items <= 0:
        # Already complete.
        if reference_date is None:
            reference_date = date.today()
        return reference_date

    if reference_date is None:
        reference_date = date.today()

    days_needed = math.ceil(remaining_items / bandwidth)
    return reference_date + timedelta(days=days_needed)


# ---------------------------------------------------------------------------
# Database-interacting functions
# ---------------------------------------------------------------------------


def find_current_position(db: Session, student_id: int, subject_id: int) -> int:
    """Find the first uncompleted item index in the syllabus sequence.

    Requirement 7.2: Auto-continue from the exact point where the student
    stopped the previous day.

    Queries all REVIEWED leaf-level syllabus nodes ordered by display_order,
    then finds the first one not yet completed by the student.

    Args:
        db: SQLAlchemy session.
        student_id: The student's user ID.
        subject_id: The GS subject ID.

    Returns:
        Index (0-based) of the first uncompleted item in the syllabus
        display order. Returns 0 if no items exist, or len(items) if
        all are completed.
    """
    # Get all reviewed leaf nodes in display order.
    leaf_nodes = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.subject_id == subject_id,
            GsLmsSyllabusNode.node_type == GsLmsNodeTypeEnum.LEAF_TOPIC,
            GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(asc(GsLmsSyllabusNode.display_order))
        .all()
    )

    if not leaf_nodes:
        return 0

    # Get IDs of nodes the student has fully completed (all 4 sections done).
    completed_node_ids = set()
    for node in leaf_nodes:
        # A node is "completed" if all its sections are marked completed.
        progress_records = (
            db.query(GsLmsStudentSectionProgress)
            .filter(
                GsLmsStudentSectionProgress.student_id == student_id,
                GsLmsStudentSectionProgress.syllabus_node_id == node.id,
                GsLmsStudentSectionProgress.completed == True,
            )
            .count()
        )
        # A leaf topic has 4 sections; consider completed if all 4 done.
        if progress_records >= 4:
            completed_node_ids.add(node.id)

    # Find first uncompleted position.
    for idx, node in enumerate(leaf_nodes):
        if node.id not in completed_node_ids:
            return idx

    # All completed.
    return len(leaf_nodes)


def get_syllabus_plan_items(
    db: Session, subject_id: int
) -> List[PlanItem]:
    """Get all leaf-level syllabus items as PlanItems in display order.

    Returns only REVIEWED leaf nodes suitable for planning.

    Args:
        db: SQLAlchemy session.
        subject_id: The GS subject ID.

    Returns:
        Ordered list of PlanItem objects.
    """
    leaf_nodes = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.subject_id == subject_id,
            GsLmsSyllabusNode.node_type == GsLmsNodeTypeEnum.LEAF_TOPIC,
            GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(asc(GsLmsSyllabusNode.display_order))
        .all()
    )

    return [
        PlanItem(node_id=node.id, title=node.title, item_type="section")
        for node in leaf_nodes
    ]


def get_plan_history(
    db: Session, student_id: int, limit: int = 10
) -> List[PlanHistoryEntry]:
    """Retrieve the most recent daily plan history for a student.

    Args:
        db: SQLAlchemy session.
        student_id: The student's user ID.
        limit: Maximum number of entries to retrieve (most recent first).

    Returns:
        List of PlanHistoryEntry ordered chronologically (oldest first).
    """
    plans = (
        db.query(GsLmsDailyPlan)
        .filter(GsLmsDailyPlan.student_id == student_id)
        .order_by(GsLmsDailyPlan.plan_date.desc())
        .limit(limit)
        .all()
    )

    # Reverse to chronological order (oldest first).
    plans.reverse()

    return [
        PlanHistoryEntry(
            plan_date=plan.plan_date,
            is_target_met=plan.is_target_met,
        )
        for plan in plans
    ]


def create_daily_plan(
    db: Session,
    student_id: int,
    subject_id: int,
    bandwidth: int,
    plan_date: Optional[date] = None,
) -> GsLmsDailyPlan:
    """Create and persist a daily plan for a student.

    Orchestrates the full planning flow:
    1. Finds current position (auto-continue from first uncompleted item).
    2. Gets syllabus items.
    3. Generates the day plan.
    4. Persists to GsLmsDailyPlan.

    Args:
        db: SQLAlchemy session.
        student_id: The student's user ID.
        subject_id: The GS subject ID.
        bandwidth: Topics/sections committed for this day.
        plan_date: The date for the plan (defaults to today).

    Returns:
        The persisted GsLmsDailyPlan record.
    """
    if plan_date is None:
        plan_date = date.today()

    # Get the full syllabus items and current position.
    syllabus_items = get_syllabus_plan_items(db, subject_id)
    current_position = find_current_position(db, student_id, subject_id)

    # Generate the day plan using pure function.
    day_plan = generate_day_plan(syllabus_items, current_position, bandwidth)

    # Persist.
    planned_items_json = [
        {"node_id": item.node_id, "type": item.item_type}
        for item in day_plan.items
    ]

    db_plan = GsLmsDailyPlan(
        student_id=student_id,
        plan_date=plan_date,
        bandwidth=bandwidth,
        planned_items=planned_items_json,
        completed_items=[],
        is_target_met=None,
        projected_completion_date=day_plan.projected_completion,
    )

    db.add(db_plan)
    db.flush()

    return db_plan


def record_replan_event(
    db: Session,
    student_id: int,
    reason: str,
    old_bandwidth: int,
    new_bandwidth: int,
    old_projected_date: Optional[date] = None,
    new_projected_date: Optional[date] = None,
) -> GsLmsReplanEvent:
    """Persist a replanning event.

    Records when and why replanning occurred, capturing both old and new
    bandwidth values and projected completion dates.

    Args:
        db: SQLAlchemy session.
        student_id: The student's user ID.
        reason: Reason for replanning ("consecutive_misses", "manual",
            "bandwidth_increase").
        old_bandwidth: Previous bandwidth setting.
        new_bandwidth: New bandwidth setting.
        old_projected_date: Previous projected completion date.
        new_projected_date: Updated projected completion date.

    Returns:
        The persisted GsLmsReplanEvent record.
    """
    event = GsLmsReplanEvent(
        student_id=student_id,
        reason=reason,
        old_bandwidth=old_bandwidth,
        new_bandwidth=new_bandwidth,
        old_projected_date=old_projected_date,
        new_projected_date=new_projected_date,
    )

    db.add(event)
    db.flush()

    return event


__all__ = [
    # DTOs
    "PlanItem",
    "DayPlan",
    "PlanHistoryEntry",
    # Pure scheduling functions
    "generate_day_plan",
    "check_replan_needed",
    "should_suggest_bandwidth_increase",
    "compute_projected_completion",
    # DB-interacting functions
    "find_current_position",
    "get_syllabus_plan_items",
    "get_plan_history",
    "create_daily_plan",
    "record_replan_event",
]
