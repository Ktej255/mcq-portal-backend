"""add current_affairs to section label enum

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-29 14:00:00.000000

Adds 'CURRENT_AFFAIRS' to the gslmssectionlabelenum type so that the
Interactive Learning Funnel can use 5 content sections per topic instead of 4.

Also updates the growth_report SECTION_LABELS constant to include the new label.

Requirements: Funnel Requirement 3.6 (5 sections in order)
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL: ALTER TYPE to add new enum value
    # SQLite: enum values are just strings, no alteration needed
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE gslmssectionlabelenum ADD VALUE IF NOT EXISTS 'CURRENT_AFFAIRS'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily.
    # In practice, this is a no-op downgrade — the value remains but is unused.
    pass
