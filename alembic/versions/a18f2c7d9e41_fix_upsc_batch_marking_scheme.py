"""fix upsc batch marking scheme

Revision ID: a18f2c7d9e41
Revises: 9d91e7261997
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a18f2c7d9e41"
down_revision: Union[str, None] = "9d91e7261997"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tests
        SET correct_marks = 2.0,
            negative_marking_value = 0.66
        WHERE title LIKE '% Batch %'
          AND correct_marks = 1.0
          AND negative_marking_value = 0.33
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE tests
        SET correct_marks = 1.0,
            negative_marking_value = 0.33
        WHERE title LIKE '% Batch %'
          AND correct_marks = 2.0
          AND negative_marking_value = 0.66
        """
    )
