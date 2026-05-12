"""Add learning interventions

Revision ID: 5d9a8c3e1f22
Revises: 2c6f1a7d0b91
Create Date: 2026-05-12 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "5d9a8c3e1f22"
down_revision: Union[str, None] = "2c6f1a7d0b91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("learning_interventions"):
        op.create_table(
            "learning_interventions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("recommendation_id", sa.String(), nullable=False),
            sa.Column("strategy_id", sa.String(), nullable=False),
            sa.Column("experiment_id", sa.String(), nullable=True),
            sa.Column("variant_id", sa.String(), nullable=True),
            sa.Column("recommendation_payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("acceptance_metadata", sa.JSON(), nullable=True),
            sa.Column("outcome_metadata", sa.JSON(), nullable=True),
            sa.Column("reliability_snapshot", sa.JSON(), nullable=True),
            sa.Column("metric_version", sa.String(), nullable=False),
            sa.Column("generated_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("recommendation_id"),
        )
        op.create_index("ix_learning_interventions_id", "learning_interventions", ["id"], unique=False)
        op.create_index("ix_learning_interventions_user_id", "learning_interventions", ["user_id"], unique=False)
        op.create_index("ix_learning_interventions_recommendation_id", "learning_interventions", ["recommendation_id"], unique=False)
        op.create_index("ix_learning_interventions_strategy_id", "learning_interventions", ["strategy_id"], unique=False)
        op.create_index("ix_learning_interventions_experiment_id", "learning_interventions", ["experiment_id"], unique=False)
        op.create_index("ix_learning_interventions_variant_id", "learning_interventions", ["variant_id"], unique=False)
        op.create_index("ix_learning_interventions_status", "learning_interventions", ["status"], unique=False)


def downgrade() -> None:
    if _has_table("learning_interventions"):
        op.drop_index("ix_learning_interventions_status", table_name="learning_interventions")
        op.drop_index("ix_learning_interventions_variant_id", table_name="learning_interventions")
        op.drop_index("ix_learning_interventions_experiment_id", table_name="learning_interventions")
        op.drop_index("ix_learning_interventions_strategy_id", table_name="learning_interventions")
        op.drop_index("ix_learning_interventions_recommendation_id", table_name="learning_interventions")
        op.drop_index("ix_learning_interventions_user_id", table_name="learning_interventions")
        op.drop_index("ix_learning_interventions_id", table_name="learning_interventions")
        op.drop_table("learning_interventions")
