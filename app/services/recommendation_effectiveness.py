from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import LearningIntervention
from app.services.causal_safety_rules import causal_confidence
from app.services.student_longitudinal_profile import build_student_longitudinal_profile

EFFECTIVENESS_VERSION = "recommendation-effectiveness.v1"


def _window(points: list[dict[str, Any]], attempt_id: int | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not points:
        return [], []
    if attempt_id is None:
        split = max(1, len(points) // 2)
    else:
        indexes = [idx for idx, point in enumerate(points) if point.get("attempt_id") == attempt_id]
        split = indexes[0] + 1 if indexes else max(1, len(points) // 2)
    return points[:split], points[split:]


def _delta(pre: list[dict[str, Any]], post: list[dict[str, Any]], key: str) -> float:
    if not pre or not post:
        return 0.0
    pre_avg = sum(point.get(key, 0) for point in pre) / len(pre)
    post_avg = sum(point.get(key, 0) for point in post) / len(post)
    return post_avg - pre_avg


def evaluate_intervention_effectiveness(db: Session, intervention: LearningIntervention) -> dict[str, Any]:
    profile = build_student_longitudinal_profile(db, intervention.user_id)
    points = profile.get("trajectory_points", [])
    anchor_attempt_id = (intervention.recommendation_payload or {}).get("anchor_attempt_id")
    pre, post = _window(points, anchor_attempt_id)
    confidence_before = profile.get("confidence_evolution", {})
    stability = profile.get("behavioral_stability", {})
    revision = profile.get("revision_effectiveness", {})
    reliability = profile.get("longitudinal_reliability", {}).get("overall_reliability", 0)
    confounders = 1 if len(post) == 0 else 0
    causal = causal_confidence(
        evidence_count=len(points),
        pre_points=len(pre),
        post_points=len(post),
        reliability=reliability,
        confounder_count=confounders,
    )

    outcome = {
        "post_intervention_accuracy_delta": round(_delta(pre, post, "accuracy"), 4),
        "post_intervention_score_delta": round(_delta(pre, post, "score"), 4),
        "stability_improvement": stability.get("consistency_score", 0),
        "confidence_correction": confidence_before.get("calibration_slope", 0),
        "pacing_stabilization": -stability.get("pacing_volatility", 0),
        "retention_topics": revision.get("topics", {}),
        "causal_safety": causal,
        "evidence_confidence": causal["causal_confidence"],
        "safe_summary": causal["claim_language"],
        "metric_version": EFFECTIVENESS_VERSION,
    }
    return outcome


def evaluate_user_interventions(db: Session, user_id: int) -> dict[str, Any]:
    interventions = db.query(LearningIntervention).filter(LearningIntervention.user_id == user_id).all()
    outcomes = []
    for intervention in interventions:
        outcome = evaluate_intervention_effectiveness(db, intervention)
        intervention.outcome_metadata = outcome
        outcomes.append({
            "recommendation_id": intervention.recommendation_id,
            "strategy_id": intervention.strategy_id,
            "status": intervention.status,
            "outcome": outcome,
        })
    db.commit()
    return {
        "user_id": user_id,
        "intervention_count": len(interventions),
        "outcomes": outcomes,
        "metric_version": EFFECTIVENESS_VERSION,
    }
