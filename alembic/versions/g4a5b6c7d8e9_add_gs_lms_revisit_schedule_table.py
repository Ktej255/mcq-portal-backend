"""add gs_lms_revisit_schedule table

Revision ID: g4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-12 10:00:00.000000

Creates the ``gs_lms_revisit_schedule`` table for Phase 4 spaced-repetition
revisit scheduling. When a student finishes all 4 sections of a topic, three
revisit records are created at Day+3, Day+7, and Day+21. These feed into the
daily planner as Quick Recall items.

Includes:
- Foreign keys to users and gs_lms_syllabus_nodes
- Unique constraint on (student_id, syllabus_node_id, revisit_type)
- Composite index on (student_id, due_date) for efficient "today's due" queries

Requirements: 4.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g4a5b6c7d8e9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gs_lms_revisit_schedule",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), sa.ForeignKey("gs_lms_syllabus_nodes.id"), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("revisit_type", sa.String(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("(CURRENT_TIMESTAMP)")),
        # Institutional audit mixin columns
        sa.Column("institution_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # Individual column indexes
    op.create_index("ix_gs_lms_revisit_schedule_id", "gs_lms_revisit_schedule", ["id"])
    op.create_index("ix_gs_lms_revisit_schedule_student_id", "gs_lms_revisit_schedule", ["student_id"])
    op.create_index("ix_gs_lms_revisit_schedule_syllabus_node_id", "gs_lms_revisit_schedule", ["syllabus_node_id"])
    op.create_index("ix_gs_lms_revisit_schedule_due_date", "gs_lms_revisit_schedule", ["due_date"])

    # Composite index for "today's due" queries
    op.create_index(
        "ix_gs_lms_revisit_student_due",
        "gs_lms_revisit_schedule",
        ["student_id", "due_date"],
    )

    # Unique constraint: one revisit per (student, topic, type)
    op.create_unique_constraint(
        "uq_gs_lms_revisit_schedule",
        "gs_lms_revisit_schedule",
        ["student_id", "syllabus_node_id", "revisit_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_gs_lms_revisit_schedule", "gs_lms_revisit_schedule", type_="unique")
    op.drop_index("ix_gs_lms_revisit_student_due", table_name="gs_lms_revisit_schedule")
    op.drop_index("ix_gs_lms_revisit_schedule_due_date", table_name="gs_lms_revisit_schedule")
    op.drop_index("ix_gs_lms_revisit_schedule_syllabus_node_id", table_name="gs_lms_revisit_schedule")
    op.drop_index("ix_gs_lms_revisit_schedule_student_id", table_name="gs_lms_revisit_schedule")
    op.drop_index("ix_gs_lms_revisit_schedule_id", table_name="gs_lms_revisit_schedule")
    op.drop_table("gs_lms_revisit_schedule")
