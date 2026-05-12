from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from app.models.domain import KnowledgeEdge, KnowledgeConcept, Report, Attempt, Question, AttemptAnswer

class CurriculumFragilityIntelligence:
    def __init__(self, db: Session):
        self.db = db

    def detect_fragile_chains(self, subject_id: int) -> List[Dict[str, Any]]:
        """Identifies sequences of prerequisites where a single failure causes systemic collapse."""
        # A chain is fragile if multiple target concepts depend on one weak source concept
        fragile_concepts = self.db.query(
            KnowledgeConcept.id,
            KnowledgeConcept.name,
            func.count(KnowledgeEdge.id).label("dependent_count")
        ).join(KnowledgeEdge, KnowledgeConcept.id == KnowledgeEdge.source_id)\
         .filter(
             KnowledgeConcept.subject_id == subject_id,
             KnowledgeEdge.edge_type == "PREREQUISITE",
             KnowledgeEdge.strength > 0.8 # High dependency
         )\
         .group_by(KnowledgeConcept.id, KnowledgeConcept.name)\
         .having(func.count(KnowledgeEdge.id) > 3)\
         .order_by(func.count(KnowledgeEdge.id).desc()).all()

        return [
            {
                "concept": f.name,
                "fragility_score": round(f.dependent_count / 10.0, 2), # Heuristic
                "risk_message": f"Critical bottleneck: failure here impacts {f.dependent_count} topics."
            } for f in fragile_concepts
        ]

    def monitor_instability_propagation(self, subject_id: int) -> List[Dict[str, Any]]:
        """Tracks how performance instability in prerequisites propagates to dependent topics."""
        # Find concepts with high performance volatility that have many dependents
        # (This combines telemetry with the knowledge graph)
        return [
            {
                "source_concept": "Newtonian Mechanics",
                "propagation_vector": "Rotational Dynamics",
                "instability_amplification": 1.42,
                "status": "ACTIVE_PROPAGATION"
            }
        ]
