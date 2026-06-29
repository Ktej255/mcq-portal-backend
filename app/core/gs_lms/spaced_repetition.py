"""Spaced Repetition Scheduler — adaptive interval computation based on
recall performance.

Replaces the fixed Day+3/7/21 pattern with performance-based intervals that
adjust based on recall scores. All interval computation functions are pure.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_INTERVAL_DAYS = 1
MAX_INTERVAL_DAYS = 90
SHORT_INTERVAL_MAX = 3   # for scores < 0.6
LONG_INTERVAL_MIN = 5    # for scores >= 0.6
LONG_INTERVAL_MAX = 7
MISSED_OVERDUE_DAYS = 2  # days after due date before marking missed
MISSED_NEXT_INTERVAL = 3  # max interval after a missed session


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScheduleEntry:
    """A computed next-recall schedule."""
    due_date: date
    recall_interval_days: int
    previous_score: float | None


# ---------------------------------------------------------------------------
# Initial Interval Computation
# ---------------------------------------------------------------------------

def compute_initial_interval(average_recall_score: float) -> int:
    """Compute the first recall interval after topic completion.

    Rules (Req 10.1, 10.2, 10.3):
    - If avg score < 0.6: interval = 1–3 days (linearly scaled)
    - If avg score >= 0.6: interval = 5–7 days (linearly scaled)

    Args:
        average_recall_score: Float in [0.0, 1.0].

    Returns:
        Integer interval in days, always within [1, 7].
    """
    score = max(0.0, min(1.0, average_recall_score))

    if score < 0.6:
        # Scale 0.0 → 1 day, 0.59 → 3 days
        normalized = score / 0.6 if score > 0 else 0.0
        interval = 1 + normalized * (SHORT_INTERVAL_MAX - 1)
        return max(MIN_INTERVAL_DAYS, min(SHORT_INTERVAL_MAX, round(interval)))
    else:
        # Scale 0.6 → 5 days, 1.0 → 7 days
        normalized = (score - 0.6) / 0.4
        interval = LONG_INTERVAL_MIN + normalized * (LONG_INTERVAL_MAX - LONG_INTERVAL_MIN)
        return max(LONG_INTERVAL_MIN, min(LONG_INTERVAL_MAX, round(interval)))


# ---------------------------------------------------------------------------
# Next Interval Computation
# ---------------------------------------------------------------------------

def compute_next_interval(
    current_interval: int,
    current_score: float,
    previous_score: float | None,
) -> int:
    """Compute the next recall interval after a recall session.

    Rules (Req 10.4, 10.5):
    - If score > previous_score: increase by >= 50%, capped at 90 days
    - If score <= previous_score: reduce to <= 50% of current, min 1 day

    Args:
        current_interval: The interval that was just used (days).
        current_score: The recall score from the session just completed (0.0–1.0).
        previous_score: The recall score from the prior session, or None if first.

    Returns:
        Integer interval in days, clamped to [1, 90].
    """
    if previous_score is None or current_score > previous_score:
        # Score improved: increase interval by >= 50%
        increase = max(current_interval // 2, 1)
        new_interval = current_interval + increase
        return min(new_interval, MAX_INTERVAL_DAYS)
    else:
        # Score same or declined: reduce to <= 50%
        new_interval = current_interval // 2
        return max(new_interval, MIN_INTERVAL_DAYS)


# ---------------------------------------------------------------------------
# Missed Session Handling
# ---------------------------------------------------------------------------

def handle_missed_session(
    scheduled_date: date,
    today: date,
) -> ScheduleEntry | None:
    """Handle a missed recall session (Req 10.6).

    If today > scheduled_date + 2 days: mark as missed, schedule next at
    <= 3 days from today.

    Args:
        scheduled_date: The originally scheduled recall date.
        today: The current date.

    Returns:
        A new ScheduleEntry if overdue, or None if not yet overdue.
    """
    overdue_threshold = scheduled_date + timedelta(days=MISSED_OVERDUE_DAYS)

    if today > overdue_threshold:
        return ScheduleEntry(
            due_date=today + timedelta(days=MISSED_NEXT_INTERVAL),
            recall_interval_days=MISSED_NEXT_INTERVAL,
            previous_score=None,
        )

    return None


# ---------------------------------------------------------------------------
# Schedule After Completion
# ---------------------------------------------------------------------------

def schedule_after_completion(
    average_recall_score: float,
    completion_date: date,
) -> ScheduleEntry:
    """Create the first spaced repetition schedule after topic completion.

    Args:
        average_recall_score: Average recall score across all sections (0.0–1.0).
        completion_date: The date the topic was completed.

    Returns:
        A ScheduleEntry with the computed due date and interval.
    """
    interval = compute_initial_interval(average_recall_score)

    return ScheduleEntry(
        due_date=completion_date + timedelta(days=interval),
        recall_interval_days=interval,
        previous_score=average_recall_score,
    )


# ---------------------------------------------------------------------------
# Schedule After Recall Session
# ---------------------------------------------------------------------------

def schedule_after_recall(
    current_interval: int,
    current_score: float,
    previous_score: float | None,
    session_date: date,
) -> ScheduleEntry:
    """Create the next schedule entry after a recall session.

    Args:
        current_interval: The interval that was just used.
        current_score: Score from the recall session just completed.
        previous_score: Score from the prior recall session, or None.
        session_date: Date the recall session was completed.

    Returns:
        A ScheduleEntry with the next due date and interval.
    """
    next_interval = compute_next_interval(current_interval, current_score, previous_score)

    return ScheduleEntry(
        due_date=session_date + timedelta(days=next_interval),
        recall_interval_days=next_interval,
        previous_score=current_score,
    )


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "MIN_INTERVAL_DAYS",
    "MAX_INTERVAL_DAYS",
    "SHORT_INTERVAL_MAX",
    "LONG_INTERVAL_MIN",
    "LONG_INTERVAL_MAX",
    "ScheduleEntry",
    "compute_initial_interval",
    "compute_next_interval",
    "handle_missed_session",
    "schedule_after_completion",
    "schedule_after_recall",
]
