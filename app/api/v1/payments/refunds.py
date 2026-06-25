"""Admin-only refund endpoint for Cashfree Payment Integration.

Provides:
- POST /orders/{order_id}/refund — Initiates a full or partial refund (admin only)

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_admin
from app.api.v1.payments.dependencies import get_payment_service
from app.api.v1.payments.schemas import RefundRequest
from app.core.payments.models import PaymentOrder
from app.core.payments.service import CashfreePaymentService, CashfreeServiceError
from app.db.session import get_db
from app.models.domain import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/orders/{order_id}/refund")
def initiate_refund(
    order_id: str,
    refund_request: RefundRequest = None,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
    payment_service: CashfreePaymentService = Depends(get_payment_service),
):
    """Initiate a full or partial refund for a paid order (admin only).

    - Validates the order exists and has status "paid"
    - Validates no prior "processing" or "refunded" refund exists
    - If amount is provided, uses it as partial refund (must be between 1 and order amount)
    - If no amount, uses full order amount
    - Calls Cashfree refund API and updates order record
    """
    # 1. Fetch the order
    order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found.",
        )

    # 2. Validate order is in "paid" status
    if order.status != "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is not eligible for refund. Current status: '{order.status}'. Only 'paid' orders can be refunded.",
        )

    # 3. Validate no prior active refund exists
    if order.refund_status in ("processing", "refunded"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order already has a refund in status '{order.refund_status}'. Cannot initiate another refund.",
        )

    # 4. Determine refund amount
    if refund_request and refund_request.amount is not None:
        refund_amount = refund_request.amount
        if refund_amount < 1 or refund_amount > order.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Refund amount must be between 1 and {order.amount} (order total). Got: {refund_amount}.",
            )
    else:
        refund_amount = order.amount

    # 5. Validate cashfree_order_id exists
    if not order.cashfree_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order does not have a Cashfree order ID. Cannot process refund.",
        )

    # 6. Generate unique refund ID
    refund_id = f"REFUND-{uuid.uuid4().hex[:16].upper()}"

    # 7. Call Cashfree refund API
    try:
        result = payment_service.initiate_refund(
            cashfree_order_id=order.cashfree_order_id,
            refund_amount=float(refund_amount),
            refund_id=refund_id,
        )
    except CashfreeServiceError as exc:
        logger.error(
            "Refund initiation failed for order=%s, refund_id=%s: %s",
            order_id,
            refund_id,
            exc.message,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Refund service error: {exc.message}",
        )

    # 8. Update order record
    order.refund_status = "processing"
    order.cashfree_refund_id = result.cashfree_refund_id
    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)

    logger.info(
        "Refund initiated by admin=%s for order=%s, refund_id=%s, "
        "amount=%s, cashfree_refund_id=%s",
        current_admin.email,
        order_id,
        refund_id,
        refund_amount,
        result.cashfree_refund_id,
    )

    # 9. Return success response
    return {
        "success": True,
        "message": "Refund initiated successfully.",
        "data": {
            "order_id": order.order_id,
            "refund_id": refund_id,
            "cashfree_refund_id": result.cashfree_refund_id,
            "refund_amount": refund_amount,
            "refund_status": "processing",
            "is_partial": refund_amount < order.amount,
        },
    }
