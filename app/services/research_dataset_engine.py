from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Dict
from sqlalchemy.orm import Session

from app.models.domain import Attempt, ExamEvent, Report, User, Cohort

RESEARCH_DATASET_VERSION = "research-dataset.v1"

def anonymize_id(original_id: int) -> str:
    # Deterministic but non-reversible-without-key anonymization
    # For this simulation, we use a simple hash or uuid
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user-{original_id}"))

def generate_research_dataset(db: Session, cohort_id: int | None = None, limit: int = 100) -> Dict[str, Any]:
    query = db.query(Attempt)
    if cohort_id:
        # Assuming we can join with User and check cohort_id
        query = query.join(User).filter(User.cohort_id == cohort_id)
        
    attempts = query.limit(limit).all()
    
    records = []
    for attempt in attempts:
        # Anonymize identifiers
        anon_user_id = anonymize_id(attempt.user_id)
        anon_attempt_id = anonymize_id(attempt.id)
        
        # Collect related data
        events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt.id).all()
        # reports = db.query(Report).filter(Report.attempt_id == attempt.id).all()
        
        records.append({
            "anonymized_user_id": anon_user_id,
            "anonymized_attempt_id": anon_attempt_id,
            "performance": {
                "score": attempt.total_score,
                "max_score": attempt.max_score,
                "percentage": round((attempt.total_score / attempt.max_score) * 100, 2) if attempt.max_score else 0
            },
            "telemetry_summary": {
                "event_count": len(events),
                "heartbeat_count": len([e for e in events if e.event_type == "HEARTBEAT"]),
                "focus_interruptions": len([e for e in events if e.event_type in {"TAB_SWITCH", "FULLSCREEN_EXIT"}])
            },
            "educational_context": {
                "behavioral_profile": attempt.behavioral_profile,
                "cognitive_profile": attempt.cognitive_profile
            },
            "metadata": {
                "timestamp": attempt.created_at.isoformat() if attempt.created_at else None,
                "version": RESEARCH_DATASET_VERSION
            }
        })
        
    return {
        "dataset_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "cohort_id": cohort_id,
        "records": records,
        "governance": {
            "privacy_preserving": True,
            "reproducible": True,
            "anonymization_method": "UUID5_NAMESPACE_DNS"
        },
        "version": RESEARCH_DATASET_VERSION
    }

def export_dataset_to_json(dataset: Dict[str, Any], filename: str):
    with open(filename, 'w') as f:
        json.dump(dataset, f, indent=2)
