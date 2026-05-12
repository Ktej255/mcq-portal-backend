from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any
from app.db.session import get_db
from app.models.domain import User, Attempt, AttemptStatusEnum, Report, Test
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.services.recommendation_service import get_personalized_recommendations

router = APIRouter()

@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    # Total tests taken
    total_tests = db.query(Attempt).filter(Attempt.user_id == current_user.id, Attempt.status == AttemptStatusEnum.SUBMITTED).count()
    
    # Average score
    avg_score_query = db.query(func.avg(Report.total_score)).join(Attempt).filter(Attempt.user_id == current_user.id, Attempt.status == AttemptStatusEnum.SUBMITTED).scalar()
    avg_score = round(avg_score_query, 2) if avg_score_query else 0.0
    
    # Recent tests
    recent_attempts = db.query(Attempt).filter(Attempt.user_id == current_user.id, Attempt.status == AttemptStatusEnum.SUBMITTED)\
        .order_by(Attempt.end_time.desc()).limit(5).all()
        
    recent_tests = []
    for att in recent_attempts:
        report = db.query(Report).filter(Report.attempt_id == att.id).first()
        max_score = len(att.answers) * att.test.correct_marks if att.answers else 0 # Simplified
        recent_tests.append({
            "attemptId": str(att.id),
            "testTitle": att.test.title,
            "score": report.total_score if report else 0,
            "maxScore": max_score,
            "date": att.end_time.isoformat() if att.end_time else att.start_time.isoformat()
        })
        
    data = {
        "totalTestsTaken": total_tests,
        "averageScore": avg_score,
        "recentTests": recent_tests
    }
    return StandardResponse(success=True, message="Dashboard summary retrieved", data=data)

@router.get("/recommendations")
def get_dashboard_recommendations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    recs = get_personalized_recommendations(db, current_user.id)
    return StandardResponse(success=True, message="Recommendations retrieved", data=recs)
