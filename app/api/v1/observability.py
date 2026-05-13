from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.models.domain import ExecutionTrace, User, RoleEnum
from app.schemas.observability import TraceListResponse, TraceDetail, TraceTreeNode
from app.api.v1.auth import get_current_user # Assuming standard auth exists

router = APIRouter()

@router.get("/traces", response_model=TraceListResponse)
def list_traces(
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    module: Optional[str] = None,
    status: Optional[str] = None
):
    query = db.query(ExecutionTrace)
    if module:
        query = query.filter(ExecutionTrace.module_name == module)
    if status:
        query = query.filter(ExecutionTrace.status == status)
    
    total = query.count()
    traces = query.order_by(ExecutionTrace.created_at.desc()).offset(offset).limit(limit).all()
    
    return {"traces": traces, "total": total}

@router.get("/traces/{trace_id}/tree", response_model=TraceTreeNode)
def get_trace_tree(trace_id: str, db: Session = Depends(get_db)):
    # Find the root or a specific trace
    root_trace = db.query(ExecutionTrace).filter(ExecutionTrace.trace_id == trace_id).first()
    if not root_trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    # Simple recursive builder (for real production, we might use a single query with parent_id)
    def build_tree(trace):
        node = TraceTreeNode(**trace.__dict__)
        children = db.query(ExecutionTrace).filter(ExecutionTrace.parent_trace_id == trace.trace_id).all()
        node.children = [build_tree(c) for c in children]
        return node
        
    return build_tree(root_trace)

@router.get("/attempts/{attempt_id}/behavioral-replay")
def get_behavioral_replay(attempt_id: int, db: Session = Depends(get_db)):
    """
    Returns a sequence of exam events for behavioral playback.
    """
    from app.models.domain import ExamEvent, Attempt
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
        
    events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).order_by(ExamEvent.timestamp.asc()).all()
    
    # Enrich events with question numbering for replay clarity
    replay_events = []
    for event in events:
        evt_dict = {
            "type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "question_id": event.question_id,
            "metadata": event.event_metadata,
        }
        replay_events.append(evt_dict)
        
    return {
        "attempt_id": attempt_id,
        "user_id": attempt.user_id,
        "test_id": attempt.test_id,
        "event_timeline": replay_events
    }

@router.get("/attempts/{attempt_id}/event-cinema")
def get_event_cinema(attempt_id: int, db: Session = Depends(get_db)):
    """
    Priority 4: Founder Event Timeline — Cinema-style educational timeline.
    Returns every system + behavioral event for a single attempt in chronological order.
    """
    from app.services.event_cinema_service import EventCinemaService
    timeline = EventCinemaService.get_educational_timeline(db, attempt_id)
    if not timeline:
        raise HTTPException(status_code=404, detail="No events found for this attempt")
    return {
        "attempt_id": attempt_id,
        "total_events": len(timeline),
        "timeline": timeline
    }
