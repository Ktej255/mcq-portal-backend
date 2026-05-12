from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Any
from app.db.session import get_db
from app.models.domain import Test, Question, Topic, Subject, User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse

router = APIRouter()

@router.get("/available")
def get_available_tests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    tests = db.query(Test).filter(Test.is_active == True).all()
    result = []
    for test in tests:
        # Get subjects for the test
        subjects = db.query(Subject.name).join(Topic).join(Question).filter(Question.test_id == test.id).distinct().all()
        total_questions = db.query(Question).filter(Question.test_id == test.id).count()
        result.append({
            "id": str(test.id),
            "title": test.title,
            "description": test.description,
            "durationMinutes": test.duration_minutes,
            "totalQuestions": total_questions,
            "subjects": [s[0] for s in subjects]
        })
    return StandardResponse(success=True, message="Tests retrieved successfully", data=result)

@router.get("/{test_id}")
def get_test(test_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    test = db.query(Test).filter(Test.id == test_id, Test.is_active == True).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    
    subjects = db.query(Subject.name).join(Topic).join(Question).filter(Question.test_id == test.id).distinct().all()
    total_questions = db.query(Question).filter(Question.test_id == test.id).count()
    
    data = {
        "id": str(test.id),
        "title": test.title,
        "description": test.description,
        "durationMinutes": test.duration_minutes,
        "totalQuestions": total_questions,
        "subjects": [s[0] for s in subjects]
    }
    return StandardResponse(success=True, message="Test retrieved successfully", data=data)

@router.get("/{test_id}/questions")
def get_test_questions(test_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    questions = db.query(Question, Topic.name.label("topic_name"), Subject.name.label("subject_name"))\
        .join(Topic, Question.topic_id == Topic.id)\
        .join(Subject, Topic.subject_id == Subject.id)\
        .filter(Question.test_id == test_id).all()
        
    result = []
    for q, topic_name, subject_name in questions:
        # options_en is stored as a dict: {"A": "text", "B": "text"}
        options = []
        options_en = q.options_en or {}
        options_hi = q.options_hi or {}
        if isinstance(options_en, dict):
            for key, opt_text in options_en.items():
                opt_id = f"{q.id}_opt_{key}"
                text_hi = options_hi.get(key) if isinstance(options_hi, dict) else None
                options.append({
                    "id": opt_id,
                    "textEn": opt_text,
                    "textHi": text_hi
                })
        elif isinstance(options_en, list):
            for idx, opt_text in enumerate(options_en):
                opt_id = f"{q.id}_opt_{idx}"
                text_hi = options_hi[idx] if isinstance(options_hi, list) and idx < len(options_hi) else None
                options.append({
                    "id": opt_id,
                    "textEn": opt_text,
                    "textHi": text_hi
                })
        
        result.append({
            "id": str(q.id),
            "textEn": q.text_en,
            "textHi": q.text_hi,
            "subject": subject_name,
            "topic": topic_name,
            "difficulty": q.difficulty.capitalize() if q.difficulty else "Medium",
            "positiveMarks": q.test.correct_marks,
            "negativeMarks": q.test.negative_marking_value,
            "options": options
        })
    return StandardResponse(success=True, message="Questions retrieved successfully", data=result)
