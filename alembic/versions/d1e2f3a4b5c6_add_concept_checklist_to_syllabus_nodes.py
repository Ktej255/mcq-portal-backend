"""add concept_checklist to syllabus nodes

Revision ID: d1e2f3a4b5c6
Revises: c5d6e7f8a9b0
Create Date: 2026-07-08 10:00:00.000000

Adds ``concept_checklist`` JSON column to ``gs_lms_syllabus_nodes`` for
concept-level discussion scoring. Stores a JSON array of concept strings.
Additive only — no existing columns modified or removed.

Requirements: 2.2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gs_lms_syllabus_nodes",
        sa.Column("concept_checklist", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gs_lms_syllabus_nodes", "concept_checklist")
