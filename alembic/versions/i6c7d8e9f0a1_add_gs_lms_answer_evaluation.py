"""add gs_lms answer-evaluation tables

Revision ID: i6c7d8e9f0a1
Revises: 38c18954ff4d
Create Date: 2026-06-28 20:10:00.000000

Additive-only migration for the unified answer-evaluation engine (GS side):

  * adds the ``gs_paper`` (GS1–GS4) discriminator to ``gs_lms_pyqs``;
  * creates ``gs_lms_answer_attempts``, ``gs_lms_answer_sheet_images``,
    ``gs_lms_evaluation_reports``.

Isolation: ONLY adds a nullable column + new ``gs_lms_*`` tables. No existing
table is altered destructively; existing rows are unaffected (the new column is
nullable and every new table is empty).

Requirements: 9.1, 10.1, 11.1, 16.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i6c7d8e9f0a1"
down_revision: Union[str, None] = "38c18954ff4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Named enums (create_type=False so we control creation explicitly on Postgres
# and avoid duplicate-create when an enum is used by more than one column).
_GS_PAPER = sa.Enum("GS1", "GS2", "GS3", "GS4", name="gslmspaperenum", create_type=False)
_GS_ANSWER_MODE = sa.Enum(
    "TYPED", "HANDWRITTEN", name="gslmsanswermodeenum", create_type=False
)
_GS_ANSWER_STATUS = sa.Enum(
    "DRAFT", "SUBMITTED", "EVALUATED", "FAILED",
    name="gslmsanswerattemptstatusenum", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        from sqlalchemy.dialects.postgresql import ENUM as pg_ENUM
        _GS_PAPER.create(bind, checkfirst=True)
        _GS_ANSWER_MODE.create(bind, checkfirst=True)
        _GS_ANSWER_STATUS.create(bind, checkfirst=True)
        paper_type = pg_ENUM(name="gslmspaperenum", create_type=False)
        mode_type = pg_ENUM(name="gslmsanswermodeenum", create_type=False)
        status_type = pg_ENUM(name="gslmsanswerattemptstatusenum", create_type=False)
    else:
        paper_type = _GS_PAPER
        mode_type = _GS_ANSWER_MODE
        status_type = _GS_ANSWER_STATUS

    # --- 1. additive column on gs_lms_pyqs --------------------------------
    op.add_column("gs_lms_pyqs", sa.Column("gs_paper", paper_type, nullable=True))
    op.create_index(
        op.f("ix_gs_lms_pyqs_gs_paper"), "gs_lms_pyqs", ["gs_paper"], unique=False
    )

    # --- 2. gs_lms_answer_attempts ----------------------------------------
    op.create_table(
        "gs_lms_answer_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("pyq_id", sa.Integer(), nullable=True),
        sa.Column("gs_paper", paper_type, nullable=True),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("max_marks", sa.Integer(), nullable=True),
        sa.Column("mode", mode_type, nullable=False),
        sa.Column("status", status_type, nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("review_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("word_limit", sa.Integer(), nullable=True),
        sa.Column("provider_key", sa.String(), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["pyq_id"], ["gs_lms_pyqs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_answer_attempts_id"), "gs_lms_answer_attempts", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_attempts_student_id"), "gs_lms_answer_attempts", ["student_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_attempts_pyq_id"), "gs_lms_answer_attempts", ["pyq_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_attempts_gs_paper"), "gs_lms_answer_attempts", ["gs_paper"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_attempts_status"), "gs_lms_answer_attempts", ["status"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_attempts_is_deleted"), "gs_lms_answer_attempts", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_attempts_content_hash"), "gs_lms_answer_attempts", ["content_hash"], unique=False)

    # --- 3. gs_lms_answer_sheet_images ------------------------------------
    op.create_table(
        "gs_lms_answer_sheet_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("media_ref", sa.String(), nullable=False),
        sa.Column("page_order", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["attempt_id"], ["gs_lms_answer_attempts.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_answer_sheet_images_id"), "gs_lms_answer_sheet_images", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_sheet_images_attempt_id"), "gs_lms_answer_sheet_images", ["attempt_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_answer_sheet_images_student_id"), "gs_lms_answer_sheet_images", ["student_id"], unique=False)

    # --- 4. gs_lms_evaluation_reports -------------------------------------
    op.create_table(
        "gs_lms_evaluation_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=True),
        sa.Column("incomplete_sections", sa.JSON(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("marks_awarded", sa.Float(), nullable=True),
        sa.Column("max_marks", sa.Integer(), nullable=True),
        sa.Column("factual_accuracy", sa.JSON(), nullable=True),
        sa.Column("value_addition", sa.JSON(), nullable=True),
        sa.Column("original_report", sa.JSON(), nullable=True),
        sa.Column("overridden_by", sa.Integer(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["attempt_id"], ["gs_lms_answer_attempts.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["overridden_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_gs_lms_evaluation_reports_attempt"),
    )
    op.create_index(op.f("ix_gs_lms_evaluation_reports_id"), "gs_lms_evaluation_reports", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_evaluation_reports_attempt_id"), "gs_lms_evaluation_reports", ["attempt_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_evaluation_reports_student_id"), "gs_lms_evaluation_reports", ["student_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gs_lms_evaluation_reports_student_id"), table_name="gs_lms_evaluation_reports")
    op.drop_index(op.f("ix_gs_lms_evaluation_reports_attempt_id"), table_name="gs_lms_evaluation_reports")
    op.drop_index(op.f("ix_gs_lms_evaluation_reports_id"), table_name="gs_lms_evaluation_reports")
    op.drop_table("gs_lms_evaluation_reports")

    op.drop_index(op.f("ix_gs_lms_answer_sheet_images_student_id"), table_name="gs_lms_answer_sheet_images")
    op.drop_index(op.f("ix_gs_lms_answer_sheet_images_attempt_id"), table_name="gs_lms_answer_sheet_images")
    op.drop_index(op.f("ix_gs_lms_answer_sheet_images_id"), table_name="gs_lms_answer_sheet_images")
    op.drop_table("gs_lms_answer_sheet_images")

    op.drop_index(op.f("ix_gs_lms_answer_attempts_content_hash"), table_name="gs_lms_answer_attempts")
    op.drop_index(op.f("ix_gs_lms_answer_attempts_is_deleted"), table_name="gs_lms_answer_attempts")
    op.drop_index(op.f("ix_gs_lms_answer_attempts_status"), table_name="gs_lms_answer_attempts")
    op.drop_index(op.f("ix_gs_lms_answer_attempts_gs_paper"), table_name="gs_lms_answer_attempts")
    op.drop_index(op.f("ix_gs_lms_answer_attempts_pyq_id"), table_name="gs_lms_answer_attempts")
    op.drop_index(op.f("ix_gs_lms_answer_attempts_student_id"), table_name="gs_lms_answer_attempts")
    op.drop_index(op.f("ix_gs_lms_answer_attempts_id"), table_name="gs_lms_answer_attempts")
    op.drop_table("gs_lms_answer_attempts")

    op.drop_index(op.f("ix_gs_lms_pyqs_gs_paper"), table_name="gs_lms_pyqs")
    op.drop_column("gs_lms_pyqs", "gs_paper")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _GS_ANSWER_STATUS.drop(bind, checkfirst=True)
        _GS_ANSWER_MODE.drop(bind, checkfirst=True)
        _GS_PAPER.drop(bind, checkfirst=True)
