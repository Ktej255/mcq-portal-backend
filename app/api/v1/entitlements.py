from typing import Any, List

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.domain import User
from app.core.entitlements import get_entitlements, ENTITLEMENTS, DEFAULT_TIER
from app.schemas.common import StandardResponse
from app.schemas.entitlements import Entitlements

router = APIRouter()


def _resolve_tier(user: User) -> str:
    """Resolve the user's subscription tier.

    Forward-compatible: when a subscription tier is persisted on the user (or a
    related Subscription record), read it here. Until then every account is on
    the free entry tier.
    """
    return getattr(user, "plan_tier", None) or DEFAULT_TIER


@router.get("/me", response_model=StandardResponse[Entitlements])
def get_my_entitlements(current_user: User = Depends(get_current_user)) -> Any:
    """Capabilities/limits for the authenticated user's current tier (default: free)."""
    tier = _resolve_tier(current_user)
    return StandardResponse(data=get_entitlements(tier))


@router.get("/catalog", response_model=StandardResponse[List[Entitlements]])
def get_entitlement_catalog() -> Any:
    """Public catalogue of every tier's capabilities/limits (free -> ultimate)."""
    catalog = [get_entitlements(t) for t in ENTITLEMENTS.keys()]
    return StandardResponse(data=catalog)
