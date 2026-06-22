"""MCQ practice scoring and session state engine for the GS LMS Platform.

This module provides **pure functions** for:

* **Scoring**: computing total score and per-question-type accuracy from a set
  of practice attempts (design Property 11 / Requirements 4.3, 4.4, 4.5).
* **Question-type classification**: tagging each question with its
  ``GsLmsQuestionTypeEnum`` category.
* **Session state management**: enforcing sequential access (only the question
  at ``current_index`` can be answered/skipped — design Property 10 /
  Requirement 4.1) and tracking session lifecycle.

The scoring math is intentionally separated from the ORM/endpoint layer so
that correctness can be validated with pure unit and property tests.

Requirements traced: 4.1, 4.3, 4.4, 4.5, 4.6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from app.core.gs_lms.models import GsLmsQuestionTypeEnum


# ---------------------------------------------------------------------------
# Data transfer objects (pure — no ORM dependency)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Attempt:
    """One student attempt at a practice question.

    Mirrors the persisted ``GsLmsPracticeAttempt`` record but as a plain
    value object for the pure scoring functions.
    """

    question_id: int
    question_type: GsLmsQuestionTypeEnum
    chosen_answer: Optional[str]  # None means skipped
    correct_answer: str
    is_correct: Optional[bool]  # None for skipped
    time_taken_seconds: Optional[float] = None


@dataclass(frozen=True)
class TypeAccuracy:
    """Per-question-type accuracy result.

    Invariant (Property 11b):
        accuracy == correct / total  (for total > 0)
    """

    question_type: GsLmsQuestionTypeEnum
    total: int
    correct: int
    accuracy: float  # 0.0–1.0


@dataclass(frozen=True)
class ScoringResult:
    """Full scoring output after session submission.

    Invariant (Property 11a):
        score == correct_count / total_questions  (for total_questions > 0)
    """

    total_questions: int
    correct_count: int
    score: float  # 0.0–1.0
    type_accuracies: List[TypeAccuracy] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    """Mutable session state tracking sequential question progression.

    Invariant (Property 10):
        Only the question at ``current_index`` may be answered or skipped.
        ``advance()`` is the sole mechanism to move forward.
    """

    total_questions: int
    current_index: int = 0

    def can_answer_at(self, index: int) -> bool:
        """Return True only if ``index`` matches the current position."""
        return index == self.current_index and not self.is_complete

    @property
    def is_complete(self) -> bool:
        """True when all questions have been traversed."""
        return self.current_index >= self.total_questions

    def advance(self) -> None:
        """Move to the next question. No-op if already complete."""
        if not self.is_complete:
            self.current_index += 1


# ---------------------------------------------------------------------------
# Scoring functions (pure)
# ---------------------------------------------------------------------------

def compute_score(attempts: Sequence[Attempt]) -> float:
    """Compute total score as count(correct) / count(total).

    Returns 0.0 when there are no attempts.

    Property 11a: score == correct_count / total_questions.
    """
    total = len(attempts)
    if total == 0:
        return 0.0
    correct = sum(1 for a in attempts if a.is_correct is True)
    return correct / total


def compute_type_accuracy(attempts: Sequence[Attempt]) -> List[TypeAccuracy]:
    """Compute per-question-type accuracy breakdown.

    For each question type T present in the attempts:
        type_accuracy(T) = count(correct of type T) / count(total of type T)

    Returns results sorted by question_type value for deterministic output.

    Property 11b: for each T, accuracy = correct_of_T / total_of_T.
    """
    # Group attempts by type.
    by_type: Dict[GsLmsQuestionTypeEnum, List[Attempt]] = {}
    for a in attempts:
        by_type.setdefault(a.question_type, []).append(a)

    results: List[TypeAccuracy] = []
    for qtype, type_attempts in sorted(by_type.items(), key=lambda x: x[0].value):
        total = len(type_attempts)
        correct = sum(1 for a in type_attempts if a.is_correct is True)
        accuracy = correct / total if total > 0 else 0.0
        results.append(TypeAccuracy(
            question_type=qtype,
            total=total,
            correct=correct,
            accuracy=accuracy,
        ))

    return results


def classify_question_type(question_type_value: str) -> GsLmsQuestionTypeEnum:
    """Map a raw question_type string to the enum.

    Raises ValueError if the string is not a valid GsLmsQuestionTypeEnum member.
    """
    return GsLmsQuestionTypeEnum(question_type_value)


# ---------------------------------------------------------------------------
# Session state management functions
# ---------------------------------------------------------------------------

def advance_session(session: SessionState) -> SessionState:
    """Advance the session to the next question. Returns the same session.

    Requirement 4.1: sequential access — only the current question can be
    answered/skipped, then the session advances.
    """
    session.advance()
    return session


def is_session_complete(session: SessionState) -> bool:
    """Check if a session has traversed all questions.

    Returns True when current_index >= total_questions.
    """
    return session.is_complete


def score_session(session: SessionState, attempts: Sequence[Attempt]) -> ScoringResult:
    """Compute the full scoring result for a completed session.

    Combines total score computation and per-type accuracy breakdown into
    a single ``ScoringResult``.

    Requirements 4.3 (total score), 4.4 (question type classification),
    4.5 (per-type accuracy in results).
    """
    total = len(attempts)
    correct_count = sum(1 for a in attempts if a.is_correct is True)
    score = correct_count / total if total > 0 else 0.0
    type_accuracies = compute_type_accuracy(attempts)

    return ScoringResult(
        total_questions=total,
        correct_count=correct_count,
        score=score,
        type_accuracies=type_accuracies,
    )


__all__ = [
    # DTOs
    "Attempt",
    "TypeAccuracy",
    "ScoringResult",
    "SessionState",
    # Pure scoring
    "compute_score",
    "compute_type_accuracy",
    "classify_question_type",
    # Session state
    "advance_session",
    "is_session_complete",
    "score_session",
]
