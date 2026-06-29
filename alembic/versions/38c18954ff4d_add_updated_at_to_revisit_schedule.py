"""add_updated_at_to_revisit_schedule

Revision ID: 38c18954ff4d
Revises: h5b6c7d8e9f0
Create Date: 2026-06-28 19:38:19.207355

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38c18954ff4d'
down_revision: Union[str, None] = 'h5b6c7d8e9f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gs_lms_revisit_schedule",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_column("gs_lms_revisit_schedule", "updated_at")
