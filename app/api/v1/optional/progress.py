"""Gap / progress endpoints for the Optional Subjects Platform
(Task 11 — Phase 1G, R12.1 / R12.2 / R12.3 / R12.4).

Turns a student's tracked activity into the "% of the syllabus covered vs
remaining" figure that powers the frontend ``GapPanel``. Mounted under
``/api/v1/optional`` and auth-gated at the package router level.

Routes:

* ``GET /{slug}/progress``
    The requesting student's weighted coverage for the subject — overall
    covered% / remaining% plus a per-paper breakdown (R12.3/R12.4). Computed
    live from the student's progress events over the subject's weighted syllabus
    tree (design Property 2).

* ``POST /{slug}/progress/events``
    Record a tracked-activity event (read completion / practice pass / recall
    threshold) against a syllabus node (R12.2), then return the freshly
    recomputed coverage so the UI updates in one round-trip. The rolled-up
    ``Coverage`` cache row is upserted opportunistically.

Ownership (design Property 10 / R15.4): events are created for, and coverage is
computed from, only the requesting student's rows; another student's activity
never contributes.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import OptionalSubject, PaperLabelEnum
from app.core.optional.student_models import (
    ProgressEvent,
    ProgressEventTypeEnum,
    Coverage,
)
from app.core.optional.coverage import (
    CoverageMath,
    compute_subject_coverage,
    compute_paper_coverage,
    subject_node_ids,
)
from app.api.v1.optional.schemas import (
    PROGRESS_EVENT_TYPES,
    ProgressEventIn,
    GapPanelOut,
    GapPaperOut,
)

router = APIRouter()


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


def _paper_label_value(paper) -> str:
    return paper.label.value if hasattr(paper.label, "value") else str(paper.label)


def _build_gap_panel(db: Session, subject: OptionalSubject, student_id: int) -> GapPanelOut:
    """Compute the overall + per-paper coverage payload for the subject."""
    overall: CoverageMath = compute_subject_coverage(
        db, subject=subject, student_id=student_id
    )

    papers_out: list[GapPaperOut] = []
    for paper, math in compute_paper_coverage(db, subject=subject, student_id=student_id):
        papers_out.append(
            GapPaperOut(
                paper_id=paper.id,
                label=_paper_label_value(paper),
                name=paper.name,
                display_order=paper.display_order,
                covered_percent=math.covered_percent,
                remaining_percent=math.remaining_percent,
                total_nodes=math.total_nodes,
                covered_nodes=math.covered_nodes,
            )
        )

    return GapPanelOut(
        slug=subject.slug,
        name=subject.name,
        covered_percent=overall.covered_percent,
        remaining_percent=overall.remaining_percent,
        total_nodes=overall.total_nodes,
        covered_nodes=overall.covered_nodes,
        papers=papers_out,
    )


def _upsert_coverage_cache(
    db: Session, *, subject_id: int, student_id: int, math: CoverageMath
) -> None:
    """Refresh the rolled-up Coverage cache row for (student, subject) (R12).

    The live computation is authoritative; this cache simply mirrors it so a
    future read path can avoid recomputing the whole tree.
    """
    row = (
        db.query(Coverage)
        .filter(Coverage.student_id == student_id, Coverage.subject_id == subject_id)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = Coverage(student_id=student_id, subject_id=subject_id)
        db.add(row)
    row.covered_weight = math.covered_weight
    row.covered_percent = math.covered_percent
    row.remaining_percent = math.remaining_percent
    row.last_computed_at = now


@router.get("/{slug}/progress")
def get_progress(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the student's weighted coverage for the subject (R12.3/R12.4)."""
    subject = _get_subject_or_404(db, slug)
    panel = _build_gap_panel(db, subject, current_user.id)

    # Refresh the cache opportunistically (best-effort; never blocks the read).
    overall = CoverageMath(
        total_weight=0.0,
        covered_weight=0.0,
        covered_percent=panel.covered_percent,
        remaining_percent=panel.remaining_percent,
        total_nodes=panel.total_nodes,
        covered_nodes=panel.covered_nodes,
    )
    _upsert_coverage_cache(
        db, subject_id=subject.id, student_id=current_user.id, math=overall
    )
    db.commit()

    return StandardResponse(
        success=True,
        message="Coverage retrieved",
        data=panel,
    )


@router.post("/{slug}/progress/events")
def record_progress_event(
    slug: str,
    payload: ProgressEventIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Record a tracked-activity event and return updated coverage (R12.2)."""
    subject = _get_subject_or_404(db, slug)

    event_type = (payload.event_type or "").strip().upper()
    if event_type not in PROGRESS_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"event_type must be one of {PROGRESS_EVENT_TYPES}, got {payload.event_type!r}",
        )

    # The node must belong to this subject (isolation + safety).
    if payload.syllabus_node_id not in subject_node_ids(subject):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Syllabus node {payload.syllabus_node_id} does not belong to subject '{slug}'",
        )

    event = ProgressEvent(
        student_id=current_user.id,
        subject_id=subject.id,
        syllabus_node_id=payload.syllabus_node_id,
        event_type=ProgressEventTypeEnum(event_type),
        value=payload.value,
        event_metadata=payload.metadata,
    )
    db.add(event)
    db.flush()

    panel = _build_gap_panel(db, subject, current_user.id)
    overall = CoverageMath(
        total_weight=0.0,
        covered_weight=0.0,
        covered_percent=panel.covered_percent,
        remaining_percent=panel.remaining_percent,
        total_nodes=panel.total_nodes,
        covered_nodes=panel.covered_nodes,
    )
    _upsert_coverage_cache(
        db, subject_id=subject.id, student_id=current_user.id, math=overall
    )
    db.commit()

    return StandardResponse(
        success=True,
        message="Progress event recorded",
        data=panel,
    )
