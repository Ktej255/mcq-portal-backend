"""Content review/authoring workflow for the Optional Subjects Platform
(Task 16.1 — Phase 2, R17.1 / R17.2 / R17.3 / R17.4).

Admin/author-gated endpoints to see what content is gated from students and to
publish it by transitioning ``review_status`` (and recording an authoritative
source). This is what lets a founder/content author turn the gated DRAFT mapping
scaffold (and any other UNREVIEWED content) into student-visible REVIEWED
content once verified for UPSC accuracy.

Routes (require an ADMIN user — `get_current_admin`):

* ``GET  /{slug}/review/queue``
    The subject's not-yet-REVIEWED items (content units, PYQs, map locations,
    map questions), so a reviewer sees exactly what is gated (R17.2/R17.3).

* ``POST /review/{kind}/{entity_id}``
    Transition one entity's ``review_status`` (UNREVIEWED / IN_REVIEW /
    REVIEWED). For a content unit, ``authored`` can be set and an authoritative
    ``source`` recorded in the same call (R17.1/R17.4). Setting REVIEWED
    publishes the entity to students; the existing read endpoints already gate
    on REVIEWED (design Property 8), so this is the single control that flips
    visibility.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_admin
from app.schemas.common import StandardResponse
from app.core.optional.models import (
    OptionalSubject,
    ContentUnit,
    SourceRef,
    Pyq,
    OptionalReviewStatusEnum,
)
from app.core.optional.mapping_models import MapLocation, MapQuestion
from app.core.optional.current_affairs_models import CurrentAffairsItem
from app.core.optional.coverage import collect_subject_nodes
from app.core.optional.subject_importer import import_subject_from_payload
from app.api.v1.optional.schemas import (
    REVIEW_KINDS,
    REVIEW_KIND_CONTENT_UNIT,
    REVIEW_KIND_PYQ,
    REVIEW_KIND_MAP_LOCATION,
    REVIEW_KIND_MAP_QUESTION,
    REVIEW_KIND_CURRENT_AFFAIRS,
    REVIEW_STATUS_VALUES,
    ReviewTransitionIn,
    ReviewQueueItemOut,
    ReviewQueueOut,
    ReviewResultOut,
    SubjectImportIn,
    SubjectImportResultOut,
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


def _rs_value(rs: Any) -> str:
    return rs.value if hasattr(rs, "value") else str(rs)


@router.get("/{slug}/review/queue")
def get_review_queue(
    slug: str,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> Any:
    """List the subject's not-yet-REVIEWED items for an author/founder (R17.2/R17.3)."""
    subject = _get_subject_or_404(db, slug)
    items: List[ReviewQueueItemOut] = []
    counts = {k: 0 for k in REVIEW_KINDS}

    # Content units (walk the subject's syllabus nodes).
    node_ids = [n.id for n in collect_subject_nodes(subject)]
    if node_ids:
        cus = (
            db.query(ContentUnit)
            .filter(
                ContentUnit.syllabus_node_id.in_(node_ids),
                ContentUnit.review_status != OptionalReviewStatusEnum.REVIEWED,
            )
            .all()
        )
        for cu in cus:
            if getattr(cu, "is_deleted", False):
                continue
            items.append(
                ReviewQueueItemOut(
                    kind=REVIEW_KIND_CONTENT_UNIT,
                    id=cu.id,
                    label=cu.title or f"Content unit {cu.id}",
                    review_status=_rs_value(cu.review_status),
                )
            )
            counts[REVIEW_KIND_CONTENT_UNIT] += 1

    # PYQs.
    pyqs = (
        db.query(Pyq)
        .filter(
            Pyq.subject_id == subject.id,
            (Pyq.review_status.is_(None))
            | (Pyq.review_status != OptionalReviewStatusEnum.REVIEWED),
        )
        .all()
    )
    for p in pyqs:
        if getattr(p, "is_deleted", False):
            continue
        items.append(
            ReviewQueueItemOut(
                kind=REVIEW_KIND_PYQ,
                id=p.id,
                label=(p.question_text or "")[:80],
                review_status=_rs_value(p.review_status) if p.review_status else "UNREVIEWED",
                extra=str(p.year),
            )
        )
        counts[REVIEW_KIND_PYQ] += 1

    # Map locations + questions.
    for loc in (
        db.query(MapLocation)
        .filter(
            MapLocation.subject_id == subject.id,
            MapLocation.review_status != OptionalReviewStatusEnum.REVIEWED,
            MapLocation.is_deleted.is_(False),
        )
        .all()
    ):
        items.append(
            ReviewQueueItemOut(
                kind=REVIEW_KIND_MAP_LOCATION,
                id=loc.id,
                label=loc.name,
                review_status=_rs_value(loc.review_status),
                extra=loc.category,
            )
        )
        counts[REVIEW_KIND_MAP_LOCATION] += 1

    for q in (
        db.query(MapQuestion)
        .filter(
            MapQuestion.subject_id == subject.id,
            MapQuestion.review_status != OptionalReviewStatusEnum.REVIEWED,
            MapQuestion.is_deleted.is_(False),
        )
        .all()
    ):
        items.append(
            ReviewQueueItemOut(
                kind=REVIEW_KIND_MAP_QUESTION,
                id=q.id,
                label=(q.question_text or "")[:80],
                review_status=_rs_value(q.review_status),
                extra=f"{q.category} {q.year}",
            )
        )
        counts[REVIEW_KIND_MAP_QUESTION] += 1

    # Current-affairs items.
    for ca in (
        db.query(CurrentAffairsItem)
        .filter(
            CurrentAffairsItem.subject_id == subject.id,
            CurrentAffairsItem.review_status != OptionalReviewStatusEnum.REVIEWED,
            CurrentAffairsItem.is_deleted.is_(False),
        )
        .all()
    ):
        items.append(
            ReviewQueueItemOut(
                kind=REVIEW_KIND_CURRENT_AFFAIRS,
                id=ca.id,
                label=ca.title,
                review_status=_rs_value(ca.review_status),
                extra=ca.topic,
            )
        )
        counts[REVIEW_KIND_CURRENT_AFFAIRS] += 1

    data = ReviewQueueOut(
        slug=subject.slug,
        name=subject.name,
        total_pending=len(items),
        counts=counts,
        items=items,
    )
    return StandardResponse(success=True, message="Review queue retrieved", data=data)


@router.post("/review/{kind}/{entity_id}")
def review_transition(
    kind: str,
    entity_id: int,
    payload: ReviewTransitionIn,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> Any:
    """Transition a review-gated entity's status; publish to students on REVIEWED."""
    if kind not in REVIEW_KINDS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown review kind '{kind}'. Expected one of {REVIEW_KINDS}.",
        )
    new_status = (payload.review_status or "").strip().upper()
    if new_status not in REVIEW_STATUS_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"review_status must be one of {REVIEW_STATUS_VALUES}, got {payload.review_status!r}",
        )
    rs_enum = OptionalReviewStatusEnum(new_status)

    model = {
        REVIEW_KIND_CONTENT_UNIT: ContentUnit,
        REVIEW_KIND_PYQ: Pyq,
        REVIEW_KIND_MAP_LOCATION: MapLocation,
        REVIEW_KIND_MAP_QUESTION: MapQuestion,
        REVIEW_KIND_CURRENT_AFFAIRS: CurrentAffairsItem,
    }[kind]

    entity = db.query(model).filter(model.id == entity_id).one_or_none()
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{kind} {entity_id} not found",
        )

    entity.review_status = rs_enum
    source_recorded = False
    authored_out = None

    if kind == REVIEW_KIND_CONTENT_UNIT:
        if payload.authored is not None:
            entity.authored = payload.authored
        # Publishing implies the unit is authored.
        if rs_enum == OptionalReviewStatusEnum.REVIEWED and payload.authored is None:
            entity.authored = True
        if hasattr(entity, "reviewed_at"):
            entity.reviewed_at = (
                datetime.now(timezone.utc)
                if rs_enum == OptionalReviewStatusEnum.REVIEWED
                else None
            )
        authored_out = bool(entity.authored)
        if payload.source is not None:
            db.add(
                SourceRef(
                    content_unit_id=entity.id,
                    title=payload.source.title,
                    citation=payload.source.citation,
                    url=payload.source.url,
                    source_type=payload.source.source_type,
                    created_by=getattr(current_admin, "email", None),
                    updated_by=getattr(current_admin, "email", None),
                )
            )
            source_recorded = True
    elif kind == REVIEW_KIND_MAP_LOCATION:
        if payload.authored is not None:
            entity.authored = payload.authored
        if rs_enum == OptionalReviewStatusEnum.REVIEWED and payload.authored is None:
            entity.authored = True
        authored_out = bool(entity.authored)

    db.commit()

    data = ReviewResultOut(
        kind=kind,
        id=entity_id,
        review_status=new_status,
        authored=authored_out,
        source_recorded=source_recorded,
    )
    return StandardResponse(success=True, message="Review status updated", data=data)


@router.post("/import-subject")
def import_subject(
    payload: SubjectImportIn,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
) -> Any:
    """Upload a subject's syllabus structure + PYQs as gated draft (R19.1/R19.2).

    Admin/author-only. Everything is ingested as UNREVIEWED (hidden from
    students) so the founder reviews and publishes it via the review workflow.
    Idempotent per slug (re-uploading replaces that subject's tree). Deep Read
    notes are authored separately later.
    """
    try:
        counts = import_subject_from_payload(
            db,
            payload.model_dump(),
            review_status="UNREVIEWED",
            actor=getattr(current_admin, "email", None) or "subject-content-upload",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()

    return StandardResponse(
        success=True,
        message="Subject content uploaded (gated draft — publish via review workflow)",
        data=SubjectImportResultOut(
            slug=payload.slug, review_status="UNREVIEWED", counts=counts
        ),
    )
