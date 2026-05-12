from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any
from app.db.session import get_db
from app.models.domain import User, Attempt, AttemptStatusEnum, Report
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse

router = APIRouter()

from app.services import report_service

@router.get("/aggregate")
def get_aggregate_report(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    # This would aggregate multiple reports
    data = {
        "subjectScores": [{"subject": "Polity", "score": 85}, {"subject": "History", "score": 72}],
        "confidenceAnalytics": [],
        "scoreTrends": []
    }
    return StandardResponse(success=True, message="Aggregate report retrieved", data=data)

@router.get("/{attempt_id}")
def get_attempt_report(attempt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    report = report_service.generate_report(db=db, attempt_id=attempt_id, user_id=current_user.id)
    
    # Format for frontend PerformanceReport
    data = {
        "totalScore": report.total_score,
        "accuracy": report.accuracy,
        "correctCount": report.correct_count,
        "incorrectCount": report.incorrect_count,
        "unattemptedCount": report.unattempted_count,
        "topicWiseAnalysis": report.topic_wise_analysis,
        "confidenceAnalytics": [
            {"level": k, "accuracy": (v["correct"] / v["total"] * 100) if v["total"] > 0 else 0, "count": v["total"]}
            for k, v in (report.confidence_analysis or {}).items()
        ],
        "subjectScores": [
            {"subject": k, "score": (v["correct"] / v["total"] * 100) if v["total"] > 0 else 0}
            for k, v in getattr(report, "subject_wise_performance", {}).items()
        ],
        "averageTimePerQuestion": getattr(report, "average_time_per_question", 0),
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
