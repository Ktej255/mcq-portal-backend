from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.domain import ExamEvent, Attempt, Report, SystemEvent

class EventCinemaService:
    @staticmethod
    def get_educational_timeline(db: Session, attempt_id: int) -> List[Dict[str, Any]]:
        """
        Priority 4: Founder Event Timeline.
        Aggregates all attempt-related events into a chronological "cinema" view.
        """
        timeline = []
        
        # 1. Attempt Level Events
        attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
        if not attempt: return []
        
        timeline.append({
            "timestamp": attempt.start_time.isoformat(),
            "type": "ATTEMPT_STARTED",
            "actor": f"Student (ID: {attempt.user_id})",
            "severity": "info"
        })
        
        # 2. Behavioral Events
        events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).all()
        for e in events:
            timeline.append({
                "timestamp": e.timestamp.isoformat(),
                "type": f"BEHAVIORAL_{e.event_type}",
                "q_id": e.question_id,
                "metadata": e.event_metadata,
                "severity": "low"
            })
            
        # 3. System & Evaluation Events
        report = db.query(Report).filter(Report.attempt_id == attempt_id).first()
        if report:
            timeline.append({
                "timestamp": report.generated_at.isoformat(),
                "type": "REPORT_GENERATED",
                "status": report.processing_status,
                "truth_status": report.truth_status,
                "reliability": report.reliability_score,
                "severity": "success" if report.truth_status == "VERIFIED" else "critical"
            })
            
        # Sort by time
        timeline.sort(key=lambda x: x["timestamp"])
        return timeline
