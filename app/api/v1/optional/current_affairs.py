"""Subject-specific Current-Affairs feature endpoint (Task 17.1 — R11.4 / R19.2).

Serves a subject's reviewed current-affairs / news feed (Public Administration
today). This proves the per-subject framework generalizes a *subject-specific*
feature beyond Geography's mapping. Mounted under ``/api/v1/optional`` and
auth-gated at the package router level.

Route:

* ``GET /{slug}/current-affairs``
    The subject's reviewed current-affairs items, newest first, plus the set of
    topics for filtering. Only ``REVIEWED`` (non-deleted) items are returned —
    draft items stay gated (design Property 8 / R17.3). An empty ``items`` list
    is the honest "no reviewed current affairs yet" state.

The affordance is shown by the frontend only for subjects whose config enables
the ``currentAffairs`` feature module (config-driven — R11.2).

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
from app.core.optional.current_affairs_models import CurrentAffairsItem
from app.api.v1.optional.schemas import CurrentAffairsItemOut, CurrentAffairsFeedOut

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


@router.get("/{slug}/current-affairs")
def get_current_affairs(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's reviewed current-affairs feed, newest first (R11.4)."""
    subject = _get_subject_or_404(db, slug)

    rows = (
        db.query(CurrentAffairsItem)
        .filter(
            CurrentAffairsItem.subject_id == subject.id,
            CurrentAffairsItem.review_status == OptionalReviewStatusEnum.REVIEWED,
            CurrentAffairsItem.is_deleted.is_(False),
        )
        .order_by(
            CurrentAffairsItem.display_order.asc(),
            CurrentAffairsItem.id.desc(),
        )
        .all()
    )

    items = [
        CurrentAffairsItemOut(
            id=r.id,
            title=r.title,
            topic=r.topic,
            summary=r.summary,
            source_url=r.source_url,
            published_on=r.published_on.isoformat() if r.published_on else None,
            display_order=r.display_order,
        )
        for r in rows
    ]
    topics = sorted({r.topic for r in rows if r.topic})

    data = CurrentAffairsFeedOut(
        slug=subject.slug,
        name=subject.name,
        total=len(items),
        topics=topics,
        items=items,
    )
    return StandardResponse(success=True, message="Current affairs retrieved", data=data)
