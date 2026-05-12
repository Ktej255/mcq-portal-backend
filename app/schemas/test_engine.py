from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from app.models.domain import ConfidenceEnum, AttemptStatusEnum

# Schemas for Test Metadata
class TestMetadataResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    duration_minutes: int
    correct_marks: float
    negative_marking_value: float
    total_questions: Optional[int] = None

    class Config:
        from_attributes = True

# Schemas for Test Start
class StartAttemptRequest(BaseModel):
    test_id: int

class StartAttemptResponse(BaseModel):
    attempt_id: int
    test: TestMetadataResponse
    start_time: datetime
    status: AttemptStatusEnum

# Schemas for Fetching Questions
class QuestionResponse(BaseModel):
    id: int
    test_id: int
    topic_id: int
    subject_id: Optional[int] = None
    topic_name: Optional[str] = None
    subject_name: Optional[str] = None
    text_en: str
    text_hi: Optional[str] = None
    options_en: Any # JSON
    options_hi: Optional[Any] = None
    difficulty: str
    question_number: Optional[int] = None

    class Config:
        from_attributes = True

# Schemas for Saving Answers
class SaveAnswerRequest(BaseModel):
    question_id: int
    selected_option: Optional[str] = None
    time_taken_seconds: int
    confidence_level: Optional[ConfidenceEnum] = None
    is_skipped: bool = False
    marked_for_review: bool = False

class SaveAnswerResponse(BaseModel):
    success: bool
    message: str

# Schemas for Reports
class ReportResponse(BaseModel):
    attempt_id: int
    total_score: float
    accuracy: float
    correct_count: int
    incorrect_count: int
    unattempted_count: int
    topic_wise_analysis: Optional[Dict] = None
    confidence_analysis: Optional[Dict] = None
    subject_wise_performance: Optional[Dict] = None
    average_time_per_question: Optional[float] = None
    generated_at: datetime

    class Config:
        from_attributes = True

class HistoryItemResponse(BaseModel):
    attemptId: str
    title: str
    date: str
    status: str
    score: Optional[float]
    maxScore: float
    accuracy: str

    class Config:
        from_attributes = True
