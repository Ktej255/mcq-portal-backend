from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.services.cohort_intelligence_engine import CohortIntelligenceEngine
from app.services.curriculum_health_intelligence import CurriculumHealthIntelligence
from app.models.domain import Cohort

class InstitutionalInterventionSystem:
    def __init__(self, db: Session):
        self.db = db
        self.cohort_engine = CohortIntelligenceEngine(db)
        self.curriculum_engine = CurriculumHealthIntelligence(db)

    def generate_institutional_recommendations(self, institution_id: int) -> List[Dict[str, Any]]:
        """Generates high-level intervention strategies for an institution."""
        cohorts = self.db.query(Cohort).filter(Cohort.institution_id == institution_id).all()
        recommendations = []

        for cohort in cohorts:
            summary = self.cohort_engine.get_cohort_summary(cohort.id)
            
            # 1. Group Remediation for critical weaknesses
            for weakness in summary.get("top_weaknesses", []):
                if weakness["accuracy"] < 50:
                    recommendations.append({
                        "type": "GROUP_REMEDIATION",
                        "target": f"Cohort: {cohort.name}",
                        "subject": weakness["topic"],
                        "priority": "HIGH",
                        "reason": f"Shared accuracy below 50% in {weakness['topic']}."
                    })

            # 2. Prerequisite Workshops
            # If a curriculum bottleneck is detected, recommend a workshop
            # (Assuming subject_id 1 for demonstration)
            health = self.curriculum_engine.analyze_curriculum_health(1)
            for bottleneck in health.get("bottlenecks", []):
                recommendations.append({
                    "type": "PREREQUISITE_WORKSHOP",
                    "target": f"All Cohorts (Subject 1)",
                    "subject": bottleneck["topic"],
                    "priority": "CRITICAL",
                    "reason": f"Curriculum bottleneck detected in {bottleneck['topic']}."
                })

        return recommendations

    def schedule_conceptual_reinforcement(self, cohort_id: int, topic: str) -> bool:
        """Schedules a targeted reinforcement session for a batch."""
        # Integration with scheduling system would happen here
        print(f"SCHEDULER | Reinforcement session scheduled for Cohort {cohort_id} on Topic: {topic}")
        return True
