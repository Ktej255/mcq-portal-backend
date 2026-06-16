import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.pricing import compute_amount
from app.db.session import get_db
from app.models.domain import (
    User,
    Subscription,
    SubscriptionTierEnum,
    BillingCycleEnum,
    SubscriptionStatusEnum,
)
from app.schemas.common import StandardResponse
from app.schemas.payments import CreateOrderIn, CreateOrderOut

router = APIRouter()


def _cashfree_base() -> str:
    return "https://api.cashfree.com/pg" if settings.CASHFREE_ENV == "production" else "https://sandbox.cashfree.com/pg"


def _require_config() -> None:
    if not (settings.CASHFREE_APP_ID and settings.CASHFREE_SECRET_KEY):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Cashfree is not configured")


def _enum_or(value, enum_cls, default):
    try:
        return enum_cls(value)
    except Exception:
        return default


@router.post("/cashfree/order", response_model=StandardResponse[CreateOrderOut])
def create_cashfree_order(
    payload: CreateOrderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Create a Cashfree order and return a payment_session_id for the JS checkout."""
    _require_config()
    try:
        amount = compute_amount(payload.tier, payload.cycle)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    order_id = f"sarit_{current_user.id}_{int(time.time())}"

    # Record a pending subscription (defensive: subscriptions table may not exist pre-migration).
    try:
        sub = Subscription(
            user_id=current_user.id,
            tier=_enum_or(payload.tier, SubscriptionTierEnum, SubscriptionTierEnum.FOUNDATION),
            billing_cycle=_enum_or(payload.cycle, BillingCycleEnum, BillingCycleEnum.MONTHLY),
            status=SubscriptionStatusEnum.PENDING,
            provider="cashfree",
            provider_ref=order_id,
        )
        db.add(sub)
        db.commit()
    except Exception:
        db.rollback()

    body: dict = {
        "order_id": order_id,
        "order_amount": float(amount),
        "order_currency": "INR",
        "customer_details": {
            "customer_id": str(current_user.id),
            "customer_email": current_user.email or "student@upsccommand.com",
            "customer_phone": payload.phone or "9999999999",
        },
        "order_meta": {
            "return_url": f"{settings.FRONTEND_BASE_URL}/login?redirect=/upsc&order_id={order_id}",
        },
        "order_note": f"{payload.tier}/{payload.cycle}",
    }
    if settings.BACKEND_BASE_URL:
        body["order_meta"]["notify_url"] = f"{settings.BACKEND_BASE_URL}/api/v1/payments/cashfree/webhook"

    headers = {
        "x-client-id": settings.CASHFREE_APP_ID,
        "x-client-secret": settings.CASHFREE_SECRET_KEY,
        "x-api-version": "2023-08-01",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(f"{_cashfree_base()}/orders", json=body, headers=headers, timeout=20.0)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {e}")

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Cashfree order failed: {resp.text}")

    data = resp.json()
    session_id = data.get("payment_session_id")
    if not session_id:
        raise HTTPException(status_code=502, detail="Cashfree did not return a payment session")

    return StandardResponse(
        message="Order created",
        data=CreateOrderOut(order_id=order_id, payment_session_id=session_id, amount=amount, env=settings.CASHFREE_ENV),
    )


@router.post("/cashfree/webhook")
async def cashfree_webhook(request: Request, db: Session = Depends(get_db)) -> Any:
    """Cashfree payment webhook. Verifies the signature and activates the subscription on success."""
    raw = await request.body()
    signature = request.headers.get("x-webhook-signature")
    timestamp = request.headers.get("x-webhook-timestamp")

    # Verify: base64(HMAC-SHA256(timestamp + rawBody, secret))
    if settings.CASHFREE_SECRET_KEY and signature and timestamp:
        signed = (timestamp + raw.decode("utf-8")).encode("utf-8")
        digest = hmac.new(settings.CASHFREE_SECRET_KEY.encode("utf-8"), signed, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    data = payload.get("data", {})
    order_id = (data.get("order", {}) or {}).get("order_id")
    pay_status = ((data.get("payment", {}) or {}).get("payment_status") or "").upper()

    if order_id and pay_status == "SUCCESS":
        try:
            sub = (
                db.query(Subscription)
                .filter(Subscription.provider_ref == order_id)
                .order_by(Subscription.created_at.desc())
                .first()
            )
            if sub:
                sub.status = SubscriptionStatusEnum.ACTIVE
                db.commit()
        except Exception:
            db.rollback()

    return {"ok": True}
