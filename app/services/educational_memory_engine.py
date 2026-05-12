from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import CognitiveSnapshot, LearningIntervention, User
from app.services.inference_reliability import clamp
from app.services.knowledge_graph_engine import (
    build_knowledge_graph,
    conceptual_recovery_sequence,
    graph_observability,
    weak_foundation_detection,
)
from app.services.student_longitudinal_profile import build_student_longitudinal_profile

EDUCATIONAL_MEMORY_VERSION = "educational-memory.v1"


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _volatility(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _topic_history(profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in profile.get("trajectory_points", []):
        for topic, score in point.get("topic_scores", {}).items():
            history[topic].append({
                "attempt_id": point.get("attempt_id"),
                "timestamp": point.get("timestamp"),
                "score": score,
                "accuracy": point.get("accuracy", 0),
                "telemetry_quality": point.get("telemetry_quality", {}),
            })
    return history


def misconception_tracking(profile: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    topic_history = _topic_history(profile)
    foundation_findings = weak_foundation_detection(graph, profile)
    foundation_by_topic = {item["topic"]: item for item in foundation_findings}
    misconceptions = []

    for topic, points in topic_history.items():
        scores = [point["score"] for point in points]
        repeated_low = len([score for score in scores if score < 60])
        peak = max(scores, default=0)
        latest = scores[-1] if scores else 0
        volatility = _volatility(scores)
        finding = foundation_by_topic.get(topic, {})
        evidence_count = len(points)
        confidence = clamp(evidence_count / 8 * 0.45 + repeated_low / max(1, evidence_count) * 0.35 + min(volatility, 40) / 40 * 0.20)

        flags = []
        if repeated_low >= 2:
            flags.append("recurring low mastery")
        if finding.get("likely_cause") == "prerequisite weakness":
            flags.append("prerequisite misunderstanding")
        if peak >= 70 and latest < 60:
            flags.append("false mastery cycle")
        if profile.get("confidence_evolution", {}).get("calibration_slope", 0) < 0 and latest < 65:
            flags.append("recurring overconfidence risk")
        if volatility > 18:
            flags.append("concept confusion volatility")

        if flags:
            misconceptions.append({
                "topic": topic,
                "flags": flags,
                "evidence_count": evidence_count,
                "supporting_attempts": [point["attempt_id"] for point in points if point.get("attempt_id")],
                "latest_score": round(latest, 4),
                "volatility": round(volatility, 4),
                "prerequisite_chain": finding.get("prerequisite_chain", []),
                "probability": round(confidence, 4),
                "safety_note": "Misconception evidence is probabilistic and educational, not a learner label.",
                "metric_version": EDUCATIONAL_MEMORY_VERSION,
            })

    return {
        "misconceptions": sorted(misconceptions, key=lambda item: item["probability"], reverse=True),
        "metric_version": EDUCATIONAL_MEMORY_VERSION,
    }


def recovery_history(profile: dict[str, Any], interventions: list[LearningIntervention]) -> dict[str, Any]:
    revision = profile.get("revision_effectiveness", {}).get("topics", {})
    failed = []
    durable = []
    for topic, data in revision.items():
        if data.get("status") == "UNSTABLE" or data.get("decay", 0) > 10:
            failed.append({
                "topic": topic,
                "reason": data.get("status", "UNSTABLE"),
                "retention_score": data.get("retention_score", 0),
                "decay": data.get("decay", 0),
                "metric_version": EDUCATIONAL_MEMORY_VERSION,
            })
        elif data.get("status") in {"IMPROVING", "STABLE"} and data.get("retention_score", 0) >= 70:
            durable.append({
                "topic": topic,
                "status": data.get("status"),
                "retention_score": data.get("retention_score", 0),
                "metric_version": EDUCATIONAL_MEMORY_VERSION,
            })

    successful_interventions = []
    for intervention in interventions:
        outcome = intervention.outcome_metadata or {}
        payload = intervention.recommendation_payload or {}
        recommendation = payload.get("recommendation", {})
        if intervention.status in {"FOLLOWED", "ACCEPTED", "PARTIALLY_FOLLOWED"} and outcome.get("outcome", outcome).get("post_intervention_accuracy_delta", 0) >= 0:
            successful_interventions.append({
                "recommendation_id": intervention.recommendation_id,
                "strategy_id": intervention.strategy_id,
                "topic": recommendation.get("topic"),
                "status": intervention.status,
                "outcome": outcome,
                "metric_version": EDUCATIONAL_MEMORY_VERSION,
            })

    return {
        "failed_recoveries": failed,
        "durable_recoveries": durable,
        "successful_interventions": successful_interventions,
        "metric_version": EDUCATIONAL_MEMORY_VERSION,
    }


def pacing_memory(profile: dict[str, Any]) -> dict[str, Any]:
    points = profile.get("trajectory_points", [])
    times = [point.get("average_time_per_question", 0) for point in points]
    volatility = _volatility(times)
    collapse_attempts = [
        point.get("attempt_id") for point in points
        if point.get("average_time_per_question", 0) > _safe_mean(times) + max(20, volatility)
    ]
    return {
        "average_time_per_question": round(_safe_mean(times), 4),
        "pacing_volatility": round(volatility, 4),
        "collapse_attempts": [attempt_id for attempt_id in collapse_attempts if attempt_id],
        "pattern": "PACING_COLLAPSE_RISK" if collapse_attempts or volatility > 45 else "NO_STRONG_PATTERN",
        "metric_version": EDUCATIONAL_MEMORY_VERSION,
    }


def learning_narrative_continuity(memory: dict[str, Any]) -> dict[str, Any]:
    reliability = memory.get("profile", {}).get("longitudinal_reliability", {})
    evidence_quality = reliability.get("level", "LOW")
    statements = []
    for item in memory.get("misconception_memory", {}).get("misconceptions", [])[:5]:
        qualifier = "may indicate" if evidence_quality == "LOW" else "appears to indicate"
        statements.append({
            "claim": f"Repeated instability {qualifier} a learning issue around {item['topic']}.",
            "evidence_quality": evidence_quality,
            "supporting_attempts": item["supporting_attempts"],
            "narrative_confidence": item["probability"],
            "contradiction_flags": [],
            "metric_version": EDUCATIONAL_MEMORY_VERSION,
        })
    for item in memory.get("recovery_memory", {}).get("durable_recoveries", [])[:3]:
        statements.append({
            "claim": f"Recovery evidence is improving around {item['topic']}, but durability should continue to be monitored.",
            "evidence_quality": evidence_quality,
            "supporting_attempts": [],
            "narrative_confidence": clamp(item.get("retention_score", 0) / 100),
            "contradiction_flags": [],
            "metric_version": EDUCATIONAL_MEMORY_VERSION,
        })
    return {
        "timeline_continuity": "LONGITUDINAL" if memory.get("profile", {}).get("attempt_count", 0) >= 3 else "EARLY_HISTORY",
        "statements": statements,
        "metric_version": EDUCATIONAL_MEMORY_VERSION,
    }


def teacher_learning_summary(memory: dict[str, Any]) -> dict[str, Any]:
    misconceptions = memory.get("misconception_memory", {}).get("misconceptions", [])
    recovery = memory.get("recovery_memory", {})
    graph = memory.get("conceptual_memory", {})
    pacing = memory.get("pacing_memory", {})
    return {
        "student_id": memory.get("user_id"),
        "summary_type": "EDUCATIONAL_SUPPORT",
        "conceptual_risk_regions": [
            {
                "topic": item["topic"],
                "evidence_count": item["evidence_count"],
                "probability": item["probability"],
                "supporting_attempts": item["supporting_attempts"],
            }
            for item in misconceptions[:8]
        ],
        "recovery_attempts": recovery.get("failed_recoveries", []) + recovery.get("durable_recoveries", []),
        "intervention_history": recovery.get("successful_interventions", []),
        "pacing_stability": pacing,
        "unresolved_bottlenecks": graph.get("unresolved_bottlenecks", []),
        "safety_note": "This is educator support, not a psychological or intelligence diagnosis.",
        "metric_version": EDUCATIONAL_MEMORY_VERSION,
    }


def build_educational_memory(db: Session, user_id: int) -> dict[str, Any]:
    profile = build_student_longitudinal_profile(db, user_id)
    graph = build_knowledge_graph(db)
    interventions = db.query(LearningIntervention).filter(LearningIntervention.user_id == user_id).all()
    snapshots = db.query(CognitiveSnapshot).filter(CognitiveSnapshot.user_id == user_id).order_by(CognitiveSnapshot.created_at.asc()).all()
    graph_metrics = graph_observability(graph, profile)
    memory = {
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "misconception_memory": misconception_tracking(profile, graph),
        "recovery_memory": recovery_history(profile, interventions),
        "pacing_memory": pacing_memory(profile),
        "conceptual_memory": {
            "recovery_sequence": conceptual_recovery_sequence(graph, profile),
            "unstable_regions": graph_metrics.get("unstable_dependency_regions", []),
            "unresolved_bottlenecks": graph_metrics.get("unresolved_prerequisite_chains", []),
            "metric_version": EDUCATIONAL_MEMORY_VERSION,
        },
        "snapshot_markers": [
            {
                "attempt_id": snapshot.attempt_id,
                "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
                "metric_version": snapshot.metric_version,
            }
            for snapshot in snapshots
        ],
        "memory_aging": {
            "aging_policy": "Recent evidence is weighted first; older memory should decay unless reconfirmed.",
            "decay_ready": True,
            "metric_version": EDUCATIONAL_MEMORY_VERSION,
        },
        "metric_version": EDUCATIONAL_MEMORY_VERSION,
    }
    memory["narrative_continuity"] = learning_narrative_continuity(memory)
    memory["teacher_summary"] = teacher_learning_summary(memory)
    return memory


def persist_educational_memory(db: Session, user_id: int) -> dict[str, Any]:
    memory = build_educational_memory(db, user_id)
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        profile = dict(user.behavioral_profile or {})
        profile["educational_memory"] = {
            "generated_at": memory["generated_at"],
            "misconception_memory": memory["misconception_memory"],
            "recovery_memory": memory["recovery_memory"],
            "pacing_memory": memory["pacing_memory"],
            "conceptual_memory": memory["conceptual_memory"],
            "narrative_continuity": memory["narrative_continuity"],
            "teacher_summary": memory["teacher_summary"],
            "memory_aging": memory["memory_aging"],
            "metric_version": EDUCATIONAL_MEMORY_VERSION,
        }
        user.behavioral_profile = profile
        db.commit()
    return memory


def educational_memory_observability(db: Session) -> dict[str, Any]:
    users = db.query(User).filter(User.behavioral_profile != None).limit(500).all()
    memories = [
        user.behavioral_profile.get("educational_memory")
        for user in users
        if isinstance(user.behavioral_profile, dict) and user.behavioral_profile.get("educational_memory")
    ]
    misconception_count = sum(len(memory.get("misconception_memory", {}).get("misconceptions", [])) for memory in memories)
    failed_recoveries = sum(len(memory.get("recovery_memory", {}).get("failed_recoveries", [])) for memory in memories)
    durable_recoveries = sum(len(memory.get("recovery_memory", {}).get("durable_recoveries", [])) for memory in memories)
    narratives = [
        statement
        for memory in memories
        for statement in memory.get("narrative_continuity", {}).get("statements", [])
    ]
    return {
        "memory_profile_count": len(memories),
        "misconception_persistence_rate": round(misconception_count / max(1, len(memories)), 4),
        "failed_recovery_count": failed_recoveries,
        "recovery_durability_rate": round(durable_recoveries / max(1, durable_recoveries + failed_recoveries) * 100, 4) if memories else 0,
        "narrative_stability": round(_safe_mean([item.get("narrative_confidence", 0) for item in narratives]), 4),
        "metric_version": EDUCATIONAL_MEMORY_VERSION,
    }
