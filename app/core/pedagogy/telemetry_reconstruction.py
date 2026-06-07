from collections import defaultdict
from typing import List, Dict, Any

HEARTBEAT_EXPECTED_SECONDS = 30
HEARTBEAT_ALLOWED_GAP_SECONDS = 45


def _payload(event: Any) -> dict[str, Any]:
    payload = getattr(event, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _event_time(event: Any):
    return getattr(event, "timestamp")


def reconstruct_attempt_timeline(events: List[Any]) -> Dict[str, Any]:
    """
    Focus Area 1: Forensic Behavioral Reconstruction.
    Transforms raw ExamEvents into a structured replay timeline.
    """
    if not events:
        return {
            "status": "EMPTY", 
            "timeline": [], 
            "quality": {
                "heartbeat_density": 0,
                "continuity_score": 0,
                "temporal_coherence": 0,
                "focus_reliability": 1,
            },
            "total_duration": 0,
            "event_count": 0,
            "question_insights": {},
            "question_sequence": [],
            "answer_evolution": {},
            "review_behavior": [],
            "pacing_shifts": [],
            "focus_interruptions": [],
            "idle_windows": [],
            "continuity_gaps": [],
        }

    sorted_events = sorted(events, key=_event_time)
    timeline = []
    question_sequence = []
    seen_questions = set()
    answer_evolution: dict[int, list[dict[str, Any]]] = defaultdict(list)
    review_behavior = []
    pacing_shifts = []
    focus_interruptions = []
    idle_windows = []
    continuity_gaps = []
    question_stats = {}
    question_views = []
    open_focus = None
    open_idle = None

    last_event_time = _event_time(sorted_events[0])

    for i, event in enumerate(sorted_events):
        event_time = _event_time(event)
        delta = (event_time - last_event_time).total_seconds()
        event_type = event.event_type
        q_id = event.question_id
        payload = _payload(event)

        if i > 0 and delta > HEARTBEAT_ALLOWED_GAP_SECONDS:
            continuity_gaps.append({
                "from_event_id": getattr(sorted_events[i - 1], "id", None),
                "to_event_id": getattr(event, "id", None),
                "gap_seconds": delta,
                "metric_version": "telemetry-reconstruction.v1",
            })

        if q_id:
            if q_id not in question_stats:
                question_stats[q_id] = {"total_time": 0, "visits": 0, "revisions": 0}
            question_stats[q_id]["total_time"] += delta
            if event_type == "QUESTION_VIEWED":
                question_stats[q_id]["visits"] += 1
                question_views.append(event)
                if q_id not in seen_questions:
                    seen_questions.add(q_id)
                    question_sequence.append({
                        "question_id": q_id,
                        "first_viewed_at": event_time.isoformat(),
                        "sequence_index": len(question_sequence),
                    })
            elif event_type == "ANSWER_CHANGED":
                if answer_evolution[q_id]:
                    question_stats[q_id]["revisions"] += 1
                answer_evolution[q_id].append({
                    "option_id": payload.get("option_id"),
                    "old_id": payload.get("old_id"),
                    "timestamp": event_time.isoformat(),
                })
            elif event_type == "REVIEW_MARKED":
                review_behavior.append({
                    "question_id": q_id,
                    "status": payload.get("status", True),
                    "timestamp": event_time.isoformat(),
                })

        if event_type == "FOCUS_STATE_CHANGED":
            state = payload.get("state")
            if state == "BLURRED" and open_focus is None:
                open_focus = event
            elif state == "FOCUSED" and open_focus is not None:
                duration = (event_time - _event_time(open_focus)).total_seconds()
                focus_interruptions.append({
                    "started_at": _event_time(open_focus).isoformat(),
                    "ended_at": event_time.isoformat(),
                    "duration_seconds": duration,
                })
                open_focus = None

        if event_type == "IDLE_STATE_CHANGED":
            state = payload.get("state")
            if state == "IDLE" and open_idle is None:
                open_idle = event
            elif state == "ACTIVE" and open_idle is not None:
                duration = (event_time - _event_time(open_idle)).total_seconds()
                idle_windows.append({
                    "started_at": _event_time(open_idle).isoformat(),
                    "ended_at": event_time.isoformat(),
                    "duration_seconds": duration,
                })
                open_idle = None

        timeline.append({
            "index": i,
            "type": event_type,
            "q_id": q_id,
            "dwell": delta,
            "timestamp": event_time.isoformat(),
            "metadata": payload or None
        })

        last_event_time = event_time

    for current, nxt in zip(question_views, question_views[1:]):
        pacing_shifts.append({
            "question_id": current.question_id,
            "next_question_id": nxt.question_id,
            "dwell_seconds": (_event_time(nxt) - _event_time(current)).total_seconds(),
        })

    heartbeat_count = len([e for e in sorted_events if e.event_type == "HEARTBEAT"])
    total_sec = (_event_time(sorted_events[-1]) - _event_time(sorted_events[0])).total_seconds()
    expected_heartbeats = max(1, total_sec / HEARTBEAT_EXPECTED_SECONDS) if total_sec > 0 else 1
    gap_penalty = min(1.0, len(continuity_gaps) * 0.25)
    focus_penalty = min(1.0, sum(item["duration_seconds"] for item in focus_interruptions) / max(1, total_sec))

    quality = {
        "heartbeat_density": min(1.0, heartbeat_count / expected_heartbeats),
        "continuity_score": max(0.0, 1.0 - gap_penalty),
        "temporal_coherence": max(0.0, 1.0 - gap_penalty),
        "focus_reliability": max(0.0, 1.0 - focus_penalty),
    }

    return {
        "status": "VERIFIED",
        "total_duration": total_sec,
        "event_count": len(events),
        "question_insights": question_stats,
        "timeline": timeline,
        "question_sequence": question_sequence,
        "answer_evolution": dict(answer_evolution),
        "review_behavior": review_behavior,
        "pacing_shifts": pacing_shifts,
        "focus_interruptions": focus_interruptions,
        "idle_windows": idle_windows,
        "continuity_gaps": continuity_gaps,
        "quality": quality
    }
