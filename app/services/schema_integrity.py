import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequiredTable:
    name: str
    columns: tuple[str, ...]


REQUIRED_SCHEMA: tuple[RequiredTable, ...] = (
    RequiredTable("users", ("id", "google_uid", "email", "role", "topic_mastery", "behavioral_profile")),
    RequiredTable("subjects", ("id", "name")),
    RequiredTable("topics", ("id", "name", "subject_id", "prerequisites")),
    RequiredTable("tests", ("id", "title", "subject_id", "duration_minutes", "correct_marks", "negative_marking_value")),
    RequiredTable("questions", ("id", "test_id", "topic_id", "text_en", "options_en", "correct_option", "explanation_en", "explanation_hi", "source", "difficulty")),
    RequiredTable("attempts", ("id", "user_id", "test_id", "start_time", "end_time", "status")),
    RequiredTable("attempt_answers", ("id", "attempt_id", "question_id", "selected_option", "is_correct", "time_taken_seconds", "confidence_level", "is_skipped", "is_changed", "marked_for_review", "interaction_history")),
    RequiredTable("exam_events", ("id", "attempt_id", "event_type", "question_id", "payload", "timestamp")),
    RequiredTable("reports", ("id", "attempt_id", "total_score", "accuracy", "correct_count", "incorrect_count", "unattempted_count", "topic_wise_analysis", "subject_wise_performance", "confidence_analysis", "average_time_per_question", "narrative", "processing_status", "evaluation_metadata", "generated_at")),
    RequiredTable("student_evolution", ("id", "user_id", "metric_type", "value", "timestamp")),
    RequiredTable("cognitive_snapshots", ("id", "user_id", "attempt_id", "cognitive_snapshot", "telemetry_snapshot", "reliability_snapshot", "metric_version", "created_at")),
    RequiredTable("learning_interventions", ("id", "user_id", "recommendation_id", "strategy_id", "experiment_id", "variant_id", "recommendation_payload", "status", "acceptance_metadata", "outcome_metadata", "reliability_snapshot", "metric_version", "generated_at", "updated_at")),
)


def collect_schema_drift(engine: Engine, required_schema: Iterable[RequiredTable] = REQUIRED_SCHEMA) -> dict[str, list[str]]:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    drift: dict[str, list[str]] = {}

    for table in required_schema:
        if table.name not in existing_tables:
            drift[table.name] = ["<missing table>"]
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing_columns = [column for column in table.columns if column not in existing_columns]
        if missing_columns:
            drift[table.name] = missing_columns

    return drift


def validate_startup_schema(engine: Engine, strict: bool = False) -> dict[str, list[str]]:
    drift = collect_schema_drift(engine)
    if drift:
        logger.error("Schema drift detected: %s", drift)
        if strict:
            raise RuntimeError(f"Schema drift detected: {drift}")
    else:
        logger.info("Schema integrity check passed.")
    return drift
