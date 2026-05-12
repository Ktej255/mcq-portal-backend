from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from app.models.domain import Institution

class InstitutionalGovernanceEngine:
    def __init__(self, db: Session):
        self.db = db

    def get_institution_config(self, institution_id: int) -> Dict[str, Any]:
        """Retrieves the governance configuration for an institution."""
        inst = self.db.query(Institution).get(institution_id)
        if not inst:
            return self.get_default_config()
        return inst.config or self.get_default_config()

    def get_default_config(self) -> Dict[str, Any]:
        """Returns the default global governance settings."""
        return {
            "intervention_aggressiveness": "MEDIUM", # LOW, MEDIUM, HIGH
            "educator_review_threshold": 0.7, # Required accuracy for auto-remediation
            "experimentation_allowed": True,
            "privacy_mode": "STRICT", # STRICT, BALANCED, ANALYTICS_ONLY
            "analytics_exposure": {
                "student_ranking": False,
                "misconception_sharing": True,
                "behavioral_profiling_exposure": "AGGREGATED"
            }
        }

    def update_governance_policy(self, institution_id: int, new_config: Dict[str, Any]) -> bool:
        """Updates the institutional governance policy."""
        inst = self.db.query(Institution).get(institution_id)
        if not inst:
            return False
        
        current_config = inst.config or self.get_default_config()
        current_config.update(new_config)
        inst.config = current_config
        self.db.commit()
        return True

    def validate_action_against_governance(self, institution_id: int, action_type: str, payload: Dict[str, Any]) -> bool:
        """Checks if a proposed educational action complies with institutional policy."""
        config = self.get_institution_config(institution_id)
        
        if action_type == "START_EXPERIMENT":
            return config.get("experimentation_allowed", True)
            
        if action_type == "EXPOSE_BEHAVIORAL_DATA":
            mode = config.get("privacy_mode", "STRICT")
            if mode == "STRICT":
                return payload.get("is_anonymized", False)
            return True
            
        return True
