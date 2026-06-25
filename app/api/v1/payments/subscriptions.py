"""Subscription query endpoint.

Returns the current active subscription for the authenticated student.

Requirements: 4.4, 4.5, 4.6, 4.7
"""

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.payments.schemas import SubscriptionResponse
from app.core.payments.models import Subscription
from app.db.session import get_db
from app.models.domain import User

router = APIRouter()


@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubscriptionResponse:
    """Return the current active subscription for the authenticated student.

    Queries for a subscription where status='active' and end_date > now().
    If found, returns full subscription details with remaining_days.
    If not found (no active subscription or expired), returns inactive status.
    """
    now = datetime.now(timezone.utc)

    subscription = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == current_user.google_uid,
            Subscription.status == "active",
            Subscription.end_date > now,
        )
        .order_by(Subscription.end_date.desc())
        .first()
    )

    if not subscription:
        return SubscriptionResponse(status="inactive", plan_tier=None)

    remaining_days = math.ceil(
        (subscription.end_date - now).total_seconds() / 86400
    )

    return SubscriptionResponse(
        status="active",
        plan_tier=subscription.plan_tier,
        billing_cycle=subscription.billing_cycle,
        start_date=subscription.start_date,
        end_date=subscription.end_date,
        remaining_days=remaining_days,
        order_id=subscription.order_id,
    )
