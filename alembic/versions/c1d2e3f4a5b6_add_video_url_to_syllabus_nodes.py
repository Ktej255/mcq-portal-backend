"""add video_url to gs_lms_syllabus_nodes

Revision ID: c1d2e3f4a5b6
Revises: b4e7f2a1c9d3
Create Date: 2026-06-24 10:00:00.000000

Adds a nullable ``video_url`` column (Text) to ``gs_lms_syllabus_nodes``.
This supports Phase 1 video integration — leaf topic nodes can now carry a
link to their associated video lecture.

Isolation: this migration ONLY adds a new nullable column. It does NOT alter,
drop, or modify any existing column or table. Fully additive and safe to run
on production data.

Requirements: 1.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b4e7f2a1c9d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gs_lms_syllabus_nodes",
        sa.Column("video_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("gs_lms_syllabus_nodes", "video_url")
