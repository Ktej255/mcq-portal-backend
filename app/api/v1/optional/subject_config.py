"""Per-subject configuration endpoint for the Optional Subjects Platform
(Task 15.1 — Phase 2, R11 / R19).

Exposes the DB-backed ``SubjectConfig`` (the ``OptionalSubject.config`` JSON):
the subject's papers/sections shape, its enabled feature modules, and content
availability. The frontend ``SubjectFeatureSlot`` mounts subject-specific
features by this config, so adding a subject in Phase 2 is **content + config,
not new architecture** (design "Per-subject framework").

Route:

* ``GET /{slug}/config``
    The subject's configuration: ``features`` (enabled feature-module keys),
    ``papers`` (label + sections shape), ``is_complete`` and
    ``completeness_status``. Safe defaults (empty features/papers) when a
    subject has no authored config yet, so the frontend degrades gracefully.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import (
    OptionalSubject,
    ContentUnit,
    Pyq,
    OptionalReviewStatusEnum,
)
from app.core.optional.mapping_models import MapLocation
from app.core.optional.current_affairs_models import CurrentAffairsItem
from app.core.optional.student_models import VideoSegment
from app.core.optional.coverage import collect_subject_nodes
from app.api.v1.optional.schemas import (
    SubjectConfigOut,
    SubjectPaperShapeOut,
    CompletenessFeatureOut,
    SubjectCompletenessOut,
)

router = APIRouter()


def _get_subject_or_404(db: Session, slug: str) -> OptionalSubject:
    subject = (
        db.query(OptionalSubject).filter(OptionalSubject.slug == slug).one_or_none()
    )
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optional subject '{slug}' not found",
        )
    return subject


@router.get("/{slug}/config")
def get_subject_config(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's DB-backed configuration (R11.1)."""
    subject = _get_subject_or_404(db, slug)
    config = subject.config if isinstance(subject.config, dict) else {}

    papers: list[SubjectPaperShapeOut] = []
    for p in config.get("papers", []) or []:
        if isinstance(p, dict):
            papers.append(
                SubjectPaperShapeOut(
                    label=str(p.get("label", "")),
                    sections=[str(s) for s in (p.get("sections") or [])],
                )
            )

    features = [str(f) for f in (config.get("features") or []) if str(f).strip()]

    data = SubjectConfigOut(
        slug=subject.slug,
        name=subject.name,
        is_complete=bool(subject.is_complete),
        features=features,
        papers=papers,
        completeness_status=subject.completeness_status
        if isinstance(subject.completeness_status, dict)
        else None,
    )
    return StandardResponse(success=True, message="Subject config retrieved", data=data)


def _is_reviewed_authored(unit) -> bool:
    return (
        bool(getattr(unit, "authored", False))
        and getattr(unit, "review_status", None) == OptionalReviewStatusEnum.REVIEWED
        and not getattr(unit, "is_deleted", False)
    )


@router.get("/{slug}/completeness")
def get_subject_completeness(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return a backend-derived completeness status for the subject (R3.5/R19.3).

    Honest counts from the DB: reviewed vs total topics/content units, reviewed
    PYQs, and which feature modules actually have student-visible (REVIEWED)
    content. A subject is reported "complete" only when its content genuinely
    exists and is reviewed — never inferred from a static flag alone.
    """
    subject = _get_subject_or_404(db, slug)

    nodes = collect_subject_nodes(subject)
    top_nodes = [n for n in nodes if n.parent_id is None]

    total_topics = len(top_nodes)
    reviewed_topics = sum(
        1 for n in top_nodes if any(_is_reviewed_authored(cu) for cu in n.content_units)
    )

    all_units = [cu for n in nodes for cu in n.content_units]
    total_content_units = len(all_units)
    reviewed_content_units = sum(1 for cu in all_units if _is_reviewed_authored(cu))
    has_reviewed_diagram = any(
        _is_reviewed_authored(cu) and cu.diagrams for cu in all_units
    )

    reviewed_pyqs = (
        db.query(Pyq)
        .filter(
            Pyq.subject_id == subject.id,
            Pyq.review_status == OptionalReviewStatusEnum.REVIEWED,
        )
        .count()
    )

    reviewed_map = (
        db.query(MapLocation)
        .filter(
            MapLocation.subject_id == subject.id,
            MapLocation.review_status == OptionalReviewStatusEnum.REVIEWED,
            MapLocation.is_deleted.is_(False),
        )
        .count()
    )
    reviewed_current_affairs = (
        db.query(CurrentAffairsItem)
        .filter(
            CurrentAffairsItem.subject_id == subject.id,
            CurrentAffairsItem.review_status == OptionalReviewStatusEnum.REVIEWED,
            CurrentAffairsItem.is_deleted.is_(False),
        )
        .count()
    )
    # A recall lesson exists when a segment has an authored concept checklist.
    recall_segments = (
        db.query(VideoSegment).filter(VideoSegment.subject_id == subject.id).all()
    )
    has_recall = any(seg.concept_points for seg in recall_segments)

    config = subject.config if isinstance(subject.config, dict) else {}
    configured = [str(f) for f in (config.get("features") or [])]

    # Map each configured feature to whether it has student-visible content.
    availability = {
        "read": reviewed_content_units > 0,
        "diagrams": has_reviewed_diagram,
        "pyq": reviewed_pyqs > 0,
        "practice": reviewed_topics > 0,
        "answer": reviewed_topics > 0,
        "gap": total_topics > 0,
        "mapping": reviewed_map > 0,
        "recall": has_recall,
        "currentAffairs": reviewed_current_affairs > 0,
    }
    features = [
        CompletenessFeatureOut(
            feature=f, available=bool(availability.get(f, False))
        )
        for f in configured
    ]

    if total_topics == 0:
        status_label = "Not started"
    elif bool(subject.is_complete):
        status_label = "Complete"
    elif reviewed_topics == 0:
        status_label = "Not started"
    else:
        status_label = "In progress"

    data = SubjectCompletenessOut(
        slug=subject.slug,
        name=subject.name,
        is_complete=bool(subject.is_complete),
        status_label=status_label,
        reviewed_topics=reviewed_topics,
        total_topics=total_topics,
        reviewed_content_units=reviewed_content_units,
        total_content_units=total_content_units,
        reviewed_pyqs=reviewed_pyqs,
        features=features,
    )
    return StandardResponse(success=True, message="Subject completeness retrieved", data=data)
