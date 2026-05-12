from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.test_engine import (
    StartAttemptRequest, StartAttemptResponse, QuestionResponse, 
    SaveAnswerRequest, SaveAnswerResponse, ReportResponse, HistoryItemResponse,
    EventBatchRequest
)
from app.schemas.common import StandardResponse
from app.services.test_engine_service import start_attempt, get_attempt_questions, save_answer
from app.services.report_service import generate_report
from app.services.event_auditor import event_auditor
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/history", response_model=StandardResponse[List[HistoryItemResponse]])
def get_attempt_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.domain import Attempt, Report
    attempts = db.query(Attempt).filter(Attempt.user_id == current_user.id).order_by(Attempt.start_time.desc()).all()
    result = []
    for att in attempts:
        report = db.query(Report).filter(Report.attempt_id == att.id).first()
        
        # Defensive check for test existence
        test_title = att.test.title if att.test else "Unknown Test"
        correct_marks = att.test.correct_marks if att.test else 1.0
        
        # Calculate max score based on number of answers provided vs questions
        # For a more accurate maxScore, we should use the total questions in the test
        max_questions = len(att.test.questions) if att.test and att.test.questions else len(att.answers)
        max_score = max_questions * correct_marks
        
        accuracy_val = report.accuracy if report and report.accuracy is not None else 0.0
        accuracy_str = f"{accuracy_val:.1f}%"
        
        result.append({
            "attemptId": str(att.id),
            "title": test_title,
            "date": att.start_time.isoformat(),
            "status": att.status.value,
            "score": report.total_score if report else None,
            "maxScore": max_score,
            "accuracy": accuracy_str
        })
    return StandardResponse(success=True, message="History retrieved", data=result)

@router.post("/start", response_model=StandardResponse[StartAttemptResponse])
def start_test_attempt(
    request: StartAttemptRequest, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    attempt = start_attempt(db, current_user.id, request)
    test = attempt.test
    return StandardResponse(success=True, message="Attempt started successfully", data={
        "attempt_id": attempt.id,
        "test": {
            "id": test.id,
            "title": test.title,
            "description": test.description,
            "duration_minutes": test.duration_minutes,
            "correct_marks": test.correct_marks,
            "negative_marking_value": test.negative_marking_value,
            "total_questions": len(test.questions) if test.questions else None,
        },
        "start_time": attempt.start_time,
        "status": attempt.status
    })

@router.get("/{attempt_id}/questions", response_model=StandardResponse[List[QuestionResponse]])
def fetch_questions(
    attempt_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    questions = get_attempt_questions(db, attempt_id, current_user.id)
    return StandardResponse(success=True, message="Questions retrieved successfully", data=questions)

@router.put("/{attempt_id}/answers", response_model=StandardResponse[SaveAnswerResponse])
def save_test_answer(
    attempt_id: int, 
    request: SaveAnswerRequest, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    success = save_answer(db, attempt_id, current_user.id, request)
    return StandardResponse(success=True, message="Answer saved successfully", data={"success": success, "message": "Answer saved successfully"})

@router.post("/{attempt_id}/submit", response_model=StandardResponse[ReportResponse])
def submit_test(
    attempt_id: int, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    from app.services.report_service import generate_report, run_async_cognitive_pipeline
    report = generate_report(db, attempt_id, current_user.id)
    
    # Offload heavy tasks to background
    background_tasks.add_task(run_async_cognitive_pipeline, attempt_id, current_user.id)
    
    return StandardResponse(success=True, message="Test submitted. Primary analysis complete. AI Insight is being generated.", data=report)

@router.post("/{attempt_id}/events", response_model=StandardResponse[dict])
def record_exam_events(
    attempt_id: int,
    request: EventBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.models.domain import ExamEvent, Attempt
    # Verify attempt ownership
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == current_user.id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
        
    # Audit events for integrity
    audit_results = event_auditor.validate_sequence(request.events)
    if not audit_results["is_valid"]:
        logger.warning(f"Event Audit Violations for Attempt {attempt_id}: {audit_results['violations']}")

    db_events = []
    for e in request.events:
        db_events.append(ExamEvent(
            attempt_id=attempt_id,
            event_type=e.event_type,
            question_id=e.question_id,
            payload=e.payload,
            timestamp=e.timestamp or datetime.now(timezone.utc)
        ))
    
    db.add_all(db_events)
    db.commit()
    return StandardResponse(
        success=True, 
        message=f"{len(db_events)} events recorded", 
        data={
            "count": len(db_events),
            "audit": audit_results["audit_summary"]
        }
    )
