"""add gs_subjects + gs_day_lessons (canonical GS content store)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-21 10:00:00.000000

Master Plan A3/B3 / GATE-1 (standardize the live loop on the backend): make
FastAPI/Postgres the source of truth for GS *content*, starting with the
Geography 30-day guided-study curriculum, mirroring the Optional content domain.

Additive + reversible: only creates the new ``gs_subjects`` and
``gs_day_lessons`` tables; touches no existing table. No data is migrated by the
migration itself — content is ingested by ``app.core.gs.importer`` from the
committed extractor artifact.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_GS_REVIEW_STATUS = sa.Enum(
    "UNREVIEWED", "IN_REVIEW", "REVIEWED", name="gsreviewstatusenum"
)


def upgrade() -> None:
    op.create_table(
        "gs_subjects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("completeness_status", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_subjects_id"), "gs_subjects", ["id"], unique=False)
    op.create_index(op.f("ix_gs_subjects_slug"), "gs_subjects", ["slug"], unique=True)
    op.create_index(op.f("ix_gs_subjects_name"), "gs_subjects", ["name"], unique=False)

    op.create_table(
        "gs_day_lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("session_title", sa.String(), nullable=True),
        sa.Column("has_session", sa.Boolean(), nullable=False),
        sa.Column("scenes", sa.JSON(), nullable=True),
        sa.Column("subtopics", sa.JSON(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("review_status", _GS_REVIEW_STATUS, nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["gs_subjects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject_id", "day_number", name="uq_gs_day_lessons_subject_day"),
    )
    op.create_index(op.f("ix_gs_day_lessons_id"), "gs_day_lessons", ["id"], unique=False)
    op.create_index(
        op.f("ix_gs_day_lessons_subject_id"), "gs_day_lessons", ["subject_id"], unique=False
    )
    op.create_index(
        op.f("ix_gs_day_lessons_day_number"), "gs_day_lessons", ["day_number"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_gs_day_lessons_day_number"), table_name="gs_day_lessons")
    op.drop_index(op.f("ix_gs_day_lessons_subject_id"), table_name="gs_day_lessons")
    op.drop_index(op.f("ix_gs_day_lessons_id"), table_name="gs_day_lessons")
    op.drop_table("gs_day_lessons")

    op.drop_index(op.f("ix_gs_subjects_name"), table_name="gs_subjects")
    op.drop_index(op.f("ix_gs_subjects_slug"), table_name="gs_subjects")
    op.drop_index(op.f("ix_gs_subjects_id"), table_name="gs_subjects")
    op.drop_table("gs_subjects")
    # The enum type is created inline with the table (SQLite) / by create_table
    # on Postgres; drop it explicitly on backends that manage named enums.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _GS_REVIEW_STATUS.drop(bind, checkfirst=True)
