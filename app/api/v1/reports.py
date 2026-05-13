from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any
from app.db.session import get_db
from app.models.domain import User, Attempt, AttemptStatusEnum, Report
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse

router = APIRouter()

from app.services import report_service, student_longitudinal_profile, recommendation_service

@router.get("/evolution")
def get_evolution_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    profile = student_longitudinal_profile.build_student_longitudinal_profile(db, current_user.id)
    return StandardResponse(success=True, message="Evolution profile retrieved", data=profile)

@router.get("/recommendations")
def get_report_recommendations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    recommendations = recommendation_service.get_personalized_recommendations(db, current_user.id)
    return StandardResponse(success=True, message="Recommendations retrieved", data=recommendations)

@router.get("/aggregate")
def get_aggregate_report(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    reports = db.query(Report).join(Attempt).filter(
        Attempt.user_id == current_user.id,
        Attempt.status == AttemptStatusEnum.SUBMITTED
    ).order_by(Report.generated_at.asc()).all()

    if not reports:
        return StandardResponse(success=True, message="No reports found", data={"scoreTrends": []})

    score_trends = [
        {
            "attemptId": str(report.attempt_id),
            "score": report.total_score,
            "accuracy": report.accuracy,
            "generatedAt": report.generated_at.isoformat(),
        }
        for report in reports
    ]
    
    profile = student_longitudinal_profile.build_student_longitudinal_profile(db, current_user.id)
    
    data = {
        "totalScore": reports[-1].total_score,
        "accuracy": reports[-1].accuracy,
        "correctCount": reports[-1].correct_count,
        "incorrectCount": reports[-1].incorrect_count,
        "unattemptedCount": reports[-1].unattempted_count,
        "subjectScores": [],
        "confidenceAnalytics": [],
        "scoreTrends": score_trends,
        "longitudinalProfile": profile,
        "topicMastery": current_user.topic_mastery
    }
    return StandardResponse(success=True, message="Aggregate report retrieved", data=data)

@router.get("/{attempt_id}")
def get_attempt_report(attempt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    report = report_service.generate_report(db=db, attempt_id=attempt_id, user_id=current_user.id)
    
    # Format for frontend PerformanceReport
    data = {
        "attemptId": str(attempt_id),
        "totalScore": report.total_score,
        "total_score": report.total_score,
        "accuracy": report.accuracy,
        "correctCount": report.correct_count,
        "correct_count": report.correct_count,
        "incorrectCount": report.incorrect_count,
        "incorrect_count": report.incorrect_count,
        "unattemptedCount": report.unattempted_count,
        "unattempted_count": report.unattempted_count,
        "topicWiseAnalysis": report.topic_wise_analysis,
        "topic_wise_analysis": report.topic_wise_analysis,
        "confidenceAnalytics": [
            {"level": k, "accuracy": (v["correct"] / v["total"] * 100) if v["total"] > 0 else 0, "count": v["total"]}
            for k, v in (report.confidence_analysis or {}).items()
        ],
        "confidence_analysis": report.confidence_analysis,
        "subjectWisePerformance": report.subject_wise_performance,
        "subject_wise_performance": report.subject_wise_performance,
        "subjectScores": [
            {"subject": k, "score": (v["correct"] / v["total"] * 100) if v["total"] > 0 else 0}
            for k, v in (report.subject_wise_performance or {}).items()
        ],
        "averageTimePerQuestion": report.average_time_per_question or 0,
        "average_time_per_question": report.average_time_per_question or 0,
        "narrative": report.narrative,
        "behavioral_analysis": report.behavioral_analysis,
        "telemetry_summary": report.telemetry_summary,
        "processingStatus": report.processing_status,
        "processing_status": report.processing_status,
        "reliability_score": report.reliability_score,
        "forensic_audit_log": report.forensic_audit_log,
        "truth_status": report.truth_status,           # VERIFIED / FAILED / UNVERIFIED
        "strengths": report.behavioral_analysis.get("strengths", []) if report.behavioral_analysis else [],
        "totalTime": report.telemetry_summary.get("total_time_seconds", 0) if report.telemetry_summary else 0,
        "generatedAt": report.generated_at.isoformat()
    }
    return StandardResponse(success=True, message="Report retrieved", data=data)

@router.get("/{attempt_id}/review")
def get_report_review(attempt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    review_data = report_service.get_detailed_review(db=db, attempt_id=attempt_id, user_id=current_user.id)
    return StandardResponse(success=True, message="Detailed review retrieved", data=review_data)

@router.get("/{attempt_id}/behavior")
def get_behavioral_analysis(attempt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    analysis = report_service.get_behavioral_analysis(db=db, attempt_id=attempt_id, user_id=current_user.id)
    return StandardResponse(success=True, message="Behavioral analysis retrieved", data=analysis)
