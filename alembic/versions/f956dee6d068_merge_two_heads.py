"""merge two heads

Revision ID: f956dee6d068
Revises: d3e4f5a6b7c8, i6c7d8e9f0a1
Create Date: 2026-06-29 18:43:41.747837

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f956dee6d068'
down_revision: Union[str, None] = ('d3e4f5a6b7c8', 'i6c7d8e9f0a1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
