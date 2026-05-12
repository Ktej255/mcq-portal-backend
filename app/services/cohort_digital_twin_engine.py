from __future__ import annotations

from typing import Any, Dict, List
from sqlalchemy.orm import Session
from app.services.longitudinal_cohort_modeling import LongitudinalCohortModeling

COHORT_TWIN_VERSION = "cohort-twin.v1"

def construct_cohort_twin(db: Session, cohort_id: int) -> Dict[str, Any]:
    modeling = LongitudinalCohortModeling(db)
    evolution = modeling.get_cohort_evolution_trends(cohort_id)
    durability = modeling.model_curriculum_durability(cohort_id)
    
    twin = {
        "cohort_id": cohort_id,
        "cohort_pacing_identity": "VARIABLE" if _calculate_volatility(evolution) > 0.2 else "STABLE",
        "conceptual_bottlenecks": durability.get("decay_bottlenecks", []),
        "volatility_regions": durability.get("bottleneck_recurrence_rate", 0),
        "learning_velocity": modeling.calculate_institutional_learning_velocity(1), # Assuming inst_id 1
        "adaptation_responsiveness": 0.75, # Probabilistic aggregate
        "metric_version": COHORT_TWIN_VERSION
    }
    return twin

def simulate_curriculum_impact(db: Session, cohort_id: int, curriculum_changes: Dict[str, Any]) -> Dict[str, Any]:
    twin = construct_cohort_twin(db, cohort_id)
    
    # Estimate impact of restructuring or compression
    compression = curriculum_changes.get("compression_factor", 1.0)
    reordering = curriculum_changes.get("topic_reordering", False)
    
    overload_shift = 0.2 * (compression - 1.0)
    stability_impact = -0.1 if reordering else 0.05
    
    return {
        "cohort_id": cohort_id,
        "estimated_impact": {
            "overload_probability_shift": round(overload_shift, 4),
            "mastery_durability_impact": round(stability_impact, 4),
            "bottleneck_propagation_risk": "MEDIUM" if compression > 1.2 else "LOW"
        },
        "long_term_retention_forecast": 0.85 + stability_impact,
        "metric_version": COHORT_TWIN_VERSION
    }

def _calculate_volatility(evolution: List[Dict[str, Any]]) -> float:
    values = [e["value"] for e in evolution]
    if not values: return 0.0
    from statistics import pstdev
    return pstdev(values) if len(values) > 1 else 0.0
