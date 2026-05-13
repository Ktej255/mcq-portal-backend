from datetime import datetime, timezone, timedelta

from app.models.domain import ExamEvent
from app.core.pedagogy.telemetry_reconstruction import reconstruct_attempt_timeline


def make_event(event_id: int, event_type: str, seconds: int, question_id=None, payload=None):
    return ExamEvent(
        id=event_id,
        attempt_id=1,
        event_type=event_type,
        question_id=question_id,
        payload=payload or {},
        timestamp=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc) + timedelta(seconds=seconds),
    )


def test_reconstructs_question_answer_review_timeline():
    timeline = reconstruct_attempt_timeline([
        make_event(1, "HEARTBEAT", 0, payload={"sequence": 1}),
        make_event(2, "QUESTION_VIEWED", 1, question_id=1),
        make_event(3, "ANSWER_CHANGED", 5, question_id=1, payload={"option_id": "B"}),
        make_event(4, "REVIEW_MARKED", 7, question_id=1, payload={"status": True}),
        make_event(5, "QUESTION_VIEWED", 15, question_id=2),
        make_event(6, "HEARTBEAT", 25, payload={"sequence": 2}),
    ])

    assert [item["question_id"] for item in timeline["question_sequence"]] == [1, 2]
    assert timeline["answer_evolution"][1][0]["option_id"] == "B"
    assert timeline["review_behavior"][0]["status"] is True
    assert timeline["pacing_shifts"][0]["dwell_seconds"] == 14
    assert timeline["quality"]["heartbeat_density"] > 0


def test_reconstructs_focus_and_idle_windows():
    timeline = reconstruct_attempt_timeline([
        make_event(1, "QUESTION_VIEWED", 0, question_id=1),
        make_event(2, "FOCUS_STATE_CHANGED", 2, payload={"state": "BLURRED"}),
        make_event(3, "FOCUS_STATE_CHANGED", 8, payload={"state": "FOCUSED"}),
        make_event(4, "IDLE_STATE_CHANGED", 10, payload={"state": "IDLE"}),
        make_event(5, "IDLE_STATE_CHANGED", 80, payload={"state": "ACTIVE"}),
    ])

    assert timeline["focus_interruptions"][0]["duration_seconds"] == 6
    assert timeline["idle_windows"][0]["duration_seconds"] == 70
    assert timeline["quality"]["focus_reliability"] < 1


def test_detects_continuity_gaps_and_temporal_quality_drop():
    timeline = reconstruct_attempt_timeline([
        make_event(1, "QUESTION_VIEWED", 0, question_id=1),
        make_event(2, "ANSWER_CHANGED", 200, question_id=1, payload={"option_id": "A"}),
    ])

    assert timeline["continuity_gaps"][0]["gap_seconds"] == 200
    assert timeline["quality"]["continuity_score"] < 1
    assert timeline["quality"]["temporal_coherence"] < 1
