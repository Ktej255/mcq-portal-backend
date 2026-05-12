from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, RoleEnum, ReviewStatusEnum
from app.schemas.common import StandardResponse

from app.services.human_review_engine import HumanReviewEngine
from app.services.educational_escalation_system import EducationalEscalationSystem
from app.services.collaborative_governance_engine import CollaborativeGovernanceEngine

router = APIRouter()

# Helper to verify Educator or Admin role
def get_educator_or_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in [RoleEnum.EDUCATOR, RoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Educator or Admin privileges required")
    return current_user

@router.get("/reviews/pending")
def get_pending_reviews(
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = HumanReviewEngine(db)
    reviews = engine.get_pending_reviews(user.id)
    return StandardResponse(success=True, message="Pending reviews retrieved", data=reviews)

@router.post("/reviews/{review_id}/submit")
def submit_review(
    review_id: int,
    status: ReviewStatusEnum,
    comment: str,
    override_payload: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = HumanReviewEngine(db)
    review = engine.submit_review(review_id, status, comment, override_payload)
    return StandardResponse(success=True, message=f"Review decision '{status}' submitted", data=review)

@router.get("/escalations/active")
def get_active_escalations(
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    system = EducationalEscalationSystem(db)
    escalations = system.get_active_escalations()
    return StandardResponse(success=True, message="Active escalations retrieved", data=escalations)

@router.post("/escalations/{escalation_id}/resolve")
def resolve_escalation(
    escalation_id: int,
    resolution_payload: Dict[str, Any],
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    system = EducationalEscalationSystem(db)
    escalation = system.resolve_escalation(escalation_id, resolution_payload)
    return StandardResponse(success=True, message="Escalation resolved", data=escalation)

@router.get("/observability")
def get_governance_status(
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = CollaborativeGovernanceEngine(db)
    status = engine.get_governance_observability()
    return StandardResponse(success=True, message="Governance observability retrieved", data=status)
