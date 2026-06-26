"""SQLAlchemy models for Cashfree Payment Integration.

Covers entities: PaymentOrder, Subscription, PaymentWebhookLog.

These models register on the shared declarative ``Base`` (``app.db.session.Base``)
so that a single Alembic ``target_metadata`` covers the whole schema.

Requirements: 1.5, 3.7, 4.1
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

from sqlalchemy.orm import relationship

from app.db.session import Base


# ---------------------------------------------------------------------------
# Payment Orders
# ---------------------------------------------------------------------------

class PaymentOrder(Base):
    """A Cashfree payment order created when a student initiates checkout.

    Stores the full lifecycle: pending → paid/failed, optional refund status,
    and Cashfree-provided identifiers for reconciliation.
    """
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(64), unique=True, nullable=False)
    cashfree_order_id = Column(String(128), nullable=True)
    payment_session_id = Column(String(256), nullable=True)
    user_id = Column(String(128), nullable=False)
    user_email = Column(String(256), nullable=True)
    plan_tier = Column(String(20), nullable=False)
    billing_cycle = Column(String(20), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), default="INR", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    refund_status = Column(String(20), nullable=True)
    cashfree_refund_id = Column(String(128), nullable=True)
    payment_method = Column(String(64), nullable=True)
    cashfree_payment_id = Column(String(128), nullable=True)
    webhook_received_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    subscription = relationship(
        "Subscription", back_populates="order", uselist=False
    )

    __table_args__ = (
        Index("idx_payment_orders_user_id", "user_id"),
        Index("idx_payment_orders_status", "status"),
        Index("idx_payment_orders_cashfree_order_id", "cashfree_order_id"),
    )


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class Subscription(Base):
    """Active subscription record created upon successful payment confirmation.

    Tracks plan tier, billing cycle, validity window, and lifecycle status
    (active → superseded/cancelled/expired).
    """
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(128), nullable=False)
    plan_tier = Column(String(20), nullable=False)
    billing_cycle = Column(String(20), nullable=False)
    order_id = Column(
        String(64), ForeignKey("payment_orders.order_id"), nullable=False
    )
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    order = relationship("PaymentOrder", back_populates="subscription")

    __table_args__ = (
        Index("idx_subscriptions_user_id", "user_id"),
        Index("idx_subscriptions_status", "status"),
        Index("idx_subscriptions_end_date", "end_date"),
    )


# ---------------------------------------------------------------------------
# Webhook Audit Log
# ---------------------------------------------------------------------------

class PaymentWebhookLog(Base):
    """Audit log for every incoming Cashfree webhook payload.

    Records event type, signature validity, processing outcome, and the raw
    JSONB payload for debugging and reconciliation.
    """
    __tablename__ = "payment_webhook_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(64), nullable=True)
    order_id = Column(String(64), nullable=True)
    cashfree_order_id = Column(String(128), nullable=True)
    payment_status = Column(String(32), nullable=True)
    raw_payload = Column(JSONB, nullable=True)
    signature_valid = Column(Boolean, nullable=True)
    processing_outcome = Column(String(32), nullable=True)
    source_ip = Column(String(45), nullable=True)
    received_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("idx_webhook_logs_order_id", "order_id"),
    )


__all__ = [
    "PaymentOrder",
    "Subscription",
    "PaymentWebhookLog",
]
