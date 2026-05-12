from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Dict, Any, Optional
from app.models.domain import EducationalReview, ReviewStatusEnum, LearningIntervention, User

class HumanReviewEngine:
    def __init__(self, db: Session):
        self.db = db

    def create_review_request(self, target_type: str, target_id: str, reviewer_id: int) -> EducationalReview:
        """Creates a new review request for an educator."""
        review = EducationalReview(
            target_type=target_type,
            target_id=target_id,
            reviewer_id=reviewer_id,
            status=ReviewStatusEnum.PENDING
        )
        self.db.add(review)
        
        # If it's an intervention, update its status
        if target_type == "INTERVENTION":
            intervention = self.db.query(LearningIntervention).filter(LearningIntervention.recommendation_id == target_id).first()
            if intervention:
                intervention.approval_status = "PENDING_REVIEW"
                
        self.db.commit()
        self.db.refresh(review)
        return review

    def submit_review(self, review_id: int, status: ReviewStatusEnum, comment: str, override_payload: Optional[Dict[str, Any]] = None) -> EducationalReview:
        """Submits an educator's review decision."""
        review = self.db.query(EducationalReview).get(review_id)
        if not review:
            raise Exception("Review not found")
            
        review.status = status
        review.comment = comment
        review.override_payload = override_payload
        
        # Propagate decision to target
        if review.target_type == "INTERVENTION":
            intervention = self.db.query(LearningIntervention).filter(LearningIntervention.recommendation_id == review.target_id).first()
            if intervention:
                intervention.approval_status = "APPROVED" if status == ReviewStatusEnum.APPROVED or status == ReviewStatusEnum.MODIFIED else "REJECTED"
                if override_payload:
                    intervention.recommendation_payload = override_payload
        
        self.db.commit()
        self.db.refresh(review)
        return review

    def get_pending_reviews(self, reviewer_id: int) -> List[EducationalReview]:
        """Retrieves all pending reviews assigned to an educator."""
        return self.db.query(EducationalReview).filter(
            EducationalReview.reviewer_id == reviewer_id,
            EducationalReview.status == ReviewStatusEnum.PENDING
        ).order_by(desc(EducationalReview.created_at)).all()

    def get_review_history(self, target_id: str) -> List[EducationalReview]:
        """Provides an audit trail for a specific educational action."""
        return self.db.query(EducationalReview).filter(EducationalReview.target_id == target_id).order_by(desc(EducationalReview.created_at)).all()
