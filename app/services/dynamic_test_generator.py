from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import Question
from app.services.adaptive_learning_engine import (
    ADAPTIVE_VERSION,
    adaptive_reliability,
    candidate_questions_for_topic,
    cognitive_load_balance,
    personalized_difficulty,
    topic_priority,
)
from app.services.knowledge_graph_engine import build_knowledge_graph, conceptual_recovery_sequence
from app.services.student_longitudinal_profile import build_student_longitudinal_profile


def _difficulty_order_key(item: dict[str, Any], fatigue_aware: bool) -> tuple[float, int]:
    relative = item["difficulty"]["relative_difficulty"]
    if fatigue_aware:
        return (abs(relative - 0.55), item["question_id"])
    return (-relative, item["question_id"])


def assemble_dynamic_test(db: Session, user_id: int, target_count: int = 10) -> dict[str, Any]:
    profile = build_student_longitudinal_profile(db, user_id)
    reliability = adaptive_reliability(profile, evidence_count=profile.get("attempt_count", 0))
    load = cognitive_load_balance(profile)
    priorities = topic_priority(profile)
    graph = build_knowledge_graph(db)
    recovery_topics = [item["topic"] for item in conceptual_recovery_sequence(graph, profile)]
    ordered_topics = list(dict.fromkeys([*recovery_topics, *[item["topic"] for item in priorities]]))
    selected: list[dict[str, Any]] = []
    seen_question_ids = set()

    for topic in ordered_topics:
        priority = next((item for item in priorities if item["topic"] == topic), {"topic": topic, "priority_score": 50})
        mastery = 100 - priority["priority_score"]
        candidates = candidate_questions_for_topic(db, topic)
        scored = []
        for question in candidates:
            if question.id in seen_question_ids:
                continue
            difficulty = personalized_difficulty(question, mastery, reliability["recommendation_confidence"])
            scored.append({
                "question_id": question.id,
                "topic": topic,
                "priority_score": priority["priority_score"],
                "difficulty": difficulty,
                "reason": "graph_prerequisite_recovery" if topic in recovery_topics else "weak_topic_or_revision_decay",
            })
        scored.sort(key=lambda item: _difficulty_order_key(item, load["fatigue_aware_ordering"]))
        for item in scored:
            if len(selected) >= target_count:
                break
            selected.append(item)
            seen_question_ids.add(item["question_id"])
        if len(selected) >= target_count:
            break

    if len(selected) < target_count:
        fallback = db.query(Question).limit(target_count * 2).all()
        for question in fallback:
            if question.id in seen_question_ids:
                continue
            selected.append({
                "question_id": question.id,
                "topic": question.topic.name if question.topic else "Unknown",
                "priority_score": 0,
                "difficulty": personalized_difficulty(question, 50, reliability["recommendation_confidence"]),
                "reason": "coverage_fallback",
            })
            seen_question_ids.add(question.id)
            if len(selected) >= target_count:
                break

    return {
        "user_id": user_id,
        "question_count": len(selected),
        "questions": selected,
        "ordering_strategy": "fatigue_sensitive_productive_challenge" if load["fatigue_aware_ordering"] else "priority_then_challenge",
        "graph_aware": True,
        "conceptual_recovery_topics": recovery_topics[:8],
        "adaptive_reliability": reliability,
        "metric_version": ADAPTIVE_VERSION,
    }
