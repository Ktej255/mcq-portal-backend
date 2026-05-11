from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, root_validator, validator

# Subject Schemas
class SubjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)

class SubjectOut(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True

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

    class Config:
        orm_mode = True

# Question Schemas
class QuestionCreate(BaseModel):
    test_id: int
    topic_id: int
    text_en: str = Field(..., min_length=5)
    text_hi: Optional[str] = None
    options_en: Dict[str, str] = Field(..., description="E.g., {'A': 'Option 1', 'B': 'Option 2'}")
    options_hi: Optional[Dict[str, str]] = None
    correct_option: str = Field(..., max_length=5)
    difficulty: str = Field(default="MEDIUM", description="E.g., EASY, MEDIUM, HARD")

    @validator("correct_option")
    def validate_correct_option(cls, v, values):
        if "options_en" in values and v not in values["options_en"]:
            raise ValueError(f"Correct option {v} must be one of the keys in options_en")
        return v

    @validator("options_en")
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
    difficulty: Optional[str] = None

class QuestionOut(BaseModel):
    id: int
    test_id: int
    topic_id: int
    text_en: str
    text_hi: Optional[str] = None
    options_en: Dict[str, str]
    options_hi: Optional[Dict[str, str]] = None
    correct_option: str
    difficulty: str

    class Config:
        orm_mode = True

class BulkQuestionCreate(BaseModel):
    questions: List[QuestionCreate]

# Test Schemas
class TestCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    subject_id: int
    duration_minutes: int = Field(default=60, gt=0)
    correct_marks: float = Field(default=1.0, gt=0)
    negative_marking_value: float = Field(default=0.33, ge=0)
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

    class Config:
        orm_mode = True
