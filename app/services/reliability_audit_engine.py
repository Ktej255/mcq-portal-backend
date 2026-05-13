from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.domain import ExamEvent, Attempt, AttemptAnswer
from app.core.pedagogy.inference_reliability import behavioral_data_quality
from app.services.schema_integrity import validate_telemetry_schema

RELIABILITY_AUDIT_VERSION = "reliability-audit.v1"

def audit_attempt_reliability(db: Session, attempt_id: int) -> dict[str, Any]:
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
    events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).all()
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    
    anomalies = []
    
    # 1. Schema Inconsistency
    for event in events:
        is_valid, error = validate_telemetry_schema(event.event_type, event.payload or {})
        if not is_valid:
            anomalies.append({
                "type": "SCHEMA_INCONSISTENCY",
                "event_id": event.id,
                "error": error
            })
            
    # 2. Missing Telemetry
    heartbeats = [e for e in events if e.event_type == "HEARTBEAT"]
    if not heartbeats and len(events) > 5:
        anomalies.append({
            "type": "MISSING_TELEMETRY",
            "detail": "Heartbeat events missing despite significant activity."
        })
        
    # 3. Inconsistent Scores
    total_score = sum(a.score_achieved or 0 for a in answers)
    if attempt and abs(total_score - (attempt.total_score or 0)) > 0.01:
        anomalies.append({
            "type": "INCONSISTENT_SCORE",
            "calculated": total_score,
            "stored": attempt.total_score
        })
        
    # 4. Low Confidence Escalation Failures
    quality = behavioral_data_quality(answers, events)
    if quality["score"] < 0.3 and not attempt.requires_review:
        anomalies.append({
            "type": "ESCALATION_FAILURE",
            "detail": "Low reliability attempt not flagged for human review."
        })
        
    return {
        "attempt_id": attempt_id,
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "reliability_score": quality["score"],
        "is_healthy": len(anomalies) == 0,
        "metric_version": RELIABILITY_AUDIT_VERSION
    }

def continuous_operational_audit(db: Session, limit: int = 50) -> dict[str, Any]:
    recent_attempts = db.query(Attempt).order_by(Attempt.created_at.desc()).limit(limit).all()
    results = [audit_attempt_reliability(db, a.id) for a in recent_attempts]
    
    unhealthy_count = len([r for r in results if not r["is_healthy"]])
    return {
        "audit_count": len(results),
        "unhealthy_attempts": unhealthy_count,
        "health_rate": round(1 - (unhealthy_count / max(1, len(results))), 4),
        "top_anomalies": _aggregate_anomalies(results),
        "metric_version": RELIABILITY_AUDIT_VERSION
    }

def _aggregate_anomalies(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {}
    for r in results:
        for a in r["anomalies"]:
            counts[a["type"]] = counts.get(a["type"], 0) + 1
    return counts
