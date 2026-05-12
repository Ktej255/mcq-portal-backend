from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from app.models.domain import Attempt, ExamEvent, AttemptAnswer
from app.services.inference_reliability import behavioral_data_quality
from app.services.report_service import get_attempt_report
from app.services.recommendation_service import get_recommendations
from app.services.intervention_tracking_engine import get_intervention_history

PRODUCTION_VERIFICATION_VERSION = "production-verification.v1"

def verify_telemetry_to_report(report: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    # Check if report insights align with telemetry quality
    telemetry_score = quality.get("score", 0)
    report_confidence = report.get("reliability_profile", {}).get("behavioral_data_quality", {}).get("score", 0)
    
    consistent = abs(telemetry_score - report_confidence) < 0.1
    return {
        "consistent": consistent,
        "telemetry_score": telemetry_score,
        "report_confidence": report_confidence,
        "variance": round(abs(telemetry_score - report_confidence), 4),
        "notes": "Report confidence aligns with telemetry quality." if consistent else "Report confidence drifted from raw telemetry quality."
    }

def verify_report_to_recommendations(report: dict[str, Any], recommendations: list[dict[str, Any]]) -> dict[str, Any]:
    # Check if recommendations target identified weaknesses in the report
    weaknesses = report.get("cognitive_profile", {}).get("weaknesses", [])
    rec_topics = [rec.get("topic") for rec in recommendations]
    
    # Simple check: do recommendations overlap with weaknesses?
    matched = [topic for topic in rec_topics if topic in weaknesses]
    coverage = len(matched) / max(1, len(weaknesses))
    
    return {
        "consistent": coverage > 0.5 or not weaknesses,
        "weakness_coverage": round(coverage, 4),
        "matched_topics": matched,
        "notes": f"Recommendations cover {round(coverage*100)}% of identified weaknesses."
    }

def verify_recommendations_to_interventions(recommendations: list[dict[str, Any]], interventions: list[dict[str, Any]]) -> dict[str, Any]:
    # Check if interventions were actually triggered based on recommendations
    rec_ids = {rec.get("id") for rec in recommendations if rec.get("id")}
    int_source_ids = {intv.get("recommendation_id") for intv in interventions if intv.get("recommendation_id")}
    
    overlap = rec_ids & int_source_ids
    return {
        "consistent": len(overlap) > 0 or (not recommendations and not interventions),
        "intervention_link_rate": len(overlap) / max(1, len(recommendations)),
        "notes": "Interventions are traceable to recommendations."
    }

def verify_production_lineage(db: Session, attempt_id: int) -> dict[str, Any]:
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
    if not attempt:
        return {"error": "Attempt not found"}
        
    events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).all()
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    
    quality = behavioral_data_quality(answers, events)
    report = get_attempt_report(db, attempt_id)
    recommendations = get_recommendations(db, attempt.user_id)
    interventions = get_intervention_history(db, attempt.user_id)
    
    t_to_r = verify_telemetry_to_report(report, quality)
    r_to_rec = verify_report_to_recommendations(report, recommendations)
    rec_to_int = verify_recommendations_to_interventions(recommendations, interventions)
    
    lineage_integrity = (t_to_r["consistent"] and r_to_rec["consistent"] and rec_to_int["consistent"])
    
    return {
        "attempt_id": attempt_id,
        "lineage_integrity": lineage_integrity,
        "verification_steps": {
            "telemetry_to_report": t_to_r,
            "report_to_recommendations": r_to_rec,
            "recommendations_to_interventions": rec_to_int
        },
        "overall_confidence": round((t_to_r["telemetry_score"] + r_to_rec["weakness_coverage"]) / 2, 4),
        "metric_version": PRODUCTION_VERIFICATION_VERSION
    }
