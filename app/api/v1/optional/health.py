from fastapi import APIRouter, Depends
from typing import Any

from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional import MODULE_NAME

router = APIRouter()


@router.get("/health")
def optional_health(current_user: User = Depends(get_current_user)) -> Any:
    """Health/contract endpoint for the Optional Subjects Platform.

    Confirms the optional module is wired into the API and that all of its
    routes are auth-gated via the existing authentication dependency. Returns a
    small JSON payload describing the module status.
    """
    data = {
        "module": MODULE_NAME,
        "status": "healthy",
        "authenticated": True,
    }
    return StandardResponse(success=True, message="Optional platform module is online", data=data)
