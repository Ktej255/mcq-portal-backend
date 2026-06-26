"""add gs_lms_video_watches table

Revision ID: c5d6e7f8a9b0
Revises: b4e7f2a1c9d3
Create Date: 2026-07-01 10:00:00.000000

Creates the ``gs_lms_video_watches`` table for tracking student video
watch events per syllabus node. Additive only — no existing tables modified.

Requirements: 1.3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gs_lms_video_watches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("watched_at", sa.DateTime(), nullable=False),
        sa.Column("watch_duration_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "syllabus_node_id", name="uq_gs_lms_video_watch"),
    )
    op.create_index(op.f("ix_gs_lms_video_watches_id"), "gs_lms_video_watches", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_video_watches_student_id"), "gs_lms_video_watches", ["student_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_video_watches_syllabus_node_id"), "gs_lms_video_watches", ["syllabus_node_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gs_lms_video_watches_syllabus_node_id"), table_name="gs_lms_video_watches")
    op.drop_index(op.f("ix_gs_lms_video_watches_student_id"), table_name="gs_lms_video_watches")
    op.drop_index(op.f("ix_gs_lms_video_watches_id"), table_name="gs_lms_video_watches")
    op.drop_table("gs_lms_video_watches")
