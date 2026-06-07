from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from app.services.domain_contracts import normalize_option_id

# Subject Schemas
class SubjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)

class SubjectOut(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)

# Topic Schemas
class TopicCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    subject_id: int

class TopicUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    subject_id: Optional[int] = None

class TopicOut(BaseModel):
    id: int
    name: str
    subject_id: int

    model_config = ConfigDict(from_attributes=True)

# Question Schemas
class QuestionCreate(BaseModel):
    test_id: int
    topic_id: int
    text_en: str = Field(..., min_length=5)
    text_hi: Optional[str] = None
    question_type: Optional[str] = "STANDARD" # E.g., MULTI_STATEMENT, ASSERTION_REASON
    statements_en: Optional[List[str]] = None
    statements_hi: Optional[List[str]] = None
    options_en: Dict[str, str] = Field(..., description="E.g., {'A': 'Option 1', 'B': 'Option 2'}")
    options_hi: Optional[Dict[str, str]] = None
    correct_option: str = Field(..., max_length=5)
    explanation_en: Optional[str] = None
    explanation_hi: Optional[str] = None
    source: Optional[str] = None
    difficulty: str = Field(default="MEDIUM", description="E.g., EASY, MEDIUM, HARD")
    question_number: Optional[int] = None

    @field_validator("correct_option")
    @classmethod
    def validate_correct_option(cls, v, info: ValidationInfo):
        v = normalize_option_id(v)
        options_en = info.data.get("options_en", {})
        if options_en and v not in options_en:
            raise ValueError(f"Correct option {v} must be one of the keys in options_en")
        return v

    @field_validator("options_en")
    @classmethod
    def validate_options(cls, v):
        if len(v) < 2:
            raise ValueError("At least 2 options are required")
        return v

class QuestionUpdate(BaseModel):
    topic_id: Optional[int] = None
    text_en: Optional[str] = Field(None, min_length=5)
    text_hi: Optional[str] = None
    options_en: Optional[Dict[str, str]] = None
    options_hi: Optional[Dict[str, str]] = None
    correct_option: Optional[str] = None
    explanation_en: Optional[str] = None
    explanation_hi: Optional[str] = None
    source: Optional[str] = None
    difficulty: Optional[str] = None
    status: Optional[str] = None # E.g., DRAFT, REVIEW, VERIFIED, PUBLISHED
    reviewer_id: Optional[int] = None
    explanation_quality_score: Optional[float] = None
    is_outdated: Optional[bool] = None

class QuestionOut(BaseModel):
    id: int
    test_id: int
    topic_id: int
    text_en: str
    text_hi: Optional[str] = None
    question_type: Optional[str] = "STANDARD"
    statements_en: Optional[List[str]] = None
    statements_hi: Optional[List[str]] = None
    options_en: Dict[str, str]
    options_hi: Optional[Dict[str, str]] = None
    correct_option: str
    explanation_en: Optional[str] = None
    explanation_hi: Optional[str] = None
    source: Optional[str] = None
    difficulty: str
    question_number: Optional[int] = None
    
    # Governance & Quality
    status: str
    reviewer_id: Optional[int] = None
    explanation_quality_score: Optional[float] = None
    is_outdated: bool
    last_reviewed_at: Optional[Any] = None
    
    # Forensic Metadata
    content_hash: Optional[str] = None
    structure_hash: Optional[str] = None
    options_hash: Optional[str] = None
    integrity_metadata: Optional[Dict[str, Any]] = None
    
    # Audit
    created_at: Any
    updated_at: Any
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class BulkQuestionCreate(BaseModel):
    questions: List[QuestionCreate]

# Test Schemas
class TestCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    subject_id: int
    duration_minutes: int = Field(default=60, gt=0)
    correct_marks: float = Field(default=2.0, gt=0)
    negative_marking_value: float = Field(default=0.66, ge=0)
    is_active: bool = True

class TestUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    subject_id: Optional[int] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    correct_marks: Optional[float] = Field(None, gt=0)
    negative_marking_value: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None

class TestOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    subject_id: int
    duration_minutes: int
    correct_marks: float
    negative_marking_value: float
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
