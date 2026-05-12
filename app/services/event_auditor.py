from typing import List, Dict, Any
from datetime import datetime
from app.schemas.test_engine import ExamEventRequest

class EventAuditor:
    @staticmethod
    def validate_sequence(events: List[ExamEventRequest]) -> Dict[str, Any]:
        """
        Audits a batch of events for logical consistency and session integrity.
        """
        violations = []
        last_timestamp = None
        viewed_questions = set()
        
        # Sort events by timestamp to ensure we check order correctly
        # If timestamp is missing, we assume they are in order as received
        sorted_events = sorted(events, key=lambda x: x.timestamp or datetime.min)

        for i, event in enumerate(sorted_events):
            # 1. Monotonicity Check
            if last_timestamp and event.timestamp and event.timestamp < last_timestamp:
                violations.append({
                    "type": "CHRONOLOGY_VIOLATION",
                    "event_index": i,
                    "message": f"Event {event.event_type} has timestamp earlier than previous event."
                })
            
            # 2. Causality Checks
            if event.event_type == 'QUESTION_VIEWED':
                viewed_questions.add(event.question_id)
            
            elif event.event_type in ['ANSWER_SELECTED', 'ANSWER_CHANGED', 'CONFIDENCE_UPDATED', 'MARKED_FOR_REVIEW']:
                if event.question_id not in viewed_questions:
                    violations.append({
                        "type": "CAUSALITY_VIOLATION",
                        "event_index": i,
                        "question_id": event.question_id,
                        "message": f"Action {event.event_type} occurred before QUESTION_VIEWED."
                    })
            
            # 3. Anomaly Detection (e.g. Rapid Flipping)
            if event.event_type == 'ANSWER_CHANGED' and last_timestamp and event.timestamp:
                delta = (event.timestamp - last_timestamp).total_seconds()
                if delta < 0.5: # Half a second
                    violations.append({
                        "type": "RAPID_FLICKER",
                        "event_index": i,
                        "message": "Answer changed in less than 500ms. Possible bot or guessing behavior."
                    })

            last_timestamp = event.timestamp

        return {
            "is_valid": len(violations) == 0,
            "violations": violations,
            "audit_summary": {
                "total_events": len(events),
                "unique_questions_viewed": len(viewed_questions),
                "violation_count": len(violations)
            }
        }

event_auditor = EventAuditor()
