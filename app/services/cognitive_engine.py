from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.domain import ExamEvent, AttemptAnswer, ConfidenceEnum
from app.schemas.cognitive import CognitiveSignal, BehavioralSnapshot
from app.core.pedagogy.inference_reliability import attempt_reliability_profile

class CognitiveEngine:
    def analyze_attempt(self, db: Session, attempt_id: int) -> BehavioralSnapshot:
        """
        Derives high-order cognitive signals from raw events and answers.
        """
        answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
        events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).all()
        
        if not answers:
            return BehavioralSnapshot(guessing_rate=0, hesitation_index=0, overconfidence_rate=0, anxiety_index=0)

        # 1. Calculate Base Metrics
        blind_guesses = [a for a in answers if a.confidence_level == ConfidenceEnum.BLIND_GUESS]
        sure_wrong = [a for a in answers if a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT and a.is_correct == False]
        hesitant_correct = [a for a in answers if a.time_taken_seconds > 60 and a.is_correct == True]
        
        guessing_rate = len(blind_guesses) / len(answers) * 100
        overconfidence = len(sure_wrong) / len(answers) * 100
        hesitation = len(hesitant_correct) / len(answers) * 100
        answer_changes = [event for event in events if event.event_type == "ANSWER_CHANGED"]
        high_confidence_answers = [a for a in answers if a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT]
        avg_time = sum((a.time_taken_seconds or 0) for a in answers) / len(answers)
        reliability = attempt_reliability_profile(answers, events, {
            "high_confidence_rate": len(high_confidence_answers) / len(answers) * 100,
            "answer_change_rate": len(answer_changes) / len(answers) * 100,
            "hesitation_index": hesitation,
            "average_time_per_question": avg_time,
            "fatigue_score": 0,
            "late_accuracy_delta": 0,
        })
        quality_score = reliability["behavioral_data_quality"]["score"]

        # 2. Derive Signals with Confidence Scores
        signals = []
        
        # Signal: Decisive Intuition vs. Reckless Guessing
        if guessing_rate > 30 and overconfidence > 10:
            signals.append(CognitiveSignal(
                name="RECKLESS_IMPULSE",
                value=guessing_rate,
                confidence=reliability["signals"]["impulsiveness"]["signal_confidence"],
                signal_confidence=reliability["signals"]["impulsiveness"]["signal_confidence"],
                interpretation="Available answer and confidence patterns may indicate low deliberation.",
                uncertainty_note="This is a behavioral inference, not a psychological diagnosis."
            ))

        # Signal: Panic / Anxiety Pattern (Pacing Collapse)
        # Check second half accuracy vs first half
        mid = len(answers) // 2
        first_half = answers[:mid]
        second_half = answers[mid:]
        first_acc = len([a for a in first_half if a.is_correct]) / len(first_half) if first_half else 0
        second_acc = len([a for a in second_half if a.is_correct]) / len(second_half) if second_half else 0
        
        # Check pacing in second half
        avg_time_first = sum(a.time_taken_seconds for a in first_half) / len(first_half) if first_half else 0
        avg_time_second = sum(a.time_taken_seconds for a in second_half) / len(second_half) if second_half else 0
        
        if second_acc < first_acc * 0.7 and avg_time_second < avg_time_first * 0.8:
             signals.append(CognitiveSignal(
                name="ANXIETY_PATTERN",
                value=(first_acc - second_acc) * 100,
                confidence=0.85,
                signal_confidence=0.85,
                interpretation="Your accuracy collapsed in the latter half as your pace accelerated. This often indicates exam anxiety or fatigue.",
                uncertainty_note="Behavioral pattern detected: 'Panic Solving'."
            ))
        
        # Signal: Calibration Accuracy (Confidence vs. Reality)
        correct_sure = [a for a in answers if a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT and a.is_correct == True]
        calibration = len(correct_sure) / len([a for a in answers if a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT]) if any(a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT for a in answers) else 0
        
        signals.append(CognitiveSignal(
            name="CONFIDENCE_CALIBRATION",
            value=calibration * 100,
            confidence=reliability["signals"]["confidence_drift"]["signal_confidence"],
            signal_confidence=reliability["signals"]["confidence_drift"]["signal_confidence"],
            interpretation=f"Available evidence suggests self-assessment alignment of {calibration*100:.1f}%.",
            uncertainty_note="Confidence calibration is less reliable with sparse attempts or missing events."
        ))

        return BehavioralSnapshot(
            guessing_rate=guessing_rate,
            hesitation_index=hesitation,
            overconfidence_rate=overconfidence,
            anxiety_index=0, # Placeholder for future biometric/pattern analysis
            signals=signals,
            behavioral_data_quality=reliability["behavioral_data_quality"],
            inference_reliability=reliability
        )

cognitive_engine = CognitiveEngine()
