from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Dict, Any, Optional
from app.models.domain import EducationalEscalation, Cohort, User, CohortMembership

class EducationalEscalationSystem:
    def __init__(self, db: Session):
        self.db = db

    def trigger_escalation(self, type: str, target_id: str, severity: str, trigger_payload: Dict[str, Any]) -> EducationalEscalation:
        """Triggers a formal educational escalation."""
        escalation = EducationalEscalation(
            type=type,
            target_id=target_id,
            severity=severity,
            trigger_payload=trigger_payload,
            status="OPEN"
        )
        self.db.add(escalation)
        self.db.commit()
        self.db.refresh(escalation)
        
        # Log for observability
        print(f"ESCALATION | New {severity} escalation triggered for {target_id} | Type: {type}")
        return escalation

    def resolve_escalation(self, escalation_id: int, resolution_payload: Dict[str, Any]) -> EducationalEscalation:
        """Resolves an open escalation with educator input."""
        escalation = self.db.query(EducationalEscalation).get(escalation_id)
        if not escalation:
            raise Exception("Escalation not found")
            
        escalation.status = "RESOLVED"
        escalation.resolution_payload = resolution_payload
        self.db.commit()
        self.db.refresh(escalation)
        return escalation

    def get_active_escalations(self, cohort_id: Optional[int] = None) -> List[EducationalEscalation]:
        """Retrieves current open escalations, optionally filtered by cohort."""
        query = self.db.query(EducationalEscalation).filter(EducationalEscalation.status == "OPEN")
        if cohort_id:
            # This would require linking target_id to cohort_id (assuming target_id is cohort_id for now)
            query = query.filter(EducationalEscalation.target_id == str(cohort_id))
        return query.order_by(desc(EducationalEscalation.severity), desc(EducationalEscalation.created_at)).all()
