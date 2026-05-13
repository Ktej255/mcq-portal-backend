from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.domain import Subject, Topic, Question, Test
from app.schemas.admin import (
    SubjectCreate, SubjectUpdate,
    TopicCreate, TopicUpdate,
    QuestionCreate, QuestionUpdate, BulkQuestionCreate,
    TestCreate, TestUpdate
)

# --- Subject CRUD ---
def create_subject(db: Session, obj_in: SubjectCreate) -> Subject:
    db_obj = Subject(**obj_in.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_subjects(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Subject).offset(skip).limit(limit).all()

def update_subject(db: Session, subject_id: int, obj_in: SubjectUpdate) -> Subject:
    db_obj = db.query(Subject).filter(Subject.id == subject_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Subject not found")
    update_data = obj_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# --- Topic CRUD ---
def create_topic(db: Session, obj_in: TopicCreate) -> Topic:
    subject = db.query(Subject).filter(Subject.id == obj_in.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    db_obj = Topic(**obj_in.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_topics(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Topic).offset(skip).limit(limit).all()

def update_topic(db: Session, topic_id: int, obj_in: TopicUpdate) -> Topic:
    db_obj = db.query(Topic).filter(Topic.id == topic_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    if obj_in.subject_id is not None:
        subject = db.query(Subject).filter(Subject.id == obj_in.subject_id).first()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
            
    update_data = obj_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# --- Question CRUD ---
def create_question(db: Session, obj_in: QuestionCreate) -> Question:
    test = db.query(Test).filter(Test.id == obj_in.test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    topic = db.query(Topic).filter(Topic.id == obj_in.topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
        
    db_obj = Question(**obj_in.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_questions(db: Session, test_id: int = None, skip: int = 0, limit: int = 100):
    query = db.query(Question)
    if test_id:
        query = query.filter(Question.test_id == test_id)
    return query.offset(skip).limit(limit).all()

def update_question(db: Session, question_id: int, obj_in: QuestionUpdate) -> Question:
    db_obj = db.query(Question).filter(Question.id == question_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Question not found")
        
    if obj_in.topic_id is not None:
        topic = db.query(Topic).filter(Topic.id == obj_in.topic_id).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
            
    update_data = obj_in.dict(exclude_unset=True)
    if "options_en" in update_data and "correct_option" not in update_data:
        if db_obj.correct_option not in update_data["options_en"]:
             raise HTTPException(status_code=400, detail="Current correct_option not in new options_en")
             
    if "correct_option" in update_data:
        options = update_data.get("options_en", db_obj.options_en)
        if update_data["correct_option"] not in options:
             raise HTTPException(status_code=400, detail="correct_option not in options_en")

    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def delete_question(db: Session, question_id: int) -> Question:
    db_obj = db.query(Question).filter(Question.id == question_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(db_obj)
    db.commit()
    return db_obj

from app.core.pedagogy.ingestion_engine import MCQIngestionEngine

def bulk_create_questions(db: Session, obj_in: BulkQuestionCreate) -> list[Question]:
    # Extract raw dictionaries from Pydantic models for the ingestion engine
    questions_data = [q.dict() for q in obj_in.questions]
    
    # Use the hardened ingestion engine
    # Note: test_id is expected to be part of each question in the current schema
    # but the engine can handle a batch for a specific test if needed.
    # For now, we pass test_id=0 if multiple tests are in one batch, or handle per question.
    
    # We'll use a wrapper to handle multiple tests if present
    created_questions = []
    test_batches = {}
    for q in questions_data:
        t_id = q["test_id"]
        if t_id not in test_batches:
            test_batches[t_id] = []
        test_batches[t_id].append(q)
        
    for t_id, batch in test_batches.items():
        batch_results = MCQIngestionEngine.ingest_batch(db, t_id, batch)
        created_questions.extend(batch_results)
        
    return created_questions

# --- Test CRUD ---
def create_test(db: Session, obj_in: TestCreate) -> Test:
    subject = db.query(Subject).filter(Subject.id == obj_in.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    db_obj = Test(**obj_in.dict())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_tests(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Test).offset(skip).limit(limit).all()

def update_test(db: Session, test_id: int, obj_in: TestUpdate) -> Test:
    db_obj = db.query(Test).filter(Test.id == test_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Test not found")
        
    if obj_in.subject_id is not None:
        subject = db.query(Subject).filter(Subject.id == obj_in.subject_id).first()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
            
    update_data = obj_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj
