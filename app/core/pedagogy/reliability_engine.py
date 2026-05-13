from typing import Dict, Any, List
from app.models.domain import Report, AttemptAnswer, Question, ExamEvent

class EducationalReliabilityEngine:
    @staticmethod
    def compute_reliability(
        total_questions: int,
        answers: List[AttemptAnswer],
        events: List[ExamEvent],
        inference_confidence: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculates the trust score of a generated report.
        """
        # 1. Mathematical Reliability (Consistency of counts)
        correct = len([a for a in answers if a.is_correct is True])
        incorrect = len([a for a in answers if a.is_correct is False])
        skipped = len([a for a in answers if a.is_skipped or a.selected_option is None])
        
        math_score = 1.0 if (correct + incorrect + skipped) == total_questions else 0.0
        
        # 2. Telemetry Reliability (Density and Quality)
        # Check if we have events for every answered question
        answered_q_ids = {a.question_id for a in answers if a.selected_option is not None}
        event_q_ids = {e.question_id for e in events if e.question_id is not None}
        
        coverage = len(answered_q_ids.intersection(event_q_ids)) / len(answered_q_ids) if answered_q_ids else 1.0
        
        # Check for event density (at least 2 events per answered question: View + Selection)
        event_density = len(events) / (len(answered_q_ids) * 2) if answered_q_ids else 1.0
        telemetry_score = min(1.0, (coverage * 0.7) + (event_density * 0.3))
        
        # 3. Global Score
        global_score = (math_score * 0.4) + (telemetry_score * 0.3) + (inference_confidence * 0.3)
        
        return {
            "reliability_score": round(global_score * 100, 2),
            "math_reliability": math_score,
            "telemetry_reliability": telemetry_score,
            "inference_reliability": inference_confidence,
            "reconciliation_log": {
                "total_expected": total_questions,
                "total_found": correct + incorrect + skipped,
                "telemetry_coverage": coverage,
                "event_count": len(events)
            }
        }
