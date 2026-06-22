"""Gap/coverage computation engine for the GS LMS Platform.

This module computes weak areas from MCQ practice attempts and produces
timestamped gap snapshots for trend tracking. The design mirrors
``app.core.optional.coverage`` but is tailored to the GS LMS domain:
accuracy-based weakness detection per topic and per question type, rather than
weighted-tree covered/remaining percentages.

**Core logic (pure functions + DB helpers):**

* ``compute_topic_accuracy(db, student_id)`` — per-topic accuracy from attempts
* ``compute_type_accuracy(db, student_id)`` — per-question-type accuracy
* ``identify_weak_topics(topic_accuracies, threshold=0.6)`` — topics below 60%
* ``identify_weak_types(type_accuracies, threshold=0.6)`` — types below 60%
* ``generate_recommended_actions(weak_topics, weak_types)`` — action list
* ``create_gap_snapshot(db, student_id)`` — persist a ``GsLmsGapSnapshot``

**Design Properties implemented:**

* Property 14: every topic with accuracy < 60% is in weak_topics; none >= 60%.
* Property 15: lists ordered by severity (lowest accuracy first).

Requirements traced: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Sequence, Tuple

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.gs_lms.models import GsLmsQuestionTypeEnum, GsLmsSyllabusNode
from app.core.gs_lms.student_models import (
    GsLmsGapSnapshot,
    GsLmsPracticeAttempt,
    GsLmsPracticeSession,
    GsLmsPracticeSessionStatusEnum,
)


# ---------------------------------------------------------------------------
# Data transfer objects (pure — no ORM dependency)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TopicAccuracy:
    """Accuracy result for a single syllabus topic.

    Attributes:
        node_id: The syllabus node identifier.
        title: Human-readable topic title.
        accuracy: Fraction correct (0.0–1.0).
        total_attempts: Number of attempts considered.
        correct_count: Number of correct attempts.
    """

    node_id: int
    title: str
    accuracy: float
    total_attempts: int
    correct_count: int


@dataclass(frozen=True)
class TypeAccuracyResult:
    """Accuracy result for a single question type.

    Attributes:
        question_type: The question type enum value.
        accuracy: Fraction correct (0.0–1.0).
        total_attempts: Number of attempts considered.
        correct_count: Number of correct attempts.
    """

    question_type: GsLmsQuestionTypeEnum
    accuracy: float
    total_attempts: int
    correct_count: int


@dataclass(frozen=True)
class RecommendedAction:
    """A recommended action for addressing a gap.

    Attributes:
        action: Description of what to do (e.g., "Practice more").
        target_node_id: Optional target syllabus node.
        reason: Why this action is recommended.
    """

    action: str
    target_node_id: int | None
    reason: str


@dataclass(frozen=True)
class GapProfile:
    """Complete gap profile for a student.

    Attributes:
        overall_accuracy: Student's overall accuracy across all attempts.
        weak_topics: Topics with accuracy < threshold, sorted lowest first.
        weak_question_types: Question types below threshold, sorted lowest first.
        recommended_actions: Prioritized action list.
    """

    overall_accuracy: float
    weak_topics: List[TopicAccuracy] = field(default_factory=list)
    weak_question_types: List[TypeAccuracyResult] = field(default_factory=list)
    recommended_actions: List[RecommendedAction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure computation functions
# ---------------------------------------------------------------------------

def identify_weak_topics(
    topic_accuracies: Sequence[TopicAccuracy],
    threshold: float = 0.6,
) -> List[TopicAccuracy]:
    """Identify weak topics: accuracy strictly below threshold.

    Returns topics ordered by severity (lowest accuracy first).

    Property 14: every topic with accuracy < threshold is included;
    no topic with accuracy >= threshold may appear.
    Property 15: ordered by ascending accuracy.
    """
    weak = [t for t in topic_accuracies if t.accuracy < threshold]
    weak.sort(key=lambda t: t.accuracy)
    return weak


def identify_weak_types(
    type_accuracies: Sequence[TypeAccuracyResult],
    threshold: float = 0.6,
) -> List[TypeAccuracyResult]:
    """Identify weak question types: accuracy strictly below threshold.

    Returns types ordered by severity (lowest accuracy first).

    Property 14: every type with accuracy < threshold is included;
    no type with accuracy >= threshold may appear.
    Property 15: ordered by ascending accuracy.
    """
    weak = [t for t in type_accuracies if t.accuracy < threshold]
    weak.sort(key=lambda t: t.accuracy)
    return weak


def generate_recommended_actions(
    weak_topics: Sequence[TopicAccuracy],
    weak_types: Sequence[TypeAccuracyResult],
) -> List[RecommendedAction]:
    """Generate recommended study actions from weak areas.

    Actions are prioritized by severity (weakest areas first). Topic-based
    actions come before type-based actions within the same priority band.
    """
    actions: List[RecommendedAction] = []

    # Topic-based recommendations (already sorted by severity).
    for topic in weak_topics:
        if topic.accuracy < 0.3:
            action_text = "Re-study topic content from Basic section"
        elif topic.accuracy < 0.5:
            action_text = "Practice more questions on this topic"
        else:
            action_text = "Review weak areas in this topic"

        actions.append(RecommendedAction(
            action=action_text,
            target_node_id=topic.node_id,
            reason=f"Topic accuracy is {topic.accuracy:.0%} "
                   f"({topic.correct_count}/{topic.total_attempts} correct)",
        ))

    # Type-based recommendations (already sorted by severity).
    for qtype in weak_types:
        if qtype.accuracy < 0.3:
            action_text = f"Focused practice on {qtype.question_type.value} questions"
        elif qtype.accuracy < 0.5:
            action_text = f"Practice more {qtype.question_type.value} questions"
        else:
            action_text = f"Review {qtype.question_type.value} question techniques"

        actions.append(RecommendedAction(
            action=action_text,
            target_node_id=None,
            reason=f"Type accuracy is {qtype.accuracy:.0%} "
                   f"({qtype.correct_count}/{qtype.total_attempts} correct)",
        ))

    return actions


def compute_overall_accuracy_from_attempts(
    attempts: Sequence[Tuple[bool | None, ...]],
) -> float:
    """Compute overall accuracy from a sequence of (is_correct,) tuples.

    Skipped attempts (is_correct is None) are excluded from the calculation.
    Returns 0.0 when there are no answered attempts.
    """
    answered = [a for a in attempts if a[0] is not None]
    if not answered:
        return 0.0
    correct = sum(1 for a in answered if a[0] is True)
    return correct / len(answered)


# ---------------------------------------------------------------------------
# DB interaction helpers
# ---------------------------------------------------------------------------

def compute_topic_accuracy(
    db: Session,
    student_id: int,
) -> List[TopicAccuracy]:
    """Compute per-topic accuracy from all practice attempts for a student.

    Queries GsLmsPracticeAttempt records grouped by the session's
    syllabus_node_id. Only answered attempts (is_correct IS NOT NULL) are
    considered.

    Returns a list of TopicAccuracy objects (one per topic with attempts).
    """
    # Query: group attempts by syllabus_node_id via the practice session,
    # computing total answered and correct counts.
    results = (
        db.query(
            GsLmsPracticeSession.syllabus_node_id,
            func.count(GsLmsPracticeAttempt.id).label("total"),
            func.sum(
                case(
                    (GsLmsPracticeAttempt.is_correct == True, 1),  # noqa: E712
                    else_=0,
                )
            ).label("correct"),
        )
        .join(
            GsLmsPracticeSession,
            GsLmsPracticeAttempt.session_id == GsLmsPracticeSession.id,
        )
        .filter(
            GsLmsPracticeAttempt.student_id == student_id,
            GsLmsPracticeAttempt.is_correct.isnot(None),
        )
        .group_by(GsLmsPracticeSession.syllabus_node_id)
        .all()
    )

    # Fetch node titles for the topics.
    node_ids = [r[0] for r in results]
    titles: Dict[int, str] = {}
    if node_ids:
        nodes = (
            db.query(GsLmsSyllabusNode.id, GsLmsSyllabusNode.title)
            .filter(GsLmsSyllabusNode.id.in_(node_ids))
            .all()
        )
        titles = {n[0]: n[1] for n in nodes}

    topic_accuracies: List[TopicAccuracy] = []
    for node_id, total, correct in results:
        correct_int = int(correct) if correct else 0
        total_int = int(total)
        accuracy = correct_int / total_int if total_int > 0 else 0.0
        topic_accuracies.append(TopicAccuracy(
            node_id=node_id,
            title=titles.get(node_id, f"Topic {node_id}"),
            accuracy=accuracy,
            total_attempts=total_int,
            correct_count=correct_int,
        ))

    return topic_accuracies


def compute_type_accuracy_from_db(
    db: Session,
    student_id: int,
) -> List[TypeAccuracyResult]:
    """Compute per-question-type accuracy from all practice attempts.

    Queries GsLmsPracticeAttempt records grouped by question_type.
    Only answered attempts (is_correct IS NOT NULL) are considered.

    Returns a list of TypeAccuracyResult objects (one per type with attempts).
    """
    results = (
        db.query(
            GsLmsPracticeAttempt.question_type,
            func.count(GsLmsPracticeAttempt.id).label("total"),
            func.sum(
                case(
                    (GsLmsPracticeAttempt.is_correct == True, 1),  # noqa: E712
                    else_=0,
                )
            ).label("correct"),
        )
        .filter(
            GsLmsPracticeAttempt.student_id == student_id,
            GsLmsPracticeAttempt.is_correct.isnot(None),
            GsLmsPracticeAttempt.question_type.isnot(None),
        )
        .group_by(GsLmsPracticeAttempt.question_type)
        .all()
    )

    type_accuracies: List[TypeAccuracyResult] = []
    for question_type, total, correct in results:
        correct_int = int(correct) if correct else 0
        total_int = int(total)
        accuracy = correct_int / total_int if total_int > 0 else 0.0
        type_accuracies.append(TypeAccuracyResult(
            question_type=question_type,
            accuracy=accuracy,
            total_attempts=total_int,
            correct_count=correct_int,
        ))

    return type_accuracies


def compute_overall_accuracy(
    db: Session,
    student_id: int,
) -> float:
    """Compute overall accuracy across all practice attempts for a student.

    Only answered attempts (is_correct IS NOT NULL) are considered.
    Returns 0.0 when there are no answered attempts.
    """
    result = (
        db.query(
            func.count(GsLmsPracticeAttempt.id).label("total"),
            func.sum(
                case(
                    (GsLmsPracticeAttempt.is_correct == True, 1),  # noqa: E712
                    else_=0,
                )
            ).label("correct"),
        )
        .filter(
            GsLmsPracticeAttempt.student_id == student_id,
            GsLmsPracticeAttempt.is_correct.isnot(None),
        )
        .first()
    )

    if not result or not result[0]:
        return 0.0

    total = int(result[0])
    correct = int(result[1]) if result[1] else 0
    return correct / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Gap snapshot creation (persistence)
# ---------------------------------------------------------------------------

def create_gap_snapshot(
    db: Session,
    student_id: int,
    threshold: float = 0.6,
) -> GsLmsGapSnapshot:
    """Compute and persist a timestamped gap snapshot for the student.

    This is the main entry point called after every practice submission.
    It computes all accuracy metrics, identifies weak areas, generates
    recommended actions, and persists the snapshot for trend tracking.

    Requirements: 6.5 (update after every practice), 6.6 (timestamped persistence).
    """
    # Compute accuracies.
    topic_accuracies = compute_topic_accuracy(db, student_id)
    type_accuracies = compute_type_accuracy_from_db(db, student_id)
    overall_accuracy = compute_overall_accuracy(db, student_id)

    # Identify weak areas (Property 14 + 15).
    weak_topics = identify_weak_topics(topic_accuracies, threshold)
    weak_types = identify_weak_types(type_accuracies, threshold)

    # Generate recommendations.
    recommended_actions = generate_recommended_actions(weak_topics, weak_types)

    # Serialize to JSON-compatible dicts for the snapshot.
    weak_topics_json = [
        {
            "node_id": t.node_id,
            "title": t.title,
            "accuracy": round(t.accuracy, 4),
        }
        for t in weak_topics
    ]
    weak_types_json = [
        {
            "type": t.question_type.value,
            "accuracy": round(t.accuracy, 4),
            "attempts": t.total_attempts,
        }
        for t in weak_types
    ]
    actions_json = [
        {
            "action": a.action,
            "target_node_id": a.target_node_id,
            "reason": a.reason,
        }
        for a in recommended_actions
    ]

    # Persist the snapshot.
    snapshot = GsLmsGapSnapshot(
        student_id=student_id,
        computed_at=datetime.now(timezone.utc),
        overall_accuracy=round(overall_accuracy, 4),
        weak_topics=weak_topics_json,
        weak_question_types=weak_types_json,
        recommended_actions=actions_json,
    )
    db.add(snapshot)
    db.flush()

    return snapshot


def get_latest_gap_snapshot(
    db: Session,
    student_id: int,
) -> GsLmsGapSnapshot | None:
    """Retrieve the most recent gap snapshot for a student.

    Returns None if no snapshot exists yet.
    """
    return (
        db.query(GsLmsGapSnapshot)
        .filter(GsLmsGapSnapshot.student_id == student_id)
        .order_by(GsLmsGapSnapshot.computed_at.desc())
        .first()
    )


def compute_gap_profile(
    db: Session,
    student_id: int,
    threshold: float = 0.6,
) -> GapProfile:
    """Compute the full gap profile for a student (without persisting).

    Useful for real-time gap display without creating a snapshot.
    """
    topic_accuracies = compute_topic_accuracy(db, student_id)
    type_accuracies = compute_type_accuracy_from_db(db, student_id)
    overall_accuracy = compute_overall_accuracy(db, student_id)

    weak_topics = identify_weak_topics(topic_accuracies, threshold)
    weak_types = identify_weak_types(type_accuracies, threshold)
    recommended_actions = generate_recommended_actions(weak_topics, weak_types)

    return GapProfile(
        overall_accuracy=overall_accuracy,
        weak_topics=weak_topics,
        weak_question_types=weak_types,
        recommended_actions=recommended_actions,
    )


__all__ = [
    # DTOs
    "TopicAccuracy",
    "TypeAccuracyResult",
    "RecommendedAction",
    "GapProfile",
    # Pure functions
    "identify_weak_topics",
    "identify_weak_types",
    "generate_recommended_actions",
    "compute_overall_accuracy_from_attempts",
    # DB helpers
    "compute_topic_accuracy",
    "compute_type_accuracy_from_db",
    "compute_overall_accuracy",
    # Snapshot
    "create_gap_snapshot",
    "get_latest_gap_snapshot",
    "compute_gap_profile",
]
