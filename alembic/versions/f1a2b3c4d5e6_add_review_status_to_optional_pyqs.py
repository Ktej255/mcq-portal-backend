"""add review_status to optional_pyqs

Revision ID: f1a2b3c4d5e6
Revises: e93f3dcfde5b
Create Date: 2026-06-19 09:30:00.000000

Adds a nullable ``review_status`` column (enum ``optionalreviewstatusenum``,
already created by revision ``e93f3dcfde5b``) to ``optional_pyqs`` so a PYQ row
can carry the same honesty/review gate as ``optional_content_units``. This lets
the PYQ read layer (spec task 7.2) keep UNREVIEWED / draft questions out of the
student view exactly like content (R17.2, R17.3, design Property 8), and lets
the Geography PYQ seeder (task 7.1) stamp every authored-but-unverified draft
question as UNREVIEWED.

Isolation (Requirement 2 / design Property 9): this migration ONLY alters the
``optional_pyqs`` table. It does NOT touch any non-``optional_`` table, the GS
Geography domain, or any other ``optional_*`` table. The column is nullable, so
no data backfill is required and the change is fully reversible.

Requirements: 4.1, 4.2, 4.3, 17.1, 17.2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e93f3dcfde5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The enum type already exists (created with optional_content_units in
# revision e93f3dcfde5b). ``create_type=False`` prevents Postgres from trying
# to CREATE TYPE a second time; it is a no-op on SQLite.
_REVIEW_STATUS_ENUM = sa.Enum(
    "UNREVIEWED",
    "IN_REVIEW",
    "REVIEWED",
    name="optionalreviewstatusenum",
    create_type=False,
)


def upgrade() -> None:
    # Batch mode keeps this safe on SQLite (dev) and uses a native ALTER on
    # Postgres. Touches ONLY optional_pyqs.
    with op.batch_alter_table("optional_pyqs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("review_status", _REVIEW_STATUS_ENUM, nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_optional_pyqs_review_status"),
            ["review_status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("optional_pyqs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_optional_pyqs_review_status"))
        batch_op.drop_column("review_status")
