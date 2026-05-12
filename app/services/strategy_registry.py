from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STRATEGY_VERSION = "strategy-registry.v1"


@dataclass(frozen=True)
class AdaptiveStrategy:
    strategy_id: str
    name: str
    intended_effect: str
    evidence_quality: str
    adaptation_aggressiveness: str
    reversible: bool
    safety_notes: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "intended_effect": self.intended_effect,
            "evidence_quality": self.evidence_quality,
            "adaptation_aggressiveness": self.adaptation_aggressiveness,
            "reversible": self.reversible,
            "safety_notes": self.safety_notes,
            "metric_version": STRATEGY_VERSION,
        }


STRATEGIES = {
    "low_intensity_recovery": AdaptiveStrategy(
        "low_intensity_recovery",
        "Low-intensity recovery",
        "Support recovery on weak or unstable topics without increasing overload.",
        "EMERGING",
        "LOW",
        True,
        "Use when reliability is low or cognitive load is elevated.",
    ),
    "fatigue_sensitive_pacing": AdaptiveStrategy(
        "fatigue_sensitive_pacing",
        "Fatigue-sensitive pacing",
        "Reduce pacing strain and preserve continuity under fatigue-sensitive patterns.",
        "EMERGING",
        "LOW",
        True,
        "Avoid using as proof of fatigue; it is a cautious pacing adjustment.",
    ),
    "confidence_recalibration": AdaptiveStrategy(
        "confidence_recalibration",
        "Confidence recalibration",
        "Improve confidence-answer alignment through reflective practice.",
        "MODERATE",
        "MEDIUM",
        True,
        "Do not frame as personality correction.",
    ),
    "revision_reinforcement": AdaptiveStrategy(
        "revision_reinforcement",
        "Revision reinforcement",
        "Improve retention for topics showing decay or unstable recovery.",
        "MODERATE",
        "MEDIUM",
        True,
        "Spacing should remain adjustable based on learner response.",
    ),
    "high_volatility_stabilization": AdaptiveStrategy(
        "high_volatility_stabilization",
        "High-volatility stabilization",
        "Prioritize consistency before challenge escalation.",
        "EMERGING",
        "LOW",
        True,
        "Use soft recommendations unless longitudinal reliability is strong.",
    ),
}


def get_strategy(strategy_id: str) -> dict[str, Any]:
    return STRATEGIES.get(strategy_id, STRATEGIES["low_intensity_recovery"]).as_dict()


def list_strategies() -> list[dict[str, Any]]:
    return [strategy.as_dict() for strategy in STRATEGIES.values()]


def choose_strategy(recommendation: dict[str, Any], adaptive_context: dict[str, Any] | None = None) -> dict[str, Any]:
    adaptive_context = adaptive_context or {}
    rec_type = recommendation.get("type", "")
    if rec_type == "CONFIDENCE_CALIBRATION":
        return get_strategy("confidence_recalibration")
    if rec_type == "PACING_DRILL" or adaptive_context.get("pacing_problem"):
        return get_strategy("fatigue_sensitive_pacing")
    if recommendation.get("priority") == "HIGH":
        return get_strategy("revision_reinforcement")
    if adaptive_context.get("trajectory_reliability", {}).get("level") == "LOW":
        return get_strategy("low_intensity_recovery")
    return get_strategy("high_volatility_stabilization")
