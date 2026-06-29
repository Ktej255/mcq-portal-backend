"""GS LMS answer-evaluation service (R7, R13, R14, R15, R18).

Owns the background ``Evaluation_Job`` lifecycle (via the existing
``JobExecutionRegistry``) and the submit-time gates (confidence, cache, rate
limit, token budget). Builds an :class:`EvaluationInput` with the
:class:`GsPaperRubricStrategy`, runs the shared :class:`EvaluationEngine`, and
persists a :class:`GsLmsEvaluationReport`.

Logs/raises reference ids only — never answer text or image bytes (R17.5).
Imports the shared core + GS models ONLY (never Optional — Requirement 2).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.evaluation.cache import InMemoryReportCache, content_hash
from app.core.evaluation.engine import EvaluationEngine, EvaluationInput
from app.core.evaluation.schema import MarkingScheme
from app.core.gs_lms.evaluation.rubric import GsPaperRubricStrategy
from app.core.gs_lms.models import (
    GsLmsAnswerAttempt,
    GsLmsAnswerAttemptStatusEnum,
    GsLmsAnswerModeEnum,
    GsLmsAnswerSheetImage,
    GsLmsEvaluationReport,
)
from app.core.storage.media_store import InMemoryMediaStore, LocalMediaStore, MediaStore
from app.models.domain import JobExecutionRegistry

# Confidence gate threshold for handwritten OCR (R14.2).
GS_OCR_CONFIDENCE_THRESHOLD = float(os.environ.get("GS_OCR_CONFIDENCE_THRESHOLD", "0.6"))
# Cost controls (R18).
GS_EVAL_RATE_LIMIT_PER_DAY = int(os.environ.get("GS_EVAL_RATE_LIMIT_PER_DAY", "50"))
GS_EVAL_MAX_TOKEN_BUDGET = int(os.environ.get("GS_EVAL_MAX_TOKEN_BUDGET", "12000"))

JOB_TYPE = "GS_LMS_EVALUATION"

# Process-wide engine + cache (cache satisfies Property 21 / R18.1).
_ENGINE = EvaluationEngine(cache=InMemoryReportCache())


def get_media_store() -> MediaStore:
    """Resolve the configured media store (env ``MEDIA_STORE_BACKEND``)."""
    backend = (os.environ.get("MEDIA_STORE_BACKEND") or "local").strip().lower()
    if backend == "memory":
        return InMemoryMediaStore()
    if backend == "s3":
        from app.core.storage.s3_media_store import S3MediaStore

        return S3MediaStore()
    return LocalMediaStore()


# ---------------------------------------------------------------------------
# Submit-time gates
# ---------------------------------------------------------------------------
def estimate_tokens(text: Optional[str]) -> int:
    """Rough token estimate (~4 chars/token) for budget gating (R18.4)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def confidence_gate_blocks(attempt: GsLmsAnswerAttempt) -> bool:
    """True when a low-confidence, unreviewed handwritten attempt must wait (R14)."""
    if attempt.review_acknowledged:
        return False
    if attempt.mode != GsLmsAnswerModeEnum.HANDWRITTEN:
        return False
    if attempt.ocr_confidence is None:
        return False
    return attempt.ocr_confidence < GS_OCR_CONFIDENCE_THRESHOLD


def rate_limit_exceeded(db: Session, student_id: int) -> bool:
    """True when the student exceeded the daily evaluation rate limit (R18.2)."""
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = (
        db.query(JobExecutionRegistry)
        .filter(
            JobExecutionRegistry.job_type == JOB_TYPE,
            JobExecutionRegistry.job_name == f"student:{student_id}",
            JobExecutionRegistry.started_at >= since,
        )
        .count()
    )
    return count >= GS_EVAL_RATE_LIMIT_PER_DAY


def token_budget_exceeded(text: Optional[str]) -> bool:
    """True when the estimated input tokens exceed the budget (R18.4)."""
    return estimate_tokens(text) > GS_EVAL_MAX_TOKEN_BUDGET


# ---------------------------------------------------------------------------
# Evaluation job
# ---------------------------------------------------------------------------
def _load_images(db: Session, attempt: GsLmsAnswerAttempt) -> List[bytes]:
    """Load uploaded pages in ascending order for the vision path (R12, R13)."""
    store = get_media_store()
    rows = (
        db.query(GsLmsAnswerSheetImage)
        .filter(GsLmsAnswerSheetImage.attempt_id == attempt.id)
        .order_by(GsLmsAnswerSheetImage.page_order)
        .all()
    )
    images: List[bytes] = []
    for row in rows:
        try:
            images.append(
                store.open(
                    row.media_ref,
                    requester_id=attempt.student_id,
                    is_evaluator=False,
                    owner_id=attempt.student_id,
                )
            )
        except Exception:
            # A missing/unreadable page must not crash evaluation; skip it.
            continue
    return images


def run_evaluation(db: Session, attempt: GsLmsAnswerAttempt) -> GsLmsEvaluationReport:
    """Evaluate one attempt and persist its report (R7, R8, R13)."""
    reference_answer = attempt.pyq.answer_text if attempt.pyq else None
    marking = MarkingScheme(max_marks=attempt.max_marks)
    strategy = GsPaperRubricStrategy(
        attempt.gs_paper.value if attempt.gs_paper else None
    )

    images = _load_images(db, attempt)
    inp = EvaluationInput(
        answer_text=attempt.raw_text or "",
        rubric_strategy=strategy,
        marking_scheme=marking,
        question=attempt.question_text,
        reference_answer=reference_answer,
        answer_images=images,
    )
    report = _ENGINE.evaluate(inp)

    sections_json = {
        name: {"feedback": sec.feedback, "score": sec.score}
        for name, sec in report.sections.items()
    }

    db_report = GsLmsEvaluationReport(
        attempt_id=attempt.id,
        student_id=attempt.student_id,
        sections=sections_json,
        incomplete_sections=list(report.incomplete_sections),
        overall_score=report.overall_score,
        marks_awarded=report.marks_awarded,
        max_marks=report.max_marks,
        factual_accuracy=report.factual_accuracy,
        value_addition=report.value_addition,
    )
    db.add(db_report)

    # Update attempt bookkeeping.
    attempt.status = GsLmsAnswerAttemptStatusEnum.EVALUATED
    attempt.word_count = report.word_count
    attempt.word_limit = report.word_limit
    attempt.provider_key = report.provider_key
    attempt.token_usage = report.token_usage
    attempt.content_hash = content_hash(
        answer_text=attempt.raw_text or "",
        question=attempt.question_text,
        rubric=strategy.build_rubric(
            question=attempt.question_text,
            reference_answer=reference_answer,
            marking_scheme=marking,
        ),
        required_sections=tuple(strategy.required_sections()),
    )
    db.flush()
    return db_report


def evaluate_attempt_job(db: Session, attempt: GsLmsAnswerAttempt) -> JobExecutionRegistry:
    """Run the evaluation under a JobExecutionRegistry lifecycle (R15).

    Records STARTED → COMPLETED (report complete) / DEGRADED (report incomplete)
    / FAILED (exception). The job row is keyed by the attempt for polling.
    """
    job = JobExecutionRegistry(
        job_name=f"student:{attempt.student_id}",
        job_type=JOB_TYPE,
        reference_id=str(attempt.id),
        status="STARTED",
    )
    db.add(job)
    db.flush()

    try:
        report = run_evaluation(db, attempt)
        job.status = "COMPLETED" if report.is_complete else "DEGRADED"
        job.completed_at = datetime.now(timezone.utc)
        job.metadata_payload = {
            "provider_key": attempt.provider_key,
            "token_usage": attempt.token_usage,
            "is_complete": report.is_complete,
        }
    except Exception as exc:  # noqa: BLE001 - record failure, never leak content
        attempt.status = GsLmsAnswerAttemptStatusEnum.FAILED
        job.status = "FAILED"
        job.completed_at = datetime.now(timezone.utc)
        job.error_payload = {"error": type(exc).__name__}
    db.flush()
    return job


def latest_job_for_attempt(db: Session, attempt_id: int) -> Optional[JobExecutionRegistry]:
    """Most recent evaluation job for an attempt (for status polling)."""
    return (
        db.query(JobExecutionRegistry)
        .filter(
            JobExecutionRegistry.job_type == JOB_TYPE,
            JobExecutionRegistry.reference_id == str(attempt_id),
        )
        .order_by(JobExecutionRegistry.id.desc())
        .first()
    )


__all__ = [
    "GS_OCR_CONFIDENCE_THRESHOLD",
    "GS_EVAL_RATE_LIMIT_PER_DAY",
    "GS_EVAL_MAX_TOKEN_BUDGET",
    "JOB_TYPE",
    "get_media_store",
    "estimate_tokens",
    "confidence_gate_blocks",
    "rate_limit_exceeded",
    "token_budget_exceeded",
    "run_evaluation",
    "evaluate_attempt_job",
    "latest_job_for_attempt",
]
