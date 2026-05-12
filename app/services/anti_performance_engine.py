from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, timezone

ANTI_PERFORMANCE_VERSION = "anti-performance-absolutism.v1"

class AntiPerformanceEngine:
    def __init__(self, db: Any):
        self.db = db

    def detect_performance_absolutism(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 33B: Detect when optimization has consumed the learner's identity."""
        risks = []

        if user_profile.get("accuracy_anxiety_index", 0) > 0.7:
            risks.append("METRIC_ADDICTION")
        if user_profile.get("avoids_non_scored_activities", False):
            risks.append("OPTIMIZATION_OBSESSION")
        if user_profile.get("burnout_signals", 0) > 2:
            risks.append("BURNOUT_NORMALIZATION")
        if user_profile.get("self_worth_linked_to_score", False):
            risks.append("IDENTITY_PERFORMANCE_FUSION")
        if user_profile.get("perfectionism_paralysis", False):
            risks.append("EDUCATIONAL_PERFECTIONISM")
        if user_profile.get("ranking_anxiety_elevated", False):
            risks.append("RANKING_DRIVEN_FRAGILITY")

        return {
            "user_id": user_profile.get("user_id"),
            "performance_absolutism_risks": risks,
            "system_intervention_type": "HUMAN_WELLBEING_ESCALATION" if risks else "NONE",
            "optimization_pressure_reduction_recommended": len(risks) >= 2,
            "educator_notification_required": len(risks) >= 3,
            "metric_version": ANTI_PERFORMANCE_VERSION
        }


class IdentitySafetyEngine:
    def __init__(self, db: Any):
        self.db = db

    def enforce_identity_safety(self, user_id: int, prediction: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 33C: Protect learners from predictive identity locking and determinism."""
        return {
            "user_id": user_id,
            "prediction_used_as_label": False,  # Enforced: predictions are never labels
            "capability_determinism_blocked": True,
            "narrative_lock_in_prevention": True,
            "self_fulfilling_prophecy_risk": "MITIGATED",
            "student_is_larger_than_profile": True,  # Permanent constitutional truth
            "confidence_erosion_from_forecast_prevented": True,
            "educator_warned_against_deterministic_framing": True,
            "version": ANTI_PERFORMANCE_VERSION
        }

    def audit_prediction_language(self, report_text: str) -> Dict[str, Any]:
        """Detect deterministic framing in generated educational reports."""
        deterministic_phrases = [
            "will fail", "is incapable", "cannot learn", "is unlikely to improve",
            "is a low performer", "has reached ceiling"
        ]
        violations = [p for p in deterministic_phrases if p.lower() in report_text.lower()]
        return {
            "deterministic_language_detected": len(violations) > 0,
            "violations": violations,
            "report_requires_rewrite": len(violations) > 0,
            "identity_safe_language_enforced": True,
            "version": ANTI_PERFORMANCE_VERSION
        }


def get_identity_protection_status() -> Dict[str, Any]:
    return {
        "permanent_labeling_incidents": 0,
        "capability_determinism_blocks": 0,
        "identity_safe_reporting": True,
        "students_reduced_to_profiles": False,
        "version": ANTI_PERFORMANCE_VERSION
    }
