from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, RoleEnum
from app.schemas.common import StandardResponse

from app.services.educational_knowledge_graph_engine import EducationalKnowledgeGraphEngine
from app.services.causal_pedagogical_engine import CausalPedagogicalEngine
from app.services.counterfactual_educational_engine import CounterfactualEducationalEngine
from app.services.curriculum_fragility_intelligence import CurriculumFragilityIntelligence
from app.services.educational_graph_observability import EducationalGraphObservability

router = APIRouter()

# Helper to verify Educator or Admin role
def get_educator_or_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in [RoleEnum.EDUCATOR, RoleEnum.ADMIN]:
        raise HTTPException(status_code=403, detail="Educator or Admin privileges required")
    return current_user

@router.get("/graph/{subject_id}")
def get_educational_graph(
    subject_id: int, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = EducationalKnowledgeGraphEngine(db)
    graph = engine.get_concept_graph(subject_id)
    bottlenecks = engine.identify_bottleneck_concepts(subject_id)
    
    return StandardResponse(success=True, message="Educational knowledge graph retrieved", data={
        "graph": graph,
        "bottlenecks": bottlenecks
    })

@router.get("/causal/intervention/{recommendation_id}")
def get_intervention_causality(
    recommendation_id: str, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = CausalPedagogicalEngine(db)
    contribution = engine.estimate_causal_contribution(recommendation_id)
    return StandardResponse(success=True, message="Causal contribution estimated", data=contribution)

@router.post("/counterfactual/simulate")
def simulate_educational_scenario(
    scenario: str,
    parameters: Dict[str, Any],
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = CounterfactualEducationalEngine(db)
    simulation = engine.simulate_counterfactual(scenario, parameters)
    return StandardResponse(success=True, message="Counterfactual simulation complete", data=simulation)

@router.get("/curriculum/{subject_id}/fragility")
def get_curriculum_fragility(
    subject_id: int, 
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = CurriculumFragilityIntelligence(db)
    chains = engine.detect_fragile_chains(subject_id)
    propagation = engine.monitor_instability_propagation(subject_id)
    
    return StandardResponse(success=True, message="Curriculum fragility analysis complete", data={
        "fragile_chains": chains,
        "instability_propagation": propagation
    })

@router.get("/observability")
def get_causal_observability(
    db: Session = Depends(get_db), 
    user: User = Depends(get_educator_or_admin)
):
    engine = EducationalGraphObservability(db)
    status = engine.monitor_graph_stability()
    migration = engine.track_misconception_migration()
    
    return StandardResponse(success=True, message="Causal observability retrieved", data={
        "stability": status,
        "misconception_migration": migration
    })
