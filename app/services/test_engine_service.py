from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timezone
from app.models.domain import Test, Attempt, AttemptStatusEnum, Question, AttemptAnswer, Topic, Subject, Report
from app.schemas.test_engine import StartAttemptRequest, SaveAnswerRequest
from app.services.domain_contracts import normalize_option_id

def start_attempt(db: Session, user_id: int, request: StartAttemptRequest) -> Attempt:
    test = db.query(Test).filter(Test.id == request.test_id, Test.is_active == True).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found or inactive")
    
    # Check if an in-progress attempt already exists
    existing_attempt = db.query(Attempt).filter(
        Attempt.user_id == user_id, 
        Attempt.test_id == request.test_id,
        Attempt.status == AttemptStatusEnum.IN_PROGRESS
    ).first()
    
    if existing_attempt:
        return existing_attempt

    attempt = Attempt(
        user_id=user_id,
        test_id=request.test_id,
        status=AttemptStatusEnum.IN_PROGRESS
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt

def get_attempt_questions(db: Session, attempt_id: int, user_id: int):
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == user_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
        
    questions = db.query(Question, Topic.name.label("topic_name"), Subject.id.label("subject_id"), Subject.name.label("subject_name"))\
        .join(Topic, Question.topic_id == Topic.id)\
        .join(Subject, Topic.subject_id == Subject.id)\
        .filter(Question.test_id == attempt.test_id).all()
        
    result = []
    for idx, (q, topic_name, subject_id, subject_name) in enumerate(questions):
        result.append({
            "id": q.id,
            "test_id": q.test_id,
            "topic_id": q.topic_id,
            "subject_id": subject_id,
            "topic_name": topic_name,
            "subject_name": subject_name,
            "text_en": q.text_en,
            "text_hi": q.text_hi,
            "options_en": q.options_en,
            "options_hi": q.options_hi,
            "difficulty": q.difficulty,
            "question_number": idx + 1
        })
    return result

def save_answer(db: Session, attempt_id: int, user_id: int, request: SaveAnswerRequest):
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == user_id).first()
    if not attempt or attempt.status != AttemptStatusEnum.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="Attempt not valid or already submitted")
        
    # Check timer (optional strict check, could also be done on submit)
    # if attempt.start_time + attempt.test.duration_minutes < now...
    
    selected_option = normalize_option_id(request.selected_option)

    answer = db.query(AttemptAnswer).filter(
        AttemptAnswer.attempt_id == attempt_id,
        AttemptAnswer.question_id == request.question_id
    ).first()
    
    if answer:
        if answer.selected_option != selected_option:
            answer.is_changed = True
        answer.selected_option = selected_option
        answer.time_taken_seconds = request.time_taken_seconds
        answer.confidence_level = request.confidence_level
        answer.is_skipped = request.is_skipped
        answer.marked_for_review = request.marked_for_review
    else:
        answer = AttemptAnswer(
            attempt_id=attempt_id,
            question_id=request.question_id,
            selected_option=selected_option,
            time_taken_seconds=request.time_taken_seconds,
            confidence_level=request.confidence_level,
            is_skipped=request.is_skipped,
            marked_for_review=request.marked_for_review
        )
        db.add(answer)
        
    db.commit()
    return True
