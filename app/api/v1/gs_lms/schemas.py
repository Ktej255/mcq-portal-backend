"""Pydantic request/response schemas for the GS LMS Platform API.

These schemas define the data contracts for all GS LMS endpoints — syllabus
tree, progressive-disclosure content, PYQs, MCQ practice, AI discussion,
progress/gap tracking, daily planner, PDF generation, and onboarding.

Design patterns mirror the Optional platform's schemas.py: flat Pydantic
models, self-referential trees via forward refs, honest empty-state
representations, and strict separation from internal SQLAlchemy models.

Requirements: 10.1, 10.2, 10.3
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Syllabus tree responses
# ---------------------------------------------------------------------------

class GsLmsSyllabusNodeOut(BaseModel):
    """A node in the GS LMS weighted syllabus tree."""
    node_id: int
    title: str
    node_type: str  # MEGA_TOPIC | SUB_TOPIC | LEAF_TOPIC
    weight: float
    display_order: int
    review_status: str
    # Per-student completion percentage (0.0–100.0 for non-leaf, bool for leaf)
    completion_percent: Optional[float] = None
    completed: Optional[bool] = None
    # Bridge to existing day-lesson system
    day_lesson_id: Optional[int] = None
    ordering_justification: Optional[str] = None
    children: list["GsLmsSyllabusNodeOut"] = []


class GsLmsSyllabusTreeOut(BaseModel):
    """The full GS Geography syllabus tree response."""
    subject_id: int
    subject_name: str
    total_nodes: int
    tree: list[GsLmsSyllabusNodeOut] = []


# Resolve self-referential forward ref.
GsLmsSyllabusNodeOut.model_rebuild()


# ---------------------------------------------------------------------------
# Content section responses (progressive disclosure)
# ---------------------------------------------------------------------------

class GsLmsContentSectionOut(BaseModel):
    """A single progressive-disclosure content section for a topic.

    When locked, ``blocks`` is None (content hidden). When unlocked,
    ``blocks`` contains the typed content blocks.

    Skippable sections are unlocked (student can read them) but NOT required
    for topic completion. This is determined by learner level + discussion
    match percentage.
    """
    section_id: int
    section_label: str  # BASIC | ADVANCED | NCERT_LEVEL | EXAMINER_TRAPS
    title: str
    display_order: int
    locked: bool
    completed: bool
    skippable: bool = False
    # Content blocks — None when section is locked.
    blocks: Optional[Any] = None


class GsLmsTopicSectionsOut(BaseModel):
    """All four sections of a topic with lock/unlock state per student."""
    node_id: int
    title: str
    discussion_gate_passed: bool
    topic_completed: bool
    video_url: Optional[str] = None
    video_watched: bool = False
    learner_level: Optional[str] = None
    sections: list[GsLmsContentSectionOut] = []


# ---------------------------------------------------------------------------
# PYQ responses
# ---------------------------------------------------------------------------

class GsLmsPyqOut(BaseModel):
    """A student-visible (REVIEWED) Previous Year Question.

    Answer and explanation are omitted until explicitly revealed (Property 8).
    """
    id: int
    year: int
    exam_type: str  # PRELIMS | MAINS
    question_text: str
    question_type: Optional[str] = None
    marks: Optional[int] = None  # Relevant for Mains
    # Answer is only included after reveal action.
    answer_text: Optional[str] = None
    explanation: Optional[str] = None
    revealed: bool = False


class GsLmsPyqListOut(BaseModel):
    """PYQs for a topic, optionally filtered by exam type."""
    node_id: int
    title: str
    exam_type_filter: Optional[str] = None
    total: int
    pyqs: list[GsLmsPyqOut] = []


# ---------------------------------------------------------------------------
# MCQ Practice requests/responses
# ---------------------------------------------------------------------------

class GsLmsPracticeStartIn(BaseModel):
    """Request to start a practice session for a topic."""

    model_config = {"extra": "forbid"}

    syllabus_node_id: int


class GsLmsMcqOptionOut(BaseModel):
    """A single MCQ option (A/B/C/D)."""
    label: str
    text: str


class GsLmsMcqQuestionOut(BaseModel):
    """The current question in a sequential practice session.

    Only exposed when it's the student's turn to answer this question
    (sequential access control — Property 10).
    """
    question_id: int
    question_text: str
    question_type: str
    options: list[GsLmsMcqOptionOut] = []
    display_order: int


class GsLmsPracticeAnswerIn(BaseModel):
    """Submit an answer for the current practice question."""

    model_config = {"extra": "forbid"}

    chosen_answer: str  # "A", "B", "C", or "D"
    time_taken_seconds: Optional[float] = None


class GsLmsPracticeAttemptResultOut(BaseModel):
    """Result of a single answered question."""
    question_id: int
    chosen_answer: Optional[str] = None
    correct_answer: str
    is_correct: Optional[bool] = None
    question_type: str
    explanation: Optional[str] = None
    time_taken_seconds: Optional[float] = None


class GsLmsQuestionTypeAccuracyOut(BaseModel):
    """Per-question-type accuracy breakdown."""
    question_type: str
    total: int
    correct: int
    accuracy: float  # 0.0–1.0


class GsLmsPracticeSessionOut(BaseModel):
    """The state of a practice session."""
    session_id: int
    syllabus_node_id: int
    status: str  # IN_PROGRESS | COMPLETED | SUBMITTED
    total_questions: int
    current_index: int
    current_question: Optional[GsLmsMcqQuestionOut] = None
    started_at: str  # ISO 8601


class GsLmsPracticeResultOut(BaseModel):
    """Scoring result after session submission."""
    session_id: int
    total_questions: int
    correct_count: int
    score: float  # 0.0–1.0
    attempts: list[GsLmsPracticeAttemptResultOut] = []
    type_accuracy: list[GsLmsQuestionTypeAccuracyOut] = []
    submitted_at: str  # ISO 8601


# ---------------------------------------------------------------------------
# AI Discussion requests/responses
# ---------------------------------------------------------------------------

class GsLmsDiscussionStartIn(BaseModel):
    """Request to start a discussion session for a topic."""

    model_config = {"extra": "forbid"}

    syllabus_node_id: int


class GsLmsDiscussionTurnIn(BaseModel):
    """Student sends a message in a discussion session."""

    model_config = {"extra": "forbid"}

    content: str


class GsLmsDiscussionTurnOut(BaseModel):
    """A single turn in the AI discussion conversation."""
    turn_order: int
    role: str  # "student" or "ai"
    content: str
    created_at: str  # ISO 8601


class GsLmsDiscussionSessionOut(BaseModel):
    """State of an AI discussion session."""
    session_id: int
    syllabus_node_id: int
    status: str  # INITIATED | IN_PROGRESS | COMPLETED | ABANDONED
    started_at: str  # ISO 8601
    completed_at: Optional[str] = None
    turns: list[GsLmsDiscussionTurnOut] = []


class GsLmsDiscussionTurnResponseOut(BaseModel):
    """Response after submitting a student turn (includes AI reply)."""
    session_id: int
    status: str
    student_turn: GsLmsDiscussionTurnOut
    ai_turn: GsLmsDiscussionTurnOut
    gate_passed: bool
    # Concept matching info (present when topic has a concept_checklist)
    concepts_matched: Optional[list[str]] = None
    concepts_missed: Optional[list[str]] = None
    match_percentage: Optional[float] = None


# ---------------------------------------------------------------------------
# Progress / Gap responses
# ---------------------------------------------------------------------------

class GsLmsWeakTopicOut(BaseModel):
    """A weak topic identified by the gap engine."""
    node_id: int
    title: str
    accuracy: float  # 0.0–1.0
    attempt_count: int


class GsLmsWeakQuestionTypeOut(BaseModel):
    """A weak question type identified by the gap engine."""
    question_type: str
    accuracy: float  # 0.0–1.0
    attempt_count: int


class GsLmsRecommendedActionOut(BaseModel):
    """A recommended action from the gap engine."""
    action: str
    target_node_id: Optional[int] = None
    reason: str


class GsLmsGapOut(BaseModel):
    """Gap profile for a student — weak areas ordered by severity."""
    overall_accuracy: float
    weak_topics: list[GsLmsWeakTopicOut] = []
    weak_question_types: list[GsLmsWeakQuestionTypeOut] = []
    recommended_actions: list[GsLmsRecommendedActionOut] = []
    computed_at: str  # ISO 8601


class GsLmsMegaTopicProgressOut(BaseModel):
    """Progress data for a single mega-topic."""
    node_id: int
    title: str
    total_children: int
    completed_children: int
    completion_percent: float  # 0.0–100.0


class GsLmsProgressOut(BaseModel):
    """Overall student progress across the GS Geography syllabus."""
    total_topics: int
    completed_topics: int
    overall_percent: float  # 0.0–100.0
    mega_topics: list[GsLmsMegaTopicProgressOut] = []


class GsLmsProgressEventIn(BaseModel):
    """Record a progress event (section completion, practice pass, etc.)."""

    model_config = {"extra": "forbid"}

    syllabus_node_id: int
    event_type: str  # "SECTION_COMPLETE" | "PRACTICE_PASS" | "DISCUSSION_COMPLETE"
    value: Optional[float] = None
    metadata: Optional[dict] = None


# ---------------------------------------------------------------------------
# Daily Planner responses
# ---------------------------------------------------------------------------

class GsLmsPlanItemOut(BaseModel):
    """A single item in the daily plan."""
    node_id: int
    title: str
    item_type: str  # "section" | "practice" | "revisit"
    completed: bool = False
    completed_at: Optional[str] = None  # ISO 8601
    # For revisit items only
    revisit_id: Optional[int] = None
    revisit_type: Optional[str] = None  # "day_3" | "day_7" | "day_21"
    overdue: bool = False


class GsLmsDailyPlanOut(BaseModel):
    """The student's daily plan for today."""
    plan_date: str  # ISO date
    bandwidth: int
    planned_items: list[GsLmsPlanItemOut] = []
    completed_count: int
    is_target_met: Optional[bool] = None
    projected_completion_date: Optional[str] = None  # ISO date
    streak_days: int = 0


class GsLmsBandwidthIn(BaseModel):
    """Request to set/update daily bandwidth."""

    model_config = {"extra": "forbid"}

    bandwidth: int = Field(..., gt=0, description="Must be a positive integer")


class GsLmsReplanOut(BaseModel):
    """Result of a replanning event."""
    reason: str  # "consecutive_misses" | "manual" | "bandwidth_increase"
    old_bandwidth: int
    new_bandwidth: int
    old_projected_date: Optional[str] = None  # ISO date
    new_projected_date: Optional[str] = None  # ISO date
    triggered_at: str  # ISO 8601


# ---------------------------------------------------------------------------
# PDF responses
# ---------------------------------------------------------------------------

class GsLmsPdfStatusOut(BaseModel):
    """Status/metadata for a topic PDF download.

    The actual PDF is served as a binary download; this schema is used
    for status checks when the topic is incomplete.
    """
    node_id: int
    title: str
    all_sections_complete: bool
    available: bool
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Onboarding responses
# ---------------------------------------------------------------------------

class GsLmsOnboardingStatusOut(BaseModel):
    """Current onboarding state for a student."""
    completed: bool
    completed_at: Optional[str] = None  # ISO 8601
    bandwidth_selected: Optional[int] = None
    first_topic_id: Optional[int] = None
    first_topic_title: Optional[str] = None
    learner_level: Optional[str] = None
    study_window_minutes: Optional[int] = None


class GsLmsOnboardingCompleteIn(BaseModel):
    """Request to mark onboarding as complete."""

    model_config = {"extra": "forbid"}

    bandwidth: int = Field(..., gt=0, description="Daily bandwidth selection")
    first_topic_id: Optional[int] = None
    learner_level: str = Field(
        default="beginner",
        description="Learner level: beginner, intermediate, or advanced",
    )
    study_window_minutes: int = Field(
        default=90,
        description="Daily study window in minutes: 60, 90, 120, or 180",
    )

    @field_validator("learner_level")
    @classmethod
    def validate_learner_level(cls, v: str) -> str:
        allowed = ("beginner", "intermediate", "advanced")
        if v not in allowed:
            raise ValueError(f"learner_level must be one of {allowed}")
        return v

    @field_validator("study_window_minutes")
    @classmethod
    def validate_study_window(cls, v: int) -> int:
        allowed = (60, 90, 120, 180)
        if v not in allowed:
            raise ValueError(f"study_window_minutes must be one of {allowed}")
        return v


class GsLmsLearnerLevelUpdateIn(BaseModel):
    """Request to update learner level post-onboarding."""

    model_config = {"extra": "forbid"}

    learner_level: str = Field(
        ..., description="Learner level: beginner, intermediate, or advanced"
    )

    @field_validator("learner_level")
    @classmethod
    def validate_learner_level(cls, v: str) -> str:
        allowed = ("beginner", "intermediate", "advanced")
        if v not in allowed:
            raise ValueError(f"learner_level must be one of {allowed}")
        return v
