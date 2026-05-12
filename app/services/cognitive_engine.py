from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.domain import ExamEvent, AttemptAnswer, ConfidenceEnum
from app.schemas.cognitive import CognitiveSignal, BehavioralSnapshot

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

        # 2. Derive Signals with Confidence Scores
        signals = []
        
        # Signal: Decisive Intuition vs. Reckless Guessing
        if guessing_rate > 30 and overconfidence > 10:
            signals.append(CognitiveSignal(
                name="RECKLESS_IMPULSE",
                value=guessing_rate,
                confidence=0.85,
                interpretation="Student is making rapid choices without sufficient deliberation or self-calibration."
            ))
        
        # Signal: Calibration Accuracy (Confidence vs. Reality)
        correct_sure = [a for a in answers if a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT and a.is_correct == True]
        calibration = len(correct_sure) / len([a for a in answers if a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT]) if any(a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT for a in answers) else 0
        
        signals.append(CognitiveSignal(
            name="CONFIDENCE_CALIBRATION",
            value=calibration * 100,
            confidence=0.9,
            interpretation=f"Student's self-assessment is {calibration*100:.1f}% aligned with actual performance."
        ))

        return BehavioralSnapshot(
            guessing_rate=guessing_rate,
            hesitation_index=hesitation,
            overconfidence_rate=overconfidence,
            anxiety_index=0, # Placeholder for future biometric/pattern analysis
            signals=signals
        )

cognitive_engine = CognitiveEngine()
