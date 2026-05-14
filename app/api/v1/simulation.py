from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.domain import Test, Attempt, AttemptStatusEnum, ExamEvent
from app.api.dependencies import get_current_user
from datetime import datetime, timezone, timedelta
import uuid

router = APIRouter()

@router.post("/start/{test_id}")
async def start_simulation(
    test_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # 1. Fetch Test
    test = db.query(Test).filter(Test.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Simulation target not found")
    
    # 2. Check for existing active simulation
    existing = db.query(Attempt).filter(
        Attempt.user_id == current_user.id,
        Attempt.status == AttemptStatusEnum.IN_PROGRESS,
        Attempt.is_simulation == True
    ).first()
    
    if existing:
        return {
            "status": "RESUMED",
            "attempt_id": existing.id,
            "message": "Resuming active simulation. Pausing was not permitted, timer continued."
        }

    # 3. Create Simulation Attempt
    # Simulation mode enforces fixed time and no pausing
    new_attempt = Attempt(
        user_id=current_user.id,
        test_id=test_id,
        status=AttemptStatusEnum.IN_PROGRESS,
        is_simulation=True,
        start_time=datetime.now(timezone.utc)
    )
    db.add(new_attempt)
    db.flush()
    
    # 4. Log Simulation Start Event
    event = ExamEvent(
        attempt_id=new_attempt.id,
        event_type="SIMULATION_START",
        payload={
            "enforced_duration_minutes": test.duration_minutes or 120,
            "negative_marking": 0.66,
            "interruption_tolerance": "ZERO"
        }
    )
    db.add(event)
    db.commit()
    
    return {
        "status": "STARTED",
        "attempt_id": new_attempt.id,
        "config": {
            "duration": test.duration_minutes or 120,
            "mode": "STRICT_SIMULATION",
            "is_pausable": False
        }
    }

@router.post("/{attempt_id}/heartbeat")
async def simulation_heartbeat(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Verify the simulation is still valid
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == current_user.id).first()
    if not attempt or not attempt.is_simulation:
        raise HTTPException(status_code=403, detail="Invalid simulation session")
    
    # Check if time exceeded
    test = db.query(Test).filter(Test.id == attempt.test_id).first()
    duration = test.duration_minutes or 120
    elapsed = (datetime.now(timezone.utc) - attempt.start_time.replace(tzinfo=timezone.utc)).total_seconds() / 60
    
    if elapsed > duration + 5: # 5 min grace for network
        attempt.status = AttemptStatusEnum.COMPLETED
        db.commit()
        return {"status": "AUTO_TERMINATED", "reason": "TIME_EXCEEDED"}
        
    return {"status": "ACTIVE", "elapsed_minutes": round(elapsed, 2)}
