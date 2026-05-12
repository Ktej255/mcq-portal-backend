from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, RoleEnum
from app.schemas.common import StandardResponse

from app.services.reality_grounding_engine import RealityGroundingEngine
from app.services.human_experience_engine import HumanExperienceEngine
from app.services.pedagogical_humility_engine import PedagogicalHumilityEngine
from app.services.cultural_preservation_engine import CulturalPreservationEngine

router = APIRouter()

# Helper to verify Educator or Admin role
def get_educator_or_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in [RoleEnum.EDUCATOR, RoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Educator or Admin privileges required")
    return current_user

@router.post("/reality/audit")
def create_reality_audit(
    target_type: str,
    target_id: str,
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = RealityGroundingEngine(db)
    audit = engine.perform_reality_audit(target_type, target_id, user.id)
    return StandardResponse(success=True, message="Reality audit initiated", data=audit)

@router.get("/reality/drift")
def get_abstraction_drift(
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = RealityGroundingEngine(db)
    status = engine.detect_abstraction_drift()
    return StandardResponse(success=True, message="Abstraction drift status retrieved", data=status)

@router.post("/experience/signal")
def submit_experience_signal(
    signal_type: str,
    content: str,
    evidence: Dict[str, Any],
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    engine = HumanExperienceEngine(db)
    signal = engine.record_experience_signal(user.id, signal_type, content, evidence)
    return StandardResponse(success=True, message="Qualitative experience signal recorded", data=signal)

@router.get("/humility/assessment")
def get_epistemic_humility(
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = PedagogicalHumilityEngine(db)
    assessment = engine.assess_epistemic_humility()
    return StandardResponse(success=True, message="Epistemic humility assessment complete", data=assessment)

@router.get("/cultural/status")
def get_cultural_preservation(
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = CulturalPreservationEngine(db)
    erasure_risk = engine.track_cultural_erasure_risk()
    return StandardResponse(success=True, message="Cultural preservation status retrieved", data=erasure_risk)
