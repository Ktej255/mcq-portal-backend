from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User
from app.schemas.common import StandardResponse
from app.services.human_flourishing_engine import HumanFlourishingEngine

router = APIRouter()

@router.get("/status")
def get_flourishing_status(
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    engine = HumanFlourishingEngine(db)
    status = engine.evaluate_flourishing_status(user.id)
    return StandardResponse(success=True, message="Human flourishing status retrieved", data=status)

@router.post("/sovereignty")
def update_sovereignty_settings(
    settings: Dict[str, bool],
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    engine = HumanFlourishingEngine(db)
    success = engine.trigger_sovereignty_override(user.id, settings)
    return StandardResponse(success=success, message="Pedagogical sovereignty settings updated", data=None)
