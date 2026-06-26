"""Shared dependencies for the GS LMS API routes.

Provides subject resolution from the `subject_slug` path parameter so that
all sub-routers can resolve the target subject from the URL.

Requirements traced: 9.1, 9.2
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.gs.models import GsSubject


def resolve_subject(
    subject_slug: str,
    db: Session = Depends(get_db),
) -> GsSubject:
    """Look up a GS subject by its URL slug.

    Raises HTTP 404 if:
    - The slug doesn't exist in the gs_subjects table
    - The slug isn't a valid GS subject

    Currently only "geography" is a valid slug. Others will 404 until
    content is seeded for them.
    """
    subject = (
        db.query(GsSubject)
        .filter(GsSubject.slug == subject_slug)
        .one_or_none()
    )
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject '{subject_slug}' not found",
        )
    return subject
