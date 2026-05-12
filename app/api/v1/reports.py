from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any
from app.db.session import get_db
from app.models.domain import User, Attempt, AttemptStatusEnum, Report
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse

router = APIRouter()

@router.get("/aggregate")
def get_aggregate_report(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    # Dummy implementation for aggregate report
    data = {
        "subjectScores": [{"subject": "General Knowledge", "score": 80, "total": 100}],
        "confidenceAnalytics": [{"level": "HUNDRED_PERCENT", "accuracy": 90, "count": 10}],
        "scoreTrends": [{"date": "2026-05-10", "score": 80}]
    }
    return StandardResponse(success=True, message="Aggregate report retrieved", data=data)

@router.get("/{attempt_id}")
def get_attempt_report(attempt_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == current_user.id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
        
    report = db.query(Report).filter(Report.attempt_id == attempt_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
        
    # Dummy implementation matching PerformanceReport interface
    data = {
        "subjectScores": [{"subject": attempt.test.subject.name, "score": report.total_score, "total": len(attempt.test.questions) * attempt.test.correct_marks}],
        "confidenceAnalytics": report.confidence_analysis or [],
        "scoreTrends": []
    }
    return StandardResponse(success=True, message="Report retrieved", data=data)
