from typing import List, Dict, Any
from datetime import datetime

def reconstruct_attempt_timeline(events: List[Any]) -> Dict[str, Any]:
    """
    Focus Area 1: Forensic Behavioral Reconstruction.
    Transforms raw ExamEvents into a structured replay timeline.
    """
    if not events:
        return {"status": "EMPTY", "timeline": []}

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
            "metadata": event.event_metadata
        })
        
        last_event_time = event.timestamp

    return {
        "status": "VERIFIED",
        "total_duration": (sorted_events[-1].timestamp - sorted_events[0].timestamp).total_seconds(),
        "event_count": len(events),
        "question_insights": question_stats,
        "timeline": timeline
    }
