from __future__ import annotations

from typing import Any, Dict, List
import random
from app.services.student_digital_twin_engine import construct_student_twin

SIMULATION_ENGINE_VERSION = "educational-simulation.v1"

def simulate_educational_scenario(db: Any, user_id: int, strategy: Dict[str, Any]) -> Dict[str, Any]:
    twin = construct_student_twin(db, user_id)
    
    # Strategy parameters
    revision_intensity = strategy.get("revision_intensity", "MEDIUM")
    pacing_pressure = strategy.get("pacing_pressure", "STANDARD")
    
    # Simulation runs (Monte Carlo-ish simplified)
    results = []
    for _ in range(100):
        improvement = twin["transition_probabilities"]["improvement"] * _intensity_multiplier(revision_intensity)
        overload_risk = twin["transition_probabilities"]["overload"] * _pressure_multiplier(pacing_pressure)
        
        # Outcome calculation
        outcome = improvement - (overload_risk * 0.5) + (random.uniform(-0.1, 0.1))
        results.append(outcome)
        
    avg_outcome = sum(results) / len(results)
    
    return {
        "user_id": user_id,
        "scenario_strategy": strategy,
        "estimated_outcomes": {
            "mastery_improvement_probability": round(clamp(avg_outcome), 4),
            "overload_probability": round(clamp(twin["transition_probabilities"]["overload"] * _pressure_multiplier(pacing_pressure)), 4),
            "pacing_stabilization": twin["twin_state"]["pacing_identity"] == "STABLE"
        },
        "forecast": {
            "intervention_effectiveness": "HIGH" if avg_outcome > 0.6 else "MODERATE" if avg_outcome > 0.4 else "LOW",
            "confidence_interval": [round(avg_outcome - 0.15, 4), round(avg_outcome + 0.15, 4)],
            "evidence_strength": twin["uncertainty"]["prediction_confidence"]
        },
        "simulation_reliability": twin["uncertainty"]["prediction_confidence"],
        "metric_version": SIMULATION_ENGINE_VERSION
    }

def _intensity_multiplier(intensity: str) -> float:
    return {"LOW": 0.8, "MEDIUM": 1.0, "HIGH": 1.3}.get(intensity, 1.0)

def _pressure_multiplier(pressure: str) -> float:
    return {"REDUCED": 0.5, "STANDARD": 1.0, "INTENSE": 1.5}.get(pressure, 1.0)

def clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, val))
