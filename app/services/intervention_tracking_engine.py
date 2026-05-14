from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import LearningIntervention
from app.services.adaptive_learning_engine import ADAPTIVE_VERSION
from app.services.strategy_registry import choose_strategy

INTERVENTION_VERSION = "intervention-tracking.v1"

VALID_STATUSES = {
    "GENERATED",
    "VIEWED",
    "ACCEPTED",
    "IGNORED",
    "PARTIALLY_FOLLOWED",
    "FOLLOWED",
    "ABANDONED",
}


def _stable_recommendation_id(user_id: int, recommendation: dict[str, Any], strategy_id: str) -> str:
    raw = json.dumps({"user_id": user_id, "recommendation": recommendation, "strategy_id": strategy_id}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def record_generated_interventions(
    db: Session,
    user_id: int,
    recommendations: list[dict[str, Any]],
    adaptive_context: dict[str, Any] | None = None,
    experiment_assignment: dict[str, Any] | None = None,
) -> list[LearningIntervention]:
    interventions = []
    for recommendation in recommendations:
        strategy = choose_strategy(recommendation, adaptive_context)
        recommendation_id = _stable_recommendation_id(user_id, recommendation, strategy["strategy_id"])
        existing = db.query(LearningIntervention).filter(LearningIntervention.recommendation_id == recommendation_id).first()
        if existing:
            interventions.append(existing)
            continue
        intervention = LearningIntervention(
            user_id=user_id,
            recommendation_id=recommendation_id,
            strategy_id=strategy["strategy_id"],
            experiment_id=(experiment_assignment or {}).get("experiment_id"),
            variant_id=(experiment_assignment or {}).get("variant_id"),
            recommendation_payload={
                "recommendation": recommendation,
                "strategy": strategy,
                "adaptive_context": adaptive_context or {},
            },
            status="GENERATED"
        )
        db.add(intervention)
        interventions.append(intervention)
    db.commit()
    for intervention in interventions:
        db.refresh(intervention)
    return interventions


def update_intervention_status(db: Session, recommendation_id: str, status: str, metadata: dict[str, Any] | None = None) -> LearningIntervention:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid intervention status: {status}")
    intervention = db.query(LearningIntervention).filter(LearningIntervention.recommendation_id == recommendation_id).first()
    if not intervention:
        raise ValueError("Intervention not found")
    intervention.status = status
    intervention.updated_at = datetime.now(timezone.utc)
    payload = dict(intervention.acceptance_metadata or {})
    payload[status.lower()] = {
        "at": intervention.updated_at.isoformat(),
        "metadata": metadata or {},
    }
    intervention.acceptance_metadata = payload
    db.commit()
    db.refresh(intervention)
    return intervention


def attach_intervention_outcome(db: Session, recommendation_id: str, outcome: dict[str, Any]) -> LearningIntervention:
    intervention = db.query(LearningIntervention).filter(LearningIntervention.recommendation_id == recommendation_id).first()
    if not intervention:
        raise ValueError("Intervention not found")
    intervention.outcome_metadata = {
        **(intervention.outcome_metadata or {}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "outcome": outcome,
    }
    intervention.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(intervention)
    return intervention


def acceptance_summary(interventions: list[LearningIntervention]) -> dict[str, Any]:
    total = len(interventions)
    accepted = len([item for item in interventions if item.status in {"ACCEPTED", "FOLLOWED", "PARTIALLY_FOLLOWED"}])
    ignored = len([item for item in interventions if item.status == "IGNORED"])
    abandoned = len([item for item in interventions if item.status == "ABANDONED"])
    return {
        "total": total,
        "accepted_rate": round((accepted / total * 100), 4) if total else 0,
        "ignored_rate": round((ignored / total * 100), 4) if total else 0,
        "abandonment_rate": round((abandoned / total * 100), 4) if total else 0,
        "metric_version": INTERVENTION_VERSION,
    }
