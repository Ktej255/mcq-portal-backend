from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from app.models.domain import ExamEvent
from app.core.pedagogy.inference_reliability import clamp
from app.core.pedagogy.telemetry_reconstruction import HEARTBEAT_ALLOWED_GAP_SECONDS, HEARTBEAT_EXPECTED_SECONDS

REALTIME_TELEMETRY_VERSION = "realtime-telemetry.v1"

HESITATION_SECONDS = 70
IMPULSE_SECONDS = 8
LIVE_WINDOW_SECONDS = 300


def _event_time(event: ExamEvent) -> datetime:
    value = event.timestamp or datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _seconds(start: datetime | None, end: datetime | None) -> float:
    if not start or not end:
        return 0.0
    start = _normalize_datetime(start)
    end = _normalize_datetime(end)
    return max(0.0, (end - start).total_seconds())


def _ordered(events: list[ExamEvent]) -> list[ExamEvent]:
    return sorted(events, key=lambda event: (_event_time(event), event.id or 0))


def live_heartbeat_aggregation(events: list[ExamEvent], now: datetime | None = None) -> dict[str, Any]:
    ordered = _ordered(events)
    now = now or datetime.now(timezone.utc)
    heartbeats = [event for event in ordered if event.event_type == "HEARTBEAT"]
    last_heartbeat = _event_time(heartbeats[-1]) if heartbeats else None
    start = _event_time(ordered[0]) if ordered else now
    duration = max(1, _seconds(start, now))
    expected = max(1, int(duration / HEARTBEAT_EXPECTED_SECONDS))
    density = clamp(len(heartbeats) / expected)
    stale_seconds = _seconds(last_heartbeat, now) if last_heartbeat else duration
    return {
        "heartbeat_count": len(heartbeats),
        "expected_heartbeats": expected,
        "heartbeat_density": round(density, 4),
        "last_heartbeat_at": last_heartbeat.isoformat() if last_heartbeat else None,
        "stale_seconds": round(stale_seconds, 4),
        "telemetry_degraded": stale_seconds > HEARTBEAT_ALLOWED_GAP_SECONDS or density < 0.5,
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }


def live_focus_monitoring(events: list[ExamEvent]) -> dict[str, Any]:
    ordered = _ordered(events)
    focus_events = [event for event in ordered if event.event_type in {"FOCUS_STATE_CHANGED", "TAB_SWITCH", "FULLSCREEN_EXIT"}]
    interruptions = 0
    active_state = "FOCUSED"
    for event in focus_events:
        payload = event.payload or {}
        if event.event_type in {"TAB_SWITCH", "FULLSCREEN_EXIT"}:
            interruptions += 1
            active_state = "INTERRUPTED"
        elif payload.get("state") == "BLURRED":
            interruptions += 1
            active_state = "BLURRED"
        elif payload.get("state") == "FOCUSED":
            active_state = "FOCUSED"
    reliability = clamp(1 - interruptions * 0.08)
    return {
        "focus_event_count": len(focus_events),
        "focus_interruptions": interruptions,
        "current_focus_state": active_state,
        "focus_reliability": round(reliability, 4),
        "focus_instability": interruptions >= 3,
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }


def pacing_drift_detection(events: list[ExamEvent]) -> dict[str, Any]:
    question_events = [event for event in _ordered(events) if event.event_type == "QUESTION_VIEWED"]
    dwell = []
    for previous, current in zip(question_events, question_events[1:]):
        dwell.append(_seconds(_event_time(previous), _event_time(current)))
    recent = dwell[-3:]
    earlier = dwell[:-3]
    recent_avg = mean(recent) if recent else 0
    earlier_avg = mean(earlier) if earlier else recent_avg
    drift = recent_avg - earlier_avg
    volatility = pstdev(dwell) if len(dwell) > 1 else 0
    return {
        "question_transitions": len(dwell),
        "recent_dwell_seconds": round(recent_avg, 4),
        "baseline_dwell_seconds": round(earlier_avg, 4),
        "pacing_drift_seconds": round(drift, 4),
        "pacing_volatility": round(volatility, 4),
        "pacing_collapse_risk": drift > 35 or volatility > 55,
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }


def active_hesitation_detection(events: list[ExamEvent], now: datetime | None = None) -> dict[str, Any]:
    ordered = _ordered(events)
    now = now or datetime.now(timezone.utc)
    last_question = next((event for event in reversed(ordered) if event.event_type == "QUESTION_VIEWED"), None)
    last_answer = next((event for event in reversed(ordered) if event.event_type == "ANSWER_CHANGED"), None)
    current_question_id = last_question.question_id if last_question else None
    answered_current = bool(last_question and last_answer and _event_time(last_answer) >= _event_time(last_question) and last_answer.question_id == current_question_id)
    elapsed = _seconds(_event_time(last_question), now) if last_question else 0
    return {
        "current_question_id": current_question_id,
        "elapsed_on_current_question": round(elapsed, 4),
        "answered_current_question": answered_current,
        "active_hesitation": bool(last_question and not answered_current and elapsed > HESITATION_SECONDS),
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }


def live_confidence_instability(events: list[ExamEvent]) -> dict[str, Any]:
    confidence_events = [event for event in _ordered(events) if event.event_type == "CONFIDENCE_SELECTED"]
    values = [(event.payload or {}).get("confidence") or (event.payload or {}).get("confidence_level") for event in confidence_events]
    changes = sum(1 for previous, current in zip(values, values[1:]) if previous != current)
    instability = changes / max(1, len(values) - 1)
    return {
        "confidence_event_count": len(confidence_events),
        "confidence_changes": changes,
        "confidence_instability": round(clamp(instability), 4),
        "instability_signal": instability > 0.5 and len(values) >= 3,
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }


def impulsive_answering_bursts(events: list[ExamEvent]) -> dict[str, Any]:
    ordered = _ordered(events)
    question_start: dict[int, datetime] = {}
    fast_answers = []
    for event in ordered:
        if event.event_type == "QUESTION_VIEWED" and event.question_id is not None:
            question_start[event.question_id] = _event_time(event)
        if event.event_type == "ANSWER_CHANGED" and event.question_id is not None and event.question_id in question_start:
            elapsed = _seconds(question_start[event.question_id], _event_time(event))
            if elapsed <= IMPULSE_SECONDS:
                fast_answers.append({"question_id": event.question_id, "elapsed_seconds": round(elapsed, 4)})
    return {
        "fast_answer_count": len(fast_answers),
        "fast_answers": fast_answers[-5:],
        "impulsive_burst_signal": len(fast_answers) >= 3,
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }


def realtime_telemetry_state(events: list[ExamEvent], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    heartbeat = live_heartbeat_aggregation(events, now)
    focus = live_focus_monitoring(events)
    pacing = pacing_drift_detection(events)
    hesitation = active_hesitation_detection(events, now)
    confidence = live_confidence_instability(events)
    impulse = impulsive_answering_bursts(events)
    continuity = clamp(
        heartbeat["heartbeat_density"] * 0.45
        + focus["focus_reliability"] * 0.25
        + (1 - clamp(len([event for event in events if event.event_type == "IDLE_STATE_CHANGED"]) / 12)) * 0.15
        + (1 - clamp(abs(pacing["pacing_drift_seconds"]) / 120)) * 0.15
    )
    return {
        "heartbeat": heartbeat,
        "focus": focus,
        "pacing": pacing,
        "hesitation": hesitation,
        "confidence": confidence,
        "impulsivity": impulse,
        "session_continuity_score": round(continuity, 4),
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }


def live_cognitive_state_detection(telemetry_state: dict[str, Any]) -> dict[str, Any]:
    fatigue = clamp(
        (1 - telemetry_state["session_continuity_score"]) * 0.30
        + (1 if telemetry_state["pacing"]["pacing_collapse_risk"] else 0) * 0.30
        + (1 if telemetry_state["focus"]["focus_instability"] else 0) * 0.20
        + (1 if telemetry_state["heartbeat"]["telemetry_degraded"] else 0) * 0.20
    )
    overload = clamp(
        (1 if telemetry_state["hesitation"]["active_hesitation"] else 0) * 0.40
        + (1 if telemetry_state["pacing"]["pacing_collapse_risk"] else 0) * 0.30
        + telemetry_state["confidence"]["confidence_instability"] * 0.30
    )
    instability = clamp(
        telemetry_state["confidence"]["confidence_instability"] * 0.35
        + (1 if telemetry_state["impulsivity"]["impulsive_burst_signal"] else 0) * 0.25
        + (1 if telemetry_state["hesitation"]["active_hesitation"] else 0) * 0.25
        + (1 - telemetry_state["session_continuity_score"]) * 0.15
    )
    signals = []
    if fatigue > 0.55:
        signals.append("EMERGING_FATIGUE")
    if overload > 0.55:
        signals.append("OVERLOAD_RISK")
    if telemetry_state["pacing"]["pacing_collapse_risk"]:
        signals.append("PACING_COLLAPSE")
    if telemetry_state["hesitation"]["active_hesitation"]:
        signals.append("HESITATION_SPIKE")
    if telemetry_state["impulsivity"]["impulsive_burst_signal"]:
        signals.append("IMPULSIVE_BURST")
    if telemetry_state["confidence"]["instability_signal"]:
        signals.append("CONFIDENCE_INSTABILITY")
    return {
        "probabilities": {
            "emerging_fatigue": round(fatigue, 4),
            "overload_risk": round(overload, 4),
            "live_instability": round(instability, 4),
        },
        "signals": signals,
        "diagnostic_boundary": "Live signals are probabilistic session evidence, not psychological diagnoses.",
        "metric_version": REALTIME_TELEMETRY_VERSION,
    }
