"""Daily Planner endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms; auth-gated at the package router):
* GET /geography/plan/today — Current day's plan with items + projected completion
* PUT /geography/plan/bandwidth — Set/update daily bandwidth
* POST /geography/plan/replan — Manual trigger replanning

Design properties enforced:
* Property 16 (position continuity): day plan contains min(B, remaining)
  items from current position in display order.
* Property 17 (replan trigger): replanning triggers on 2 consecutive misses.
* Property 18 (projected completion): today + ceil(R / B) days.

Requirements traced: 7.1, 7.2, 7.4, 7.5, 7.6
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs.models import GsSubject
from app.core.gs_lms.planner import (
    create_daily_plan,
    find_current_position,
    get_syllabus_plan_items,
    get_plan_history,
    record_replan_event,
    check_replan_needed,
    should_suggest_bandwidth_increase,
    compute_projected_completion,
    generate_day_plan,
)
from app.core.gs_lms.student_models import (
    GsLmsDailyPlan,
    GsLmsOnboardingStatus,
    GsLmsReplanEvent,
)
from app.api.v1.gs_lms.schemas import (
    GsLmsDailyPlanOut,
    GsLmsPlanItemOut,
    GsLmsBandwidthIn,
    GsLmsReplanOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_geography_subject(db: Session) -> GsSubject:
    """Retrieve the GS Geography subject or raise 404."""
    subject = (
        db.query(GsSubject)
        .filter(GsSubject.slug == "geography")
        .one_or_none()
    )
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GS Geography subject not found",
        )
    return subject


def _get_student_bandwidth(db: Session, student_id: int) -> int:
    """Get the student's configured bandwidth from onboarding or most recent plan.

    Priority: most recent daily plan bandwidth > onboarding bandwidth_selected > default 3.
    """
    # Check most recent daily plan first.
    latest_plan = (
        db.query(GsLmsDailyPlan)
        .filter(GsLmsDailyPlan.student_id == student_id)
        .order_by(GsLmsDailyPlan.plan_date.desc())
        .first()
    )
    if latest_plan is not None:
        return latest_plan.bandwidth

    # Fall back to onboarding bandwidth selection.
    onboarding = (
        db.query(GsLmsOnboardingStatus)
        .filter(GsLmsOnboardingStatus.student_id == student_id)
        .first()
    )
    if onboarding is not None and onboarding.bandwidth_selected is not None:
        return onboarding.bandwidth_selected

    # Default bandwidth.
    return 3


def _get_today_plan(db: Session, student_id: int) -> GsLmsDailyPlan | None:
    """Get today's existing plan for the student, or None."""
    today = date.today()
    return (
        db.query(GsLmsDailyPlan)
        .filter(
            GsLmsDailyPlan.student_id == student_id,
            GsLmsDailyPlan.plan_date == today,
        )
        .first()
    )


def _count_completed_items(plan: GsLmsDailyPlan) -> int:
    """Count completed items in a plan."""
    completed_items = plan.completed_items or []
    return len(completed_items)


def _compute_streak(db: Session, student_id: int) -> int:
    """Compute the current streak of consecutive target-met days."""
    plans = (
        db.query(GsLmsDailyPlan)
        .filter(
            GsLmsDailyPlan.student_id == student_id,
            GsLmsDailyPlan.is_target_met == True,  # noqa: E712
        )
        .order_by(GsLmsDailyPlan.plan_date.desc())
        .all()
    )
    # Count consecutive target-met days from most recent backwards.
    # We need all plans ordered by date to check actual consecutiveness.
    all_plans = (
        db.query(GsLmsDailyPlan)
        .filter(GsLmsDailyPlan.student_id == student_id)
        .order_by(GsLmsDailyPlan.plan_date.desc())
        .all()
    )
    streak = 0
    for plan in all_plans:
        if plan.is_target_met is True:
            streak += 1
        elif plan.is_target_met is False:
            break
        # Skip plans with is_target_met = None (today's plan, not yet evaluated)
    return streak


def _plan_to_response(
    plan: GsLmsDailyPlan, streak_days: int
) -> GsLmsDailyPlanOut:
    """Convert a GsLmsDailyPlan DB record to the response schema."""
    planned_items = plan.planned_items or []
    completed_items = plan.completed_items or []
    completed_count = len(completed_items)

    items_out = []
    # Build a set of completed node_ids for fast lookup.
    completed_node_ids = {item["node_id"] for item in completed_items}

    for item in planned_items:
        node_id = item["node_id"]
        is_completed = node_id in completed_node_ids
        # Find completed_at if available.
        completed_at = None
        if is_completed:
            for ci in completed_items:
                if ci["node_id"] == node_id:
                    completed_at = ci.get("completed_at")
                    break

        items_out.append(
            GsLmsPlanItemOut(
                node_id=node_id,
                title=item.get("title", f"Topic {node_id}"),
                item_type=item.get("type", "section"),
                completed=is_completed,
                completed_at=completed_at,
            )
        )

    projected_date = None
    if plan.projected_completion_date is not None:
        projected_date = plan.projected_completion_date.isoformat()

    return GsLmsDailyPlanOut(
        plan_date=plan.plan_date.isoformat(),
        bandwidth=plan.bandwidth,
        planned_items=items_out,
        completed_count=completed_count,
        is_target_met=plan.is_target_met,
        projected_completion_date=projected_date,
        streak_days=streak_days,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/geography/plan/today")
def get_today_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return today's plan for the authenticated student.

    Creates a new plan for today if one doesn't exist yet. Includes
    planned items, completion count, target status, projected completion,
    and streak info.

    Requirements: 7.1, 7.2, 7.5, 7.6
    """
    subject = _get_geography_subject(db)
    student_id = current_user.id

    # Check if today's plan already exists.
    plan = _get_today_plan(db, student_id)

    if plan is None:
        # Create a new plan for today.
        bandwidth = _get_student_bandwidth(db, student_id)
        plan = create_daily_plan(
            db=db,
            student_id=student_id,
            subject_id=subject.id,
            bandwidth=bandwidth,
        )
        # Enrich planned_items with titles from syllabus items.
        syllabus_items = get_syllabus_plan_items(db, subject.id)
        item_titles = {item.node_id: item.title for item in syllabus_items}
        enriched_items = []
        for item in (plan.planned_items or []):
            enriched_items.append({
                "node_id": item["node_id"],
                "type": item.get("type", "section"),
                "title": item_titles.get(item["node_id"], f"Topic {item['node_id']}"),
            })
        plan.planned_items = enriched_items
        db.flush()
        db.commit()
    else:
        db.commit()

    streak = _compute_streak(db, student_id)
    data = _plan_to_response(plan, streak)

    return StandardResponse(
        success=True,
        message="Today's plan retrieved",
        data=data,
    )


@router.put("/geography/plan/bandwidth")
def update_bandwidth(
    payload: GsLmsBandwidthIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Set or update the student's daily bandwidth.

    Validates bandwidth > 0, updates the student's bandwidth in onboarding,
    and creates/updates today's plan with the new bandwidth.

    Requirements: 7.1, 7.6
    """
    subject = _get_geography_subject(db)
    student_id = current_user.id
    new_bandwidth = payload.bandwidth

    # Validate bandwidth > 0 (Pydantic does this via gt=0, but be explicit).
    if new_bandwidth <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bandwidth must be a positive integer",
        )

    # Update onboarding record if it exists.
    onboarding = (
        db.query(GsLmsOnboardingStatus)
        .filter(GsLmsOnboardingStatus.student_id == student_id)
        .first()
    )
    if onboarding is not None:
        onboarding.bandwidth_selected = new_bandwidth
    else:
        # Create a minimal onboarding record with the bandwidth.
        onboarding = GsLmsOnboardingStatus(
            student_id=student_id,
            completed=False,
            bandwidth_selected=new_bandwidth,
        )
        db.add(onboarding)

    # Check if today's plan exists — update or create.
    today_plan = _get_today_plan(db, student_id)

    if today_plan is not None:
        # Update existing plan with new bandwidth and regenerate items.
        old_bandwidth = today_plan.bandwidth
        syllabus_items = get_syllabus_plan_items(db, subject.id)
        current_position = find_current_position(db, student_id, subject.id)
        day_plan = generate_day_plan(syllabus_items, current_position, new_bandwidth)

        planned_items_json = [
            {
                "node_id": item.node_id,
                "type": item.item_type,
                "title": item.title,
            }
            for item in day_plan.items
        ]

        today_plan.bandwidth = new_bandwidth
        today_plan.planned_items = planned_items_json
        today_plan.projected_completion_date = day_plan.projected_completion
    else:
        # Create a new plan for today with the new bandwidth.
        plan = create_daily_plan(
            db=db,
            student_id=student_id,
            subject_id=subject.id,
            bandwidth=new_bandwidth,
        )
        # Enrich with titles.
        syllabus_items = get_syllabus_plan_items(db, subject.id)
        item_titles = {item.node_id: item.title for item in syllabus_items}
        enriched_items = []
        for item in (plan.planned_items or []):
            enriched_items.append({
                "node_id": item["node_id"],
                "type": item.get("type", "section"),
                "title": item_titles.get(item["node_id"], f"Topic {item['node_id']}"),
            })
        plan.planned_items = enriched_items

    db.commit()

    # Re-fetch today's plan for the response.
    today_plan = _get_today_plan(db, student_id)
    streak = _compute_streak(db, student_id)
    data = _plan_to_response(today_plan, streak)

    return StandardResponse(
        success=True,
        message="Bandwidth updated successfully",
        data=data,
    )


@router.post("/geography/plan/replan")
def trigger_replan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Manually trigger replanning.

    Records a replan event and regenerates today's plan. Uses the current
    bandwidth (no change on manual replan — only recalculates items from
    current position).

    Requirements: 7.4, 7.6
    """
    subject = _get_geography_subject(db)
    student_id = current_user.id

    # Get current bandwidth.
    current_bandwidth = _get_student_bandwidth(db, student_id)

    # Get current projected completion.
    syllabus_items = get_syllabus_plan_items(db, subject.id)
    current_position = find_current_position(db, student_id, subject.id)
    remaining = max(0, len(syllabus_items) - current_position)
    old_projected = compute_projected_completion(remaining, current_bandwidth)

    # For manual replan, bandwidth stays the same but plan is regenerated.
    new_bandwidth = current_bandwidth
    new_projected = compute_projected_completion(remaining, new_bandwidth)

    # Record the replan event.
    event = record_replan_event(
        db=db,
        student_id=student_id,
        reason="manual",
        old_bandwidth=current_bandwidth,
        new_bandwidth=new_bandwidth,
        old_projected_date=old_projected,
        new_projected_date=new_projected,
    )

    # Regenerate today's plan.
    today_plan = _get_today_plan(db, student_id)
    if today_plan is not None:
        # Regenerate from current position.
        day_plan = generate_day_plan(syllabus_items, current_position, new_bandwidth)
        planned_items_json = [
            {
                "node_id": item.node_id,
                "type": item.item_type,
                "title": item.title,
            }
            for item in day_plan.items
        ]
        today_plan.planned_items = planned_items_json
        today_plan.projected_completion_date = day_plan.projected_completion
    else:
        # Create a new plan for today.
        plan = create_daily_plan(
            db=db,
            student_id=student_id,
            subject_id=subject.id,
            bandwidth=new_bandwidth,
        )
        # Enrich with titles.
        item_titles = {item.node_id: item.title for item in syllabus_items}
        enriched_items = []
        for item in (plan.planned_items or []):
            enriched_items.append({
                "node_id": item["node_id"],
                "type": item.get("type", "section"),
                "title": item_titles.get(item["node_id"], f"Topic {item['node_id']}"),
            })
        plan.planned_items = enriched_items

    db.commit()

    # Build response.
    data = GsLmsReplanOut(
        reason="manual",
        old_bandwidth=current_bandwidth,
        new_bandwidth=new_bandwidth,
        old_projected_date=old_projected.isoformat() if old_projected else None,
        new_projected_date=new_projected.isoformat() if new_projected else None,
        triggered_at=event.triggered_at.isoformat() if event.triggered_at else datetime.now(timezone.utc).isoformat(),
    )

    return StandardResponse(
        success=True,
        message="Replanning triggered successfully",
        data=data,
    )
