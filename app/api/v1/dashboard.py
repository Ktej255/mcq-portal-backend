from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any
from app.db.session import get_db
from app.models.domain import User, Attempt, AttemptStatusEnum, Report, Test
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.services.recommendation_service import get_personalized_recommendations
from app.services.student_longitudinal_profile import build_student_longitudinal_profile

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

@router.get("/evolution")
def get_dashboard_evolution(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    """Learning-evolution signals computed from the student's own attempt history.

    Delegates to the real longitudinal profile (derived from submitted reports);
    a student with no history honestly gets zeroed slopes/stability rather than
    fabricated numbers.
    """
    profile = build_student_longitudinal_profile(db, current_user.id)
    return StandardResponse(success=True, message="Evolution retrieved", data={
        "attempt_count": profile["attempt_count"],
        "learning_velocity": profile["learning_velocity"],
        "behavioral_stability": profile["behavioral_stability"],
        "longitudinal_reliability": profile["longitudinal_reliability"],
    })

@router.get("/export-journey")
async def export_journey(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compile the student's real journey data for export (student sovereignty).

    ``total_attempts`` and ``mastery_trend`` are computed from the student's own
    submitted attempts/reports — never fabricated. With fewer than two attempts
    the trend is honestly reported as ``INSUFFICIENT_DATA``.
    """
    total_attempts = (
        db.query(Attempt)
        .filter(Attempt.user_id == current_user.id, Attempt.status == AttemptStatusEnum.SUBMITTED)
        .count()
    )

    if total_attempts < 2:
        mastery_trend = "INSUFFICIENT_DATA"
    else:
        slope = build_student_longitudinal_profile(db, current_user.id)["learning_velocity"]["accuracy_slope"]
        if slope > 0.5:
            mastery_trend = "UPWARD"
        elif slope < -0.5:
            mastery_trend = "DOWNWARD"
        else:
            mastery_trend = "STABLE"

    return StandardResponse(success=True, message="Journey data compiled", data={
        "user_id": current_user.id,
        "total_attempts": total_attempts,
        "mastery_trend": mastery_trend,
        "export_ready": True
    })

