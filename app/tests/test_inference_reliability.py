from datetime import datetime, timezone

from app.models.domain import AttemptAnswer, ExamEvent, ConfidenceEnum
from app.schemas.test_engine import ExamEventRequest
from app.services.inference_reliability import (
    METRIC_VERSION,
    behavioral_data_quality,
    contradiction_detector,
    narrative_uncertainty_guidance,
    sample_confidence,
    signal_reliability,
    timing_signal_confidence,
)


def answer(question_id: int, selected="A", seconds=30, confidence=ConfidenceEnum.EDUCATED_GUESS, correct=None):
    return AttemptAnswer(
        attempt_id=1,
        question_id=question_id,
        selected_option=selected,
        time_taken_seconds=seconds,
        confidence_level=confidence,
        is_correct=correct,
    )


def event(event_type: str, question_id: int | None = None, payload=None):
    return ExamEvent(
        attempt_id=1,
        event_type=event_type,
        question_id=question_id,
        payload=payload,
        timestamp=datetime.now(timezone.utc),
    )


def test_sample_confidence_is_longitudinally_weighted():
    assert sample_confidence(1) < sample_confidence(10) < sample_confidence(50)


def test_behavioral_data_quality_penalizes_missing_heartbeat_and_zero_time():
    answers = [answer(1, seconds=0), answer(2, seconds=20)]
    events = [event("QUESTION_VIEWED", 1), event("QUESTION_VIEWED", 2)]
    quality = behavioral_data_quality(answers, events)

    assert quality["score"] < 1
    assert "answered questions with zero recorded time" in quality["notes"]
    assert "heartbeat telemetry missing" in quality["notes"]
    assert quality["metric_version"] == METRIC_VERSION


def test_timing_signal_confidence_uses_data_quality():
    trusted = timing_signal_confidence(
        [answer(1, seconds=25), answer(2, seconds=35)],
        [event("QUESTION_VIEWED", 1), event("QUESTION_VIEWED", 2), event("HEARTBEAT")],
    )
    sparse = timing_signal_confidence([answer(1, seconds=0)], [])

    assert trusted.signal_confidence > sparse.signal_confidence


def test_signal_reliability_applies_anomaly_penalty():
    clean = signal_reliability("guessing_detection", evidence_count=20, data_quality_score=0.9)
    anomalous = signal_reliability("guessing_detection", evidence_count=20, data_quality_score=0.9, anomaly_count=3)

    assert clean["signal_confidence"] > anomalous["signal_confidence"]


def test_contradiction_detector_scores_conflicting_claims():
    result = contradiction_detector({
        "high_confidence_rate": 80,
        "answer_change_rate": 60,
        "hesitation_index": 5,
        "average_time_per_question": 180,
        "fatigue_score": 80,
        "late_accuracy_delta": 0,
    })

    assert result["contradiction_score"] > 0
    assert len(result["contradictions"]) == 3
    assert result["reliability_downgrade"] > 0


def test_narrative_uncertainty_requires_review_for_low_quality():
    guidance = narrative_uncertainty_guidance({
        "behavioral_data_quality": {"score": 0.2},
        "contradictions": {"contradiction_score": 0},
    })

    assert guidance["requires_human_review"] is True
    assert "tentative" in guidance["uncertainty_qualifier"]


def test_temporal_telemetry_event_contracts_are_strict():
    heartbeat = ExamEventRequest(
        event_type="HEARTBEAT",
        payload={"client_elapsed_seconds": 10},
        timestamp=datetime.now(timezone.utc),
    )
    assert heartbeat.payload == {"client_elapsed_seconds": 10}

    focus = ExamEventRequest(
        event_type="FOCUS_STATE_CHANGED",
        payload={"state": "BLURRED"},
        timestamp=datetime.now(timezone.utc),
    )
    assert focus.payload == {"state": "BLURRED"}

    try:
        ExamEventRequest(
            event_type="IDLE_STATE_CHANGED",
            payload={"state": "UNKNOWN"},
            timestamp=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        assert "IDLE_STATE_CHANGED" in str(exc)
    else:
        raise AssertionError("Invalid idle state should be rejected")
