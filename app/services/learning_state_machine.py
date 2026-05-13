from __future__ import annotations

from typing import Any

from app.core.pedagogy.inference_reliability import clamp

STATE_MODEL_VERSION = "learning-state.v1"


def probabilistic_learning_states(profile: dict[str, Any]) -> dict[str, Any]:
    reliability = profile.get("longitudinal_reliability", {}).get("overall_reliability", 0)
    stability = profile.get("behavioral_stability", {}).get("consistency_score", 0)
    volatility = profile.get("behavioral_stability", {}).get("accuracy_volatility", 0)
    pacing_volatility = profile.get("behavioral_stability", {}).get("pacing_volatility", 0)
    velocity = profile.get("learning_velocity", {}).get("accuracy_slope", 0)
    calibration_slope = profile.get("confidence_evolution", {}).get("calibration_slope", 0)
    weak_topics = len(profile.get("adaptive_recommendation_context", {}).get("weak_topics", []))

    probabilities = {
        "unstable_learner": clamp((1 - stability) * 0.55 + min(volatility / 50, 1) * 0.30 + (1 - reliability) * 0.15),
        "recovering_learner": clamp(max(velocity, 0) / 10 * 0.55 + min(weak_topics / 5, 1) * 0.20 + stability * 0.25),
        "calibrated_learner": clamp(stability * 0.35 + max(calibration_slope, 0) / 20 * 0.35 + reliability * 0.30),
        "fatigue_sensitive_learner": clamp(min(pacing_volatility / 60, 1) * 0.65 + (1 - stability) * 0.20 + (1 - reliability) * 0.15),
        "high_volatility_learner": clamp(min(volatility / 60, 1) * 0.70 + min(pacing_volatility / 80, 1) * 0.20 + (1 - reliability) * 0.10),
        "stabilized_learner": clamp(stability * 0.60 + reliability * 0.30 + (0.10 if velocity >= 0 else 0)),
    }
    total = sum(probabilities.values()) or 1
    normalized = {state: round(value / total, 4) for state, value in probabilities.items()}
    primary_state = max(normalized, key=normalized.get)

    return {
        "primary_state": primary_state,
        "state_probabilities": normalized,
        "model_version": STATE_MODEL_VERSION,
        "safety_note": "Learning states are probabilistic adaptation hints, not psychological labels.",
    }


def state_adaptation_guidance(state_profile: dict[str, Any]) -> dict[str, Any]:
    primary = state_profile.get("primary_state")
    guidance = {
        "unstable_learner": {"challenge_bias": "LOWER", "revision_bias": "HIGH", "pace_bias": "SLOW"},
        "recovering_learner": {"challenge_bias": "MODERATE", "revision_bias": "MEDIUM", "pace_bias": "STEADY"},
        "calibrated_learner": {"challenge_bias": "RAISE", "revision_bias": "LOW", "pace_bias": "NORMAL"},
        "fatigue_sensitive_learner": {"challenge_bias": "MIXED", "revision_bias": "MEDIUM", "pace_bias": "BUFFERED"},
        "high_volatility_learner": {"challenge_bias": "LOWER", "revision_bias": "HIGH", "pace_bias": "CONSISTENCY_FIRST"},
        "stabilized_learner": {"challenge_bias": "RAISE", "revision_bias": "SPACED", "pace_bias": "NORMAL"},
    }
    return {
        "primary_state": primary,
        "adaptation_bias": guidance.get(primary, guidance["unstable_learner"]),
        "model_version": STATE_MODEL_VERSION,
    }
