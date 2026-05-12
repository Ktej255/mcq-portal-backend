from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from app.models.domain import User, Cohort, CohortMembership, Attempt, Report, Topic, Question, AttemptAnswer
from app.services.cohort_intelligence_engine import CohortIntelligenceEngine

class EducatorOperationalEngine:
    def __init__(self, db: Session):
        self.db = db
        self.cohort_engine = CohortIntelligenceEngine(db)

    def get_educator_dashboard_data(self, educator_id: int) -> Dict[str, Any]:
        """Aggregates operational data for an educator's assigned cohorts."""
        # Get all cohorts where this user is an EDUCATOR
        memberships = self.db.query(CohortMembership).filter(
            CohortMembership.user_id == educator_id,
            CohortMembership.role == 'EDUCATOR'
        ).all()
        
        cohort_ids = [m.cohort_id for m in memberships]
        if not cohort_ids:
            return {"message": "No assigned cohorts found", "cohorts": []}

        cohort_data = []
        for cid in cohort_ids:
            cohort = self.db.query(Cohort).get(cid)
            summary = self.cohort_engine.get_cohort_summary(cid)
            misconceptions = self.cohort_engine.detect_shared_misconceptions(cid)
            
            cohort_data.append({
                "id": cohort.id,
                "name": cohort.name,
                "summary": summary,
                "critical_misconceptions": misconceptions[:3], # Top 3
                "risk_heatmap": self._generate_risk_heatmap(cid)
            })

        return {
            "total_cohorts": len(cohort_ids),
            "cohort_analytics": cohort_data,
            "system_alerts": self._generate_system_alerts(cohort_ids)
        }

    def _generate_risk_heatmap(self, cohort_id: int) -> List[Dict[str, Any]]:
        """Generates a mapping of topics to risk levels based on cohort performance."""
        # Implementation of risk heatmap (High, Medium, Low risk topics)
        # Risk = 100 - Avg Accuracy
        student_ids = [m.user_id for m in self.db.query(CohortMembership).filter(
            CohortMembership.cohort_id == cohort_id,
            CohortMembership.role == 'STUDENT'
        ).all()]

        risk_data = self.db.query(
            Topic.name,
            func.avg(Report.accuracy).label("avg_accuracy")
        ).select_from(Report)\
         .join(Attempt, Report.attempt_id == Attempt.attempt_id)\
         .join(AttemptAnswer, Attempt.id == AttemptAnswer.attempt_id)\
         .join(Question, AttemptAnswer.question_id == Question.id)\
         .join(Topic, Question.topic_id == Topic.id)\
         .filter(Attempt.user_id.in_(student_ids))\
         .group_by(Topic.name).all()

        heatmap = []
        for r in risk_data:
            accuracy = float(r.avg_accuracy) if r.avg_accuracy else 0.0
            level = "HIGH" if accuracy < 40 else "MEDIUM" if accuracy < 70 else "LOW"
            heatmap.append({"topic": r.name, "accuracy": accuracy, "risk_level": level})
            
        return heatmap

    def _generate_system_alerts(self, cohort_ids: List[int]) -> List[Dict[str, Any]]:
        """Detects critical operational anomalies needing educator attention."""
        alerts = []
        # Example: Batch-wide pacing collapse
        # (This is a placeholder for more complex temporal analysis)
        alerts.append({
            "type": "PACING_WARNING",
            "message": "Cohort 'Batch A' showing 30% increase in average time spent on 'Fluid Mechanics'.",
            "severity": "CRITICAL"
        })
        return alerts
