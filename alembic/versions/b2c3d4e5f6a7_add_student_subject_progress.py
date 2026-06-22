"""add student_subject_progress table (canonical GS progress persistence)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-19 16:30:00.000000

Master Plan A3 / GATE-4: backend source of truth for per-student, per-subject
GS progress (previously localStorage/Supabase-only). One row per
``(user_id, subject_slug)``; progress stored as JSON so its shape can evolve.

Additive + reversible: only creates the new ``student_subject_progress`` table;
touches no existing table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_subject_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_slug", sa.String(), nullable=False),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "subject_slug", name="uq_student_subject_progress_user_subject"),
    )
    op.create_index(
        op.f("ix_student_subject_progress_id"), "student_subject_progress", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_student_subject_progress_user_id"), "student_subject_progress", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_student_subject_progress_subject_slug"),
        "student_subject_progress",
        ["subject_slug"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_student_subject_progress_subject_slug"), table_name="student_subject_progress")
    op.drop_index(op.f("ix_student_subject_progress_user_id"), table_name="student_subject_progress")
    op.drop_index(op.f("ix_student_subject_progress_id"), table_name="student_subject_progress")
    op.drop_table("student_subject_progress")
