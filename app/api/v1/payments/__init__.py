"""Payment API endpoints package."""

from fastapi import APIRouter

from app.api.v1.payments.orders import router as orders_router
from app.api.v1.payments.refunds import router as refunds_router
from app.api.v1.payments.subscriptions import router as subscriptions_router
from app.api.v1.payments.webhooks import router as webhooks_router

router = APIRouter()

router.include_router(orders_router, tags=["payments"])
router.include_router(refunds_router, tags=["payments-refunds"])
router.include_router(subscriptions_router, tags=["payments"])
router.include_router(webhooks_router, tags=["payment-webhooks"])
