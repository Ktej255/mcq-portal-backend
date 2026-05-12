from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
from app.models.domain import KnowledgeConcept, KnowledgeEdge

class EducationalKnowledgeGraphEngine:
    def __init__(self, db: Session):
        self.db = db

    def get_concept_graph(self, subject_id: int) -> Dict[str, Any]:
        """Constructs the directed educational graph for a subject."""
        concepts = self.db.query(KnowledgeConcept).filter(KnowledgeConcept.subject_id == subject_id).all()
        concept_ids = [c.id for c in concepts]
        
        edges = self.db.query(KnowledgeEdge).filter(KnowledgeEdge.source_id.in_(concept_ids)).all()

        return {
            "concepts": [
                {
                    "id": c.id,
                    "name": c.name,
                    "metadata": c.metadata_payload
                } for c in concepts
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type,
                    "strength": e.strength,
                    "durability": e.durability
                } for e in edges
            ]
        }

    def identify_bottleneck_concepts(self, subject_id: int) -> List[Dict[str, Any]]:
        """Identifies concepts that act as major structural prerequisites for others."""
        # Heuristic: Concepts with the highest out-degree in the PREREQUISITE graph
        bottlenecks = self.db.query(
            KnowledgeConcept.id,
            KnowledgeConcept.name,
            func.count(KnowledgeEdge.id).label("dependent_count")
        ).join(KnowledgeEdge, KnowledgeConcept.id == KnowledgeEdge.source_id)\
         .filter(
             KnowledgeConcept.subject_id == subject_id,
             KnowledgeEdge.edge_type == "PREREQUISITE"
         )\
         .group_by(KnowledgeConcept.id, KnowledgeConcept.name)\
         .order_by(func.count(KnowledgeEdge.id).desc())\
         .limit(5).all()

        return [
            {"concept_id": b.id, "name": b.name, "dependent_concepts": b.dependent_count}
            for b in bottlenecks
        ]

    def track_misconception_pathways(self, subject_id: int) -> List[Dict[str, Any]]:
        """Identifies directed pathways where one misconception propagates to others."""
        pathways = self.db.query(KnowledgeEdge).filter(
            KnowledgeEdge.edge_type == "MISCONCEPTION_PATH"
        ).all()
        
        return [
            {
                "source_concept": e.source.name,
                "target_concept": e.target.name,
                "propagation_strength": e.strength
            } for e in pathways
        ]
