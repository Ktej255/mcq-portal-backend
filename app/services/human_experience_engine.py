from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.models.domain import QualitativeSignal, User

class HumanExperienceEngine:
    def __init__(self, db: Session):
        self.db = db

    def record_experience_signal(self, user_id: int, signal_type: str, content: str, evidence: Dict[str, Any]) -> QualitativeSignal:
        """Preserves qualitative human signals that cannot be captured by telemetry."""
        signal = QualitativeSignal(
            user_id=user_id,
            signal_type=signal_type,
            content=content,
            evidence_payload=evidence
        )
        self.db.add(signal)
        self.db.commit()
        self.db.refresh(signal)
        return signal

    def get_contextual_intuition(self, target_id: str) -> List[Dict[str, Any]]:
        """Retrieves educator intuition and classroom context for a specific learning region."""
        signals = self.db.query(QualitativeSignal).filter(
            QualitativeSignal.signal_type == "INTUITION"
        ).all()
        
        return [
            {
                "educator_id": s.user_id,
                "insight": s.content,
                "context": s.evidence_payload,
                "timestamp": s.created_at.isoformat()
            } for s in signals
        ]
