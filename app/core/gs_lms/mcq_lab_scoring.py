"""MCQ Lab Scoring Engine — batch scoring for the 15-question simultaneous
MCQ Lab with all-or-nothing per-question evaluation and weakness pattern
computation.

All scoring functions are pure (no I/O). Persistence is handled by the
caller (API router or service layer).

Requirements: 6.2, 6.6, 7.1, 7.4, 7.5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


# ---------------------------------------------------------------------------
# Constants — Required Type Distribution
# ---------------------------------------------------------------------------

# Maps UPSC question type → required count in each MCQ Lab (total = 15)
REQUIRED_TYPE_DISTRIBUTION: Dict[str, int] = {
    "MULTI_STATEMENT": 3,
    "HOW_MANY_CORRECT": 2,
    "ASSERTION_REASON": 2,
    "NOT_EXCEPTION": 2,
    "SCENARIO_APPLIED": 3,
    "MATCH_THE_PAIRS": 2,
    "DIRECT_RECALL": 1,
}

TOTAL_MCQ_LAB_QUESTIONS = 15

# Weakness thresholds
WEAKNESS_THRESHOLD = 0.5       # Flag as weak below this accuracy
WEAKNESS_MIN_ATTEMPTS = 3      # Minimum attempts before flagging
RECOVERY_THRESHOLD = 0.7       # Remove flag above this accuracy
RECOVERY_WINDOW = 5            # Look at last N attempts for recovery


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class McqLabAttempt:
    """A single question attempt within an MCQ Lab session."""
    question_id: int
    question_type: str
    chosen_answer: str
    correct_answer: str
    is_correct: bool
    time_taken_seconds: float | None = None


@dataclass(frozen=True)
class TypeBreakdown:
    """Per-type accuracy breakdown."""
    question_type: str
    total: int
    correct: int
    accuracy: float  # 0.0–1.0


@dataclass(frozen=True)
class McqLabResult:
    """Complete MCQ Lab session result."""
    total_questions: int       # always 15
    correct_count: int
    score: float               # 0.0–1.0
    attempts: List[McqLabAttempt] = field(default_factory=list)
    type_breakdown: List[TypeBreakdown] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scoring Functions
# ---------------------------------------------------------------------------

def score_mcq_lab(attempts: list[McqLabAttempt]) -> McqLabResult:
    """Score a complete MCQ Lab submission (all 15 answers).

    All-or-nothing per question: correct only when chosen == stored correct.

    Args:
        attempts: List of 15 McqLabAttempt objects.

    Returns:
        McqLabResult with overall score and per-type breakdown.
    """
    total_questions = len(attempts)
    correct_count = sum(1 for a in attempts if a.is_correct)
    score = correct_count / total_questions if total_questions > 0 else 0.0

    # Compute per-type breakdown
    type_stats: Dict[str, tuple[int, int]] = {}  # type -> (correct, total)
    for attempt in attempts:
        qtype = attempt.question_type
        correct, total = type_stats.get(qtype, (0, 0))
        total += 1
        if attempt.is_correct:
            correct += 1
        type_stats[qtype] = (correct, total)

    type_breakdown = [
        TypeBreakdown(
            question_type=qtype,
            total=total,
            correct=correct,
            accuracy=correct / total if total > 0 else 0.0,
        )
        for qtype, (correct, total) in sorted(type_stats.items())
    ]

    return McqLabResult(
        total_questions=total_questions,
        correct_count=correct_count,
        score=score,
        attempts=list(attempts),
        type_breakdown=type_breakdown,
    )


def create_attempt(
    question_id: int,
    question_type: str,
    chosen_answer: str,
    correct_answer: str,
    time_taken_seconds: float | None = None,
) -> McqLabAttempt:
    """Create a McqLabAttempt with all-or-nothing correctness computed.

    Args:
        question_id: The question's database ID.
        question_type: The UPSC question type classification.
        chosen_answer: The student's selected answer.
        correct_answer: The stored correct answer.
        time_taken_seconds: Optional time taken on this question.

    Returns:
        McqLabAttempt with is_correct computed.
    """
    is_correct = chosen_answer.strip().upper() == correct_answer.strip().upper()
    return McqLabAttempt(
        question_id=question_id,
        question_type=question_type,
        chosen_answer=chosen_answer,
        correct_answer=correct_answer,
        is_correct=is_correct,
        time_taken_seconds=time_taken_seconds,
    )


# ---------------------------------------------------------------------------
# Weakness Pattern Functions
# ---------------------------------------------------------------------------

def update_weakness_pattern(
    existing_pattern: Dict[str, tuple[int, int]],
    new_session: McqLabResult,
) -> Dict[str, tuple[int, int]]:
    """Merge new session results into the running weakness pattern.

    For each question type: accumulates (correct, total) across all sessions.

    Args:
        existing_pattern: Current pattern as {type: (correct_count, total_count)}
        new_session: The MCQ Lab result to merge in.

    Returns:
        Updated pattern dict.
    """
    pattern = dict(existing_pattern)

    for breakdown in new_session.type_breakdown:
        existing_correct, existing_total = pattern.get(breakdown.question_type, (0, 0))
        pattern[breakdown.question_type] = (
            existing_correct + breakdown.correct,
            existing_total + breakdown.total,
        )

    return pattern


def get_weak_types(
    pattern: Dict[str, tuple[int, int]],
    weakness_threshold: float = WEAKNESS_THRESHOLD,
    min_attempts: int = WEAKNESS_MIN_ATTEMPTS,
) -> list[str]:
    """Return question types flagged as weaknesses.

    A type is weak if: accuracy < threshold AND total >= min_attempts.

    Args:
        pattern: Pattern as {type: (correct_count, total_count)}
        weakness_threshold: Accuracy below which a type is weak.
        min_attempts: Minimum attempts before flagging.

    Returns:
        List of weak question type strings.
    """
    weak_types: list[str] = []

    for qtype, (correct, total) in pattern.items():
        if total >= min_attempts:
            accuracy = correct / total if total > 0 else 0.0
            if accuracy < weakness_threshold:
                weak_types.append(qtype)

    return weak_types


def check_weakness_recovery(
    recent_attempts: list[McqLabAttempt],
    question_type: str,
    recovery_threshold: float = RECOVERY_THRESHOLD,
    recent_window: int = RECOVERY_WINDOW,
) -> bool:
    """Check if a question type has recovered from weakness status.

    Recovered if accuracy >= recovery_threshold across the most recent
    `recent_window` attempts of that type.

    Args:
        recent_attempts: List of recent attempts (should be pre-filtered to type).
        question_type: The type to check recovery for.
        recovery_threshold: Accuracy threshold for recovery.
        recent_window: Number of recent attempts to consider.

    Returns:
        True if the type has recovered.
    """
    type_attempts = [
        a for a in recent_attempts
        if a.question_type == question_type
    ]

    # Take the most recent N
    recent = type_attempts[-recent_window:] if len(type_attempts) > recent_window else type_attempts

    if len(recent) < recent_window:
        return False

    correct = sum(1 for a in recent if a.is_correct)
    accuracy = correct / len(recent) if recent else 0.0

    return accuracy >= recovery_threshold


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "REQUIRED_TYPE_DISTRIBUTION",
    "TOTAL_MCQ_LAB_QUESTIONS",
    "WEAKNESS_THRESHOLD",
    "WEAKNESS_MIN_ATTEMPTS",
    "RECOVERY_THRESHOLD",
    "RECOVERY_WINDOW",
    "McqLabAttempt",
    "TypeBreakdown",
    "McqLabResult",
    "score_mcq_lab",
    "create_attempt",
    "update_weakness_pattern",
    "get_weak_types",
    "check_weakness_recovery",
]
