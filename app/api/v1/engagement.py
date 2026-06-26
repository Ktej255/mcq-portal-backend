"""
POST /api/v1/engagement/welcome — Trigger welcome messages for a new student.
Called after signup/profile creation.
Sends WhatsApp + Email based on available contact info.

This endpoint is fire-and-forget from the frontend's perspective.
It never fails with a 5xx even if the underlying services are unconfigured.
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, EmailStr

from app.core.engagement.email_service import send_welcome_email
from app.core.engagement.whatsapp_service import send_welcome_message

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class WelcomeEngagementRequest(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    target_year: str = "2027"
    first_topic_url: str = "/upsc"
    first_topic_title: str = "your first topic"


class WelcomeEngagementResponse(BaseModel):
    status: str  # "queued" | "skipped"
    email_queued: bool
    whatsapp_queued: bool


# ---------------------------------------------------------------------------
# Background task — actual sending happens here
# ---------------------------------------------------------------------------


def _send_engagement_messages(data: WelcomeEngagementRequest) -> None:
    """Run in background: send email + WhatsApp. Never raises."""
    plan_data = {
        "target_year": data.target_year,
        "first_topic_url": data.first_topic_url,
        "first_topic_title": data.first_topic_title,
        "plan_summary": f"Your UPSC {data.target_year} study plan is ready.",
    }

    # Send email if address provided
    if data.email:
        try:
            send_welcome_email(name=data.name, email=data.email, plan_data=plan_data)
        except Exception as exc:
            logger.error("Engagement email failed: %s", str(exc))

    # Send WhatsApp if phone provided
    if data.phone:
        try:
            send_welcome_message(
                phone=data.phone,
                student_name=data.name.split()[0],  # First name only
                first_topic_url=data.first_topic_url,
            )
        except Exception as exc:
            logger.error("Engagement WhatsApp failed: %s", str(exc))


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/welcome", response_model=WelcomeEngagementResponse)
async def trigger_welcome_engagement(
    data: WelcomeEngagementRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger welcome messages (WhatsApp + Email) for a newly signed-up student.

    This endpoint returns immediately and processes messages in the background.
    It always returns 200 — engagement failures are logged, never surfaced to client.
    """
    email_queued = data.email is not None
    whatsapp_queued = data.phone is not None

    if email_queued or whatsapp_queued:
        background_tasks.add_task(_send_engagement_messages, data)
        status = "queued"
    else:
        status = "skipped"
        logger.info("Welcome engagement skipped — no email or phone provided for %s", data.name)

    return WelcomeEngagementResponse(
        status=status,
        email_queued=email_queued,
        whatsapp_queued=whatsapp_queued,
    )
