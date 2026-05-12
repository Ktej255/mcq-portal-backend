from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.db.session import get_db
from app.api.dependencies import get_current_admin, get_current_user
from app.models.domain import User, RoleEnum
from app.schemas.common import StandardResponse

from app.services.cohort_intelligence_engine import CohortIntelligenceEngine
from app.services.curriculum_health_intelligence import CurriculumHealthIntelligence
from app.services.educator_operational_engine import EducatorOperationalEngine
from app.services.institutional_governance_engine import InstitutionalGovernanceEngine
from app.services.institutional_intervention_system import InstitutionalInterventionSystem
from app.services.longitudinal_cohort_modeling import LongitudinalCohortModeling
from app.services.operational_observability_engine import OperationalObservabilityEngine

router = APIRouter()

# Helper to verify Educator or Admin role
def get_educator_or_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in [RoleEnum.EDUCATOR, RoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Educator or Admin privileges required")
    return current_user

@router.get("/cohort/{cohort_id}/intelligence")
def get_cohort_intelligence(
    cohort_id: int, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = CohortIntelligenceEngine(db)
    summary = engine.get_cohort_summary(cohort_id)
    misconceptions = engine.detect_shared_misconceptions(cohort_id)
    volatility = engine.analyze_topic_volatility(cohort_id)
    
    data = {
        "summary": summary,
        "shared_misconceptions": misconceptions,
        "volatility": volatility
    }
    return StandardResponse(success=True, message="Cohort intelligence retrieved", data=data)

@router.get("/curriculum/{subject_id}/health")
def get_curriculum_health(
    subject_id: int, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = CurriculumHealthIntelligence(db)
    health = engine.analyze_curriculum_health(subject_id)
    return StandardResponse(success=True, message="Curriculum health analytics retrieved", data=health)

@router.get("/educator/dashboard")
def get_educator_dashboard(
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    # Verify role is EDUCATOR
    if user.role != RoleEnum.EDUCATOR:
         raise HTTPException(status_code=403, detail="Educator dashboard only accessible to Educators")
         
    engine = EducatorOperationalEngine(db)
    dashboard_data = engine.get_educator_dashboard_data(user.id)
    return StandardResponse(success=True, message="Educator dashboard data retrieved", data=dashboard_data)

@router.get("/institution/{institution_id}/recommendations")
def get_institutional_interventions(
    institution_id: int, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    # Enforce institutional boundary
    if user.role != RoleEnum.ADMIN and user.institution_id != institution_id:
        raise HTTPException(status_code=403, detail="Access to other institutions denied")
        
    system = InstitutionalInterventionSystem(db)
    recs = system.generate_institutional_recommendations(institution_id)
    return StandardResponse(success=True, message="Institutional recommendations generated", data=recs)

@router.get("/institution/{institution_id}/observability")
def get_institutional_observability(
    institution_id: int, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_admin)
):
    engine = OperationalObservabilityEngine(db)
    health = engine.monitor_institutional_health(institution_id)
    return StandardResponse(success=True, message="Institutional operational health retrieved", data=health)

@router.get("/cohort/{cohort_id}/trends")
def get_cohort_longitudinal_trends(
    cohort_id: int, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = LongitudinalCohortModeling(db)
    trends = engine.get_cohort_evolution_trends(cohort_id)
    return StandardResponse(success=True, message="Longitudinal cohort trends retrieved", data=trends)
