from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator

class UPSCQuestionType(str, Enum):
    STANDARD = "STANDARD"
    MULTI_STATEMENT = "MULTI_STATEMENT"
    ASSERTION_REASON = "ASSERTION_REASON"
    MATCH_FOLLOWING = "MATCH_FOLLOWING"
    CHRONOLOGY = "CHRONOLOGY"
    PAIR_MATCHING = "PAIR_MATCHING"

class MCQOption(BaseModel):
    id: str  # A, B, C, D
    text_en: str
    text_hi: Optional[str] = None

class MCQStructure(BaseModel):
    question_number: int
    subject: str
    topic: str
    batch: str
    difficulty: str = "MEDIUM"
    
    # Textual Content
    text_en: str
    text_hi: Optional[str] = None
    
    # Structural Content (UPSC specific)
    question_type: UPSCQuestionType = UPSCQuestionType.STANDARD
    statements_en: List[str] = Field(default_factory=list)
    statements_hi: List[str] = Field(default_factory=list)
    
    options: List[MCQOption]
    correct_option: str  # id from MCQOption
    
    explanation_en: Optional[str] = None
    explanation_hi: Optional[str] = None
    
    @validator('options')
    def validate_options_count(cls, v):
        if len(v) != 4:
            raise ValueError("MCQ must have exactly 4 options for UPSC compliance.")
        return v

    @validator('correct_option')
    def validate_correct_option(cls, v, values):
        if 'options' in values:
            option_ids = [opt.id for opt in values['options']]
            if v not in option_ids:
                raise ValueError(f"Correct option {v} must be one of the option IDs: {option_ids}")
        return v

class IngestionFingerprint(BaseModel):
    content_hash: str
    structure_hash: str
    options_hash: str
    integrity_hash: str  # Global hash of the entire educational unit
