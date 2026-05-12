from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import User
from app.services.adaptive_experimentation import assign_experiment
from app.services.educational_policy_engine import arbitrate_educational_action
from app.services.educational_policy_engine import live_intervention_governance
from app.services.educational_state_manager import build_unified_educational_state
from app.services.session_intelligence_engine import build_session_intelligence

EDUCATIONAL_ORCHESTRATOR_VERSION = "educational-orchestrator.v1"


ENGINE_WEIGHTS = {
    "telemetry_intelligence": 0.12,
    "longitudinal_intelligence": 0.20,
    "adaptive_intelligence": 0.18,
    "conceptual_intelligence": 0.18,
    "pedagogical_memory": 0.18,
    "experimentation_layer": 0.06,
    "content_intelligence": 0.08,
}


def cross_engine_reasoning(state: dict[str, Any]) -> dict[str, Any]:
    reliability = state.get("reliability", {}).get("components", {})
    reasoning_claims = state.get("pedagogical_reasoning", {}).get("claims", [])
    contributions = {
        "telemetry_intelligence": {
            "weight": ENGINE_WEIGHTS["telemetry_intelligence"],
            "signal": reliability.get("telemetry_reliability", 0),
        },
        "longitudinal_intelligence": {
            "weight": ENGINE_WEIGHTS["longitudinal_intelligence"],
            "signal": reliability.get("longitudinal_reliability", 0),
        },
        "adaptive_intelligence": {
            "weight": ENGINE_WEIGHTS["adaptive_intelligence"],
            "signal": reliability.get("adaptive_reliability", 0),
        },
        "conceptual_intelligence": {
            "weight": ENGINE_WEIGHTS["conceptual_intelligence"],
            "signal": reliability.get("conceptual_reliability", 0),
        },
        "pedagogical_memory": {
            "weight": ENGINE_WEIGHTS["pedagogical_memory"],
            "signal": reliability.get("memory_continuity", 0),
        },
        "content_intelligence": {
            "weight": ENGINE_WEIGHTS["content_intelligence"],
            "signal": 0.35,
            "note": "Content evidence is available as infrastructure but remains weak until linked to outcomes.",
        },
        "experimentation_layer": {
            "weight": ENGINE_WEIGHTS["experimentation_layer"],
            "signal": 0.25,
            "note": "Experimentation contributes only when policy permits low-risk assignment.",
        },
    }
    unresolved = [
        contradiction["type"]
        for contradiction in state.get("contradictions", [])
    ]
    return {
        "contributing_engines": contributions,
        "evidence_weights": ENGINE_WEIGHTS,
        "reasoning_claim_count": len(reasoning_claims),
        "contradictions": state.get("contradictions", []),
        "unresolved_uncertainty": unresolved,
        "metric_version": EDUCATIONAL_ORCHESTRATOR_VERSION,
    }


def explain_orchestration_decision(state: dict[str, Any], arbitration: dict[str, Any], reasoning: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    blocked = arbitration.get("safety_overrides", [])
    return {
        "why_generated": f"{arbitration['action_type']} selected from adaptive plan, conceptual state, and educational memory.",
        "contributing_systems": list(reasoning["contributing_engines"].keys()),
        "reliability_weighting": reasoning["evidence_weights"],
        "uncertainty": {
            "state_level": state.get("reliability", {}).get("level"),
            "contradictions": reasoning["unresolved_uncertainty"],
            "decision_confidence": arbitration.get("decision_confidence", 0),
        },
        "blocked_alternatives": blocked,
        "safety_overrides": arbitration.get("governance", {}),
        "experiment_assignment": experiment,
        "metric_version": EDUCATIONAL_ORCHESTRATOR_VERSION,
    }


def orchestrate_education(db: Session, user_id: int) -> dict[str, Any]:
    state = build_unified_educational_state(db, user_id)
    arbitration = arbitrate_educational_action(state)
    reasoning = cross_engine_reasoning(state)
    experiment = assign_experiment(
        user_id,
        "revision_intensity_v1",
        {
            "recommendation_confidence": arbitration["decision_confidence"],
            "mode": "SOFT" if arbitration["policy"]["adaptation_aggressiveness"] == "LOW" else "GUIDED",
        },
    ) if arbitration["policy"]["allow_experimentation"] else {
        "assigned": False,
        "reason": "Policy blocked experimentation for this orchestration decision.",
        "metric_version": EDUCATIONAL_ORCHESTRATOR_VERSION,
    }
    # Phase 19G: Failure Containment
    reliability = state.get("reliability", {})
    is_degraded = (
        reliability.get("level") == "LOW" or 
        state.get("reliability", {}).get("components", {}).get("telemetry_reliability", 1) < 0.3 or
        arbitration.get("decision_confidence", 1) < 0.4
    )
    
    if is_degraded:
        # Graceful degradation
        arbitration["action_type"] = "OBSERVE_ONLY"
        arbitration["policy"]["adaptation_aggressiveness"] = "MINIMAL"
        arbitration["governance"]["failure_containment_active"] = True
        arbitration["governance"]["reason"] = "Low reliability detected; entering safe degradation mode."

    explanation = explain_orchestration_decision(state, arbitration, reasoning, experiment)
    
    # Phase 19E: Decision Graph Linkage
    explanation["decision_graph"] = {
        "upstream_evidence": ["telemetry", "longitudinal_memory", "conceptual_state"],
        "policy_gates": arbitration.get("policy", {}),
        "reliability_weights": reasoning["evidence_weights"],
        "failure_containment": is_degraded
    }
    return {
        "user_id": user_id,
        "decision": arbitration,
        "unified_state": {
            "reliability": state["reliability"],
            "contradictions": state["contradictions"],
            "graph_state": state["graph_state"],
        },
        "cross_engine_reasoning": reasoning,
        "explanation": explanation,
        "memory_aware_context": {
            "failed_recoveries": state["educational_memory"].get("recovery_memory", {}).get("failed_recoveries", []),
            "misconceptions": state["educational_memory"].get("misconception_memory", {}).get("misconceptions", []),
            "pacing_memory": state["educational_memory"].get("pacing_memory", {}),
        },
        "scientific_safety": {
            "transparent": True,
            "evidence_linked": True,
            "reversible": True,
            "uncertainty_aware": True,
            "educator_aligned": arbitration["policy"]["requires_human_review"],
        },
        "metric_version": EDUCATIONAL_ORCHESTRATOR_VERSION,
    }


def orchestration_observability(db: Session) -> dict[str, Any]:
    users = db.query(User).filter(User.behavioral_profile != None).limit(100).all()
    decisions = []
    for user in users:
        try:
            decisions.append(orchestrate_education(db, user.id))
        except Exception:
            continue
    action_counts = Counter(decision.get("decision", {}).get("action_type") for decision in decisions)
    conflicts = sum(len(decision.get("unified_state", {}).get("contradictions", [])) for decision in decisions)
    blocked = sum(len(decision.get("decision", {}).get("safety_overrides", [])) for decision in decisions)
    human_review = len([decision for decision in decisions if decision.get("decision", {}).get("policy", {}).get("requires_human_review")])
    low_confidence = len([decision for decision in decisions if decision.get("decision", {}).get("decision_confidence", 0) < 0.55])
    return {
        "orchestrated_user_count": len(decisions),
        "action_counts": dict(action_counts),
        "arbitration_conflict_count": conflicts,
        "blocked_unsafe_adaptation_count": blocked,
        "human_review_escalation_rate": round(human_review / max(1, len(decisions)) * 100, 4),
        "low_confidence_orchestration_rate": round(low_confidence / max(1, len(decisions)) * 100, 4),
        "metric_version": EDUCATIONAL_ORCHESTRATOR_VERSION,
    }


def orchestrate_live_session(db: Session, attempt_id: int) -> dict[str, Any]:
    session = build_session_intelligence(db, attempt_id)
    user_id = session.get("user_id")
    base = orchestrate_education(db, user_id) if user_id else {}
    memory_context = base.get("memory_aware_context", {})
    governance = live_intervention_governance(session, memory_context)
    signals = session.get("live_cognitive_state", {}).get("signals", [])
    action_type = "OBSERVE_ONLY"
    action = {"message": "Continue monitoring without intervention."}
    if governance["allow_live_intervention"]:
        if "OVERLOAD_RISK" in signals or "PACING_COLLAPSE" in signals:
            action_type = "LIVE_PACING_BUFFER"
            action = {"adjustment": "soft_pace_buffer", "seconds": 30, "disruption": "LOW"}
        elif "HESITATION_SPIKE" in signals:
            action_type = "LIVE_RECOVERY_PROMPT"
            action = {"prompt_type": "gentle_strategy_hint", "disruption": "LOW"}
        elif "IMPULSIVE_BURST" in signals:
            action_type = "LIVE_REFLECTION_NUDGE"
            action = {"prompt_type": "brief_review_nudge", "disruption": "LOW"}
    return {
        "attempt_id": attempt_id,
        "user_id": user_id,
        "action_type": action_type,
        "action": action,
        "session_intelligence": session,
        "base_orchestration": {
            "decision": base.get("decision"),
            "reliability": base.get("unified_state", {}).get("reliability"),
        },
        "governance": governance,
        "explanation": {
            "why_generated": "Live action selected from session telemetry, live cognitive signals, memory context, and policy gates.",
            "signals": signals,
            "blocked_alternatives": governance["blocked_actions"],
            "reversibility": True,
            "uncertainty_boundary": "Transient live struggle is not treated as persistent weakness.",
        },
        "metric_version": EDUCATIONAL_ORCHESTRATOR_VERSION,
    }
