import uuid
import time
from datetime import datetime, timezone
from typing import Optional, Any, Dict
from sqlalchemy.orm import Session
from app.models.domain import ExecutionTrace

class ExecutionTracer:
    def __init__(self, db: Session):
        self.db = db
        self.current_trace_id: Optional[str] = None
        self.parent_trace_id: Optional[str] = None

    def start_trace(self, 
                    module_name: str, 
                    function_name: str, 
                    user_id: Optional[int] = None, 
                    attempt_id: Optional[int] = None,
                    input_payload: Optional[Dict] = None,
                    parent_id: Optional[str] = None) -> str:
        
        trace_id = str(uuid.uuid4())
        self.current_trace_id = trace_id
        self.parent_trace_id = parent_id
        
        trace = ExecutionTrace(
            trace_id=trace_id,
            parent_trace_id=parent_id,
            user_id=user_id,
            attempt_id=attempt_id,
            module_name=module_name,
            function_name=function_name,
            input_payload=input_payload,
            status="STARTED",
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(trace)
        self.db.commit()
        return trace_id

    def complete_trace(self, trace_id: str, output_payload: Optional[Dict] = None, duration_ms: Optional[float] = None):
        trace = self.db.query(ExecutionTrace).filter(ExecutionTrace.trace_id == trace_id).first()
        if trace:
            trace.output_payload = output_payload
            trace.status = "COMPLETED"
            trace.duration_ms = duration_ms
            self.db.commit()

    def fail_trace(self, trace_id: str, error_message: str, duration_ms: Optional[float] = None):
        trace = self.db.query(ExecutionTrace).filter(ExecutionTrace.trace_id == trace_id).first()
        if trace:
            trace.status = "FAILED"
            trace.error_message = error_message
            trace.duration_ms = duration_ms
            self.db.commit()

# Context manager for easier tracing
class trace_execution:
    def __init__(self, db: Session, module: str, function: str, **kwargs):
        self.db = db
        self.module = module
        self.function = function
        self.kwargs = kwargs
        self.tracer = ExecutionTracer(db)
        self.trace_id = None
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        self.trace_id = self.tracer.start_trace(
            self.module, 
            self.function, 
            **self.kwargs
        )
        return self.trace_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self.start_time) * 1000
        if exc_type:
            self.tracer.fail_trace(self.trace_id, str(exc_val), duration)
        else:
            self.tracer.complete_trace(self.trace_id, duration_ms=duration)
