"""add optional current-affairs table (subject-specific feature)

Revision ID: d8f3a1c6e92b
Revises: c7e2a9f4b801
Create Date: 2026-06-19 14:00:00.000000

Adds ``optional_current_affairs`` backing the subject-specific Current-Affairs
feature module (spec task 17.1, R11.4) — presented for subjects whose config
enables the ``currentAffairs`` feature (Public Administration). Carries a
``review_status`` (enum ``optionalreviewstatusenum``, already created by
revision ``e93f3dcfde5b``) so draft items stay gated from students until
reviewed (R17.2, R17.3, design Property 8).

Isolation (Requirement 2 / design Property 9): this migration ONLY creates a
new ``optional_*`` table; it does not touch GS Geography or any existing table,
so it is fully reversible by dropping the new table.

Requirements: 11.4, 17.2, 17.3, 19.2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8f3a1c6e92b"
down_revision: Union[str, None] = "c7e2a9f4b801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REVIEW_STATUS_ENUM = sa.Enum(
    "UNREVIEWED",
    "IN_REVIEW",
    "REVIEWED",
    name="optionalreviewstatusenum",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "optional_current_affairs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("review_status", _REVIEW_STATUS_ENUM, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["optional_subjects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_optional_current_affairs_id"), "optional_current_affairs", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_optional_current_affairs_subject_id"),
        "optional_current_affairs",
        ["subject_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_current_affairs_topic"),
        "optional_current_affairs",
        ["topic"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_current_affairs_published_on"),
        "optional_current_affairs",
        ["published_on"],
        unique=False,
    )
    op.create_index(
        op.f("ix_optional_current_affairs_review_status"),
        "optional_current_affairs",
        ["review_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("optional_current_affairs")
