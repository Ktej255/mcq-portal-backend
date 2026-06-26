"""
Email webhook endpoints for triggering welcome sequence emails.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.email.sequences import trigger_immediate_welcome, send_welcome_sequence_email
from app.models.domain import User

router = APIRouter(prefix="/email", tags=["email"])


@router.post("/welcome")
def send_welcome(current_user: User = Depends(get_current_user)):
    """Trigger welcome email for the current user (called after signup/onboarding)."""
    success = trigger_immediate_welcome(
        current_user.email,
        current_user.full_name or "Aspirant",
    )
    return {"sent": success}


@router.post("/sequence/{days_since_signup}")
def send_sequence_email(
    days_since_signup: int,
    current_user: User = Depends(get_current_user),
):
    """Trigger a specific sequence email based on days since signup.

    This endpoint can be called by a cron job or scheduler to send
    the appropriate email in the welcome sequence.
    """
    success = send_welcome_sequence_email(
        current_user.email,
        current_user.full_name or "Aspirant",
        days_since_signup,
    )
    return {"sent": success, "day": days_since_signup}
