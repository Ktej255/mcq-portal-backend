from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import Question, Topic
from app.services.inference_reliability import clamp
from app.services.knowledge_graph_engine import build_knowledge_graph, conceptual_recovery_sequence, graph_observability, propagate_mastery
from app.services.learning_state_machine import probabilistic_learning_states, state_adaptation_guidance
from app.services.student_longitudinal_profile import build_student_longitudinal_profile

ADAPTIVE_VERSION = "adaptive-learning.v1"

DIFFICULTY_VALUES = {
    "EASY": 0.25,
    "MEDIUM": 0.55,
    "HARD": 0.85,
}


def _topic_mastery(profile: dict[str, Any], topic_name: str) -> float:
    points = profile.get("trajectory_points", [])
    scores = [
        point.get("topic_scores", {}).get(topic_name)
        for point in points
        if point.get("topic_scores", {}).get(topic_name) is not None
    ]
    return scores[-1] if scores else 50.0


def adaptive_reliability(profile: dict[str, Any], evidence_count: int = 0) -> dict[str, Any]:
    trajectory = profile.get("longitudinal_reliability", {})
    base = trajectory.get("overall_reliability", 0)
    evidence = clamp(evidence_count / 10)
    confidence = clamp(base * 0.7 + evidence * 0.3)
    return {
        "recommendation_confidence": round(confidence, 4),
        "evidence_quality": trajectory.get("level", "LOW"),
        "trajectory_reliability": trajectory,
        "mode": "SOFT" if confidence < 0.55 else "GUIDED" if confidence < 0.8 else "ASSERTIVE_BUT_REVERSIBLE",
        "metric_version": ADAPTIVE_VERSION,
    }


def personalized_difficulty(question: Question, topic_mastery: float, reliability: float) -> dict[str, Any]:
    base = DIFFICULTY_VALUES.get((question.difficulty or "MEDIUM").upper(), 0.55)
    mastery_adjustment = (topic_mastery - 50) / 100
    relative = clamp(base - mastery_adjustment * 0.45)
    challenge = "UNDER_CHALLENGE" if relative < 0.25 else "FRUSTRATION_RISK" if relative > 0.78 else "PRODUCTIVE_CHALLENGE"
    if reliability < 0.4 and challenge != "PRODUCTIVE_CHALLENGE":
        challenge = "UNCERTAIN_" + challenge
    return {
        "question_id": question.id,
        "base_difficulty": (question.difficulty or "MEDIUM").upper(),
        "relative_difficulty": round(relative, 4),
        "challenge_band": challenge,
        "mastery_adjusted": True,
        "metric_version": ADAPTIVE_VERSION,
    }


def topic_priority(profile: dict[str, Any]) -> list[dict[str, Any]]:
    revision = profile.get("revision_effectiveness", {}).get("topics", {})
    weak_topics = profile.get("adaptive_recommendation_context", {}).get("weak_topics", [])
    weak_topic_names = {item["topic"] for item in weak_topics}
    priorities = []
    for topic, data in revision.items():
        retention_gap = max(0, 75 - data.get("retention_score", 0))
        instability = 25 if data.get("status") == "UNSTABLE" else 10 if data.get("status") == "INSUFFICIENT_EVIDENCE" else 0
        weakness = 20 if topic in weak_topic_names else 0
        priorities.append({
            "topic": topic,
            "priority_score": round(clamp((retention_gap + instability + weakness) / 100) * 100, 4),
            "drivers": {
                "retention_gap": retention_gap,
                "instability": instability,
                "weakness": weakness,
            },
        })
    return sorted(priorities, key=lambda item: item["priority_score"], reverse=True)


def cognitive_load_balance(profile: dict[str, Any]) -> dict[str, Any]:
    stability = profile.get("behavioral_stability", {})
    pacing_volatility = stability.get("pacing_volatility", 0)
    consistency = stability.get("consistency_score", 0)
    fatigue_probability = probabilistic_learning_states(profile)["state_probabilities"].get("fatigue_sensitive_learner", 0)
    load = clamp(fatigue_probability * 0.45 + min(pacing_volatility / 90, 1) * 0.35 + (1 - consistency) * 0.20)
    return {
        "load_risk": round(load, 4),
        "recommended_session_intensity": "LIGHT" if load > 0.65 else "MODERATE" if load > 0.35 else "STANDARD",
        "fatigue_aware_ordering": load > 0.35,
        "pace_buffer_seconds": 30 if load > 0.65 else 15 if load > 0.35 else 0,
        "metric_version": ADAPTIVE_VERSION,
    }


def revision_schedule(profile: dict[str, Any]) -> list[dict[str, Any]]:
    reliability = adaptive_reliability(profile)
    load = cognitive_load_balance(profile)
    schedule = []
    for item in topic_priority(profile):
        interval_days = 1 if item["priority_score"] >= 60 else 3 if item["priority_score"] >= 35 else 7
        intensity = "LOW" if reliability["mode"] == "SOFT" else "HIGH" if item["priority_score"] >= 60 and load["recommended_session_intensity"] != "LIGHT" else "MEDIUM"
        schedule.append({
            "topic": item["topic"],
            "review_after_days": interval_days,
            "intensity": intensity,
            "priority_score": item["priority_score"],
            "next_review_at": (datetime.now(timezone.utc) + timedelta(days=interval_days)).isoformat(),
            "metric_version": ADAPTIVE_VERSION,
        })
    return schedule


def personalized_study_plan(profile: dict[str, Any]) -> dict[str, Any]:
    state = probabilistic_learning_states(profile)
    guidance = state_adaptation_guidance(state)
    load = cognitive_load_balance(profile)
    reliability = adaptive_reliability(profile, evidence_count=profile.get("attempt_count", 0))
    revisions = revision_schedule(profile)
    return {
        "learning_state": state,
        "adaptation_guidance": guidance,
        "cognitive_load": load,
        "revision_schedule": revisions[:5],
        "workload": {
            "question_count": 8 if load["recommended_session_intensity"] == "LIGHT" else 12 if load["recommended_session_intensity"] == "MODERATE" else 20,
            "difficulty_mix": difficulty_mix(profile),
            "pace_buffer_seconds": load["pace_buffer_seconds"],
        },
        "adaptive_reliability": reliability,
        "metric_version": ADAPTIVE_VERSION,
    }


def difficulty_mix(profile: dict[str, Any]) -> dict[str, int]:
    state = probabilistic_learning_states(profile)["primary_state"]
    if state in {"unstable_learner", "high_volatility_learner", "fatigue_sensitive_learner"}:
        return {"EASY": 40, "MEDIUM": 50, "HARD": 10}
    if state in {"calibrated_learner", "stabilized_learner"}:
        return {"EASY": 15, "MEDIUM": 55, "HARD": 30}
    return {"EASY": 25, "MEDIUM": 60, "HARD": 15}


def build_adaptive_learning_plan(db: Session, user_id: int) -> dict[str, Any]:
    profile = build_student_longitudinal_profile(db, user_id)
    graph = build_knowledge_graph(db)
    conceptual_sequence = conceptual_recovery_sequence(graph, profile)
    conceptual_mastery = propagate_mastery(graph, profile)
    return {
        "user_id": user_id,
        "profile_version": profile.get("metric_version"),
        "topic_priority": topic_priority(profile),
        "study_plan": personalized_study_plan(profile),
        "conceptual_recovery_sequence": conceptual_sequence[:8],
        "conceptual_mastery": conceptual_mastery,
        "graph_observability": graph_observability(graph, profile),
        "metric_version": ADAPTIVE_VERSION,
        "safety": {
            "adaptation_is_reversible": True,
            "avoid_aggressive_adaptation": profile.get("longitudinal_reliability", {}).get("level") == "LOW",
            "scientific_boundary": "Adaptive guidance is educational support; conceptual inference remains probabilistic and graph-calibrated.",
        },
    }


def candidate_questions_for_topic(db: Session, topic_name: str) -> list[Question]:
    return (
        db.query(Question)
        .join(Topic, Question.topic_id == Topic.id)
        .filter(Topic.name == topic_name)
        .all()
    )
