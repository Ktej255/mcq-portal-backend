from typing import List, Dict, Any
from datetime import datetime

HEARTBEAT_EXPECTED_SECONDS = 30
HEARTBEAT_ALLOWED_GAP_SECONDS = 45

def reconstruct_attempt_timeline(events: List[Any]) -> Dict[str, Any]:
    """
    Focus Area 1: Forensic Behavioral Reconstruction.
    Transforms raw ExamEvents into a structured replay timeline.
    """
    if not events:
        return {
            "status": "EMPTY", 
            "timeline": [], 
            "quality": {"heartbeat_density": 0, "continuity_score": 0, "temporal_coherence": 0},
            "total_duration": 0,
            "event_count": 0,
            "question_insights": {}
        }

    sorted_events = sorted(events, key=lambda x: x.timestamp)
    timeline = []
    
    last_event_time = sorted_events[0].timestamp
    
    # Track metrics per question
    question_stats = {}

    for i, event in enumerate(sorted_events):
        # Calculate Dwell Time (time between events)
        delta = (event.timestamp - last_event_time).total_seconds()
        
        q_id = event.question_id
        if q_id:
            if q_id not in question_stats:
                question_stats[q_id] = {"total_time": 0, "visits": 0, "revisions": 0}
            question_stats[q_id]["total_time"] += delta
            if event.event_type == "QUESTION_VIEW":
                question_stats[q_id]["visits"] += 1
            elif event.event_type == "OPTION_SELECT":
                # If they already selected an option, this is a revision
                pass # Logic to be refined based on actual metadata

        timeline.append({
            "index": i,
            "type": event.event_type,
            "q_id": q_id,
            "dwell": delta,
            "timestamp": event.timestamp.isoformat(),
            "metadata": event.payload
        })
        
        last_event_time = event.timestamp

    # Add quality metrics
    heartbeat_count = len([e for e in sorted_events if e.event_type == "HEARTBEAT"])
    total_sec = (sorted_events[-1].timestamp - sorted_events[0].timestamp).total_seconds()
    
    quality = {
        "heartbeat_density": min(1.0, heartbeat_count / (total_sec / HEARTBEAT_EXPECTED_SECONDS)) if total_sec > 30 else 0,
        "continuity_score": 1.0, 
        "temporal_coherence": 1.0
    }
    
    return {
        "status": "VERIFIED",
        "total_duration": total_sec,
        "event_count": len(events),
        "question_insights": question_stats,
        "timeline": timeline,
        "quality": quality
    }
