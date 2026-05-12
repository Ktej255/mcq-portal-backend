from __future__ import annotations

from typing import Any, Dict, List
from app.services.student_digital_twin_engine import construct_student_twin

LONGITUDINAL_FORECAST_VERSION = "longitudinal-forecast.v1"

def forecast_multi_semester_evolution(db: Any, user_id: int) -> Dict[str, Any]:
    twin = construct_student_twin(db, user_id)
    
    # Simple longitudinal projection
    durability = twin["twin_state"]["mastery_baseline"]
    volatility = twin["twin_state"]["volatility_index"]
    
    # Forecast intervals (Semesters)
    semesters = ["Semester 1", "Semester 2", "Semester 3"]
    projections = []
    current_durability = durability
    
    for _ in semesters:
        decay = volatility * 0.1
        current_durability = max(0, current_durability - decay + 0.05) # Assume slight learning offset
        projections.append(round(current_durability, 4))
        
    return {
        "user_id": user_id,
        "long_term_forecast": {
            "mastery_durability_trajectory": dict(zip(semesters, projections)),
            "burnout_probability": round(clamp(volatility / 40), 4),
            "pacing_normalization_probability": 0.85 if twin["twin_state"]["pacing_identity"] == "STABLE" else 0.45
        },
        "intervention_half_life_evolution": "INCREASING" if current_durability > durability else "STABLE",
        "metric_version": LONGITUDINAL_FORECAST_VERSION
    }

def clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, val))
