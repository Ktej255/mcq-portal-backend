"""add gs_lms_weekly_retros table

Revision ID: h5b6c7d8e9f0
Revises: g4a5b6c7d8e9
Create Date: 2026-07-15 10:00:00.000000

Creates the ``gs_lms_weekly_retros`` table for Phase 5 weekly retrospective.
Every 7th planned day, a retro item is injected into the planner. The student
reflects on topics completed, gaps noticed, and provides free-text reflection.

Requirements: 7.1, 7.4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h5b6c7d8e9f0"
down_revision: Union[str, None] = "g4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gs_lms_weekly_retros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("topics_completed", sa.JSON(), nullable=True),
        sa.Column("gap_summary", sa.JSON(), nullable=True),
        sa.Column("reflection_text", sa.String(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "week_number", name="uq_gs_lms_weekly_retro"),
    )
    op.create_index("ix_gs_lms_weekly_retros_id", "gs_lms_weekly_retros", ["id"])
    op.create_index("ix_gs_lms_weekly_retros_student_id", "gs_lms_weekly_retros", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_gs_lms_weekly_retros_student_id", table_name="gs_lms_weekly_retros")
    op.drop_index("ix_gs_lms_weekly_retros_id", table_name="gs_lms_weekly_retros")
    op.drop_table("gs_lms_weekly_retros")
