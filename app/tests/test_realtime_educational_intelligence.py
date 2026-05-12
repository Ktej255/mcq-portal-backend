from datetime import datetime, timezone, timedelta

from app.db.session import Base
from app.models.domain import Attempt, AttemptStatusEnum, ExamEvent
from app.services.educational_orchestrator import orchestrate_live_session
from app.services.educational_policy_engine import live_intervention_governance
from app.services.realtime_telemetry_engine import (
    live_cognitive_state_detection,
    realtime_telemetry_state,
)
from app.services.session_intelligence_engine import build_session_intelligence, educator_live_awareness
from app.tests.test_knowledge_graph_engine import seed_concept_graph
from app.tests.test_student_longitudinal_profile import make_db


def seed_live_attempt(db):
    user = seed_concept_graph(db)
    test_id = user.attempts[0].test_id
    attempt = Attempt(
        user_id=user.id,
        test_id=test_id,
        status=AttemptStatusEnum.IN_PROGRESS,
        start_time=datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
    )
    db.add(attempt)
    db.commit()
    base = attempt.start_time
    events = [
        ExamEvent(attempt_id=attempt.id, event_type="HEARTBEAT", timestamp=base),
        ExamEvent(attempt_id=attempt.id, event_type="QUESTION_VIEWED", question_id=1, timestamp=base + timedelta(seconds=1)),
        ExamEvent(attempt_id=attempt.id, event_type="CONFIDENCE_SELECTED", question_id=1, payload={"confidence": "HIGH"}, timestamp=base + timedelta(seconds=10)),
        ExamEvent(attempt_id=attempt.id, event_type="FOCUS_STATE_CHANGED", payload={"state": "BLURRED"}, timestamp=base + timedelta(seconds=25)),
        ExamEvent(attempt_id=attempt.id, event_type="FOCUS_STATE_CHANGED", payload={"state": "FOCUSED"}, timestamp=base + timedelta(seconds=40)),
        ExamEvent(attempt_id=attempt.id, event_type="QUESTION_VIEWED", question_id=2, timestamp=base + timedelta(seconds=120)),
        ExamEvent(attempt_id=attempt.id, event_type="ANSWER_CHANGED", question_id=2, payload={"option_id": "A"}, timestamp=base + timedelta(seconds=124)),
        ExamEvent(attempt_id=attempt.id, event_type="QUESTION_VIEWED", question_id=3, timestamp=base + timedelta(seconds=260)),
        ExamEvent(attempt_id=attempt.id, event_type="CONFIDENCE_SELECTED", question_id=3, payload={"confidence": "LOW"}, timestamp=base + timedelta(seconds=270)),
    ]
    db.add_all(events)
    db.commit()
    return attempt, base + timedelta(seconds=380)


def test_realtime_telemetry_detects_live_instability_without_diagnosis():
    db, engine = make_db()
    try:
        attempt, now = seed_live_attempt(db)
        events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt.id).all()
        telemetry = realtime_telemetry_state(events, now)
        cognitive = live_cognitive_state_detection(telemetry)

        assert telemetry["heartbeat"]["telemetry_degraded"] is True
        assert telemetry["hesitation"]["active_hesitation"] is True
        assert "HESITATION_SPIKE" in cognitive["signals"]
        assert "not psychological diagnoses" in cognitive["diagnostic_boundary"]
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_session_intelligence_combines_live_and_memory_context():
    db, engine = make_db()
    try:
        attempt, now = seed_live_attempt(db)
        session = build_session_intelligence(db, attempt.id, now)

        assert session["current_session_stability"] < 1
        assert session["live_behavioral_drift"]["historical_pacing_volatility"] >= 0
        assert session["real_time_conceptual_struggle"]["memory_risk_topics"]
        assert session["metric_version"] == "session-intelligence.v1"
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_live_policy_blocks_strong_actions_on_degraded_telemetry():
    db, engine = make_db()
    try:
        attempt, now = seed_live_attempt(db)
        session = build_session_intelligence(db, attempt.id, now)
        governance = live_intervention_governance(session)

        assert governance["allow_live_intervention"] is False
        assert governance["anti_surveillance_boundary"] is True
        assert any(item["action"] == "CONTENT_ADAPTATION" for item in governance["blocked_actions"])
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_live_orchestration_is_explainable_and_minimally_disruptive():
    db, engine = make_db()
    try:
        attempt, _now = seed_live_attempt(db)
        result = orchestrate_live_session(db, attempt.id)

        assert result["action_type"] in {"OBSERVE_ONLY", "LIVE_PACING_BUFFER", "LIVE_RECOVERY_PROMPT", "LIVE_REFLECTION_NUDGE"}
        assert result["explanation"]["why_generated"]
        assert result["explanation"]["reversibility"] is True
        assert result["governance"]["throttle_seconds"] >= 180
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_educator_live_awareness_is_support_not_surveillance():
    db, engine = make_db()
    try:
        attempt, now = seed_live_attempt(db)
        session = build_session_intelligence(db, attempt.id, now)
        awareness = educator_live_awareness([session])

        assert awareness["active_session_count"] == 1
        assert awareness["educator_alerts"]
        assert "not surveillance" in awareness["privacy_boundary"]
    finally:
        db.close()
        Base.metadata.drop_all(engine)
