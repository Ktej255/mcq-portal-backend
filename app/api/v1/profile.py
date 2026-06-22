"""Canonical student-profile persistence (Master Plan A3 / GATE-4).

The student's self-study profile + onboarding state is the single backend
source of truth on FastAPI/Postgres — the same stack the Optional platform uses
— rather than localStorage/Supabase. The whole profile is stored as JSON so its
shape can evolve (it mirrors the frontend ``StudentProfile``) without a schema
migration.

Routes (mounted under ``/api/v1/student``, auth-gated):
* ``GET  /profile`` → the caller's stored profile (``null`` when none yet).
* ``PUT  /profile`` → upsert the caller's profile.

Ownership (mirrors the Optional ownership property): every query is scoped to
``current_user.id`` so one student can never read or overwrite another's
profile.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User, StudentProfile, StudentSubjectProgress
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse

router = APIRouter()


class StudentProfileIn(BaseModel):
    """Upsert payload — the full profile object (free-form, mirrors frontend)."""

    profile: dict[str, Any] = Field(default_factory=dict)


class SubjectProgressIn(BaseModel):
    """Upsert payload — the full per-subject progress map (free-form)."""

    progress: dict[str, Any] = Field(default_factory=dict)


def _serialize(row: StudentProfile | None) -> dict[str, Any]:
    return {
        "profile": row.profile if row else None,
        "updated_at": row.updated_at.isoformat() if row else None,
    }


@router.get("/profile")
def get_student_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the caller's stored profile, or an honest empty when none exists."""
    row = (
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == current_user.id)
        .one_or_none()
    )
    return StandardResponse(
        success=True,
        message="Profile loaded" if row else "No profile saved yet",
        data=_serialize(row),
    )


@router.put("/profile")
def upsert_student_profile(
    payload: StudentProfileIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Create or update the caller's profile (ownership-scoped)."""
    row = (
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == current_user.id)
        .one_or_none()
    )
    if row is None:
        row = StudentProfile(user_id=current_user.id, profile=payload.profile)
        db.add(row)
    else:
        row.profile = payload.profile
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return StandardResponse(success=True, message="Profile saved", data=_serialize(row))


def _serialize_progress(row: StudentSubjectProgress | None) -> dict[str, Any]:
    return {
        "progress": row.progress if row else None,
        "updated_at": row.updated_at.isoformat() if row else None,
    }


@router.get("/progress/{subject_slug}")
def get_subject_progress(
    subject_slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the caller's progress for a GS subject, honest empty when none."""
    row = (
        db.query(StudentSubjectProgress)
        .filter(
            StudentSubjectProgress.user_id == current_user.id,
            StudentSubjectProgress.subject_slug == subject_slug,
        )
        .one_or_none()
    )
    return StandardResponse(
        success=True,
        message="Progress loaded" if row else "No progress saved yet",
        data=_serialize_progress(row),
    )


@router.put("/progress/{subject_slug}")
def upsert_subject_progress(
    subject_slug: str,
    payload: SubjectProgressIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Create or update the caller's progress for a GS subject (ownership-scoped)."""
    row = (
        db.query(StudentSubjectProgress)
        .filter(
            StudentSubjectProgress.user_id == current_user.id,
            StudentSubjectProgress.subject_slug == subject_slug,
        )
        .one_or_none()
    )
    if row is None:
        row = StudentSubjectProgress(
            user_id=current_user.id, subject_slug=subject_slug, progress=payload.progress
        )
        db.add(row)
    else:
        row.progress = payload.progress
        row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return StandardResponse(success=True, message="Progress saved", data=_serialize_progress(row))
