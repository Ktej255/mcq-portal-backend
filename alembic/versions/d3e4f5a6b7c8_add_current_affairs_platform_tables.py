"""add current affairs platform tables

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-29 18:00:00.000000

Creates all Current Affairs Platform tables (ca_ prefix):
  ca_items, ca_threads, ca_thread_items, ca_mcqs, ca_mains_questions,
  ca_student_progress, ca_syllabus_links, ca_causality_links,
  ca_revision_schedules, ca_audit_log, ca_monthly_compilations.

Isolation: this migration ONLY creates new tables. No existing tables altered.

Requirements: 14.1
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. ca_items
    op.create_table(
        "ca_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("publish_date", sa.Date(), nullable=False),
        sa.Column("subject", sa.String(30), nullable=False),
        sa.Column("secondary_subjects", sa.JSON(), nullable=True),
        sa.Column("gs_paper", sa.String(5), nullable=False),
        sa.Column("exam_relevance", sa.String(10), nullable=False),
        sa.Column("video_url", sa.String(500), nullable=True),
        sa.Column("content_blocks", sa.JSON(), nullable=False),
        sa.Column("upsc_statement_frames", sa.JSON(), nullable=True),
        sa.Column("so_what_analysis", sa.JSON(), nullable=True),
        sa.Column("source_authority", sa.String(15), nullable=False, server_default="standard"),
        sa.Column("relevance_score", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("review_status", sa.String(15), nullable=False, server_default="DRAFT"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("relevance_score >= 1 AND relevance_score <= 5", name="ck_ca_items_relevance_range"),
    )
    op.create_index("ix_ca_items_id", "ca_items", ["id"])
    op.create_index("ix_ca_items_publish_date", "ca_items", ["publish_date"])
    op.create_index("ix_ca_items_subject", "ca_items", ["subject"])
    op.create_index("ix_ca_items_review_status", "ca_items", ["review_status"])

    # 2. ca_threads
    op.create_table(
        "ca_threads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("primary_subject", sa.String(30), nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="active"),
        sa.Column("direction", sa.String(20), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ca_threads_id", "ca_threads", ["id"])
    op.create_index("ix_ca_threads_subject", "ca_threads", ["primary_subject"])
    op.create_index("ix_ca_threads_status", "ca_threads", ["status"])

    # 3. ca_thread_items
    op.create_table(
        "ca_thread_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("causality_direction", sa.String(15), nullable=True),
        sa.Column("causality_target_item_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["ca_threads.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["ca_items.id"]),
        sa.ForeignKeyConstraint(["causality_target_item_id"], ["ca_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "item_id", name="uq_ca_thread_item"),
        sa.CheckConstraint("sequence_order >= 1", name="ck_ca_thread_item_seq"),
    )
    op.create_index("ix_ca_thread_items_id", "ca_thread_items", ["id"])
    op.create_index("ix_ca_thread_items_thread_id", "ca_thread_items", ["thread_id"])
    op.create_index("ix_ca_thread_items_item_id", "ca_thread_items", ["item_id"])

    # 4. ca_mcqs
    op.create_table(
        "ca_mcqs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ca_item_id", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(30), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_answer", sa.String(5), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["ca_item_id"], ["ca_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ca_mcqs_id", "ca_mcqs", ["id"])
    op.create_index("ix_ca_mcqs_ca_item_id", "ca_mcqs", ["ca_item_id"])

    # 5. ca_mains_questions
    op.create_table(
        "ca_mains_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ca_item_id", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("gs_paper", sa.String(5), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("word_limit", sa.Integer(), nullable=False),
        sa.Column("model_answer", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["ca_item_id"], ["ca_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ca_mains_questions_id", "ca_mains_questions", ["id"])
    op.create_index("ix_ca_mains_questions_ca_item_id", "ca_mains_questions", ["ca_item_id"])

    # 6. ca_student_progress
    op.create_table(
        "ca_student_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("ca_item_id", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_steps", sa.JSON(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("mcq_score", sa.Float(), nullable=True),
        sa.Column("mcq_attempts", sa.JSON(), nullable=True),
        sa.Column("mains_attempted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("mains_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ca_item_id"], ["ca_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "ca_item_id", name="uq_ca_student_progress"),
        sa.CheckConstraint("current_step >= 1 AND current_step <= 5", name="ck_ca_progress_step_range"),
    )
    op.create_index("ix_ca_student_progress_id", "ca_student_progress", ["id"])
    op.create_index("ix_ca_student_progress_student_id", "ca_student_progress", ["student_id"])
    op.create_index("ix_ca_student_progress_ca_item_id", "ca_student_progress", ["ca_item_id"])

    # 7. ca_syllabus_links
    op.create_table(
        "ca_syllabus_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ca_item_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("link_type", sa.String(20), nullable=False, server_default="primary"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["ca_item_id"], ["ca_items.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ca_item_id", "syllabus_node_id", name="uq_ca_syllabus_link"),
    )
    op.create_index("ix_ca_syllabus_links_id", "ca_syllabus_links", ["id"])
    op.create_index("ix_ca_syllabus_links_ca_item_id", "ca_syllabus_links", ["ca_item_id"])
    op.create_index("ix_ca_syllabus_links_syllabus_node_id", "ca_syllabus_links", ["syllabus_node_id"])

    # 8. ca_causality_links
    op.create_table(
        "ca_causality_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.Integer(), nullable=False),
        sa.Column("target_item_id", sa.Integer(), nullable=False),
        sa.Column("impact_type", sa.String(100), nullable=False),
        sa.Column("impact_description", sa.Text(), nullable=True),
        sa.Column("source_gs_paper", sa.String(5), nullable=True),
        sa.Column("target_gs_paper", sa.String(5), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["source_item_id"], ["ca_items.id"]),
        sa.ForeignKeyConstraint(["target_item_id"], ["ca_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_item_id", "target_item_id", name="uq_ca_causality"),
        sa.CheckConstraint("source_item_id != target_item_id", name="ck_ca_causality_no_self"),
    )
    op.create_index("ix_ca_causality_links_id", "ca_causality_links", ["id"])
    op.create_index("ix_ca_causality_links_source", "ca_causality_links", ["source_item_id"])
    op.create_index("ix_ca_causality_links_target", "ca_causality_links", ["target_item_id"])

    # 9. ca_revision_schedules
    op.create_table(
        "ca_revision_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("quiz_type", sa.String(15), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("mcq_count", sa.Integer(), nullable=False),
        sa.Column("source_item_ids", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ca_revision_schedules_id", "ca_revision_schedules", ["id"])
    op.create_index("ix_ca_revision_student_due", "ca_revision_schedules", ["student_id", "due_date"])

    # 10. ca_audit_log
    op.create_table(
        "ca_audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ca_audit_log_id", "ca_audit_log", ["id"])
    op.create_index("ix_ca_audit_log_admin_id", "ca_audit_log", ["admin_id"])

    # 11. ca_monthly_compilations
    op.create_table(
        "ca_monthly_compilations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(15), nullable=False, server_default="DRAFT"),
        sa.Column("pdf_storage_ref", sa.String(500), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ca_monthly_compilations_id", "ca_monthly_compilations", ["id"])


def downgrade() -> None:
    op.drop_table("ca_monthly_compilations")
    op.drop_table("ca_audit_log")
    op.drop_table("ca_revision_schedules")
    op.drop_table("ca_causality_links")
    op.drop_table("ca_syllabus_links")
    op.drop_table("ca_student_progress")
    op.drop_table("ca_mains_questions")
    op.drop_table("ca_mcqs")
    op.drop_table("ca_thread_items")
    op.drop_table("ca_threads")
    op.drop_table("ca_items")
