from __future__ import annotations

from typing import Any, Dict, List
from statistics import mean, pstdev
from app.services.student_longitudinal_profile import build_student_longitudinal_profile

STUDENT_TWIN_VERSION = "student-twin.v1"

def construct_student_twin(db: Any, user_id: int) -> Dict[str, Any]:
    profile = build_student_longitudinal_profile(db, user_id)
    
    # Probabilistic state twin construction
    stability = profile.get("behavioral_stability", {})
    velocity = profile.get("learning_velocity", {})
    reliability = profile.get("longitudinal_reliability", {})
    
    # Calculate state transition probabilities based on history
    transitions = profile.get("state_transitions", [])
    
    twin = {
        "user_id": user_id,
        "twin_state": {
            "mastery_baseline": profile.get("learning_velocity", {}).get("accuracy_slope", 0),
            "volatility_index": stability.get("accuracy_volatility", 0),
            "pacing_identity": "HESITANT" if stability.get("pacing_volatility", 0) > 30 else "STABLE",
            "conceptual_fragility": _estimate_fragility(profile),
            "intervention_responsiveness": _estimate_responsiveness(profile)
        },
        "uncertainty": {
            "prediction_confidence": reliability.get("overall_reliability", 0),
            "volatility_range": [
                stability.get("accuracy_volatility", 0) * 0.8,
                stability.get("accuracy_volatility", 0) * 1.2
            ]
        },
        "transition_probabilities": {
            "improvement": clamp(0.5 + velocity.get("accuracy_slope", 0) / 10),
            "overload": clamp(stability.get("accuracy_volatility", 0) / 50),
            "stabilization": 1.0 if velocity.get("stabilization_detected") else 0.3
        },
        "metric_version": STUDENT_TWIN_VERSION
    }
    return twin

def _estimate_fragility(profile: Dict[str, Any]) -> float:
    topics = profile.get("revision_effectiveness", {}).get("topics", {})
    unstable_count = sum(1 for t in topics.values() if t["status"] == "UNSTABLE")
    return clamp(unstable_count / max(1, len(topics)))

def _estimate_responsiveness(profile: Dict[str, Any]) -> float:
    velocity = profile.get("learning_velocity", {}).get("recovery_velocity", 0)
    return clamp(0.5 + velocity / 20)

def clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, val))
