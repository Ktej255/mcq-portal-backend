"""Order endpoints for Cashfree Payment Integration.

Routes (mounted under /api/v1/payments):
* POST /orders — Create a new payment order (or return existing pending)
* GET /orders — Paginated order history for the authenticated student
* GET /orders/{order_id} — Single order details for the authenticated student

All endpoints require Firebase authentication via get_current_user.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.4, 9.5
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.payments.dependencies import get_payment_service
from app.api.v1.payments.schemas import (
    CreateOrderRequest,
    CreateOrderResponse,
    ErrorResponse,
    OrderHistoryItem,
    OrderHistoryResponse,
)
from app.core.payments.models import PaymentOrder
from app.core.payments.pricing import compute_plan_amount
from app.core.payments.service import CashfreePaymentService, CashfreeServiceError
from app.db.session import get_db
from app.models.domain import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_order_id() -> str:
    """Generate a unique order ID with SARIT- prefix and 12+ char identifier."""
    unique_part = uuid.uuid4().hex[:16]
    return f"SARIT-{unique_part}"


# ---------------------------------------------------------------------------
# POST /orders — Create a new payment order
# ---------------------------------------------------------------------------


@router.post(
    "/orders",
    response_model=CreateOrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def create_order(
    body: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    payment_service: CashfreePaymentService = Depends(get_payment_service),
):
    """Create a new Cashfree payment order.

    Flow:
    1. Validate plan_tier and billing_cycle (done by Pydantic schema)
    2. Compute amount server-side via pricing engine
    3. Check for existing pending order (same user + plan + cycle, <30 min old)
    4. If found, return existing session; otherwise create new order
    5. Store pending PaymentOrder in database
    6. Call Cashfree create_order to get payment_session_id
    7. Update DB record with Cashfree identifiers
    8. Return CreateOrderResponse
    """
    plan_tier = body.plan_tier
    billing_cycle = body.billing_cycle

    # Step 2: Compute amount server-side
    amount = compute_plan_amount(plan_tier, billing_cycle)

    # Step 3: Check for existing pending order (deduplication)
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    existing_order = (
        db.query(PaymentOrder)
        .filter(
            PaymentOrder.user_id == current_user.google_uid,
            PaymentOrder.plan_tier == plan_tier,
            PaymentOrder.billing_cycle == billing_cycle,
            PaymentOrder.status == "pending",
            PaymentOrder.created_at >= cutoff_time,
        )
        .order_by(PaymentOrder.created_at.desc())
        .first()
    )

    if existing_order and existing_order.payment_session_id:
        logger.info(
            "Returning existing pending order %s for user %s",
            existing_order.order_id,
            current_user.google_uid,
        )
        return CreateOrderResponse(
            order_id=existing_order.order_id,
            payment_session_id=existing_order.payment_session_id,
            amount=existing_order.amount,
            currency=existing_order.currency,
            plan_tier=existing_order.plan_tier,
            billing_cycle=existing_order.billing_cycle,
        )

    # Step 4: Generate unique order_id
    order_id = _generate_order_id()

    # Step 5: Store pending order in database
    payment_order = PaymentOrder(
        order_id=order_id,
        user_id=current_user.google_uid,
        user_email=current_user.email,
        plan_tier=plan_tier,
        billing_cycle=billing_cycle,
        amount=amount,
        currency="INR",
        status="pending",
    )
    db.add(payment_order)
    db.commit()
    db.refresh(payment_order)

    # Step 6: Call Cashfree to create payment order
    try:
        result = payment_service.create_order(
            order_id=order_id,
            amount=amount,
            customer_id=current_user.google_uid,
            customer_email=current_user.email or "",
            customer_phone="9999999999",  # Placeholder; Cashfree requires phone
            return_url=f"https://saritlearn.com/upsc/pricing/checkout?order_id={order_id}",
        )
    except CashfreeServiceError as exc:
        logger.error(
            "Cashfree order creation failed for order_id=%s: %s",
            order_id,
            exc.message,
        )
        # Mark order as failed in DB
        payment_order.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": exc.code, "message": exc.message},
        )

    # Step 7: Update DB record with Cashfree identifiers
    payment_order.cashfree_order_id = result.cashfree_order_id
    payment_order.payment_session_id = result.payment_session_id
    db.commit()
    db.refresh(payment_order)

    logger.info(
        "Payment order created: order_id=%s, amount=%d, user=%s",
        order_id,
        amount,
        current_user.google_uid,
    )

    # Step 8: Return response
    return CreateOrderResponse(
        order_id=payment_order.order_id,
        payment_session_id=result.payment_session_id,
        amount=payment_order.amount,
        currency=payment_order.currency,
        plan_tier=payment_order.plan_tier,
        billing_cycle=payment_order.billing_cycle,
    )


# ---------------------------------------------------------------------------
# GET /orders — Order history (paginated)
# ---------------------------------------------------------------------------


@router.get(
    "/orders",
    response_model=OrderHistoryResponse,
    responses={200: {"model": OrderHistoryResponse}},
)
def get_order_history(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return paginated order history for the authenticated student.

    Orders are sorted by created_at descending (most recent first).
    Default page size is 20. Returns empty list if no orders exist.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 1
    if page_size > 100:
        page_size = 100

    # Total count for this user
    total = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.user_id == current_user.google_uid)
        .count()
    )

    # Paginated query
    offset = (page - 1) * page_size
    orders = (
        db.query(PaymentOrder)
        .filter(PaymentOrder.user_id == current_user.google_uid)
        .order_by(PaymentOrder.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    order_items = [
        OrderHistoryItem(
            order_id=order.order_id,
            plan_tier=order.plan_tier,
            billing_cycle=order.billing_cycle,
            amount=order.amount,
            status=order.status,
            refund_status=order.refund_status,
            created_at=order.created_at,
        )
        for order in orders
    ]

    return OrderHistoryResponse(
        orders=order_items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# GET /orders/{order_id} — Single order details
# ---------------------------------------------------------------------------


@router.get(
    "/orders/{order_id}",
    response_model=OrderHistoryItem,
    responses={
        404: {"model": ErrorResponse},
    },
)
def get_order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return details of a single order belonging to the authenticated user.

    Returns 404 if the order does not exist or does not belong to the user.
    """
    order = (
        db.query(PaymentOrder)
        .filter(
            PaymentOrder.order_id == order_id,
            PaymentOrder.user_id == current_user.google_uid,
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": "Order not found."},
        )

    return OrderHistoryItem(
        order_id=order.order_id,
        plan_tier=order.plan_tier,
        billing_cycle=order.billing_cycle,
        amount=order.amount,
        status=order.status,
        refund_status=order.refund_status,
        created_at=order.created_at,
    )
