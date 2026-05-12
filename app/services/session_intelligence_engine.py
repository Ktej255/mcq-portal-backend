from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import Attempt, ExamEvent
from app.services.educational_memory_engine import build_educational_memory
from app.services.realtime_telemetry_engine import (
    REALTIME_TELEMETRY_VERSION,
    live_cognitive_state_detection,
    realtime_telemetry_state,
)

SESSION_INTELLIGENCE_VERSION = "session-intelligence.v1"


def build_session_intelligence(db: Session, attempt_id: int, now: datetime | None = None) -> dict[str, Any]:
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
    events = (
        db.query(ExamEvent)
        .filter(ExamEvent.attempt_id == attempt_id)
        .order_by(ExamEvent.timestamp.asc())
        .all()
    )
    telemetry = realtime_telemetry_state(events, now or datetime.now(timezone.utc))
    cognitive = live_cognitive_state_detection(telemetry)
    memory = build_educational_memory(db, attempt.user_id) if attempt else {}
    pacing_memory = memory.get("pacing_memory", {})
    misconception_topics = {
        item["topic"] for item in memory.get("misconception_memory", {}).get("misconceptions", [])
    }
    current_question_id = telemetry.get("hesitation", {}).get("current_question_id")
    live_drift = telemetry.get("pacing", {}).get("pacing_drift_seconds", 0)
    stability = 1 - max(
        cognitive["probabilities"]["live_instability"],
        cognitive["probabilities"]["overload_risk"],
        1 - telemetry["session_continuity_score"],
    )
    recovery_attempts = [
        event for event in events
        if event.event_type in {"REVIEW_MARKED", "CONFIDENCE_SELECTED"} and event.question_id is not None
    ]
    return {
        "attempt_id": attempt_id,
        "user_id": attempt.user_id if attempt else None,
        "current_session_stability": round(max(0, stability), 4),
        "telemetry": telemetry,
        "live_cognitive_state": cognitive,
        "recovery_attempt_count": len(recovery_attempts),
        "live_behavioral_drift": {
            "pacing_drift_seconds": live_drift,
            "pacing_memory_pattern": pacing_memory.get("pattern"),
            "historical_pacing_volatility": pacing_memory.get("pacing_volatility", 0),
        },
        "real_time_conceptual_struggle": {
            "current_question_id": current_question_id,
            "memory_risk_topics": sorted(misconception_topics),
            "risk_present": bool(misconception_topics and cognitive["signals"]),
        },
        "metric_version": SESSION_INTELLIGENCE_VERSION,
    }


def educator_live_awareness(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    unstable = [session for session in sessions if session.get("current_session_stability", 1) < 0.45]
    overload = [
        session for session in sessions
        if session.get("live_cognitive_state", {}).get("probabilities", {}).get("overload_risk", 0) > 0.55
    ]
    telemetry_degraded = [
        session for session in sessions
        if session.get("telemetry", {}).get("heartbeat", {}).get("telemetry_degraded")
    ]
    return {
        "active_session_count": len(sessions),
        "unstable_session_count": len(unstable),
        "high_overload_risk_count": len(overload),
        "telemetry_degradation_count": len(telemetry_degraded),
        "educator_alerts": [
            {
                "attempt_id": session.get("attempt_id"),
                "alert_type": "SUBTLE_SUPPORT_RECOMMENDED",
                "reason": "Live session signals suggest instability; avoid disruptive intervention.",
            }
            for session in unstable[:10]
        ],
        "privacy_boundary": "Live awareness is for educational support, not surveillance or diagnosis.",
        "metric_version": SESSION_INTELLIGENCE_VERSION,
    }
