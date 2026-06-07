from pydantic import BaseModel, ConfigDict
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

class JobExecutionSchema(BaseModel):
    id: int
    job_name: str
    job_type: str
    reference_id: Optional[str] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    retries: int
    error_payload: Optional[Dict[str, Any]] = None
    metadata_payload: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class MetricSchema(BaseModel):
    id: int
    metric_type: str
    value: float
    metadata_json: Optional[Dict[str, Any]] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class JobListResponse(BaseModel):
    jobs: List[JobExecutionSchema]
    total: int

class MetricListResponse(BaseModel):
    metrics: List[MetricSchema]
    total: int
