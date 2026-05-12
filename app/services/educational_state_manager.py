from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.adaptive_learning_engine import adaptive_reliability, build_adaptive_learning_plan
from app.services.educational_memory_engine import build_educational_memory
from app.services.inference_reliability import clamp
from app.services.knowledge_graph_engine import build_knowledge_graph, graph_observability, propagate_mastery
from app.services.pedagogical_reasoning_engine import pedagogical_reasoning_report
from app.services.student_longitudinal_profile import build_student_longitudinal_profile

EDUCATIONAL_STATE_VERSION = "educational-state.v1"


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def unified_reliability_state(
    profile: dict[str, Any],
    adaptive_plan: dict[str, Any],
    graph: dict[str, Any],
    memory: dict[str, Any],
) -> dict[str, Any]:
    longitudinal = profile.get("longitudinal_reliability", {})
    adaptive = adaptive_plan.get("study_plan", {}).get("adaptive_reliability", {})
    graph_metrics = graph_observability(graph, profile)
    conceptual = propagate_mastery(graph, profile).get("mastery", {})
    conceptual_confidence = _avg([item.get("dependency_confidence", 0) for item in conceptual.values()])
    memory_statements = memory.get("narrative_continuity", {}).get("statements", [])
    memory_continuity = _avg([item.get("narrative_confidence", 0) for item in memory_statements])
    graph_stability = 1 - clamp(len(graph_metrics.get("unstable_dependency_regions", [])) / max(1, graph.get("topic_count", 1)))

    components = {
        "telemetry_reliability": longitudinal.get("telemetry_continuity", 0),
        "longitudinal_reliability": longitudinal.get("overall_reliability", 0),
        "conceptual_reliability": conceptual_confidence,
        "adaptive_reliability": adaptive.get("recommendation_confidence", 0),
        "memory_continuity": memory_continuity,
        "graph_stability": graph_stability,
    }
    overall = (
        components["telemetry_reliability"] * 0.15
        + components["longitudinal_reliability"] * 0.25
        + components["conceptual_reliability"] * 0.15
        + components["adaptive_reliability"] * 0.20
        + components["memory_continuity"] * 0.15
        + components["graph_stability"] * 0.10
    )
    return {
        "components": {key: round(clamp(value), 4) for key, value in components.items()},
        "overall_reliability": round(clamp(overall), 4),
        "level": "HIGH" if overall >= 0.78 else "MEDIUM" if overall >= 0.55 else "LOW",
        "metric_version": EDUCATIONAL_STATE_VERSION,
    }


def contradiction_scan(profile: dict[str, Any], adaptive_plan: dict[str, Any], memory: dict[str, Any]) -> list[dict[str, Any]]:
    contradictions = []
    load = adaptive_plan.get("study_plan", {}).get("cognitive_load", {})
    difficulty_mix = adaptive_plan.get("study_plan", {}).get("workload", {}).get("difficulty_mix", {})
    if load.get("recommended_session_intensity") == "LIGHT" and difficulty_mix.get("HARD", 0) >= 25:
        contradictions.append({
            "type": "LOAD_VS_DIFFICULTY",
            "description": "Cognitive load suggests light intensity while difficulty mix still includes substantial hard work.",
            "severity": "HIGH",
        })
    weak_foundations = len(memory.get("misconception_memory", {}).get("misconceptions", []))
    if weak_foundations and adaptive_plan.get("study_plan", {}).get("adaptive_reliability", {}).get("mode") == "ASSERTIVE_BUT_REVERSIBLE":
        contradictions.append({
            "type": "ASSERTIVE_ADAPTATION_WITH_MEMORY_RISK",
            "description": "Adaptive plan is assertive while memory contains unresolved misconception evidence.",
            "severity": "MEDIUM",
        })
    if profile.get("longitudinal_reliability", {}).get("level") == "LOW" and adaptive_plan.get("conceptual_recovery_sequence"):
        contradictions.append({
            "type": "LOW_RELIABILITY_GRAPH_ACTION",
            "description": "Graph-guided recovery exists, but longitudinal reliability is low.",
            "severity": "LOW",
        })
    return contradictions


def build_unified_educational_state(db: Session, user_id: int) -> dict[str, Any]:
    profile = build_student_longitudinal_profile(db, user_id)
    graph = build_knowledge_graph(db)
    adaptive_plan = build_adaptive_learning_plan(db, user_id)
    memory = build_educational_memory(db, user_id)
    reasoning = pedagogical_reasoning_report(memory)
    reliability = unified_reliability_state(profile, adaptive_plan, graph, memory)
    contradictions = contradiction_scan(profile, adaptive_plan, memory)
    return {
        "user_id": user_id,
        "profile": profile,
        "adaptive_plan": adaptive_plan,
        "educational_memory": memory,
        "pedagogical_reasoning": reasoning,
        "graph_state": graph_observability(graph, profile),
        "reliability": reliability,
        "contradictions": contradictions,
        "metric_version": EDUCATIONAL_STATE_VERSION,
    }
