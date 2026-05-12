"""add user behavioral profile columns

Revision ID: ff64f4eededb
Revises: 5d9a8c3e1f22
Create Date: 2026-05-12 19:08:40.372227

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff64f4eededb'
down_revision: Union[str, None] = '5d9a8c3e1f22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    # These columns are also added by the integrity-alignment migration in
    # older branches. Keep this revision idempotent so the chain can upgrade
    # cleanly across both histories.
    if not _has_column("users", "behavioral_profile"):
        op.add_column("users", sa.Column("behavioral_profile", sa.JSON(), nullable=True))
    if not _has_column("users", "topic_mastery"):
        op.add_column("users", sa.Column("topic_mastery", sa.JSON(), nullable=True))


def downgrade() -> None:
    # No-op: the canonical owner for these columns is the earlier
    # integrity-alignment migration.
    pass
