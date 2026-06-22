"""add student_profiles table (canonical student profile persistence)

Revision ID: a1b2c3d4e5f6
Revises: d8f3a1c6e92b
Create Date: 2026-06-19 16:00:00.000000

Master Plan A3 / GATE-4: make the FastAPI/Postgres backend the single source of
truth for the student's self-study profile + onboarding state (previously
localStorage/Supabase-only). One row per user; the profile is stored as JSON so
its shape can evolve without further migrations.

Additive + reversible: this migration ONLY creates a new ``student_profiles``
table and does not touch any existing table (GS, Optional, or core), so it is
fully reversible by dropping the new table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d8f3a1c6e92b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_student_profiles_id"), "student_profiles", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_student_profiles_user_id"), "student_profiles", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_student_profiles_user_id"), table_name="student_profiles")
    op.drop_index(op.f("ix_student_profiles_id"), table_name="student_profiles")
    op.drop_table("student_profiles")
