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

@router.get("/traces/{trace_id}", response_model=TraceDetail)
def get_trace_detail(trace_id: str, db: Session = Depends(get_db)):
    trace = db.query(ExecutionTrace).filter(ExecutionTrace.trace_id == trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
