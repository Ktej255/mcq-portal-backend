from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from app.models.domain import CausalInference, KnowledgeEdge, KnowledgeConcept

class CausalPedagogicalEngine:
    def __init__(self, db: Session):
        self.db = db

    def estimate_causal_contribution(self, intervention_id: str) -> Dict[str, Any]:
        """Estimates the probable causal contribution of an intervention to student recovery."""
        # This would typically use Causal Model (e.g. Do-calculus or RCT simulation)
        # We retrieve the latest inference record
        inference = self.db.query(CausalInference).filter(
            CausalInference.target_type == "INTERVENTION",
            CausalInference.target_id == intervention_id
        ).first()

        if not inference:
            return {"status": "UNSTABLE", "message": "Insufficient evidence for causal attribution."}

        return {
            "intervention_id": intervention_id,
            "causal_estimate": inference.estimate,
            "confidence_interval": inference.confidence_interval,
            "evidence_support": inference.evidence_support,
            "confounder_risk": self._analyze_confounders(inference.confounders),
            "certainty_level": "CAUSAL_TENTATIVE" if inference.p_value > 0.05 else "CAUSAL_SIGNIFICANT"
        }

    def analyze_prerequisite_causality(self, concept_id: int) -> List[Dict[str, Any]]:
        """Estimates how much a gap in this prerequisite causes failure in dependent concepts."""
        edges = self.db.query(KnowledgeEdge).filter(
            KnowledgeEdge.source_id == concept_id,
            KnowledgeEdge.edge_type == "PREREQUISITE"
        ).all()
        
        causal_effects = []
        for edge in edges:
            # Effect size = strength * durability
            causal_effects.append({
                "target_concept": edge.target.name,
                "causal_weight": round(edge.strength * edge.durability, 3),
                "instability_propagation_risk": "HIGH" if edge.strength > 0.8 else "MEDIUM"
            })
            
        return causal_effects

    def _analyze_confounders(self, confounders: Optional[Dict[str, Any]]) -> str:
        """Heuristic to evaluate the risk of hidden confounders in a causal estimate."""
        if not confounders: return "LOW"
        if len(confounders) > 5: return "HIGH"
        return "MEDIUM"
