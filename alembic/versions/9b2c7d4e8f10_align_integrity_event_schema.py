"""Align integrity and event schema

Revision ID: 9b2c7d4e8f10
Revises: 1a4a1f9a032c
Create Date: 2026-05-12 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "9b2c7d4e8f10"
down_revision: Union[str, None] = "1a4a1f9a032c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspect(op.get_bind()).get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    _add_column_if_missing("users", sa.Column("topic_mastery", sa.JSON(), nullable=True))
    _add_column_if_missing("users", sa.Column("behavioral_profile", sa.JSON(), nullable=True))

    _add_column_if_missing("topics", sa.Column("prerequisites", sa.JSON(), nullable=True))

    _add_column_if_missing("questions", sa.Column("explanation_en", sa.String(), nullable=True))
    _add_column_if_missing("questions", sa.Column("explanation_hi", sa.String(), nullable=True))
    _add_column_if_missing("questions", sa.Column("source", sa.String(), nullable=True))
    _create_index_if_missing("ix_questions_source", "questions", ["source"])
    _create_index_if_missing("ix_questions_difficulty", "questions", ["difficulty"])

    _add_column_if_missing("attempt_answers", sa.Column("interaction_history", sa.JSON(), nullable=True))

    if not _has_table("exam_events"):
        op.create_table(
            "exam_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("attempt_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("question_id", sa.Integer(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["attempt_id"], ["attempts.id"]),
            sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_exam_events_id", "exam_events", ["id"], unique=False)
        op.create_index("ix_exam_events_event_type", "exam_events", ["event_type"], unique=False)
    else:
        _create_index_if_missing("ix_exam_events_id", "exam_events", ["id"])
        _create_index_if_missing("ix_exam_events_event_type", "exam_events", ["event_type"])

    _add_column_if_missing("reports", sa.Column("topic_wise_analysis", sa.JSON(), nullable=True))
    _add_column_if_missing("reports", sa.Column("subject_wise_performance", sa.JSON(), nullable=True))
    _add_column_if_missing("reports", sa.Column("average_time_per_question", sa.Float(), nullable=True))
    _add_column_if_missing("reports", sa.Column("narrative", sa.String(), nullable=True))
    _add_column_if_missing("reports", sa.Column("processing_status", sa.String(), nullable=False, server_default="COMPLETED"))
    _add_column_if_missing("reports", sa.Column("evaluation_metadata", sa.JSON(), nullable=True))

    if not _has_table("student_evolution"):
        op.create_table(
            "student_evolution",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("metric_type", sa.String(), nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_student_evolution_id", "student_evolution", ["id"], unique=False)
        op.create_index("ix_student_evolution_metric_type", "student_evolution", ["metric_type"], unique=False)


def downgrade() -> None:
    if _has_table("student_evolution"):
        op.drop_index("ix_student_evolution_metric_type", table_name="student_evolution")
        op.drop_index("ix_student_evolution_id", table_name="student_evolution")
        op.drop_table("student_evolution")

    for column_name in ["evaluation_metadata", "processing_status", "narrative", "average_time_per_question", "subject_wise_performance"]:
        if _has_column("reports", column_name):
            op.drop_column("reports", column_name)

    if _has_table("exam_events"):
        op.drop_index("ix_exam_events_event_type", table_name="exam_events")
        op.drop_index("ix_exam_events_id", table_name="exam_events")
        op.drop_table("exam_events")

    if _has_column("attempt_answers", "interaction_history"):
        op.drop_column("attempt_answers", "interaction_history")

    for index_name in ["ix_questions_difficulty", "ix_questions_source"]:
        indexes = {index["name"] for index in inspect(op.get_bind()).get_indexes("questions")}
        if index_name in indexes:
            op.drop_index(index_name, table_name="questions")
    for column_name in ["source", "explanation_hi", "explanation_en"]:
        if _has_column("questions", column_name):
            op.drop_column("questions", column_name)

    if _has_column("topics", "prerequisites"):
        op.drop_column("topics", "prerequisites")
    for column_name in ["behavioral_profile", "topic_mastery"]:
        if _has_column("users", column_name):
            op.drop_column("users", column_name)
