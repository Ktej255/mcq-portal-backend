"""add gs_lms platform tables

Revision ID: a7b8c9d0e1f2
Revises: c3d4e5f6a7b8
Create Date: 2026-06-22 10:00:00.000000

Creates all GS LMS Platform tables (the ``gs_lms_*`` namespace):

  Content/syllabus domain: gs_lms_syllabus_nodes, gs_lms_content_sections,
  gs_lms_pyqs, gs_lms_mcq_questions.

  Student-activity domain: gs_lms_student_section_progress,
  gs_lms_discussion_sessions, gs_lms_discussion_turns,
  gs_lms_practice_sessions, gs_lms_practice_attempts,
  gs_lms_gap_snapshots, gs_lms_daily_plans, gs_lms_replan_events,
  gs_lms_onboarding.

Isolation: this migration ONLY creates new ``gs_lms_*`` tables. It does NOT
alter, drop, or recreate any existing table. FK references to existing tables
(gs_subjects, gs_day_lessons, users) are additive only.

Requirements: 10.1, 11.4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum types for the GS LMS domain
_GS_LMS_NODE_TYPE = sa.Enum(
    "MEGA_TOPIC", "SUB_TOPIC", "LEAF_TOPIC",
    name="gslmsnodetypeenum"
)
_GS_LMS_EXAM_TYPE = sa.Enum(
    "PRELIMS", "MAINS",
    name="gslmsexamtypeenum"
)
_GS_LMS_QUESTION_TYPE = sa.Enum(
    "STATEMENT_BASED", "MATCH_THE_FOLLOWING", "ASSERTION_REASON",
    "MAP_BASED", "CAUSE_EFFECT", "CHRONOLOGICAL", "FACTUAL",
    name="gslmsquestiontypeenum"
)
_GS_LMS_SECTION_LABEL = sa.Enum(
    "BASIC", "ADVANCED", "NCERT_LEVEL", "EXAMINER_TRAPS",
    name="gslmssectionlabelenum"
)
_GS_LMS_DISCUSSION_STATUS = sa.Enum(
    "INITIATED", "IN_PROGRESS", "COMPLETED", "ABANDONED",
    name="gslmsdiscussionstatusenum"
)
_GS_LMS_PRACTICE_SESSION_STATUS = sa.Enum(
    "IN_PROGRESS", "COMPLETED", "SUBMITTED",
    name="gslmspracticesessionstatusenum"
)

# Re-use the existing gsreviewstatusenum created in c3d4e5f6a7b8
_GS_REVIEW_STATUS = sa.Enum(
    "UNREVIEWED", "IN_REVIEW", "REVIEWED",
    name="gsreviewstatusenum", create_type=False
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. gs_lms_syllabus_nodes (self-referencing weighted tree)
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_syllabus_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("day_lesson_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("node_type", _GS_LMS_NODE_TYPE, nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("ordering_justification", sa.Text(), nullable=True),
        sa.Column("review_status", _GS_REVIEW_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["gs_subjects.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.ForeignKeyConstraint(["day_lesson_id"], ["gs_day_lessons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_syllabus_nodes_id"), "gs_lms_syllabus_nodes", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_syllabus_nodes_subject_id"), "gs_lms_syllabus_nodes", ["subject_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_syllabus_nodes_parent_id"), "gs_lms_syllabus_nodes", ["parent_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_syllabus_nodes_day_lesson_id"), "gs_lms_syllabus_nodes", ["day_lesson_id"], unique=False)

    # ------------------------------------------------------------------
    # 2. gs_lms_content_sections (progressive disclosure)
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_content_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("section_label", _GS_LMS_SECTION_LABEL, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("review_status", _GS_REVIEW_STATUS, nullable=False),
        sa.Column("authored", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_content_sections_id"), "gs_lms_content_sections", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_content_sections_syllabus_node_id"), "gs_lms_content_sections", ["syllabus_node_id"], unique=False)

    # ------------------------------------------------------------------
    # 3. gs_lms_pyqs (Previous Year Questions)
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_pyqs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("exam_type", _GS_LMS_EXAM_TYPE, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("marks", sa.Integer(), nullable=True),
        sa.Column("question_type", _GS_LMS_QUESTION_TYPE, nullable=True),
        sa.Column("review_status", _GS_REVIEW_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["subject_id"], ["gs_subjects.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_pyqs_id"), "gs_lms_pyqs", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_pyqs_subject_id"), "gs_lms_pyqs", ["subject_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_pyqs_syllabus_node_id"), "gs_lms_pyqs", ["syllabus_node_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_pyqs_exam_type"), "gs_lms_pyqs", ["exam_type"], unique=False)
    op.create_index(op.f("ix_gs_lms_pyqs_year"), "gs_lms_pyqs", ["year"], unique=False)
    op.create_index(op.f("ix_gs_lms_pyqs_review_status"), "gs_lms_pyqs", ["review_status"], unique=False)

    # ------------------------------------------------------------------
    # 4. gs_lms_mcq_questions (MCQ practice questions)
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_mcq_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_option", sa.String(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("question_type", _GS_LMS_QUESTION_TYPE, nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("review_status", _GS_REVIEW_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_mcq_questions_id"), "gs_lms_mcq_questions", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_mcq_questions_syllabus_node_id"), "gs_lms_mcq_questions", ["syllabus_node_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_mcq_questions_review_status"), "gs_lms_mcq_questions", ["review_status"], unique=False)

    # ------------------------------------------------------------------
    # 5. gs_lms_student_section_progress
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_student_section_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["gs_lms_content_sections.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "section_id", name="uq_gs_lms_student_section_progress"),
    )
    op.create_index(op.f("ix_gs_lms_student_section_progress_id"), "gs_lms_student_section_progress", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_student_section_progress_student_id"), "gs_lms_student_section_progress", ["student_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_student_section_progress_section_id"), "gs_lms_student_section_progress", ["section_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_student_section_progress_syllabus_node_id"), "gs_lms_student_section_progress", ["syllabus_node_id"], unique=False)

    # ------------------------------------------------------------------
    # 6. gs_lms_discussion_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_discussion_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("status", _GS_LMS_DISCUSSION_STATUS, nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_discussion_sessions_id"), "gs_lms_discussion_sessions", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_discussion_sessions_student_id"), "gs_lms_discussion_sessions", ["student_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_discussion_sessions_syllabus_node_id"), "gs_lms_discussion_sessions", ["syllabus_node_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_discussion_sessions_status"), "gs_lms_discussion_sessions", ["status"], unique=False)

    # ------------------------------------------------------------------
    # 7. gs_lms_discussion_turns
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_discussion_turns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("turn_order", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["gs_lms_discussion_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_discussion_turns_id"), "gs_lms_discussion_turns", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_discussion_turns_session_id"), "gs_lms_discussion_turns", ["session_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_discussion_turns_turn_order"), "gs_lms_discussion_turns", ["turn_order"], unique=False)

    # ------------------------------------------------------------------
    # 8. gs_lms_practice_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_practice_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("syllabus_node_id", sa.Integer(), nullable=False),
        sa.Column("status", _GS_LMS_PRACTICE_SESSION_STATUS, nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["syllabus_node_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_practice_sessions_id"), "gs_lms_practice_sessions", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_practice_sessions_student_id"), "gs_lms_practice_sessions", ["student_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_practice_sessions_syllabus_node_id"), "gs_lms_practice_sessions", ["syllabus_node_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_practice_sessions_status"), "gs_lms_practice_sessions", ["status"], unique=False)

    # ------------------------------------------------------------------
    # 9. gs_lms_practice_attempts
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_practice_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("chosen_answer", sa.String(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("time_taken_seconds", sa.Float(), nullable=True),
        sa.Column("question_type", _GS_LMS_QUESTION_TYPE, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["gs_lms_practice_sessions.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["gs_lms_mcq_questions.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_practice_attempts_id"), "gs_lms_practice_attempts", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_practice_attempts_session_id"), "gs_lms_practice_attempts", ["session_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_practice_attempts_question_id"), "gs_lms_practice_attempts", ["question_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_practice_attempts_student_id"), "gs_lms_practice_attempts", ["student_id"], unique=False)

    # ------------------------------------------------------------------
    # 10. gs_lms_gap_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_gap_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.Column("overall_accuracy", sa.Float(), nullable=False),
        sa.Column("weak_topics", sa.JSON(), nullable=True),
        sa.Column("weak_question_types", sa.JSON(), nullable=True),
        sa.Column("recommended_actions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_gap_snapshots_id"), "gs_lms_gap_snapshots", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_gap_snapshots_student_id"), "gs_lms_gap_snapshots", ["student_id"], unique=False)

    # ------------------------------------------------------------------
    # 11. gs_lms_daily_plans
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_daily_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("bandwidth", sa.Integer(), nullable=False),
        sa.Column("planned_items", sa.JSON(), nullable=True),
        sa.Column("completed_items", sa.JSON(), nullable=True),
        sa.Column("is_target_met", sa.Boolean(), nullable=True),
        sa.Column("projected_completion_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_daily_plans_id"), "gs_lms_daily_plans", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_daily_plans_student_id"), "gs_lms_daily_plans", ["student_id"], unique=False)
    op.create_index(op.f("ix_gs_lms_daily_plans_plan_date"), "gs_lms_daily_plans", ["plan_date"], unique=False)

    # ------------------------------------------------------------------
    # 12. gs_lms_replan_events
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_replan_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("old_bandwidth", sa.Integer(), nullable=False),
        sa.Column("new_bandwidth", sa.Integer(), nullable=False),
        sa.Column("old_projected_date", sa.Date(), nullable=True),
        sa.Column("new_projected_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gs_lms_replan_events_id"), "gs_lms_replan_events", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_replan_events_student_id"), "gs_lms_replan_events", ["student_id"], unique=False)

    # ------------------------------------------------------------------
    # 13. gs_lms_onboarding
    # ------------------------------------------------------------------
    op.create_table(
        "gs_lms_onboarding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("bandwidth_selected", sa.Integer(), nullable=True),
        sa.Column("first_topic_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["first_topic_id"], ["gs_lms_syllabus_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", name="uq_gs_lms_onboarding_student"),
    )
    op.create_index(op.f("ix_gs_lms_onboarding_id"), "gs_lms_onboarding", ["id"], unique=False)
    op.create_index(op.f("ix_gs_lms_onboarding_student_id"), "gs_lms_onboarding", ["student_id"], unique=False)



def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_index(op.f("ix_gs_lms_onboarding_student_id"), table_name="gs_lms_onboarding")
    op.drop_index(op.f("ix_gs_lms_onboarding_id"), table_name="gs_lms_onboarding")
    op.drop_table("gs_lms_onboarding")

    op.drop_index(op.f("ix_gs_lms_replan_events_student_id"), table_name="gs_lms_replan_events")
    op.drop_index(op.f("ix_gs_lms_replan_events_id"), table_name="gs_lms_replan_events")
    op.drop_table("gs_lms_replan_events")

    op.drop_index(op.f("ix_gs_lms_daily_plans_plan_date"), table_name="gs_lms_daily_plans")
    op.drop_index(op.f("ix_gs_lms_daily_plans_student_id"), table_name="gs_lms_daily_plans")
    op.drop_index(op.f("ix_gs_lms_daily_plans_id"), table_name="gs_lms_daily_plans")
    op.drop_table("gs_lms_daily_plans")

    op.drop_index(op.f("ix_gs_lms_gap_snapshots_student_id"), table_name="gs_lms_gap_snapshots")
    op.drop_index(op.f("ix_gs_lms_gap_snapshots_id"), table_name="gs_lms_gap_snapshots")
    op.drop_table("gs_lms_gap_snapshots")

    op.drop_index(op.f("ix_gs_lms_practice_attempts_student_id"), table_name="gs_lms_practice_attempts")
    op.drop_index(op.f("ix_gs_lms_practice_attempts_question_id"), table_name="gs_lms_practice_attempts")
    op.drop_index(op.f("ix_gs_lms_practice_attempts_session_id"), table_name="gs_lms_practice_attempts")
    op.drop_index(op.f("ix_gs_lms_practice_attempts_id"), table_name="gs_lms_practice_attempts")
    op.drop_table("gs_lms_practice_attempts")

    op.drop_index(op.f("ix_gs_lms_practice_sessions_status"), table_name="gs_lms_practice_sessions")
    op.drop_index(op.f("ix_gs_lms_practice_sessions_syllabus_node_id"), table_name="gs_lms_practice_sessions")
    op.drop_index(op.f("ix_gs_lms_practice_sessions_student_id"), table_name="gs_lms_practice_sessions")
    op.drop_index(op.f("ix_gs_lms_practice_sessions_id"), table_name="gs_lms_practice_sessions")
    op.drop_table("gs_lms_practice_sessions")

    op.drop_index(op.f("ix_gs_lms_discussion_turns_turn_order"), table_name="gs_lms_discussion_turns")
    op.drop_index(op.f("ix_gs_lms_discussion_turns_session_id"), table_name="gs_lms_discussion_turns")
    op.drop_index(op.f("ix_gs_lms_discussion_turns_id"), table_name="gs_lms_discussion_turns")
    op.drop_table("gs_lms_discussion_turns")

    op.drop_index(op.f("ix_gs_lms_discussion_sessions_status"), table_name="gs_lms_discussion_sessions")
    op.drop_index(op.f("ix_gs_lms_discussion_sessions_syllabus_node_id"), table_name="gs_lms_discussion_sessions")
    op.drop_index(op.f("ix_gs_lms_discussion_sessions_student_id"), table_name="gs_lms_discussion_sessions")
    op.drop_index(op.f("ix_gs_lms_discussion_sessions_id"), table_name="gs_lms_discussion_sessions")
    op.drop_table("gs_lms_discussion_sessions")

    op.drop_index(op.f("ix_gs_lms_student_section_progress_syllabus_node_id"), table_name="gs_lms_student_section_progress")
    op.drop_index(op.f("ix_gs_lms_student_section_progress_section_id"), table_name="gs_lms_student_section_progress")
    op.drop_index(op.f("ix_gs_lms_student_section_progress_student_id"), table_name="gs_lms_student_section_progress")
    op.drop_index(op.f("ix_gs_lms_student_section_progress_id"), table_name="gs_lms_student_section_progress")
    op.drop_table("gs_lms_student_section_progress")

    op.drop_index(op.f("ix_gs_lms_mcq_questions_review_status"), table_name="gs_lms_mcq_questions")
    op.drop_index(op.f("ix_gs_lms_mcq_questions_syllabus_node_id"), table_name="gs_lms_mcq_questions")
    op.drop_index(op.f("ix_gs_lms_mcq_questions_id"), table_name="gs_lms_mcq_questions")
    op.drop_table("gs_lms_mcq_questions")

    op.drop_index(op.f("ix_gs_lms_pyqs_review_status"), table_name="gs_lms_pyqs")
    op.drop_index(op.f("ix_gs_lms_pyqs_year"), table_name="gs_lms_pyqs")
    op.drop_index(op.f("ix_gs_lms_pyqs_exam_type"), table_name="gs_lms_pyqs")
    op.drop_index(op.f("ix_gs_lms_pyqs_syllabus_node_id"), table_name="gs_lms_pyqs")
    op.drop_index(op.f("ix_gs_lms_pyqs_subject_id"), table_name="gs_lms_pyqs")
    op.drop_index(op.f("ix_gs_lms_pyqs_id"), table_name="gs_lms_pyqs")
    op.drop_table("gs_lms_pyqs")

    op.drop_index(op.f("ix_gs_lms_content_sections_syllabus_node_id"), table_name="gs_lms_content_sections")
    op.drop_index(op.f("ix_gs_lms_content_sections_id"), table_name="gs_lms_content_sections")
    op.drop_table("gs_lms_content_sections")

    op.drop_index(op.f("ix_gs_lms_syllabus_nodes_day_lesson_id"), table_name="gs_lms_syllabus_nodes")
    op.drop_index(op.f("ix_gs_lms_syllabus_nodes_parent_id"), table_name="gs_lms_syllabus_nodes")
    op.drop_index(op.f("ix_gs_lms_syllabus_nodes_subject_id"), table_name="gs_lms_syllabus_nodes")
    op.drop_index(op.f("ix_gs_lms_syllabus_nodes_id"), table_name="gs_lms_syllabus_nodes")
    op.drop_table("gs_lms_syllabus_nodes")

    # Drop enum types on Postgres (SQLite doesn't have named enums)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _GS_LMS_PRACTICE_SESSION_STATUS.drop(bind, checkfirst=True)
        _GS_LMS_DISCUSSION_STATUS.drop(bind, checkfirst=True)
        _GS_LMS_SECTION_LABEL.drop(bind, checkfirst=True)
        _GS_LMS_QUESTION_TYPE.drop(bind, checkfirst=True)
        _GS_LMS_EXAM_TYPE.drop(bind, checkfirst=True)
        _GS_LMS_NODE_TYPE.drop(bind, checkfirst=True)
