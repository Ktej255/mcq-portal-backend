"""Current Affairs Platform — student-facing API router package.

All routes require authentication (get_current_user dependency).
Only PUBLISHED items are returned to students (publish-gate enforced).

Routes mounted at /api/v1/current-affairs/
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.v1.current_affairs import feed
from app.api.v1.current_affairs import threads
from app.api.v1.current_affairs import funnel
from app.api.v1.current_affairs import progress
from app.api.v1.current_affairs import doubt_chat
from app.api.v1.current_affairs import quick_test

router = APIRouter(dependencies=[Depends(get_current_user)])

router.include_router(feed.router, tags=["current-affairs"])
router.include_router(threads.router, tags=["current-affairs"])
router.include_router(funnel.router, tags=["current-affairs"])
router.include_router(progress.router, tags=["current-affairs"])
router.include_router(doubt_chat.router, tags=["current-affairs"])
router.include_router(quick_test.router, tags=["current-affairs"])
