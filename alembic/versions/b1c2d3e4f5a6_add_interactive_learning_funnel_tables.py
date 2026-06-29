"""add interactive learning funnel tables

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-06-29 12:00:00.000000

Creates all Interactive Learning Funnel tables (the ``gs_lms_*`` namespace):

  gs_lms_funnel_progress, gs_lms_reading_times, gs_lms_recall_attempts,
  gs_lms_mcq_lab_sessions, gs_lms_mcq_lab_attempts, gs_lms_weakness_patterns,
  gs_lms_growth_reports, gs_lms_spaced_rep_schedules, gs_lms_external_resources.

Isolation: this migration ONLY creates new tables. It does NOT alter, drop,
or recreate any existing table. FK references to existing tables are additive only.

Requirements: 13.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. gs_lms_funnel_progress
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_funnel_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "syllabus_node_id", "step_number", name="uq_gs_lms_funnel_step"),
        sa.CheckConstraint("step_number >= 1 AND step_number <= 14", name="ck_funnel_step_range"),
    )
    op.create_index("ix_gs_lms_funnel_progress_id", "gs_lms_funnel_progress", ["id"])
    op.create_index("ix_gs_lms_funnel_progress_student_id", "gs_lms_funnel_progress", ["student_id"])
    op.create_index("ix_gs_lms_funnel_progress_syllabus_node_id", "gs_lms_funnel_progress", ["syllabus_node_id"])

    # ------------------------------------------------------------------
    # 2. gs_lms_reading_times
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_reading_times",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["gs_lms_content_sections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "section_id", name="uq_gs_lms_reading_time"),
        sa.CheckConstraint("duration_seconds >= 0 AND duration_seconds <= 7200", name="ck_reading_time_range"),
    )
    op.create_index("ix_gs_lms_reading_times_id", "gs_lms_reading_times", ["id"])
    op.create_index("ix_gs_lms_reading_times_student_id", "gs_lms_reading_times", ["student_id"])
    op.create_index("ix_gs_lms_reading_times_section_id", "gs_lms_reading_times", ["section_id"])

    # ------------------------------------------------------------------
    # 3. gs_lms_recall_attempts
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_recall_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("section_label", sa.String(30), nullable=False),
        sa.Column("audio_storage_ref", sa.String(500), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("recall_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("concepts_matched", sa.JSON(), nullable=True),
        sa.Column("concepts_missed", sa.JSON(), nullable=True),
        sa.Column("stt_confidence", sa.Float(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("recall_score >= 0.0 AND recall_score <= 1.0", name="ck_recall_score_range"),
        sa.CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name="ck_confidence_score_range"),
    )
    op.create_index("ix_gs_lms_recall_attempts_id", "gs_lms_recall_attempts", ["id"])
    op.create_index("ix_gs_lms_recall_attempts_student_id", "gs_lms_recall_attempts", ["student_id"])
    op.create_index("ix_gs_lms_recall_attempts_syllabus_node_id", "gs_lms_recall_attempts", ["syllabus_node_id"])

    # ------------------------------------------------------------------
    # 4. gs_lms_mcq_lab_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_mcq_lab_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("correct_count", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gs_lms_mcq_lab_sessions_id", "gs_lms_mcq_lab_sessions", ["id"])
    op.create_index("ix_gs_lms_mcq_lab_sessions_student_id", "gs_lms_mcq_lab_sessions", ["student_id"])
    op.create_index("ix_gs_lms_mcq_lab_sessions_syllabus_node_id", "gs_lms_mcq_lab_sessions", ["syllabus_node_id"])

    # ------------------------------------------------------------------
    # 5. gs_lms_mcq_lab_attempts
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_mcq_lab_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(30), nullable=False),
        sa.Column("chosen_answer", sa.String(10), nullable=False),
        sa.Column("correct_answer", sa.String(10), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("time_taken_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["gs_lms_mcq_lab_sessions.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["gs_lms_mcq_questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gs_lms_mcq_lab_attempts_id", "gs_lms_mcq_lab_attempts", ["id"])
    op.create_index("ix_gs_lms_mcq_lab_attempts_session_id", "gs_lms_mcq_lab_attempts", ["session_id"])

    # ------------------------------------------------------------------
    # 6. gs_lms_weakness_patterns
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_weakness_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.String(30), nullable=False),
        sa.Column("total_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_weak", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "question_type", name="uq_gs_lms_weakness"),
    )
    op.create_index("ix_gs_lms_weakness_patterns_id", "gs_lms_weakness_patterns", ["id"])
    op.create_index("ix_gs_lms_weakness_patterns_student_id", "gs_lms_weakness_patterns", ["student_id"])

    # ------------------------------------------------------------------
    # 7. gs_lms_growth_reports
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_growth_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("section_metrics", sa.JSON(), nullable=False),
        sa.Column("mcq_total_score", sa.Float(), nullable=False),
        sa.Column("mcq_type_breakdown", sa.JSON(), nullable=False),
        sa.Column("mains_score", sa.Float(), nullable=True),
        sa.Column("mains_max_marks", sa.Integer(), nullable=True),
        sa.Column("next_recall_date", sa.Date(), nullable=False),
        sa.Column("recall_interval_days", sa.Integer(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("comparison_data", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gs_lms_growth_reports_id", "gs_lms_growth_reports", ["id"])
    op.create_index("ix_gs_lms_growth_reports_student_id", "gs_lms_growth_reports", ["student_id"])
    op.create_index("ix_gs_lms_growth_reports_syllabus_node_id", "gs_lms_growth_reports", ["syllabus_node_id"])

    # ------------------------------------------------------------------
    # 8. gs_lms_spaced_rep_schedules
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_spaced_rep_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("recall_score", sa.Float(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("missed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "syllabus_node_id", "sequence_number", name="uq_gs_lms_spaced_rep"),
    )
    op.create_index("ix_gs_lms_spaced_rep_schedules_id", "gs_lms_spaced_rep_schedules", ["id"])
    op.create_index("ix_gs_lms_spaced_rep_schedules_student_id", "gs_lms_spaced_rep_schedules", ["student_id"])
    op.create_index("ix_gs_lms_spaced_rep_student_due", "gs_lms_spaced_rep_schedules", ["student_id", "due_date"])

    # ------------------------------------------------------------------
    # 9. gs_lms_external_resources
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_external_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("section_label", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source_name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("relevance_description", sa.String(150), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gs_lms_external_resources_id", "gs_lms_external_resources", ["id"])
    op.create_index("ix_gs_lms_external_resources_syllabus_node_id", "gs_lms_external_resources", ["syllabus_node_id"])


def downgrade() -> None:
    op.drop_index("ix_gs_lms_external_resources_syllabus_node_id", table_name="gs_lms_external_resources")
    op.drop_index("ix_gs_lms_external_resources_id", table_name="gs_lms_external_resources")
    op.drop_table("gs_lms_external_resources")

    op.drop_index("ix_gs_lms_spaced_rep_student_due", table_name="gs_lms_spaced_rep_schedules")
    op.drop_index("ix_gs_lms_spaced_rep_schedules_student_id", table_name="gs_lms_spaced_rep_schedules")
    op.drop_index("ix_gs_lms_spaced_rep_schedules_id", table_name="gs_lms_spaced_rep_schedules")
    op.drop_table("gs_lms_spaced_rep_schedules")

    op.drop_index("ix_gs_lms_growth_reports_syllabus_node_id", table_name="gs_lms_growth_reports")
    op.drop_index("ix_gs_lms_growth_reports_student_id", table_name="gs_lms_growth_reports")
    op.drop_index("ix_gs_lms_growth_reports_id", table_name="gs_lms_growth_reports")
    op.drop_table("gs_lms_growth_reports")

    op.drop_index("ix_gs_lms_weakness_patterns_student_id", table_name="gs_lms_weakness_patterns")
    op.drop_index("ix_gs_lms_weakness_patterns_id", table_name="gs_lms_weakness_patterns")
    op.drop_table("gs_lms_weakness_patterns")

    op.drop_index("ix_gs_lms_mcq_lab_attempts_session_id", table_name="gs_lms_mcq_lab_attempts")
    op.drop_index("ix_gs_lms_mcq_lab_attempts_id", table_name="gs_lms_mcq_lab_attempts")
    op.drop_table("gs_lms_mcq_lab_attempts")

    op.drop_index("ix_gs_lms_mcq_lab_sessions_syllabus_node_id", table_name="gs_lms_mcq_lab_sessions")
    op.drop_index("ix_gs_lms_mcq_lab_sessions_student_id", table_name="gs_lms_mcq_lab_sessions")
    op.drop_index("ix_gs_lms_mcq_lab_sessions_id", table_name="gs_lms_mcq_lab_sessions")
    op.drop_table("gs_lms_mcq_lab_sessions")

    op.drop_index("ix_gs_lms_recall_attempts_syllabus_node_id", table_name="gs_lms_recall_attempts")
    op.drop_index("ix_gs_lms_recall_attempts_student_id", table_name="gs_lms_recall_attempts")
    op.drop_index("ix_gs_lms_recall_attempts_id", table_name="gs_lms_recall_attempts")
    op.drop_table("gs_lms_recall_attempts")

    op.drop_index("ix_gs_lms_reading_times_section_id", table_name="gs_lms_reading_times")
    op.drop_index("ix_gs_lms_reading_times_student_id", table_name="gs_lms_reading_times")
    op.drop_index("ix_gs_lms_reading_times_id", table_name="gs_lms_reading_times")
    op.drop_table("gs_lms_reading_times")

    op.drop_index("ix_gs_lms_funnel_progress_syllabus_node_id", table_name="gs_lms_funnel_progress")
    op.drop_index("ix_gs_lms_funnel_progress_student_id", table_name="gs_lms_funnel_progress")
    op.drop_index("ix_gs_lms_funnel_progress_id", table_name="gs_lms_funnel_progress")
    op.drop_table("gs_lms_funnel_progress")
