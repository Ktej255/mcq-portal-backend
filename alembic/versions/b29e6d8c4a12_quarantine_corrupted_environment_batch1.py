"""quarantine corrupted environment batch 1 question

Revision ID: b29e6d8c4a12
Revises: a18f2c7d9e41
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b29e6d8c4a12"
down_revision: Union[str, None] = "a18f2c7d9e41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE questions
        SET status = 'ARCHIVED',
            is_deleted = 1,
            updated_by = 'content_integrity_audit_2026_05_18'
        WHERE test_id = 1
          AND question_number = 42
          AND text_en LIKE '%finalisation%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE questions
        SET status = 'PUBLISHED',
            is_deleted = 0,
            updated_by = 'content_integrity_audit_rollback_2026_05_18'
        WHERE test_id = 1
          AND question_number = 42
          AND text_en LIKE '%finalisation%'
        """
    )
