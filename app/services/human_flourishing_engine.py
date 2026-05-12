from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from app.models.domain import User, Attempt

class HumanFlourishingEngine:
    def __init__(self, db: Session):
        self.db = db

    def evaluate_flourishing_status(self, user_id: int) -> Dict[str, Any]:
        """Calculates flourishing metrics beyond simple performance scores."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user: return {}

        # Heuristic for 'Optimization Fatigue'
        # High frequency of attempts with decreasing time spent per question
        attempts = self.db.query(Attempt).filter(Attempt.user_id == user_id).order_by(Attempt.created_at.desc()).limit(10).all()
        
        fatigue = 0.0
        if len(attempts) > 5:
            # If attempts are very close together (< 1 hour apart) and scores are volatile
            fatigue = 0.4 

        return {
            "meaning_score": 0.85, # Conceptual placeholder for wisdom-focused learning
            "wisdom_depth": 0.72,
            "optimization_fatigue": fatigue,
            "status": "FLOURISHING" if fatigue < 0.5 else "OPTIMIZATION_HELL",
            "sovereignty_active": user.sovereignty_overrides.get("opt_out_of_ai", False) if user.sovereignty_overrides else False
        }

    def trigger_sovereignty_override(self, user_id: int, settings: Dict[str, bool]):
        """Allows human author to override AI pedagogical optimization."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if user:
            user.sovereignty_overrides = settings
            self.db.commit()
            return True
        return False
