from __future__ import annotations

from typing import Any, Dict, List
from app.services.pedagogical_agent_framework import get_specialized_agents

CROSS_AGENT_VERSION = "cross-agent-reasoning.v1"

class CrossAgentReasoningEngine:
    def __init__(self):
        self.agents = get_specialized_agents()

    def arbitrate_distributed_reasoning(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 25B & 25C: Negotiate consensus and expose disagreements."""
        reasoning_outputs = []
        for agent in self.agents:
            reasoning_outputs.append(agent.reason(state))
            
        consensus = self._generate_evidence_weighted_consensus(reasoning_outputs)
        
        return {
            "distributed_consensus": consensus,
            "agent_contributions": reasoning_outputs,
            "contradiction_negotiation": self._detect_contradictions(reasoning_outputs),
            "metric_version": CROSS_AGENT_VERSION
        }

    def _generate_evidence_weighted_consensus(self, outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Produce a weighted consensus that exposes participating agents."""
        total_reliability = sum(o["metadata"]["reliability_score"] for o in outputs)
        if total_reliability == 0: return {"status": "LOW_CONFIDENCE_STALEMATE"}
        
        # In a real system, we'd use a more complex merging logic
        participating = [o["metadata"]["agent_id"] for o in outputs]
        weighted_influence = {o["metadata"]["agent_id"]: round(o["metadata"]["reliability_score"] / total_reliability, 4) for o in outputs}
        
        return {
            "participating_agents": participating,
            "weighted_influence": weighted_influence,
            "consensus_confidence": round(total_reliability / len(outputs), 4),
            "unresolved_contradictions": self._detect_contradictions(outputs),
            "minority_disagreement_signals": self._capture_disagreements(outputs)
        }

    def _detect_contradictions(self, outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Simple contradiction detection: check if conclusions vary wildly
        conclusions = [o["conclusion"] for o in outputs]
        if len(set(conclusions)) > 1:
            return [{"type": "CONCLUSION_MISMATCH", "details": list(set(conclusions))}]
        return []

    def _capture_disagreements(self, outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Find agents with reliability scores significantly lower than average
        avg_rel = sum(o["metadata"]["reliability_score"] for o in outputs) / len(outputs)
        return [o for o in outputs if o["metadata"]["reliability_score"] < avg_rel * 0.5]

def get_agent_consensus(state: Dict[str, Any]) -> Dict[str, Any]:
    engine = CrossAgentReasoningEngine()
    return engine.arbitrate_distributed_reasoning(state)
