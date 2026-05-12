from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import LearningIntervention
from app.services.intervention_tracking_engine import acceptance_summary

ANALYTICS_VERSION = "intervention-analytics.v1"


def longitudinal_intervention_analytics(db: Session) -> dict[str, Any]:
    interventions = db.query(LearningIntervention).all()
    by_strategy: dict[str, list[LearningIntervention]] = defaultdict(list)
    for intervention in interventions:
        by_strategy[intervention.strategy_id].append(intervention)

    strategy_results = {}
    for strategy_id, items in by_strategy.items():
        outcomes = [item.outcome_metadata or {} for item in items]
        evidence = [outcome.get("evidence_confidence", 0) for outcome in outcomes]
        accuracy_deltas = [outcome.get("post_intervention_accuracy_delta", 0) for outcome in outcomes]
        overload_markers = len([outcome for outcome in outcomes if outcome.get("pacing_stabilization", 0) < -60])
        strategy_results[strategy_id] = {
            "count": len(items),
            "acceptance": acceptance_summary(items),
            "avg_evidence_confidence": round(sum(evidence) / len(evidence), 4) if evidence else 0,
            "avg_accuracy_delta_after": round(sum(accuracy_deltas) / len(accuracy_deltas), 4) if accuracy_deltas else 0,
            "overload_marker_rate": round((overload_markers / len(items) * 100), 4) if items else 0,
        }

    unstable = len([
        item for item in interventions
        if (item.outcome_metadata or {}).get("causal_safety", {}).get("level") == "LOW"
    ])
    return {
        "intervention_count": len(interventions),
        "overall_acceptance": acceptance_summary(interventions),
        "strategy_results": strategy_results,
        "unstable_outcome_rate": round((unstable / len(interventions) * 100), 4) if interventions else 0,
        "metric_version": ANALYTICS_VERSION,
    }
