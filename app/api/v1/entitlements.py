from typing import Any, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, Subscription, SubscriptionStatusEnum
from app.core.entitlements import get_entitlements, ENTITLEMENTS, DEFAULT_TIER
from app.schemas.common import StandardResponse
from app.schemas.entitlements import Entitlements

router = APIRouter()


def _resolve_tier(user: User, db: Session) -> str:
    """Resolve the user's subscription tier from the latest ACTIVE subscription.

    Defensive: if the `subscriptions` table doesn't exist yet (migration not
    applied) the query fails and we roll back and fall back to the free tier, so
    this endpoint is safe whether or not the migration has run.
    """
    try:
        sub = (
            db.query(Subscription)
            .filter(Subscription.user_id == user.id, Subscription.status == SubscriptionStatusEnum.ACTIVE)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if sub and sub.tier:
            return getattr(sub.tier, "value", sub.tier) or DEFAULT_TIER
    except Exception:
        db.rollback()
    return DEFAULT_TIER


@router.get("/me", response_model=StandardResponse[Entitlements])
def get_my_entitlements(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Any:
    """Capabilities/limits for the authenticated user's current tier (default: free)."""
    tier = _resolve_tier(current_user, db)
    return StandardResponse(data=get_entitlements(tier))


@router.get("/catalog", response_model=StandardResponse[List[Entitlements]])
def get_entitlement_catalog() -> Any:
    """Public catalogue of every tier's capabilities/limits (free -> ultimate)."""
    catalog = [get_entitlements(t) for t in ENTITLEMENTS.keys()]
    return StandardResponse(data=catalog)
