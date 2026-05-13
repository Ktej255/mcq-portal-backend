"""merge_operational_branches

Revision ID: e8b7bfcab8da
Revises: 0006_truth_status, 64afae94d021
Create Date: 2026-05-13 17:44:21.089868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b7bfcab8da'
down_revision: Union[str, None] = ('0006_truth_status', '64afae94d021')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
