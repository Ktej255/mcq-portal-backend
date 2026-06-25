"""add payment tables

Revision ID: b4e7f2a1c9d3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-23 12:00:00.000000

Creates the payment integration tables:

  - payment_orders: Cashfree payment orders with full lifecycle tracking
  - subscriptions: Active subscription records linked to confirmed orders
  - payment_webhook_logs: Audit log for every incoming Cashfree webhook

Isolation: this migration ONLY creates new payment tables. It does NOT alter,
drop, or modify any existing table. FK references are internal only
(subscriptions → payment_orders).

Requirements: 1.5, 4.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b4e7f2a1c9d3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. payment_orders
    # ------------------------------------------------------------------
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("cashfree_order_id", sa.String(128), nullable=True),
        sa.Column("payment_session_id", sa.String(256), nullable=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("user_email", sa.String(256), nullable=True),
        sa.Column("plan_tier", sa.String(20), nullable=False),
        sa.Column("billing_cycle", sa.String(20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("refund_status", sa.String(20), nullable=True),
        sa.Column("cashfree_refund_id", sa.String(128), nullable=True),
        sa.Column("payment_method", sa.String(64), nullable=True),
        sa.Column("cashfree_payment_id", sa.String(128), nullable=True),
        sa.Column("webhook_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_payment_orders_order_id"),
    )
    op.create_index(
        op.f("ix_payment_orders_id"), "payment_orders", ["id"], unique=False
    )
    op.create_index(
        "idx_payment_orders_user_id", "payment_orders", ["user_id"], unique=False
    )
    op.create_index(
        "idx_payment_orders_status", "payment_orders", ["status"], unique=False
    )
    op.create_index(
        "idx_payment_orders_cashfree_order_id",
        "payment_orders",
        ["cashfree_order_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 2. subscriptions
    # ------------------------------------------------------------------
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("plan_tier", sa.String(20), nullable=False),
        sa.Column("billing_cycle", sa.String(20), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["payment_orders.order_id"],
            name="fk_subscriptions_order_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_subscriptions_id"), "subscriptions", ["id"], unique=False
    )
    op.create_index(
        "idx_subscriptions_user_id", "subscriptions", ["user_id"], unique=False
    )
    op.create_index(
        "idx_subscriptions_status", "subscriptions", ["status"], unique=False
    )
    op.create_index(
        "idx_subscriptions_end_date", "subscriptions", ["end_date"], unique=False
    )

    # ------------------------------------------------------------------
    # 3. payment_webhook_logs
    # ------------------------------------------------------------------
    op.create_table(
        "payment_webhook_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=True),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("cashfree_order_id", sa.String(128), nullable=True),
        sa.Column("payment_status", sa.String(32), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("signature_valid", sa.Boolean(), nullable=True),
        sa.Column("processing_outcome", sa.String(32), nullable=True),
        sa.Column("source_ip", sa.String(45), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_webhook_logs_id"),
        "payment_webhook_logs",
        ["id"],
        unique=False,
    )
    op.create_index(
        "idx_webhook_logs_order_id",
        "payment_webhook_logs",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop in reverse dependency order: webhook_logs first (no FK deps),
    # then subscriptions (FK to payment_orders), then payment_orders.

    # payment_webhook_logs
    op.drop_index("idx_webhook_logs_order_id", table_name="payment_webhook_logs")
    op.drop_index(op.f("ix_payment_webhook_logs_id"), table_name="payment_webhook_logs")
    op.drop_table("payment_webhook_logs")

    # subscriptions
    op.drop_index("idx_subscriptions_end_date", table_name="subscriptions")
    op.drop_index("idx_subscriptions_status", table_name="subscriptions")
    op.drop_index("idx_subscriptions_user_id", table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_id"), table_name="subscriptions")
    op.drop_table("subscriptions")

    # payment_orders
    op.drop_index("idx_payment_orders_cashfree_order_id", table_name="payment_orders")
    op.drop_index("idx_payment_orders_status", table_name="payment_orders")
    op.drop_index("idx_payment_orders_user_id", table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_id"), table_name="payment_orders")
    op.drop_table("payment_orders")
