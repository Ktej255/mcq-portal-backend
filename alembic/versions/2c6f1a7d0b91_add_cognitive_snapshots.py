"""Add cognitive snapshots

Revision ID: 2c6f1a7d0b91
Revises: 9b2c7d4e8f10
Create Date: 2026-05-12 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "2c6f1a7d0b91"
down_revision: Union[str, None] = "9b2c7d4e8f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("cognitive_snapshots"):
        op.create_table(
            "cognitive_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("attempt_id", sa.Integer(), nullable=False),
            sa.Column("cognitive_snapshot", sa.JSON(), nullable=False),
            sa.Column("telemetry_snapshot", sa.JSON(), nullable=True),
            sa.Column("reliability_snapshot", sa.JSON(), nullable=True),
            sa.Column("metric_version", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("attempt_id"),
        )
        op.create_index("ix_cognitive_snapshots_id", "cognitive_snapshots", ["id"], unique=False)
        op.create_index("ix_cognitive_snapshots_user_id", "cognitive_snapshots", ["user_id"], unique=False)
        op.create_index("ix_cognitive_snapshots_attempt_id", "cognitive_snapshots", ["attempt_id"], unique=False)


def downgrade() -> None:
    if _has_table("cognitive_snapshots"):
        op.drop_index("ix_cognitive_snapshots_attempt_id", table_name="cognitive_snapshots")
        op.drop_index("ix_cognitive_snapshots_user_id", table_name="cognitive_snapshots")
        op.drop_index("ix_cognitive_snapshots_id", table_name="cognitive_snapshots")
        op.drop_table("cognitive_snapshots")
