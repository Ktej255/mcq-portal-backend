"""Subject selection + entitlement endpoints for the Optional Subjects Platform
(Task 13.1 / 13.2 — Phase 1I, R1.3 / R15 / R16).

Two concerns, both per-student subject-level state:

* **Subject selection (R1.3 / R15.1–R15.3)** — persists the student's chosen
  optional subject to the backend (not just client storage) so it reloads on
  return, across devices.
    - ``GET  /selection`` → the student's active selection (or the honest
      "none selected" state).
    - ``PUT  /selection`` → set/switch the active selection (history retained).

* **Entitlement seam (R16)** — ``GET /{slug}/access`` returns the access
  decision (allowed / premium / reason / upgrade path) from the swappable
  entitlement seam, with a safe configurable default until the real engine is
  wired.

Ownership (design Property 10 / R15.4): selection rows are created for and read
from only the requesting student.

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
from app.core.optional.models import OptionalSubject
from app.core.optional.student_models import SubjectSelection
from app.core.optional.entitlement import (
    EntitlementProvider,
    get_entitlement_provider,
)
from app.api.v1.optional.schemas import (
    SubjectSelectionIn,
    SubjectSelectionOut,
    AccessOut,
)

router = APIRouter()


def get_entitlement_provider_dep() -> EntitlementProvider:
    """Entitlement provider dependency (test-overridable)."""
    return get_entitlement_provider()


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


def _active_selection(db: Session, student_id: int) -> Optional[SubjectSelection]:
    return (
        db.query(SubjectSelection)
        .filter(
            SubjectSelection.student_id == student_id,
            SubjectSelection.is_active.is_(True),
        )
        .order_by(SubjectSelection.selected_at.desc(), SubjectSelection.id.desc())
        .first()
    )


def _selection_out(db: Session, selection: Optional[SubjectSelection]) -> SubjectSelectionOut:
    if selection is None:
        return SubjectSelectionOut(selected=False)
    subject = (
        db.query(OptionalSubject)
        .filter(OptionalSubject.id == selection.subject_id)
        .one_or_none()
    )
    return SubjectSelectionOut(
        selected=True,
        slug=subject.slug if subject else None,
        name=subject.name if subject else None,
        subject_id=selection.subject_id,
        selected_at=selection.selected_at.isoformat() if selection.selected_at else None,
    )


@router.get("/selection")
def get_selection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the student's active optional-subject selection (R1.3 / R15.3)."""
    selection = _active_selection(db, current_user.id)
    return StandardResponse(
        success=True,
        message="Selection retrieved",
        data=_selection_out(db, selection),
    )


@router.put("/selection")
def set_selection(
    payload: SubjectSelectionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Set or switch the student's active optional subject (R1.3 / R15.2).

    Deactivates any prior active selection (history retained for audit) and
    records the new one as active.
    """
    subject = _get_subject_or_404(db, payload.slug)

    # Deactivate prior active selections for this student (one active at a time).
    db.query(SubjectSelection).filter(
        SubjectSelection.student_id == current_user.id,
        SubjectSelection.is_active.is_(True),
    ).update({SubjectSelection.is_active: False}, synchronize_session=False)

    selection = SubjectSelection(
        student_id=current_user.id,
        subject_id=subject.id,
        is_active=True,
    )
    db.add(selection)
    db.commit()
    db.refresh(selection)

    return StandardResponse(
        success=True,
        message="Selection saved",
        data=_selection_out(db, selection),
    )


@router.get("/{slug}/access")
def get_access(
    slug: str,
    db: Session = Depends(get_db),
    provider: EntitlementProvider = Depends(get_entitlement_provider_dep),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the entitlement decision for the subject + student (R16).

    A safe, configurable default until the real entitlement engine is wired;
    the frontend gates premium content on ``allowed`` and shows ``upgrade_path``
    when restricted (R16.2).
    """
    subject = _get_subject_or_404(db, slug)
    decision = provider.check_access(student_id=current_user.id, subject=subject)
    return StandardResponse(
        success=True,
        message="Access decision",
        data=AccessOut(
            slug=subject.slug,
            allowed=decision.allowed,
            premium=decision.premium,
            reason=decision.reason,
            upgrade_path=decision.upgrade_path,
        ),
    )
