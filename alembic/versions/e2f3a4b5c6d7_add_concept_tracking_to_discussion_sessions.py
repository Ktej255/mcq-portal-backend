"""add concept tracking to discussion sessions

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-08 11:00:00.000000

Adds concept tracking columns to ``gs_lms_discussion_sessions`` for
Phase 2 concept-level scoring. Three new nullable columns track which
concepts the student matched, which were missed, and the overall match
percentage. Additive only — no existing columns modified or removed.

Requirements: 2.1, 2.5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gs_lms_discussion_sessions",
        sa.Column("concepts_matched", sa.JSON(), nullable=True),
    )
    op.add_column(
        "gs_lms_discussion_sessions",
        sa.Column("concepts_missed", sa.JSON(), nullable=True),
    )
    op.add_column(
        "gs_lms_discussion_sessions",
        sa.Column("match_percentage", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gs_lms_discussion_sessions", "match_percentage")
    op.drop_column("gs_lms_discussion_sessions", "concepts_missed")
    op.drop_column("gs_lms_discussion_sessions", "concepts_matched")
