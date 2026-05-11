from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.test_engine import (
    StartAttemptRequest, StartAttemptResponse, QuestionResponse, 
    SaveAnswerRequest, SaveAnswerResponse, ReportResponse
)
from app.schemas.common import StandardResponse
from app.services.test_engine_service import start_attempt, get_attempt_questions, save_answer
from app.services.report_service import generate_report

router = APIRouter()

@router.post("/start", response_model=StandardResponse[StartAttemptResponse])
def start_test_attempt(
    request: StartAttemptRequest, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    attempt = start_attempt(db, current_user.id, request)
    return StandardResponse(success=True, message="Attempt started successfully", data={
        "attempt_id": attempt.id,
        "test": attempt.test,
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
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    report = generate_report(db, attempt_id, current_user.id)
    return StandardResponse(success=True, message="Test submitted and report generated successfully", data=report)
