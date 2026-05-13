"""add_intelligence_fields_to_report

Revision ID: ce88a5aa7844
Revises: 6a54c4d280dd
Create Date: 2026-05-13 12:11:40.091379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce88a5aa7844'
down_revision: Union[str, None] = '6a54c4d280dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adding columns only to avoid SQLite ALTER limitations
    op.add_column('reports', sa.Column('behavioral_analysis', sa.JSON(), nullable=True))
    op.add_column('reports', sa.Column('telemetry_summary', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('reports', 'telemetry_summary')
    op.drop_column('reports', 'behavioral_analysis')
