"""fix_db_drift_missing_columns

Revision ID: 9d91e7261997
Revises: dbdacf5ea416
Create Date: 2026-05-14 16:32:49.128243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d91e7261997'
down_revision: Union[str, None] = 'dbdacf5ea416'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    from sqlalchemy import inspect
    inspector = inspect(conn)
    
    # Check attempts table
    existing_attempts_cols = [c['name'] for c in inspector.get_columns('attempts')]
    
    if 'is_simulation' not in existing_attempts_cols:
        op.add_column('attempts', sa.Column('is_simulation', sa.Boolean(), nullable=True, server_default='0'))
    
    # Check questions table
    existing_questions_cols = [c['name'] for c in inspector.get_columns('questions')]
    
    if 'bilingual_alignment_score' not in existing_questions_cols:
        op.add_column('questions', sa.Column('bilingual_alignment_score', sa.Float(), nullable=True))
    if 'is_current_affairs' not in existing_questions_cols:
        op.add_column('questions', sa.Column('is_current_affairs', sa.Boolean(), nullable=True, server_default='0'))
    if 'content_date' not in existing_questions_cols:
        op.add_column('questions', sa.Column('content_date', sa.DateTime(), nullable=True))
    if 'quality_notes' not in existing_questions_cols:
        op.add_column('questions', sa.Column('quality_notes', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('attempts', 'is_simulation')
    op.drop_column('questions', 'quality_notes')
    op.drop_column('questions', 'content_date')
    op.drop_column('questions', 'is_current_affairs')
    op.drop_column('questions', 'bilingual_alignment_score')
