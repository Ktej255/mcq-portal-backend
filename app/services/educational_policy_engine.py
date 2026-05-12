from __future__ import annotations

from typing import Any

ORCHESTRATION_POLICY_VERSION = "educational-policy.v1"
LIVE_POLICY_VERSION = "live-educational-policy.v1"


def policy_thresholds(state: dict[str, Any]) -> dict[str, Any]:
    reliability = state.get("reliability", {})
    level = reliability.get("level", "LOW")
    return {
        "adaptation_aggressiveness": "LOW" if level == "LOW" else "MODERATE" if level == "MEDIUM" else "CAUTIOUS_HIGH",
        "minimum_recommendation_confidence": 0.55 if level == "LOW" else 0.45 if level == "MEDIUM" else 0.35,
        "requires_human_review": level == "LOW" or bool(state.get("contradictions")),
        "allow_experimentation": level != "LOW" and not any(item.get("severity") == "HIGH" for item in state.get("contradictions", [])),
        "max_session_intensity": "LIGHT" if level == "LOW" else "MODERATE" if any(item.get("severity") == "HIGH" for item in state.get("contradictions", [])) else "STANDARD",
        "reliability_governance": {
            "evidence_retention_days": 90 if level == "HIGH" else 30,
            "replay_integrity_required": True,
            "min_confidence_floor": 0.4,
            "audit_visibility": "FULL" if level == "LOW" else "STANDARD"
        },
        "metric_version": ORCHESTRATION_POLICY_VERSION,
    }


def safety_governance(state: dict[str, Any]) -> dict[str, Any]:
    contradictions = state.get("contradictions", [])
    reliability = state.get("reliability", {})
    memory = state.get("educational_memory", {})
    persistent_misconceptions = len(memory.get("misconception_memory", {}).get("misconceptions", []))
    blocked = []
    if reliability.get("level") == "LOW":
        blocked.append({
            "action": "ASSERTIVE_ADAPTATION",
            "reason": "Unified reliability is low.",
        })
    if persistent_misconceptions:
        blocked.append({
            "action": "SKIP_FOUNDATION_REPAIR",
            "reason": "Educational memory contains unresolved misconception evidence.",
        })
    for contradiction in contradictions:
        if contradiction.get("severity") == "HIGH":
            blocked.append({
                "action": "HIGH_INTENSITY_WORKLOAD",
                "reason": contradiction["description"],
            })
    return {
        "blocked_actions": blocked,
        "human_review_required": reliability.get("level") == "LOW" or bool(contradictions),
        "runaway_adaptation_guard": True,
        "reversibility_required": True,
        "metric_version": ORCHESTRATION_POLICY_VERSION,
    }


def arbitrate_educational_action(state: dict[str, Any]) -> dict[str, Any]:
    thresholds = policy_thresholds(state)
    governance = safety_governance(state)
    adaptive = state.get("adaptive_plan", {})
    study_plan = adaptive.get("study_plan", {})
    conceptual_sequence = adaptive.get("conceptual_recovery_sequence", [])
    memory = state.get("educational_memory", {})
    misconceptions = memory.get("misconception_memory", {}).get("misconceptions", [])
    load = study_plan.get("cognitive_load", {})
    reliability = state.get("reliability", {})

    if conceptual_sequence and misconceptions:
        action_type = "FOUNDATION_FIRST_REMEDIATION"
        action = conceptual_sequence[0]
    elif load.get("recommended_session_intensity") == "LIGHT":
        action_type = "LOAD_REDUCTION"
        action = {"topic": "Session pacing", "priority": "STABILITY_FIRST"}
    else:
        action_type = "ADAPTIVE_PRACTICE"
        schedule = study_plan.get("revision_schedule", [])
        action = schedule[0] if schedule else {"topic": "General review", "priority": "LOW"}

    confidence = min(
        reliability.get("overall_reliability", 0),
        study_plan.get("adaptive_reliability", {}).get("recommendation_confidence", 0),
    )
    if confidence < thresholds["minimum_recommendation_confidence"]:
        action_type = "SOFT_GUIDANCE"

    return {
        "action_type": action_type,
        "action": action,
        "decision_confidence": round(confidence, 4),
        "policy": thresholds,
        "governance": governance,
        "safety_overrides": governance["blocked_actions"],
        "metric_version": ORCHESTRATION_POLICY_VERSION,
    }


def live_intervention_governance(session_state: dict[str, Any], memory_context: dict[str, Any] | None = None) -> dict[str, Any]:
    cognitive = session_state.get("live_cognitive_state", {})
    probabilities = cognitive.get("probabilities", {})
    telemetry = session_state.get("telemetry", {})
    memory_context = memory_context or {}
    overload = probabilities.get("overload_risk", 0)
    fatigue = probabilities.get("emerging_fatigue", 0)
    instability = probabilities.get("live_instability", 0)
    degraded = telemetry.get("heartbeat", {}).get("telemetry_degraded", False)
    historical_pacing = memory_context.get("pacing_memory", {}).get("pattern") == "PACING_COLLAPSE_RISK"
    max_signal = max(overload, fatigue, instability)
    blocked = []
    if degraded:
        blocked.append({"action": "CONTENT_ADAPTATION", "reason": "Telemetry is degraded; avoid strong live inference."})
    if max_signal < 0.45:
        blocked.append({"action": "LIVE_INTERRUPTION", "reason": "Live signal confidence is too low."})
    return {
        "allow_live_intervention": max_signal >= 0.45 and not degraded,
        "allowed_action_intensity": "SUBTLE" if max_signal < 0.75 else "LOW",
        "throttle_seconds": 180 if historical_pacing else 240,
        "blocked_actions": blocked,
        "requires_educator_awareness": max_signal >= 0.7 or degraded,
        "anti_surveillance_boundary": True,
        "metric_version": LIVE_POLICY_VERSION,
    }
