from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.models.domain import ExecutionTrace, User, RoleEnum, JobExecutionRegistry, OperationalMetric
from app.schemas.observability import (
    TraceListResponse, TraceDetail, TraceTreeNode, 
    JobListResponse, MetricListResponse
)
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

@router.get("/attempts/{attempt_id}/reconciliation")
def get_attempt_reconciliation(attempt_id: int, db: Session = Depends(get_db)):
    """
    Priority 1 + Priority 3: Founder Forensic Inspector.
    Returns the full reconciliation report:
      - event-reconstructed answers
      - stored DB answers
      - any divergences (FORENSIC_DIVERGENCE)
    """
    from app.services.attempt_reconciliation_engine import AttemptReconciliationEngine
    from dataclasses import asdict
    rec = AttemptReconciliationEngine.reconcile(db, attempt_id)
    reconstructed = AttemptReconciliationEngine.reconstruct_from_events(db, attempt_id)
    return {
        "attempt_id": attempt_id,
        "status": rec.status,
        "summary": rec.summary,
        "total_questions": rec.total_questions,
        "reconstructed_answered": rec.reconstructed_answered,
        "reconstructed_skipped": rec.reconstructed_skipped,
        "stored_answered": rec.stored_answered,
        "stored_skipped": rec.stored_skipped,
        "divergences": rec.divergences,
        "reconstructed_answers": [
            {
                "question_id": r.question_id,
                "final_option": r.final_option,
                "revision_count": r.revision_count,
                "time_seconds": r.time_seconds,
                "first_set_at": r.first_set_at.isoformat() if r.first_set_at else None,
                "last_set_at": r.last_set_at.isoformat() if r.last_set_at else None,
            }
            for r in reconstructed.values()
        ],
    }

@router.get("/health")
def operational_health_check(db: Session = Depends(get_db)):
    """
    Priority 9: Founder operational health check.
    Runs all alert detectors and returns current system health status.
    """
    from app.services.operational_alert_service import run_operational_health_check
    return run_operational_health_check(db)

@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
):
    query = db.query(JobExecutionRegistry)
    if status:
        query = query.filter(JobExecutionRegistry.status == status)
    
    total = query.count()
    jobs = query.order_by(JobExecutionRegistry.started_at.desc()).offset(offset).limit(limit).all()
    
    return {"jobs": jobs, "total": total}

@router.get("/metrics", response_model=MetricListResponse)
def list_metrics(
    db: Session = Depends(get_db),
    limit: int = 100,
    metric_type: Optional[str] = None
):
    query = db.query(OperationalMetric)
    if metric_type:
        query = query.filter(OperationalMetric.metric_type == metric_type)
    
    total = query.count()
    metrics = query.order_by(OperationalMetric.timestamp.desc()).limit(limit).all()
    
    return {"metrics": metrics, "total": total}
    
@router.post("/metrics/snapshot")
def record_metrics_snapshot(db: Session = Depends(get_db)):
    """
    Priority 10: Manual trigger for operational maturity monitoring.
    Snapshots current system health into persistent metrics.
    """
    from app.services.observability import observability_service
    observability_service.record_operational_metrics(db)
    return {"success": True, "message": "Metrics snapshot recorded"}

@router.get("/governance/graph")
def get_governance_graph():
    """
    Institutional Stabilization: Serves the Graphify dependency graph.
    """
    import os
    import json
    graph_path = "docs/governance/graph/graph_data.json"
    if os.path.exists(graph_path):
        with open(graph_path, "r") as f:
            return json.load(f)
    
    return {
        "nodes": [
            {"id": "scoring", "label": "Scoring Engine", "type": "SERVICE", "ownership": "Chat #2", "risk": "CRITICAL"},
            {"id": "report", "label": "Report Service", "type": "SERVICE", "ownership": "Chat #2", "risk": "CRITICAL"},
            {"id": "attempts", "label": "Attempt API", "type": "API", "ownership": "Chat #2", "risk": "HIGH"},
            {"id": "revision", "label": "Revision Service", "type": "SERVICE", "ownership": "Chat #1", "risk": "MEDIUM"},
            {"id": "db", "label": "PostgreSQL", "type": "DATABASE", "ownership": "INFRA", "risk": "CRITICAL"},
        ],
        "edges": [
            {"from": "attempts", "to": "scoring"},
            {"from": "scoring", "to": "report"},
            {"from": "report", "to": "db"},
            {"from": "report", "to": "revision"},
        ]
    }

@router.get("/governance/timeline")
def get_mutation_timeline():
    """
    Autonomous Governance: Parses SYSTEM_STATE.md to return a chronological mutation history.
    """
    import os
    import re
    state_path = "docs/governance/graph/SYSTEM_STATE.md"
    if not os.path.exists(state_path):
        return {"mutations": []}
    
    with open(state_path, "r") as f:
        content = f.read()
    
    # Simple regex parser for Markdown blocks
    mutations = []
    blocks = re.split(r"### Mutation:", content)
    for block in blocks[1:]: # Skip preamble
        lines = block.strip().split("\n")
        timestamp = lines[0].strip()
        
        mutation = {"timestamp": timestamp}
        for line in lines[1:]:
            if "- **Agent**:" in line: mutation["agent"] = line.split(":", 1)[1].strip()
            if "- **Files**:" in line: mutation["files"] = [f.strip() for f in line.split(":", 1)[1].split(",")]
            if "- **Justification**:" in line: mutation["justification"] = line.split(":", 1)[1].strip()
            if "- **Risk**:" in line: mutation["risk"] = line.split(":", 1)[1].strip()
            if "- **Status**:" in line: mutation["status"] = line.split(":", 1)[1].strip()
        
        mutations.append(mutation)
        
    return {"mutations": mutations[::-1]} # Return newest first
