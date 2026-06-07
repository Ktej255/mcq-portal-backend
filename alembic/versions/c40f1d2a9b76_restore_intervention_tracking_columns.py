"""restore intervention tracking columns

Revision ID: c40f1d2a9b76
Revises: b29e6d8c4a12
Create Date: 2026-05-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c40f1d2a9b76"
down_revision: Union[str, None] = "b29e6d8c4a12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("learning_interventions")
    if "reliability_snapshot" not in columns:
        op.add_column("learning_interventions", sa.Column("reliability_snapshot", sa.JSON(), nullable=True))
    if "metric_version" not in columns:
        op.add_column("learning_interventions", sa.Column("metric_version", sa.String(), nullable=True))
    if "generated_at" not in columns:
        op.add_column("learning_interventions", sa.Column("generated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    columns = _columns("learning_interventions")
    with op.batch_alter_table("learning_interventions") as batch_op:
        if "generated_at" in columns:
            batch_op.drop_column("generated_at")
        if "metric_version" in columns:
            batch_op.drop_column("metric_version")
        if "reliability_snapshot" in columns:
            batch_op.drop_column("reliability_snapshot")
