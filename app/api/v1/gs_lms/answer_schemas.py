"""Pydantic schemas for the GS LMS answer-writing + evaluation API (R9, R10, R16).

Server-authored media references only — clients never supply a storage key
(R11.2). Subject-neutral report shape mirrors the shared evaluation core.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class GsAnswerSubmitIn(BaseModel):
    """A typed descriptive-answer submission for a GS PYQ or free-form question."""

    # Typed composition (either structured parts or a single raw text).
    intro_text: Optional[str] = None
    body_text: Optional[str] = None
    conclusion_text: Optional[str] = None
    raw_text: Optional[str] = None
    # Prompt context. ``pyq_id`` links to a stored PYQ; ``question_text`` is used
    # for a free-form practice question (R9.5).
    pyq_id: Optional[int] = None
    question_text: Optional[str] = None
    gs_paper: Optional[str] = None
    max_marks: Optional[int] = Field(default=None, ge=0)


class GsAnswerAckOut(BaseModel):
    """202 acknowledgement after a submission is accepted for evaluation."""

    attempt_id: int
    status: str
    message: Optional[str] = None
    review_required: bool = False


class GsPageUploadOut(BaseModel):
    """Result of uploading one handwritten answer page."""

    attempt_id: int
    image_id: int
    page_order: int
    total_pages: int


class GsEvaluationSectionOut(BaseModel):
    feedback: str
    score: Optional[float] = None


class GsEvaluationReportOut(BaseModel):
    report_id: int
    attempt_id: int
    sections: Dict[str, GsEvaluationSectionOut] = Field(default_factory=dict)
    incomplete_sections: List[str] = Field(default_factory=list)
    is_complete: bool
    overall_score: Optional[float] = None
    marks_awarded: Optional[float] = None
    max_marks: Optional[int] = None
    word_count: Optional[int] = None
    word_limit: Optional[int] = None
    value_addition: Optional[Dict[str, object]] = None
    factual_accuracy: Optional[Dict[str, object]] = None
    overridden: bool = False


class GsAnswerStatusOut(BaseModel):
    """Polling result for an attempt's evaluation job."""

    attempt_id: int
    status: str  # in_progress | completed | failed | degraded | review_required
    report: Optional[GsEvaluationReportOut] = None
    message: Optional[str] = None


class GsOverrideIn(BaseModel):
    """An evaluator's override of a report (R16)."""

    sections: Dict[str, GsEvaluationSectionOut] = Field(default_factory=dict)
    incomplete_sections: List[str] = Field(default_factory=list)
    overall_score: Optional[float] = None
    marks_awarded: Optional[float] = None


__all__ = [
    "GsAnswerSubmitIn",
    "GsAnswerAckOut",
    "GsPageUploadOut",
    "GsEvaluationSectionOut",
    "GsEvaluationReportOut",
    "GsAnswerStatusOut",
    "GsOverrideIn",
]
