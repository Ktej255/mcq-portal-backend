"""Mains practice endpoints for the Interactive Learning Funnel (funnel step 13).

The frontend ``MainsPracticeStep`` calls three routes that previously did not
exist in the GS LMS funnel, leaving the Mains tab empty:

* GET  /funnel/{node_id}/mains/questions       — MAINS PYQs as writing prompts
* POST /funnel/{node_id}/mains/submit          — submit answer, start evaluation
* GET  /funnel/{node_id}/mains/status/{job_id} — poll evaluation result

These wrap the existing answer-evaluation engine (``eval_service``) and the
node's MAINS PYQs. ``job_id`` is the answer-attempt id (as a string) so the
existing evaluation pipeline is reused without new job infrastructure.

Mounted under ``/api/v1/gs-lms/{subject_slug}`` (auth-gated at the package router).
"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.gs.models import GsReviewStatusEnum, GsSubject
from app.core.gs_lms.models import (
    GsLmsAnswerAttempt,
    GsLmsAnswerAttemptStatusEnum,
    GsLmsAnswerModeEnum,
    GsLmsEvaluationReport,
    GsLmsExamTypeEnum,
    GsLmsPyq,
    GsLmsSyllabusNode,
)
from app.core.gs_lms.evaluation import service as eval_service
from app.api.v1.gs_lms.dependencies import resolve_subject

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas (match frontend funnelService.MainsQuestionOut / MainsSubmitPayload)
# ---------------------------------------------------------------------------
class MainsQuestionOut(BaseModel):
    question_id: int
    gs_paper: str
    year: int
    marks: int
    word_limit: int
    question_text: str


class MainsSubmitIn(BaseModel):
    question_id: int
    introduction: str = ""
    body: str = ""
    conclusion: str = ""
    mode: str = "TYPED"


class EvaluationReportOut(BaseModel):
    marks_awarded: Optional[float] = None
    max_marks: Optional[int] = None
    word_count: Optional[int] = None
    word_limit: Optional[int] = None
    sections: dict = {}
    incomplete_sections: List[str] = []
    is_complete: bool = False


class MainsEvalStatusOut(BaseModel):
    job_id: str
    status: str
    report: Optional[EvaluationReportOut] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _word_limit_for_marks(marks: Optional[int]) -> int:
    """UPSC convention: 10-mark answers ~150 words, 15-mark ~250 words."""
    if marks is None:
        return 250
    return 150 if marks <= 10 else 250


def _job_status_label(raw: str) -> str:
    return {
        "STARTED": "IN_PROGRESS",
        "COMPLETED": "COMPLETED",
        "DEGRADED": "DEGRADED",
        "FAILED": "FAILED",
    }.get(raw, "PENDING")


def _node_or_404(db: Session, node_id: int, subject_id: int) -> GsLmsSyllabusNode:
    node = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.id == node_id,
            GsLmsSyllabusNode.subject_id == subject_id,
        )
        .one_or_none()
    )
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Topic node not found")
    return node


def _report_out(report: GsLmsEvaluationReport) -> EvaluationReportOut:
    sections: dict = {}
    for name, value in (report.sections or {}).items():
        if isinstance(value, dict):
            sections[name] = {
                "feedback": str(value.get("feedback", "")),
                "score": value.get("score"),
            }
    attempt = report.attempt
    return EvaluationReportOut(
        marks_awarded=report.marks_awarded,
        max_marks=report.max_marks,
        word_count=getattr(attempt, "word_count", None) if attempt else None,
        word_limit=getattr(attempt, "word_limit", None) if attempt else None,
        sections=sections,
        incomplete_sections=list(report.incomplete_sections or []),
        is_complete=report.is_complete,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/funnel/{node_id}/mains/questions", response_model=List[MainsQuestionOut])
def get_mains_questions(
    node_id: int,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Return MAINS PYQs for this topic as writing prompts."""
    _node_or_404(db, node_id, subject.id)
    pyqs = (
        db.query(GsLmsPyq)
        .filter(
            GsLmsPyq.syllabus_node_id == node_id,
            GsLmsPyq.exam_type == GsLmsExamTypeEnum.MAINS,
            GsLmsPyq.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(GsLmsPyq.year.desc())
        .all()
    )
    out: List[MainsQuestionOut] = []
    for p in pyqs:
        gs_paper = p.gs_paper.value if hasattr(p.gs_paper, "value") else (p.gs_paper or "GS1")
        out.append(
            MainsQuestionOut(
                question_id=p.id,
                gs_paper=str(gs_paper),
                year=p.year or 0,
                marks=p.marks or 15,
                word_limit=_word_limit_for_marks(p.marks),
                question_text=p.question_text,
            )
        )
    return out


@router.post("/funnel/{node_id}/mains/submit")
def submit_mains_answer(
    node_id: int,
    body: MainsSubmitIn,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Submit a structured Mains answer and start background evaluation."""
    _node_or_404(db, node_id, subject.id)

    pyq = (
        db.query(GsLmsPyq)
        .filter(
            GsLmsPyq.id == body.question_id,
            GsLmsPyq.exam_type == GsLmsExamTypeEnum.MAINS,
        )
        .one_or_none()
    )
    if pyq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mains question not found")

    parts = []
    if body.introduction.strip():
        parts.append(f"Introduction:\n{body.introduction.strip()}")
    if body.body.strip():
        parts.append(f"Body:\n{body.body.strip()}")
    if body.conclusion.strip():
        parts.append(f"Conclusion:\n{body.conclusion.strip()}")
    text = "\n\n".join(parts).strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No answer text provided.")

    word_count = len(text.split())
    word_limit = _word_limit_for_marks(pyq.marks)

    attempt = GsLmsAnswerAttempt(
        student_id=current_user.id,
        pyq_id=pyq.id,
        gs_paper=pyq.gs_paper,
        question_text=pyq.question_text,
        max_marks=pyq.marks,
        mode=GsLmsAnswerModeEnum.TYPED,
        status=GsLmsAnswerAttemptStatusEnum.SUBMITTED,
        raw_text=text,
        review_acknowledged=True,
    )
    # word_count / word_limit are optional columns on the attempt model.
    if hasattr(attempt, "word_count"):
        attempt.word_count = word_count
    if hasattr(attempt, "word_limit"):
        attempt.word_limit = word_limit
    db.add(attempt)
    db.flush()

    eval_service.evaluate_attempt_job(db, attempt)
    db.commit()
    db.refresh(attempt)

    return {"job_id": str(attempt.id)}


@router.get("/funnel/{node_id}/mains/status/{job_id}", response_model=MainsEvalStatusOut)
def poll_mains_evaluation(
    node_id: int,
    job_id: str,
    subject: GsSubject = Depends(resolve_subject),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Poll the evaluation job for a submitted Mains answer (job_id = attempt id)."""
    try:
        attempt_id = int(job_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid job id")

    attempt = (
        db.query(GsLmsAnswerAttempt)
        .filter(
            GsLmsAnswerAttempt.id == attempt_id,
            GsLmsAnswerAttempt.student_id == current_user.id,
        )
        .one_or_none()
    )
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Answer attempt not found")

    job = eval_service.latest_job_for_attempt(db, attempt_id)
    report = (
        db.query(GsLmsEvaluationReport)
        .filter(GsLmsEvaluationReport.attempt_id == attempt_id)
        .one_or_none()
    )
    status_label = _job_status_label(job.status) if job else "PENDING"
    return MainsEvalStatusOut(
        job_id=job_id,
        status=status_label,
        report=_report_out(report) if report else None,
    )
