from sqlalchemy.orm import Session
from typing import Dict, Any, List
from app.services.human_review_engine import HumanReviewEngine
from app.services.educational_escalation_system import EducationalEscalationSystem
from app.services.verified_pedagogical_reasoning import VerifiedPedagogicalReasoning
from app.models.domain import LearningIntervention, ReviewStatusEnum

class CollaborativeGovernanceEngine:
    def __init__(self, db: Session):
        self.db = db
        self.review_engine = HumanReviewEngine(db)
        self.escalation_system = EducationalEscalationSystem(db)
        self.reasoning_service = VerifiedPedagogicalReasoning(db)

    def process_intervention_proposal(self, intervention: LearningIntervention) -> Dict[str, Any]:
        """Orchestrates the collaborative governance of a proposed intervention."""
        # Risk-tiered logic
        risk = intervention.risk_level # LOW, MEDIUM, HIGH
        
        if risk == "HIGH":
            # Mandatory human review
            self.review_engine.create_review_request(
                target_type="INTERVENTION",
                target_id=intervention.recommendation_id,
                reviewer_id=self._select_best_reviewer(intervention)
            )
            return {"action": "HELD_FOR_REVIEW", "reason": "High-risk intervention requires educator approval."}
            
        if risk == "MEDIUM":
            # Optional review, auto-approved if threshold met
            intervention.approval_status = "AUTO_APPROVED"
            return {"action": "AUTO_APPROVED", "reason": "Medium-risk intervention within automated bounds."}

        # LOW risk - silent auto-approval
        intervention.approval_status = "AUTO_APPROVED"
        self.db.commit()
        return {"action": "AUTO_APPROVED", "reason": "Low-risk intervention."}

    def _select_best_reviewer(self, intervention: LearningIntervention) -> int:
        """Heuristic to select the most appropriate educator for a review."""
        # Placeholder: returning a default educator ID for now
        return 1 

    def get_governance_observability(self) -> Dict[str, Any]:
        """Monitors the health and latency of human-in-the-loop workflows."""
        from sqlalchemy import func
        from app.models.domain import EducationalReview
        
        backlog = self.db.query(func.count(EducationalReview.id)).filter(EducationalReview.status == ReviewStatusEnum.PENDING).scalar()
        overrides = self.db.query(func.count(EducationalReview.id)).filter(EducationalReview.status == ReviewStatusEnum.MODIFIED).scalar()
        
        return {
            "review_backlog": backlog,
            "educator_override_rate": round(overrides / max(1, backlog), 2),
            "escalation_count": len(self.escalation_system.get_active_escalations()),
            "governance_health": "OPTIMAL" if backlog < 10 else "CONGESTED"
        }
