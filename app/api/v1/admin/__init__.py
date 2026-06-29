"""Admin CMS — API router package.

All routes require ADMIN role (get_current_admin dependency).
Covers CA item CRUD, thread management, MCQ/Mains management,
bulk import, content health, and audit trail.

Routes mounted at /api/v1/admin/
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_admin
from app.api.v1.admin import ca_items

router = APIRouter(dependencies=[Depends(get_current_admin)])

router.include_router(ca_items.router, prefix="/current-affairs", tags=["admin-cms"])
