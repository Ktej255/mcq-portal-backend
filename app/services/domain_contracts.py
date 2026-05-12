from __future__ import annotations

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

CANONICAL_OPTION_KEYS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
OPTION_ID_SEPARATOR = "_opt_"


class ContractViolation(ValueError):
    pass


class CanonicalConfidence(str, Enum):
    BLIND_GUESS = "BLIND_GUESS"
    FIFTY_FIFTY = "FIFTY_FIFTY"
    EDUCATED_GUESS = "EDUCATED_GUESS"
    FAIRLY_SURE = "FAIRLY_SURE"
    HUNDRED_PERCENT = "HUNDRED_PERCENT"


CONFIDENCE_ALIASES = {
    "50_50": CanonicalConfidence.FIFTY_FIFTY.value,
    "100_SURE": CanonicalConfidence.HUNDRED_PERCENT.value,
}


class CanonicalExamEvent(str, Enum):
    QUESTION_VIEWED = "QUESTION_VIEWED"
    ANSWER_CHANGED = "ANSWER_CHANGED"
    CONFIDENCE_SELECTED = "CONFIDENCE_SELECTED"
    REVIEW_MARKED = "REVIEW_MARKED"
    TAB_SWITCH = "TAB_SWITCH"
    FULLSCREEN_EXIT = "FULLSCREEN_EXIT"
    SUBMIT_CLICKED = "SUBMIT_CLICKED"
    HEARTBEAT = "HEARTBEAT"
    FOCUS_STATE_CHANGED = "FOCUS_STATE_CHANGED"
    IDLE_STATE_CHANGED = "IDLE_STATE_CHANGED"


EVENTS_REQUIRING_QUESTION = {
    CanonicalExamEvent.QUESTION_VIEWED.value,
    CanonicalExamEvent.ANSWER_CHANGED.value,
    CanonicalExamEvent.CONFIDENCE_SELECTED.value,
    CanonicalExamEvent.REVIEW_MARKED.value,
}

MAX_CLIENT_CLOCK_SKEW = timedelta(minutes=5)
MAX_REASONABLE_QUESTION_TIME_SECONDS = 6 * 60 * 60


def normalize_option_id(value: str | None) -> str | None:
    if value is None:
        return None

    option_id = str(value).strip()
    if not option_id:
        return None
    if OPTION_ID_SEPARATOR in option_id:
        option_id = option_id.rsplit(OPTION_ID_SEPARATOR, 1)[-1]
    option_id = option_id.upper()

    if option_id not in CANONICAL_OPTION_KEYS:
        raise ContractViolation(f"Invalid option id '{value}'. Expected a canonical option key such as A, B, C, or D.")
    return option_id


def normalize_confidence(value: str | None) -> str | None:
    if value is None:
        return None
    confidence = CONFIDENCE_ALIASES.get(str(value), str(value))
    if confidence not in {item.value for item in CanonicalConfidence}:
        raise ContractViolation(f"Invalid confidence level '{value}'.")
    return confidence


def normalize_event_payload(event_type: str, question_id: int | None, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = dict(payload or {})
    if event_type not in {item.value for item in CanonicalExamEvent}:
        raise ContractViolation(f"Invalid event type '{event_type}'.")
    if event_type in EVENTS_REQUIRING_QUESTION and question_id is None:
        raise ContractViolation(f"{event_type} requires question_id.")

    if event_type == CanonicalExamEvent.ANSWER_CHANGED.value:
        if "option_id" not in payload:
            raise ContractViolation("ANSWER_CHANGED requires payload.option_id.")
        payload["option_id"] = normalize_option_id(payload["option_id"])
        if payload.get("old_id") is not None:
            payload["old_id"] = normalize_option_id(payload["old_id"])

    if event_type == CanonicalExamEvent.CONFIDENCE_SELECTED.value:
        if "level" not in payload:
            raise ContractViolation("CONFIDENCE_SELECTED requires payload.level.")
        payload["level"] = normalize_confidence(payload["level"])

    if event_type == CanonicalExamEvent.REVIEW_MARKED.value:
        if "status" not in payload or not isinstance(payload["status"], bool):
            raise ContractViolation("REVIEW_MARKED requires boolean payload.status.")

    if event_type == CanonicalExamEvent.HEARTBEAT.value:
        if payload.get("client_elapsed_seconds") is not None and float(payload["client_elapsed_seconds"]) < 0:
            raise ContractViolation("HEARTBEAT payload.client_elapsed_seconds must be non-negative.")

    if event_type == CanonicalExamEvent.FOCUS_STATE_CHANGED.value:
        if payload.get("state") not in {"FOCUSED", "BLURRED"}:
            raise ContractViolation("FOCUS_STATE_CHANGED requires payload.state as FOCUSED or BLURRED.")

    if event_type == CanonicalExamEvent.IDLE_STATE_CHANGED.value:
        if payload.get("state") not in {"ACTIVE", "IDLE"}:
            raise ContractViolation("IDLE_STATE_CHANGED requires payload.state as ACTIVE or IDLE.")

    return payload or None


def validate_event_timestamp(timestamp: datetime | None) -> datetime:
    event_time = timestamp or datetime.now(timezone.utc)
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if event_time > now + MAX_CLIENT_CLOCK_SKEW:
        raise ContractViolation("Event timestamp is too far in the future.")
    return event_time


def detect_analytics_anomalies(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    total_questions = int(metrics.get("total_questions") or 0)
    correct = int(metrics.get("correct_count") or 0)
    incorrect = int(metrics.get("incorrect_count") or 0)
    unattempted = int(metrics.get("unattempted_count") or 0)
    average_time = float(metrics.get("average_time_per_question") or 0)
    accuracy = float(metrics.get("accuracy") or 0)

    if total_questions and correct + incorrect + unattempted != total_questions:
        anomalies.append({"type": "COUNT_CONTRADICTION", "message": "Question outcome counts do not sum to total questions."})
    if not 0 <= accuracy <= 100:
        anomalies.append({"type": "ACCURACY_RANGE", "message": "Accuracy must be between 0 and 100."})
    if average_time < 0 or average_time > MAX_REASONABLE_QUESTION_TIME_SECONDS:
        anomalies.append({"type": "IMPOSSIBLE_TIMING", "message": "Average time per question is outside the valid range."})
    if incorrect == 0 and float(metrics.get("total_score") or 0) < 0:
        anomalies.append({"type": "SCORE_CONTRADICTION", "message": "Negative score without incorrect answers is impossible."})

    return anomalies
