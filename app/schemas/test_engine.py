from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from typing import List, Optional, Any, Dict
from datetime import datetime
from app.models.domain import ConfidenceEnum, AttemptStatusEnum
from app.services.domain_contracts import (
    ContractViolation,
    normalize_option_id,
    normalize_confidence,
    normalize_event_payload,
    validate_event_timestamp,
)

# Schemas for Test Metadata
class TestMetadataResponse(BaseModel):
    __test__ = False

    id: int
    title: str
    description: Optional[str]
    duration_minutes: int
    correct_marks: float
    negative_marking_value: float
    total_questions: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)

# Schemas for Saving Answers
class SaveAnswerRequest(BaseModel):
    question_id: int
    selected_option: Optional[str] = None
    time_taken_seconds: int
    confidence_level: Optional[ConfidenceEnum] = None
    is_skipped: bool = False
    marked_for_review: bool = False
    clear_response: bool = False

    @field_validator("selected_option")
    @classmethod
    def validate_selected_option(cls, value):
        return normalize_option_id(value)

    @field_validator("confidence_level", mode="before")
    @classmethod
    def validate_confidence(cls, value):
        return normalize_confidence(value)

    @field_validator("time_taken_seconds")
    @classmethod
    def validate_time_taken(cls, value):
        if value < 0:
            raise ValueError("time_taken_seconds must be non-negative")
        return value

class SaveAnswerResponse(BaseModel):
    success: bool
    message: str

# Schemas for Reports
class ReportResponse(BaseModel):
    attempt_id: int
    total_score: float
    accuracy: float
    mastery_percentage: Optional[float] = None
    score_percentage: Optional[float] = None
    correct_count: int
    incorrect_count: int
    unattempted_count: int
    negative_marks: Optional[float] = None
    topic_wise_analysis: Optional[Dict] = None
    confidence_analysis: Optional[Dict] = None
    subject_wise_performance: Optional[Dict] = None
    average_time_per_question: Optional[float] = None
    narrative: Optional[str] = None
    processing_status: str = "COMPLETED"
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class HistoryItemResponse(BaseModel):
    attemptId: str
    title: str
    date: str
    status: str
    score: Optional[float]
    maxScore: float
    accuracy: str

    model_config = ConfigDict(from_attributes=True)
# Schemas for Behavioral Events
class ExamEventRequest(BaseModel):
    event_type: str
    question_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_contract(self):
        try:
            self.timestamp = validate_event_timestamp(self.timestamp)
            self.payload = normalize_event_payload(self.event_type, self.question_id, self.payload)
        except ContractViolation as exc:
            raise ValueError(str(exc)) from exc
        return self

class EventBatchRequest(BaseModel):
    events: List[ExamEventRequest]

    @field_validator("events")
    @classmethod
    def validate_non_empty_batch(cls, value):
        if not value:
            raise ValueError("events batch must contain at least one event")
        if len(value) > 100:
            raise ValueError("events batch cannot exceed 100 events")
        return value
