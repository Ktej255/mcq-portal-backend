from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Dict, Any

class TraceBase(BaseModel):
    trace_id: str
    parent_trace_id: Optional[str] = None
    module_name: str
    function_name: str
    status: str
    duration_ms: Optional[float] = None
    created_at: datetime

class TraceDetail(TraceBase):
    user_id: Optional[int] = None
    attempt_id: Optional[int] = None
    input_payload: Optional[Dict[str, Any]] = None
    output_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    provider_metadata: Optional[Dict[str, Any]] = None

class TraceTreeNode(TraceDetail):
    children: List["TraceTreeNode"] = []

class TraceListResponse(BaseModel):
    traces: List[TraceDetail]
    total: int
