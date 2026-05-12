from __future__ import annotations

from typing import Any
from statistics import mean, pstdev
from sqlalchemy.orm import Session
from app.models.domain import Attempt

DRIFT_DETECTION_VERSION = "drift-detection.v1"

def detect_scoring_drift(db: Session, window_size: int = 100) -> dict[str, Any]:
    # Compare recent scoring distribution with historical baseline
    recent_attempts = db.query(Attempt.total_score).order_by(Attempt.created_at.desc()).limit(window_size).all()
    historical_attempts = db.query(Attempt.total_score).order_by(Attempt.created_at.asc()).limit(window_size).all()
    
    recent_scores = [a[0] for a in recent_attempts if a[0] is not None]
    hist_scores = [a[0] for a in historical_attempts if a[0] is not None]
    
    if not recent_scores or not hist_scores:
        return {"status": "INSUFFICIENT_DATA"}
        
    recent_avg = mean(recent_scores)
    hist_avg = mean(hist_scores)
    
    drift = recent_avg - hist_avg
    is_drifting = abs(drift) > (pstdev(hist_scores) * 0.5) if len(hist_scores) > 1 else False
    
    return {
        "is_drifting": is_drifting,
        "recent_avg": round(recent_avg, 4),
        "historical_avg": round(hist_avg, 4),
        "drift_magnitude": round(drift, 4),
        "notes": "Scoring distribution is shifting significantly." if is_drifting else "Scoring distribution is stable."
    }

def detect_confidence_inflation(db: Session, limit: int = 100) -> dict[str, Any]:
    # Check if user-reported confidence is drifting away from actual performance
    attempts = db.query(Attempt).filter(Attempt.behavioral_profile != None).limit(limit).all()
    
    diffs = []
    for a in attempts:
        profile = a.behavioral_profile or {}
        confidence = profile.get("reported_confidence", 0)
        performance = (a.total_score or 0) / (a.max_score or 1)
        diffs.append(confidence - performance)
        
    if not diffs:
        return {"status": "INSUFFICIENT_DATA"}
        
    avg_diff = mean(diffs)
    inflation_detected = avg_diff > 0.3
    
    return {
        "inflation_detected": inflation_detected,
        "average_confidence_performance_gap": round(avg_diff, 4),
        "metric_version": DRIFT_DETECTION_VERSION
    }

def production_drift_analysis(db: Session) -> dict[str, Any]:
    score_drift = detect_scoring_drift(db)
    conf_inflation = detect_confidence_inflation(db)
    
    return {
        "scoring_drift": score_drift,
        "confidence_inflation": conf_inflation,
        "overall_stability_rating": "STABLE" if not (score_drift.get("is_drifting") or conf_inflation.get("inflation_detected")) else "STABLE_WITH_DRIFT",
        "metric_version": DRIFT_DETECTION_VERSION
    }
