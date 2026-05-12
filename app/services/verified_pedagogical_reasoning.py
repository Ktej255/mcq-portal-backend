from sqlalchemy.orm import Session
from typing import Dict, Any, List
from app.models.domain import EducationalReview, ReviewStatusEnum

class VerifiedPedagogicalReasoning:
    def __init__(self, db: Session):
        self.db = db

    def generate_verified_reasoning(self, base_reasoning: Dict[str, Any], target_id: str) -> Dict[str, Any]:
        """Wraps AI reasoning with verification metadata and educator contributions."""
        reviews = self.db.query(EducationalReview).filter(
            EducationalReview.target_id == target_id,
            EducationalReview.target_type == "REASONING"
        ).order_by(EducationalReview.created_at).all()

        is_verified = any(r.status == ReviewStatusEnum.APPROVED for r in reviews)
        has_overrides = any(r.status == ReviewStatusEnum.MODIFIED for r in reviews)
        
        # Merge overrides if any
        final_reasoning = base_reasoning.copy()
        contributions = []
        
        for r in reviews:
            contributions.append({
                "reviewer_id": r.reviewer_id,
                "status": r.status,
                "comment": r.comment,
                "timestamp": r.created_at.isoformat()
            })
            if r.override_payload:
                final_reasoning.update(r.override_payload)

        return {
            "ai_reasoning": base_reasoning,
            "verified_reasoning": final_reasoning,
            "governance": {
                "is_verified": is_verified,
                "verification_status": "APPROVED" if is_verified else "PENDING" if not reviews else "REJECTED",
                "has_educator_overrides": has_overrides,
                "contributor_history": contributions,
                "approval_confidence": self._calculate_approval_confidence(reviews)
            }
        }

    def _calculate_approval_confidence(self, reviews: List[EducationalReview]) -> float:
        """Heuristic for confidence based on educator feedback consistency."""
        if not reviews: return 0.0
        approvals = [r for r in reviews if r.status in [ReviewStatusEnum.APPROVED, ReviewStatusEnum.MODIFIED]]
        return round(len(approvals) / len(reviews), 2)
