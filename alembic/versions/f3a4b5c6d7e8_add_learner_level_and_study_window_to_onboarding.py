"""add learner_level and study_window_minutes to onboarding

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-10 09:00:00.000000

Adds ``learner_level`` and ``study_window_minutes`` columns to
``gs_lms_onboarding`` for Phase 3 learner-level paths. Both columns have
server defaults so existing rows receive sensible values on migration.
Additive only — no existing columns modified or removed.

Requirements: 3.1, 3.2, 6.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gs_lms_onboarding",
        sa.Column(
            "learner_level",
            sa.String(),
            nullable=False,
            server_default="beginner",
        ),
    )
    op.add_column(
        "gs_lms_onboarding",
        sa.Column(
            "study_window_minutes",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
    )


def downgrade() -> None:
    op.drop_column("gs_lms_onboarding", "study_window_minutes")
    op.drop_column("gs_lms_onboarding", "learner_level")
