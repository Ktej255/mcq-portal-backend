"""Pydantic request/response schemas for the Cashfree Payment Integration API.

These schemas define the data contracts for all payment endpoints — order
creation, subscription queries, order history, refund requests, and error
responses.

Requirements: 1.3, 4.4, 9.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_PLAN_TIERS = ("foundation", "plus", "pro", "ultimate")
VALID_BILLING_CYCLES = ("monthly", "yearly", "two-year", "three-year")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateOrderRequest(BaseModel):
    """Request body for creating a new payment order."""

    model_config = {"extra": "forbid"}

    plan_tier: str = Field(..., description="Subscription plan tier")
    billing_cycle: str = Field(..., description="Billing cycle duration")

    @field_validator("plan_tier")
    @classmethod
    def validate_plan_tier(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_PLAN_TIERS:
            raise ValueError(
                f"Invalid plan_tier '{v}'. Must be one of: {', '.join(VALID_PLAN_TIERS)}"
            )
        return v

    @field_validator("billing_cycle")
    @classmethod
    def validate_billing_cycle(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_BILLING_CYCLES:
            raise ValueError(
                f"Invalid billing_cycle '{v}'. Must be one of: {', '.join(VALID_BILLING_CYCLES)}"
            )
        return v


class RefundRequest(BaseModel):
    """Request body for initiating a refund (admin-only)."""

    model_config = {"extra": "forbid"}

    amount: Optional[int] = Field(
        default=None,
        gt=0,
        description="Partial refund amount in INR. If omitted, full refund is issued.",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class CreateOrderResponse(BaseModel):
    """Response after successfully creating a payment order."""

    order_id: str
    payment_session_id: str
    amount: int
    currency: str = "INR"
    plan_tier: str
    billing_cycle: str


class SubscriptionResponse(BaseModel):
    """Current subscription status for the authenticated student."""

    status: str  # active | inactive | superseded | cancelled | expired
    plan_tier: Optional[str] = None
    billing_cycle: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    remaining_days: Optional[int] = None
    order_id: Optional[str] = None


class OrderHistoryItem(BaseModel):
    """A single order in the student's payment history."""

    order_id: str
    plan_tier: str
    billing_cycle: str
    amount: int
    status: str  # pending | paid | failed | expired
    refund_status: Optional[str] = None
    created_at: datetime


class OrderHistoryResponse(BaseModel):
    """Paginated list of student orders."""

    orders: list[OrderHistoryItem] = []
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    """Structured error response for payment endpoints."""

    code: str
    message: str
