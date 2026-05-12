from __future__ import annotations

from typing import Any, Dict, List
from app.services.cross_agent_reasoning_engine import CrossAgentReasoningEngine

INSTITUTIONAL_COORDINATION_VERSION = "institutional-coordination.v1"

class InstitutionalAgentCoordinator:
    def __init__(self, db: Any):
        self.db = db
        self.engine = CrossAgentReasoningEngine()

    def coordinate_for_institution(self, institution_id: int, user_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 25G: Adapt agent coordination based on institutional policy context."""
        # Fetch institutional constraints (mocked)
        constraints = self._get_institutional_constraints(institution_id)
        
        # Arbitrate reasoning
        distributed_reasoning = self.engine.arbitrate_distributed_reasoning(state)
        
        # Apply institutional filters to consensus
        final_consensus = self._apply_policy_filters(distributed_reasoning["distributed_consensus"], constraints)
        
        return {
            "institution_id": institution_id,
            "user_id": user_id,
            "coordinated_consensus": final_consensus,
            "original_distributed_reasoning": distributed_reasoning,
            "institutional_overrides": final_consensus["applied_filters"],
            "metric_version": INSTITUTIONAL_COORDINATION_VERSION
        }

    def _get_institutional_constraints(self, institution_id: int) -> Dict[str, Any]:
        return {
            "max_intervention_intensity": "MEDIUM",
            "required_consensus_confidence": 0.7,
            "prioritize_pacing_over_mastery": False
        }

    def _apply_policy_filters(self, consensus: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
        applied = []
        if consensus.get("consensus_confidence", 0) < constraints["required_consensus_confidence"]:
            consensus["status"] = "REJECTED_BY_INSTITUTIONAL_THRESHOLD"
            applied.append("THRESHOLD_ENFORCEMENT")
            
        consensus["applied_filters"] = applied
        return consensus

def get_institution_aware_cognition(db: Any, institution_id: int, user_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
    coordinator = InstitutionalAgentCoordinator(db)
    return coordinator.coordinate_for_institution(institution_id, user_id, state)
