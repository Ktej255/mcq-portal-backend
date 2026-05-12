from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.domain import ExamEvent
from app.services.inference_reliability import METRIC_VERSION, clamp

HEARTBEAT_EXPECTED_SECONDS = 25
HEARTBEAT_ALLOWED_GAP_SECONDS = 75


@dataclass
class TimelineState:
    question_sequence: list[dict[str, Any]] = field(default_factory=list)
    answer_evolution: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    review_behavior: list[dict[str, Any]] = field(default_factory=list)
    focus_interruptions: list[dict[str, Any]] = field(default_factory=list)
    idle_windows: list[dict[str, Any]] = field(default_factory=list)
    pacing_shifts: list[dict[str, Any]] = field(default_factory=list)
    continuity_gaps: list[dict[str, Any]] = field(default_factory=list)
    temporal_anomalies: list[dict[str, Any]] = field(default_factory=list)


def _event_time(event: ExamEvent) -> datetime:
    return event.timestamp or datetime.min


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    return (end - start).total_seconds()


def reconstruct_attempt_timeline(events: list[ExamEvent]) -> dict[str, Any]:
    ordered_events = sorted(events, key=lambda event: (_event_time(event), event.id or 0))
    timeline = TimelineState()
    last_event: ExamEvent | None = None
    last_question_event: ExamEvent | None = None
    active_idle_start: ExamEvent | None = None
    active_blur_start: ExamEvent | None = None
    heartbeat_events: list[ExamEvent] = []

    for event in ordered_events:
        if last_event:
            gap = _seconds_between(_event_time(last_event), _event_time(event))
            if gap is not None and gap < 0:
                timeline.temporal_anomalies.append({"type": "NEGATIVE_ORDERING", "event_id": event.id})
            if gap is not None and gap > HEARTBEAT_ALLOWED_GAP_SECONDS:
                timeline.continuity_gaps.append({
                    "type": "EVENT_GAP",
                    "from_event_id": last_event.id,
                    "to_event_id": event.id,
                    "gap_seconds": round(gap, 2),
                })

        if event.event_type == "QUESTION_VIEWED":
            dwell_seconds = _seconds_between(_event_time(last_question_event), _event_time(event)) if last_question_event else None
            if dwell_seconds is not None:
                timeline.pacing_shifts.append({
                    "from_question_id": last_question_event.question_id,
                    "to_question_id": event.question_id,
                    "dwell_seconds": round(dwell_seconds, 2),
                })
            timeline.question_sequence.append({
                "question_id": event.question_id,
                "timestamp": _event_time(event).isoformat(),
            })
            last_question_event = event

        elif event.event_type == "ANSWER_CHANGED" and event.question_id is not None:
            timeline.answer_evolution.setdefault(event.question_id, []).append({
                "timestamp": _event_time(event).isoformat(),
                "option_id": (event.payload or {}).get("option_id"),
                "old_id": (event.payload or {}).get("old_id"),
            })

        elif event.event_type == "REVIEW_MARKED":
            timeline.review_behavior.append({
                "question_id": event.question_id,
                "timestamp": _event_time(event).isoformat(),
                "status": (event.payload or {}).get("status"),
            })

        elif event.event_type in {"TAB_SWITCH", "FULLSCREEN_EXIT"}:
            timeline.focus_interruptions.append({
                "type": event.event_type,
                "timestamp": _event_time(event).isoformat(),
                "payload": event.payload or {},
            })

        elif event.event_type == "FOCUS_STATE_CHANGED":
            state = (event.payload or {}).get("state")
            if state == "BLURRED":
                active_blur_start = event
            elif state == "FOCUSED" and active_blur_start:
                duration = _seconds_between(_event_time(active_blur_start), _event_time(event))
                timeline.focus_interruptions.append({
                    "type": "BLUR_WINDOW",
                    "start": _event_time(active_blur_start).isoformat(),
                    "end": _event_time(event).isoformat(),
                    "duration_seconds": round(duration or 0, 2),
                })
                active_blur_start = None

        elif event.event_type == "IDLE_STATE_CHANGED":
            state = (event.payload or {}).get("state")
            if state == "IDLE":
                active_idle_start = event
            elif state == "ACTIVE" and active_idle_start:
                duration = _seconds_between(_event_time(active_idle_start), _event_time(event))
                timeline.idle_windows.append({
                    "start": _event_time(active_idle_start).isoformat(),
                    "end": _event_time(event).isoformat(),
                    "duration_seconds": round(duration or 0, 2),
                })
                active_idle_start = None

        elif event.event_type == "HEARTBEAT":
            heartbeat_events.append(event)

        last_event = event

    if active_idle_start:
        timeline.idle_windows.append({
            "start": _event_time(active_idle_start).isoformat(),
            "end": None,
            "duration_seconds": None,
        })
    if active_blur_start:
        timeline.focus_interruptions.append({
            "type": "BLUR_WINDOW",
            "start": _event_time(active_blur_start).isoformat(),
            "end": None,
            "duration_seconds": None,
        })

    quality = telemetry_quality_metrics(ordered_events, timeline, heartbeat_events)
    return {
        "metric_version": METRIC_VERSION,
        "event_count": len(ordered_events),
        "question_sequence": timeline.question_sequence,
        "answer_evolution": timeline.answer_evolution,
        "review_behavior": timeline.review_behavior,
        "focus_interruptions": timeline.focus_interruptions,
        "idle_windows": timeline.idle_windows,
        "pacing_shifts": timeline.pacing_shifts,
        "continuity_gaps": timeline.continuity_gaps,
        "temporal_anomalies": timeline.temporal_anomalies,
        "quality": quality,
    }


def telemetry_quality_metrics(events: list[ExamEvent], timeline: TimelineState, heartbeat_events: list[ExamEvent] | None = None) -> dict[str, Any]:
    heartbeat_events = heartbeat_events if heartbeat_events is not None else [event for event in events if event.event_type == "HEARTBEAT"]
    if not events:
        return {
            "heartbeat_density": 0,
            "continuity_score": 0,
            "focus_reliability": 0,
            "idle_reliability": 0,
            "event_sparsity": 1,
            "temporal_coherence": 0,
            "metric_version": METRIC_VERSION,
        }

    start = _event_time(events[0])
    end = _event_time(events[-1])
    duration_seconds = max(1, (end - start).total_seconds())
    expected_heartbeats = max(1, int(duration_seconds / HEARTBEAT_EXPECTED_SECONDS))
    heartbeat_density = clamp(len(heartbeat_events) / expected_heartbeats)
    gap_penalty = min(0.6, len(timeline.continuity_gaps) * 0.12)
    anomaly_penalty = min(0.6, len(timeline.temporal_anomalies) * 0.2)
    focus_penalty = min(0.5, len(timeline.focus_interruptions) * 0.05)
    idle_penalty = min(0.4, len([window for window in timeline.idle_windows if window.get("end") is None]) * 0.2)
    sparse_expected = max(1, len(timeline.question_sequence) * 3)

    return {
        "heartbeat_density": round(heartbeat_density, 4),
        "continuity_score": round(clamp(1 - gap_penalty), 4),
        "focus_reliability": round(clamp(1 - focus_penalty), 4),
        "idle_reliability": round(clamp(1 - idle_penalty), 4),
        "event_sparsity": round(clamp(1 - (len(events) / sparse_expected)), 4),
        "temporal_coherence": round(clamp(1 - anomaly_penalty - gap_penalty), 4),
        "metric_version": METRIC_VERSION,
    }
