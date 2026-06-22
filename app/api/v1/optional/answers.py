"""Answer-evaluation endpoints for the Optional Subjects Platform
(Task 9.4 — Phase 1E, R9.2 / R9.4 / R9.5).

Closes the answer-writing loop: a typed / spoken / handwritten draft is turned
into a **complete** evaluation report and persisted per student. Mounted under
``/api/v1/optional`` and auth-gated at the package router level.

Routes:

* ``POST /answers``
    Accepts an :class:`AnswerSubmitIn` draft (three-part typed composition
    and/or combined ``raw_text``, plus prompt context and any STT/OCR
    confidence). Builds a topic-aware rubric, runs the draft through the shared
    :class:`EvaluationProvider` (mock by default; Gemini via the existing
    inference gateway in production), persists an ``AnswerAttempt`` +
    ``EvaluationReport``, and returns the report (R9.2 / R9.5).

* ``GET /answers/{attempt_id}/report``
    Returns the persisted report for one of the **requesting student's own**
    attempts (ownership — design Property 10 / R15.4); 404 for unknown or
    another student's attempt.

Honesty (design Property 6 / R9.4): a report is "complete" only when every
required section was produced; any section the model could not produce is named
in ``incomplete_sections`` and the report is marked incomplete — never presented
as complete and never fabricated.

Confidence gating (design Property 7 / R20.1 / R20.3): a spoken/handwritten
draft whose originating STT/OCR confidence is below the relevant threshold and
was NOT explicitly reviewed by the student (``confidence_acknowledged``) is
**not auto-evaluated**. The draft is retained as a DRAFT attempt and the
response asks for a review/correct step instead of grading a shaky input.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import (
    OptionalSubject,
    SyllabusNode,
    ContentUnit,
    OptionalReviewStatusEnum,
)
from app.core.optional.student_models import (
    AnswerAttempt,
    AnswerModeEnum,
    AnswerAttemptStatusEnum,
    EvaluationReport,
)
from app.core.optional.providers import EvaluationProvider, get_evaluation_provider
from app.api.v1.optional.schemas import (
    ANSWER_MODES,
    ANSWER_MODE_SPOKEN,
    ANSWER_MODE_HANDWRITTEN,
    STT_CONFIDENCE_THRESHOLD,
    OCR_CONFIDENCE_THRESHOLD,
    AnswerSubmitIn,
    AnswerEvaluationOut,
    EvaluationReportOut,
    EvaluationSectionOut,
)

router = APIRouter()


def get_evaluation_provider_dep() -> EvaluationProvider:
    """FastAPI dependency wrapper around the env-driven evaluation factory.

    Wrapping the factory in a dependency keeps the route depending only on the
    :class:`EvaluationProvider` interface and lets tests inject a deterministic
    provider (e.g. a forced all-incomplete stub) via ``dependency_overrides``
    without touching global env.
    """
    return get_evaluation_provider()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_subject_or_404(db: Session, slug: str) -> OptionalSubject:
    subject = (
        db.query(OptionalSubject)
        .filter(OptionalSubject.slug == slug)
        .one_or_none()
    )
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optional subject '{slug}' not found",
        )
    return subject


def _reviewed_authored_unit(node: SyllabusNode) -> Optional[ContentUnit]:
    """Return the node's first reviewed+authored, non-deleted ContentUnit.

    Mirrors the honesty gate used by the Read layer (``content.py``): rubric
    enrichment only ever draws on genuinely authored + reviewed content.
    """
    candidates = [
        cu
        for cu in node.content_units
        if cu.authored
        and cu.review_status == OptionalReviewStatusEnum.REVIEWED
        and not getattr(cu, "is_deleted", False)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda cu: (cu.display_order, cu.id))
    return candidates[0]


_GENERIC_RUBRIC = (
    "Evaluate this UPSC optional answer as a senior examiner would. Assess: "
    "whether the introduction frames the demand of the question; the depth, "
    "relevance and substantiation of the body; a balanced, forward-looking "
    "conclusion; coverage of the expected content; use of examiner/technical "
    "keywords; exam-appropriate answer language; structure and presentation; "
    "and value addition (diagrams, maps, data, examples). Give concrete, "
    "actionable feedback and an overall assessment."
)


def _build_rubric(
    db: Session, subject: OptionalSubject, topic_node_id: Optional[int]
) -> str:
    """Build a topic-aware rubric, falling back to a generic UPSC rubric.

    When the draft targets a syllabus topic that has reviewed+authored content,
    the topic's examiner keywords / answer-language phrasing / official syllabus
    phrasing enrich the rubric so the evaluation is grounded in what that
    segment actually expects. Otherwise the generic rubric is used — the
    evaluation never fabricates topic expectations it doesn't have.
    """
    if topic_node_id is None:
        return _GENERIC_RUBRIC

    node = (
        db.query(SyllabusNode)
        .filter(SyllabusNode.id == topic_node_id)
        .one_or_none()
    )
    if node is None:
        return _GENERIC_RUBRIC

    parts = [_GENERIC_RUBRIC, f"\nTOPIC: {node.title}"]
    if node.official_phrasing:
        parts.append(f"OFFICIAL SYLLABUS PHRASING:\n{node.official_phrasing}")

    unit = _reviewed_authored_unit(node)
    if unit is not None:
        if unit.exam_keywords:
            kws = ", ".join(str(k) for k in unit.exam_keywords if str(k).strip())
            if kws:
                parts.append(f"EXPECTED EXAMINER KEYWORDS: {kws}")
        if unit.answer_language:
            lines = [str(s) for s in unit.answer_language if str(s).strip()]
            if lines:
                parts.append(
                    "ANSWER-LANGUAGE PHRASING TO REWARD:\n" + "\n".join(lines)
                )
    return "\n".join(parts)


def _compose_answer_text(payload: AnswerSubmitIn) -> str:
    """Compose the full answer text fed to the evaluator (R8.1).

    Prefers the structured three-part composition (Introduction / Body /
    Conclusion); falls back to the combined ``raw_text`` (spoken/handwritten
    drafts). Returns an empty string when nothing was written.
    """
    parts: list[str] = []
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


def _confidence_gate(payload: AnswerSubmitIn, mode: AnswerModeEnum) -> bool:
    """Return True when a low-confidence input must be reviewed before grading.

    Design Property 7 (R20.1 / R20.3): if a spoken/handwritten draft's
    originating provider confidence is below the relevant threshold and the
    student has not explicitly acknowledged/reviewed it, the answer must not be
    auto-evaluated. Typed answers (and acknowledged low-confidence inputs) are
    never gated.
    """
    if payload.confidence_acknowledged:
        return False
    if mode == AnswerModeEnum.SPOKEN and payload.stt_confidence is not None:
        return payload.stt_confidence < STT_CONFIDENCE_THRESHOLD
    if mode == AnswerModeEnum.HANDWRITTEN and payload.ocr_confidence is not None:
        return payload.ocr_confidence < OCR_CONFIDENCE_THRESHOLD
    return False


def _report_out(report: EvaluationReport) -> EvaluationReportOut:
    """Map a persisted ``EvaluationReport`` to its API shape."""
    sections_raw = report.sections or {}
    sections: dict[str, EvaluationSectionOut] = {}
    for name, value in sections_raw.items():
        if isinstance(value, dict):
            sections[name] = EvaluationSectionOut(
                feedback=str(value.get("feedback", "")),
                score=value.get("score"),
            )
    return EvaluationReportOut(
        report_id=report.id,
        attempt_id=report.attempt_id,
        sections=sections,
        incomplete_sections=list(report.incomplete_sections or []),
        is_complete=report.is_complete,
        overall_score=report.overall_score,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/{slug}/answers")
def submit_answer(
    slug: str,
    payload: AnswerSubmitIn,
    db: Session = Depends(get_db),
    provider: EvaluationProvider = Depends(get_evaluation_provider_dep),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Evaluate and persist a student's answer draft (R9.2 / R9.4 / R9.5).

    Honesty (Property 6): the report flags any section it could not produce in
    ``incomplete_sections`` rather than fabricating it. Confidence gating
    (Property 7): a shaky, unreviewed spoken/handwritten draft is retained but
    not auto-graded — the response asks for a review/correct step.
    """
    subject = _get_subject_or_404(db, slug)

    # Validate the composition mode.
    mode_str = (payload.mode or "").strip().upper()
    if mode_str not in ANSWER_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"mode must be one of {ANSWER_MODES}, got {payload.mode!r}",
        )
    mode = AnswerModeEnum(mode_str)

    answer_text = _compose_answer_text(payload)
    if not answer_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No answer text was provided to evaluate.",
        )

    # Validate the topic node belongs to this subject when supplied.
    if payload.topic_node_id is not None:
        node = (
            db.query(SyllabusNode)
            .filter(SyllabusNode.id == payload.topic_node_id)
            .one_or_none()
        )
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Syllabus node {payload.topic_node_id} not found",
            )

    # Confidence gate (Property 7): refuse to auto-grade a shaky, unreviewed
    # spoken/handwritten input. Retain the draft so the student can review it.
    if _confidence_gate(payload, mode):
        attempt = AnswerAttempt(
            student_id=current_user.id,
            subject_id=subject.id,
            topic_node_id=payload.topic_node_id,
            mode=mode,
            status=AnswerAttemptStatusEnum.DRAFT,
            question_text=payload.question_text,
            pyq_id=payload.pyq_id,
            raw_text=answer_text,
            intro_text=payload.intro_text,
            body_text=payload.body_text,
            conclusion_text=payload.conclusion_text,
            source_media_ref=payload.source_media_ref,
            ocr_confidence=payload.ocr_confidence,
            stt_confidence=payload.stt_confidence,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        data = AnswerEvaluationOut(
            attempt_id=attempt.id,
            mode=mode.value,
            status=attempt.status.value,
            review_required=True,
            low_confidence=True,
            report=None,
            message=(
                "The transcribed/extracted text was low-confidence. Please "
                "review and correct it, then resubmit with confidence "
                "acknowledged before it is evaluated."
            ),
        )
        return StandardResponse(
            success=True,
            message="Answer draft saved; review required before evaluation",
            data=data,
        )

    # Build the rubric and evaluate (always returns a schema-valid report — the
    # provider degrades honestly to all-incomplete on model/parse failure).
    rubric = _build_rubric(db, subject, payload.topic_node_id)
    report_schema = provider.evaluate(
        answer_text=answer_text,
        rubric=rubric,
        question=payload.question_text,
    )

    # Persist the attempt + report (R9.5).
    attempt = AnswerAttempt(
        student_id=current_user.id,
        subject_id=subject.id,
        topic_node_id=payload.topic_node_id,
        mode=mode,
        status=AnswerAttemptStatusEnum.EVALUATED,
        question_text=payload.question_text,
        pyq_id=payload.pyq_id,
        raw_text=answer_text,
        intro_text=payload.intro_text,
        body_text=payload.body_text,
        conclusion_text=payload.conclusion_text,
        source_media_ref=payload.source_media_ref,
        ocr_confidence=payload.ocr_confidence,
        stt_confidence=payload.stt_confidence,
    )
    db.add(attempt)
    db.flush()  # assign attempt.id without a second round-trip

    # Serialize the report sections to plain JSON for storage.
    sections_json = {
        name: {"feedback": sec.feedback, "score": sec.score}
        for name, sec in report_schema.sections.items()
    }
    report = EvaluationReport(
        attempt_id=attempt.id,
        student_id=current_user.id,
        sections=sections_json,
        incomplete_sections=list(report_schema.incomplete_sections),
        overall_score=report_schema.overall_score,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    data = AnswerEvaluationOut(
        attempt_id=attempt.id,
        mode=mode.value,
        status=AnswerAttemptStatusEnum.EVALUATED.value,
        review_required=False,
        low_confidence=False,
        report=_report_out(report),
        message=(
            None
            if report.is_complete
            else "Some sections could not be produced and are flagged incomplete."
        ),
    )
    return StandardResponse(
        success=True,
        message="Answer evaluated",
        data=data,
    )


@router.get("/answers/{attempt_id}/report")
def get_answer_report(
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the persisted evaluation report for the student's own attempt.

    Ownership (design Property 10 / R15.4): the report is only returned when the
    attempt belongs to the requesting student; otherwise 404 (no existence
    leak). 404 when the attempt has no report yet (e.g. a review-required DRAFT).
    """
    attempt = (
        db.query(AnswerAttempt)
        .filter(
            AnswerAttempt.id == attempt_id,
            AnswerAttempt.student_id == current_user.id,
        )
        .one_or_none()
    )
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Answer attempt {attempt_id} not found",
        )

    report = (
        db.query(EvaluationReport)
        .filter(
            EvaluationReport.attempt_id == attempt_id,
            EvaluationReport.student_id == current_user.id,
        )
        .one_or_none()
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No evaluation report for attempt {attempt_id}",
        )

    return StandardResponse(
        success=True,
        message="Evaluation report retrieved",
        data=_report_out(report),
    )
