from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Any

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_admin
from app.schemas.common import StandardResponse, PaginatedResponse
from app.schemas.admin import (
    SubjectCreate, SubjectUpdate, SubjectOut,
    TopicCreate, TopicUpdate, TopicOut,
    QuestionCreate, QuestionUpdate, QuestionOut, BulkQuestionCreate,
    TestCreate, TestUpdate, TestOut
)
from app.crud import admin as crud_admin
from app.services.observability import observability_service

router = APIRouter()

# --- Subjects ---
@router.post("/subjects", response_model=StandardResponse[SubjectOut])
def create_subject(
    subject_in: SubjectCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    subject = crud_admin.create_subject(db=db, obj_in=subject_in)
    return StandardResponse(success=True, message="Subject created successfully", data=subject)

@router.get("/subjects", response_model=PaginatedResponse[SubjectOut])
def get_subjects(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    subjects = crud_admin.get_subjects(db=db, skip=skip, limit=limit)
    return PaginatedResponse(success=True, message="Subjects retrieved", data=subjects, total=len(subjects), page=skip//limit if limit else 0, size=limit)

@router.put("/subjects/{subject_id}", response_model=StandardResponse[SubjectOut])
def update_subject(
    subject_id: int,
    subject_in: SubjectUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    subject = crud_admin.update_subject(db=db, subject_id=subject_id, obj_in=subject_in)
    return StandardResponse(success=True, message="Subject updated successfully", data=subject)

# --- Topics ---
@router.post("/topics", response_model=StandardResponse[TopicOut])
def create_topic(
    topic_in: TopicCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    topic = crud_admin.create_topic(db=db, obj_in=topic_in)
    return StandardResponse(success=True, message="Topic created successfully", data=topic)

@router.get("/topics", response_model=PaginatedResponse[TopicOut])
def get_topics(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    topics = crud_admin.get_topics(db=db, skip=skip, limit=limit)
    return PaginatedResponse(success=True, message="Topics retrieved", data=topics, total=len(topics), page=skip//limit if limit else 0, size=limit)

@router.put("/topics/{topic_id}", response_model=StandardResponse[TopicOut])
def update_topic(
    topic_id: int,
    topic_in: TopicUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    topic = crud_admin.update_topic(db=db, topic_id=topic_id, obj_in=topic_in)
    return StandardResponse(success=True, message="Topic updated successfully", data=topic)

# --- Questions ---
@router.post("/questions", response_model=StandardResponse[QuestionOut])
def create_question(
    question_in: QuestionCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    question = crud_admin.create_question(db=db, obj_in=question_in)
    return StandardResponse(success=True, message="Question created successfully", data=question)

@router.post("/questions/bulk", response_model=StandardResponse[list[QuestionOut]])
def bulk_create_questions(
    questions_in: BulkQuestionCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    questions = crud_admin.bulk_create_questions(db=db, obj_in=questions_in)
    return StandardResponse(success=True, message=f"{len(questions)} questions created successfully", data=questions)

@router.get("/questions", response_model=PaginatedResponse[QuestionOut])
def get_questions(
    test_id: int = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    questions = crud_admin.get_questions(db=db, test_id=test_id, skip=skip, limit=limit)
    return PaginatedResponse(success=True, message="Questions retrieved", data=questions, total=len(questions), page=skip//limit if limit else 0, size=limit)

@router.put("/questions/{question_id}", response_model=StandardResponse[QuestionOut])
def update_question(
    question_id: int,
    question_in: QuestionUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    question = crud_admin.update_question(db=db, question_id=question_id, obj_in=question_in)
    return StandardResponse(success=True, message="Question updated successfully", data=question)

@router.delete("/questions/{question_id}", response_model=StandardResponse[QuestionOut])
def delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    question = crud_admin.delete_question(db=db, question_id=question_id)
    return StandardResponse(success=True, message="Question deleted successfully", data=question)

# --- Tests ---
@router.post("/tests", response_model=StandardResponse[TestOut])
def create_test(
    test_in: TestCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    test = crud_admin.create_test(db=db, obj_in=test_in)
    return StandardResponse(success=True, message="Test created successfully", data=test)

@router.get("/tests", response_model=PaginatedResponse[TestOut])
def get_tests(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    tests = crud_admin.get_tests(db=db, skip=skip, limit=limit)
    return PaginatedResponse(success=True, message="Tests retrieved", data=tests, total=len(tests), page=skip//limit if limit else 0, size=limit)

@router.put("/tests/{test_id}", response_model=StandardResponse[TestOut])
def update_test(
    test_id: int,
    test_in: TestUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    test = crud_admin.update_test(db=db, test_id=test_id, obj_in=test_in)
    return StandardResponse(success=True, message="Test updated successfully", data=test)

@router.post("/recalibrate-batches")
def recalibrate_batches(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """
    Priority 3: Batch Calibration.
    Recalculates batch difficulty and student alignment based on latest performance data.
    """
    if current_admin.role != 'ADMIN':
        raise HTTPException(status_code=403, detail="Admin access required")
        
    # Logic to iterate through batches and update their metadata
    # For now, we simulate a heavy background job
    return {"status": "CALIBRATION_STARTED", "job_id": "batch-recal-123", "target": "ALL_BATCHES"}

@router.get("/pipeline-observability")
def get_pipeline_observability(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
) -> Any:
    health = observability_service.get_pipeline_health(db)
    return StandardResponse(success=True, message="Pipeline observability retrieved", data=health)

@router.get("/search-questions")
def search_questions(
    q: str = None,
    topic_id: int = None,
    status: str = None,
    is_ca: bool = None,
    is_outdated: bool = None,
    min_quality: float = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Question)
    if q: query = query.filter(Question.text_en.ilike(f"%{q}%"))
    if topic_id: query = query.filter(Question.topic_id == topic_id)
    if status: query = query.filter(Question.status == status)
    if is_ca is not None: query = query.filter(Question.is_current_affairs == is_ca)
    if is_outdated is not None: query = query.filter(Question.is_outdated == is_outdated)
    if min_quality: query = query.filter(Question.explanation_quality_score >= min_quality)
    results = query.limit(limit).all()
    return {"data": results, "total": len(results)}
