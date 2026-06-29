"""Answer-writing + evaluation endpoints for the GS LMS Platform (R9–R18).

Mounted under ``/api/v1/gs-lms/{subject_slug}`` (auth-gated at the package
router). Routes:

* ``POST /answers/typed``            — submit a typed answer; evaluate (R10, R15)
* ``POST /answers/handwritten``      — create a handwritten attempt (R11)
* ``POST /answers/{id}/pages``       — upload a page image (R11, R12)
* ``POST /answers/{id}/submit``      — confidence-gate + evaluate (R12, R14, R15)
* ``GET  /answers/{id}/status``      — poll the evaluation job (R15)
* ``GET  /answers/{id}/report``      — ownership-scoped report read (R16, R17)
* ``POST /answers/{id}/override``    — evaluator override + audit (R16)
* ``GET  /answers/{id}/pages/{n}``   — access-controlled image fetch (R17)

Isolation: imports the shared evaluation core + GS modules ONLY — never the
Optional domain (Requirement 2 / Property 9).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs_lms.models import (
    GsLmsAnswerAttempt,
    GsLmsAnswerAttemptStatusEnum,
    GsLmsAnswerModeEnum,
    GsLmsAnswerSheetImage,
    GsLmsEvaluationReport,
    GsLmsExamTypeEnum,
    GsLmsPaperEnum,
    GsLmsPyq,
)
from app.core.gs_lms.evaluation import service as eval_service
from app.api.v1.gs_lms.answer_schemas import (
    GsAnswerAckOut,
    GsAnswerStatusOut,
    GsAnswerSubmitIn,
    GsEvaluationReportOut,
    GsEvaluationSectionOut,
    GsOverrideIn,
    GsPageUploadOut,
)

router = APIRouter()

_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_IMAGE_BYTES = int(os.environ.get("GS_ANSWER_IMAGE_MAX_BYTES", str(10 * 1024 * 1024)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_evaluator(user: User) -> bool:
    """Whether the user may override reports (R16.2/R16.6).

    Recognizes common admin/evaluator role markers defensively.
    """
    role = (getattr(user, "role", "") or "").upper()
    if role in {"ADMIN", "EVALUATOR", "FOUNDER", "STAFF"}:
        return True
    return bool(
        getattr(user, "is_admin", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
    )


def _compose_typed_text(payload: GsAnswerSubmitIn) -> str:
    parts = []
    if payload.intro_text and payload.intro_text.strip():
        parts.append(f"Introduction:\n{payload.intro_text.strip()}")
    if payload.body_text and payload.body_text.strip():
        parts.append(f"Body:\n{payload.body_text.strip()}")
    if payload.conclusion_text and payload.conclusion_text.strip():
        parts.append(f"Conclusion:\n{payload.conclusion_text.strip()}")
    if parts:
        return "\n\n".join(parts)
    if payload.raw_text and payload.raw_text.strip():
        return payload.raw_text.strip()
    return ""


def _resolve_pyq_context(
    db: Session, payload_pyq_id: Optional[int]
) -> tuple[Optional[GsLmsPyq], Optional[GsLmsPaperEnum], Optional[int]]:
    if payload_pyq_id is None:
        return None, None, None
    pyq = db.query(GsLmsPyq).filter(GsLmsPyq.id == payload_pyq_id).one_or_none()
    if pyq is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="PYQ not found")
    # Descriptive answer submission is offered only for MAINS PYQs (R9.3/R9.4).
    if pyq.exam_type != GsLmsExamTypeEnum.MAINS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Descriptive answers are only accepted for MAINS questions.",
        )
    return pyq, pyq.gs_paper, pyq.marks


def _paper_enum(value: Optional[str]) -> Optional[GsLmsPaperEnum]:
    if not value:
        return None
    try:
        return GsLmsPaperEnum(value.strip().upper())
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="gs_paper must be one of GS1, GS2, GS3, GS4",
        )


def _report_out(report: GsLmsEvaluationReport) -> GsEvaluationReportOut:
    sections = {}
    for name, value in (report.sections or {}).items():
        if isinstance(value, dict):
            sections[name] = GsEvaluationSectionOut(
                feedback=str(value.get("feedback", "")),
                score=value.get("score"),
            )
    return GsEvaluationReportOut(
        report_id=report.id,
        attempt_id=report.attempt_id,
        sections=sections,
        incomplete_sections=list(report.incomplete_sections or []),
        is_complete=report.is_complete,
        overall_score=report.overall_score,
        marks_awarded=report.marks_awarded,
        max_marks=report.max_marks,
        word_count=getattr(report.attempt, "word_count", None) if report.attempt else None,
        word_limit=getattr(report.attempt, "word_limit", None) if report.attempt else None,
        value_addition=report.value_addition,
        factual_accuracy=report.factual_accuracy,
        overridden=report.overridden_by is not None,
    )


def _own_attempt_or_404(db: Session, attempt_id: int, user: User) -> GsLmsAnswerAttempt:
    attempt = (
        db.query(GsLmsAnswerAttempt)
        .filter(
            GsLmsAnswerAttempt.id == attempt_id,
            GsLmsAnswerAttempt.student_id == user.id,
        )
        .one_or_none()
    )
    if attempt is None:
        # No existence leak for another student's attempt (R17.2).
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Answer attempt not found")
    return attempt


def _enforce_cost_gates(db: Session, student_id: int, text: str) -> None:
    if eval_service.rate_limit_exceeded(db, student_id):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily evaluation limit reached; please try again later.",
        )
    if eval_service.token_budget_exceeded(text):
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Answer exceeds the maximum size for evaluation.",
        )


# ---------------------------------------------------------------------------
# Typed submission (R10)
# ---------------------------------------------------------------------------
@router.post("/answers/typed")
def submit_typed_answer(
    payload: GsAnswerSubmitIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    text = _compose_typed_text(payload)
    if not text:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="No answer text was provided."
        )

    pyq, pyq_paper, pyq_marks = _resolve_pyq_context(db, payload.pyq_id)
    gs_paper = pyq_paper or _paper_enum(payload.gs_paper)
    max_marks = payload.max_marks if payload.max_marks is not None else pyq_marks

    _enforce_cost_gates(db, current_user.id, text)

    attempt = GsLmsAnswerAttempt(
        student_id=current_user.id,
        pyq_id=payload.pyq_id,
        gs_paper=gs_paper,
        question_text=payload.question_text or (pyq.question_text if pyq else None),
        max_marks=max_marks,
        mode=GsLmsAnswerModeEnum.TYPED,
        status=GsLmsAnswerAttemptStatusEnum.SUBMITTED,
        raw_text=text,
        review_acknowledged=True,
    )
    db.add(attempt)
    db.flush()

    job = eval_service.evaluate_attempt_job(db, attempt)
    db.commit()
    db.refresh(attempt)

    return StandardResponse(
        success=True,
        message="Answer submitted for evaluation",
        data=GsAnswerAckOut(
            attempt_id=attempt.id,
            status=_job_status_label(job.status),
        ),
    )


# ---------------------------------------------------------------------------
# Handwritten attempt + page upload (R11, R12)
# ---------------------------------------------------------------------------
@router.post("/answers/handwritten")
def create_handwritten_attempt(
    payload: GsAnswerSubmitIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    pyq, pyq_paper, pyq_marks = _resolve_pyq_context(db, payload.pyq_id)
    attempt = GsLmsAnswerAttempt(
        student_id=current_user.id,
        pyq_id=payload.pyq_id,
        gs_paper=pyq_paper or _paper_enum(payload.gs_paper),
        question_text=payload.question_text or (pyq.question_text if pyq else None),
        max_marks=payload.max_marks if payload.max_marks is not None else pyq_marks,
        mode=GsLmsAnswerModeEnum.HANDWRITTEN,
        status=GsLmsAnswerAttemptStatusEnum.DRAFT,
        raw_text=payload.raw_text,
        review_acknowledged=False,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return StandardResponse(
        success=True,
        message="Handwritten attempt created; upload pages then submit.",
        data=GsAnswerAckOut(attempt_id=attempt.id, status="draft"),
    )


@router.post("/answers/{attempt_id}/pages")
async def upload_answer_page(
    attempt_id: int,
    image: UploadFile = File(..., description="Handwritten answer page image"),
    page_order: int = Form(...),
    ocr_confidence: Optional[float] = Form(default=None),
    ocr_text: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    attempt = _own_attempt_or_404(db, attempt_id, current_user)

    ext = os.path.splitext(image.filename or "")[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported image type '{ext}'.",
        )
    data = await image.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image exceeds the maximum allowed size.",
        )

    store = eval_service.get_media_store()
    ref = store.put(
        data,
        content_type=image.content_type or "application/octet-stream",
        owner_id=current_user.id,
        attempt_id=attempt.id,
        page_order=page_order,
    )

    # Server-side OCR (R11): when the client did not supply extracted text, run
    # the configured OCR provider so handwritten answers become gradeable text
    # and carry a confidence used by the review gate (R14). If no OCR/vision
    # backend is configured, fall back to the vision path / client values.
    if not ocr_text:
        try:
            from app.core.evaluation.providers.ocr import (
                OcrNotConfiguredError,
                get_ocr_provider,
            )

            result = get_ocr_provider().extract(data, mime_type=image.content_type)
            ocr_text = result.text
            if ocr_confidence is None:
                ocr_confidence = result.confidence
        except Exception:
            # OcrNotConfiguredError or any backend failure: do not block upload;
            # rely on the vision-grading path or client-supplied values.
            pass

    sheet = GsLmsAnswerSheetImage(
        attempt_id=attempt.id,
        student_id=current_user.id,
        media_ref=ref.key,
        page_order=page_order,
        content_type=image.content_type,
    )
    db.add(sheet)

    # Accumulate any OCR text/confidence supplied alongside the page.
    if ocr_text:
        attempt.raw_text = ((attempt.raw_text or "") + "\n" + ocr_text).strip()
    if ocr_confidence is not None:
        prev = attempt.ocr_confidence
        attempt.ocr_confidence = ocr_confidence if prev is None else min(prev, ocr_confidence)

    db.flush()
    total = (
        db.query(GsLmsAnswerSheetImage)
        .filter(GsLmsAnswerSheetImage.attempt_id == attempt.id)
        .count()
    )
    db.commit()
    db.refresh(sheet)
    return StandardResponse(
        success=True,
        message="Page uploaded",
        data=GsPageUploadOut(
            attempt_id=attempt.id,
            image_id=sheet.id,
            page_order=page_order,
            total_pages=total,
        ),
    )


@router.post("/answers/{attempt_id}/submit")
def submit_attempt(
    attempt_id: int,
    acknowledge_review: bool = Form(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    attempt = _own_attempt_or_404(db, attempt_id, current_user)

    if acknowledge_review:
        attempt.review_acknowledged = True
        db.flush()

    # Confidence gate (R14): low-confidence, unreviewed handwriting waits.
    if eval_service.confidence_gate_blocks(attempt):
        db.commit()
        return StandardResponse(
            success=True,
            message="Low-confidence extraction; please review and resubmit.",
            data=GsAnswerAckOut(
                attempt_id=attempt.id,
                status="review_required",
                review_required=True,
                message="Review the extracted text, then resubmit with acknowledgement.",
            ),
        )

    _enforce_cost_gates(db, current_user.id, attempt.raw_text or "")
    job = eval_service.evaluate_attempt_job(db, attempt)
    db.commit()
    return StandardResponse(
        success=True,
        message="Answer submitted for evaluation",
        data=GsAnswerAckOut(attempt_id=attempt.id, status=_job_status_label(job.status)),
    )


# ---------------------------------------------------------------------------
# Status / report (R15, R16, R17)
# ---------------------------------------------------------------------------
def _job_status_label(raw: str) -> str:
    return {
        "STARTED": "in_progress",
        "COMPLETED": "completed",
        "DEGRADED": "degraded",
        "FAILED": "failed",
    }.get(raw, "in_progress")


@router.get("/answers/{attempt_id}/status")
def get_attempt_status(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    attempt = _own_attempt_or_404(db, attempt_id, current_user)
    job = eval_service.latest_job_for_attempt(db, attempt_id)
    report = (
        db.query(GsLmsEvaluationReport)
        .filter(GsLmsEvaluationReport.attempt_id == attempt_id)
        .one_or_none()
    )
    status_label = _job_status_label(job.status) if job else "in_progress"
    if eval_service.confidence_gate_blocks(attempt):
        status_label = "review_required"
    return StandardResponse(
        success=True,
        message="Status retrieved",
        data=GsAnswerStatusOut(
            attempt_id=attempt_id,
            status=status_label,
            report=_report_out(report) if report else None,
        ),
    )


@router.get("/answers/{attempt_id}/report")
def get_attempt_report(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    _own_attempt_or_404(db, attempt_id, current_user)
    report = (
        db.query(GsLmsEvaluationReport)
        .filter(GsLmsEvaluationReport.attempt_id == attempt_id)
        .one_or_none()
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No report for this attempt")
    return StandardResponse(
        success=True, message="Report retrieved", data=_report_out(report)
    )


@router.post("/answers/{attempt_id}/override")
def override_report(
    attempt_id: int,
    payload: GsOverrideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    if not _is_evaluator(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Evaluator role required")

    report = (
        db.query(GsLmsEvaluationReport)
        .filter(GsLmsEvaluationReport.attempt_id == attempt_id)
        .one_or_none()
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No report for this attempt")

    # Preserve the original machine report exactly once (R16.1/R16.4/R16.5).
    if report.original_report is None:
        report.original_report = {
            "sections": report.sections,
            "incomplete_sections": report.incomplete_sections,
            "overall_score": report.overall_score,
            "marks_awarded": report.marks_awarded,
        }

    report.sections = {
        name: {"feedback": sec.feedback, "score": sec.score}
        for name, sec in payload.sections.items()
    }
    report.incomplete_sections = list(payload.incomplete_sections)
    if payload.overall_score is not None:
        report.overall_score = payload.overall_score
    if payload.marks_awarded is not None:
        report.marks_awarded = payload.marks_awarded
    report.overridden_by = current_user.id
    report.overridden_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    return StandardResponse(
        success=True, message="Report overridden", data=_report_out(report)
    )


@router.get("/answers/{attempt_id}/pages/{page_order}")
def fetch_answer_page(
    attempt_id: int,
    page_order: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    attempt = (
        db.query(GsLmsAnswerAttempt)
        .filter(GsLmsAnswerAttempt.id == attempt_id)
        .one_or_none()
    )
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Answer attempt not found")

    is_evaluator = _is_evaluator(current_user)
    if attempt.student_id != current_user.id and not is_evaluator:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Answer attempt not found")

    sheet = (
        db.query(GsLmsAnswerSheetImage)
        .filter(
            GsLmsAnswerSheetImage.attempt_id == attempt_id,
            GsLmsAnswerSheetImage.page_order == page_order,
        )
        .one_or_none()
    )
    if sheet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found")

    store = eval_service.get_media_store()
    try:
        data = store.open(
            sheet.media_ref,
            requester_id=current_user.id,
            is_evaluator=is_evaluator,
            owner_id=attempt.student_id,
        )
    except Exception:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found")

    return Response(content=data, media_type=sheet.content_type or "application/octet-stream")
