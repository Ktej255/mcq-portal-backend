"""Geography Mapping module endpoint for the Optional Subjects Platform
(Task 10 — Phase 1F, R10).

Serves the subject's reviewed map content organized topic-wise by feature
category (river / plateau / plain / …, R10.2): clickable locations with the
3–4 line UPSC-style "what to know" detail (R10.3) and previous-year map-based
questions (R10.1). Mounted under ``/api/v1/optional`` and auth-gated at the
package router level.

Route:

* ``GET /{slug}/mapping``
    The subject's reviewed mapping content, grouped by category. Only
    ``REVIEWED`` (and non-deleted) locations/questions are returned — draft or
    seeded-but-unreviewed mapping stays gated from students (design Property 8 /
    R17.3) until reviewed for UPSC accuracy. An empty ``categories`` list is the
    honest "no reviewed mapping content yet" state.

Subject-specific feature (R10.4 / R11.3): mapping is presented only for subjects
that define map features. The endpoint itself is generic and simply returns an
empty result for subjects with no (reviewed) mapping content; the frontend gates
the affordance to map-feature subjects.

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
from app.core.optional.models import OptionalSubject, OptionalReviewStatusEnum
from app.core.optional.mapping_models import MapLocation, MapQuestion
from app.api.v1.optional.schemas import (
    MapLocationOut,
    MapQuestionOut,
    MapCategoryGroupOut,
    MappingOut,
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


@router.get("/{slug}/mapping")
def get_mapping(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's reviewed mapping content, category-wise (R10)."""
    subject = _get_subject_or_404(db, slug)

    # Honesty gate (design Property 8 / R17.3): student-visible == REVIEWED and
    # not soft-deleted. Draft/seeded mapping (UNREVIEWED) is never returned.
    locations = (
        db.query(MapLocation)
        .filter(
            MapLocation.subject_id == subject.id,
            MapLocation.review_status == OptionalReviewStatusEnum.REVIEWED,
            MapLocation.is_deleted.is_(False),
        )
        .order_by(MapLocation.category.asc(), MapLocation.display_order.asc(), MapLocation.id.asc())
        .all()
    )
    questions = (
        db.query(MapQuestion)
        .filter(
            MapQuestion.subject_id == subject.id,
            MapQuestion.review_status == OptionalReviewStatusEnum.REVIEWED,
            MapQuestion.is_deleted.is_(False),
        )
        .order_by(MapQuestion.category.asc(), MapQuestion.year.desc(), MapQuestion.id.asc())
        .all()
    )

    # Group by feature category (R10.2), preserving stable ordering.
    categories: dict[str, dict[str, list]] = {}
    order: list[str] = []

    def _bucket(category: str) -> dict[str, list]:
        if category not in categories:
            categories[category] = {"locations": [], "questions": []}
            order.append(category)
        return categories[category]

    for loc in locations:
        _bucket(loc.category)["locations"].append(
            MapLocationOut(
                id=loc.id,
                name=loc.name,
                category=loc.category,
                latitude=loc.latitude,
                longitude=loc.longitude,
                detail=loc.detail,
                display_order=loc.display_order,
            )
        )
    for q in questions:
        _bucket(q.category)["questions"].append(
            MapQuestionOut(
                id=q.id,
                year=q.year,
                category=q.category,
                question_text=q.question_text,
                marks=q.marks,
                beyond_syllabus=q.beyond_syllabus,
                location_id=q.location_id,
            )
        )

    groups = [
        MapCategoryGroupOut(
            category=cat,
            location_count=len(categories[cat]["locations"]),
            question_count=len(categories[cat]["questions"]),
            locations=categories[cat]["locations"],
            questions=categories[cat]["questions"],
        )
        for cat in order
    ]

    data = MappingOut(
        slug=subject.slug,
        name=subject.name,
        category_count=len(groups),
        location_count=len(locations),
        question_count=len(questions),
        categories=groups,
    )
    return StandardResponse(success=True, message="Mapping retrieved", data=data)
