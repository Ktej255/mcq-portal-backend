"""Spaced-repetition revisit scheduling for the GS LMS.

When a student completes all non-skippable sections of a topic, the system
auto-creates three revisit schedule records at Day+3, Day+7, and Day+21.
These records drive the daily planner's "Quick Recall" items.

The unique constraint on (student_id, syllabus_node_id, revisit_type) ensures
idempotency — calling schedule_revisits multiple times for the same topic
will not create duplicates.

Requirements traced: 4.1
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.gs_lms.student_models import GsLmsRevisitSchedule


# The three revisit intervals: (revisit_type label, days offset from today)
_REVISIT_INTERVALS: list[tuple[str, int]] = [
    ("day_3", 3),
    ("day_7", 7),
    ("day_21", 21),
]


def schedule_revisits(
    db: Session,
    student_id: int,
    syllabus_node_id: int,
) -> list[GsLmsRevisitSchedule]:
    """Create spaced-repetition revisit records for a completed topic.

    Creates 3 records with due dates at today + 3, 7, and 21 days.
    Uses INSERT with IntegrityError handling to be idempotent — if records
    already exist (unique constraint on student_id + node_id + revisit_type),
    they are silently skipped.

    Args:
        db: Active SQLAlchemy session.
        student_id: The student who completed the topic.
        syllabus_node_id: The topic node that was just completed.

    Returns:
        List of newly created GsLmsRevisitSchedule records (may be empty
        if all 3 already existed).
    """
    today = date.today()
    created: list[GsLmsRevisitSchedule] = []

    for revisit_type, days_offset in _REVISIT_INTERVALS:
        # Check if this revisit already exists (idempotency guard)
        existing = (
            db.query(GsLmsRevisitSchedule)
            .filter(
                GsLmsRevisitSchedule.student_id == student_id,
                GsLmsRevisitSchedule.syllabus_node_id == syllabus_node_id,
                GsLmsRevisitSchedule.revisit_type == revisit_type,
            )
            .one_or_none()
        )
        if existing is not None:
            continue

        record = GsLmsRevisitSchedule(
            student_id=student_id,
            syllabus_node_id=syllabus_node_id,
            due_date=today + timedelta(days=days_offset),
            revisit_type=revisit_type,
            completed=False,
        )
        db.add(record)

        try:
            db.flush()
            created.append(record)
        except IntegrityError:
            # Unique constraint violation — record already exists (race condition)
            db.rollback()

    return created
