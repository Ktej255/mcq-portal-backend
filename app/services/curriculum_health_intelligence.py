from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Dict, Any
from app.models.domain import Topic, Question, AttemptAnswer, Report, Attempt

class CurriculumHealthIntelligence:
    def __init__(self, db: Session):
        self.db = db

    def analyze_curriculum_health(self, subject_id: int) -> Dict[str, Any]:
        """Analyzes the structural and performance health of a curriculum."""
        # 1. Detect Weak Regions (Topics with lowest aggregate accuracy)
        weak_regions = self.db.query(
            Topic.name,
            func.avg(Report.accuracy).label("avg_accuracy")
        ).select_from(Report)\
         .join(Attempt, Report.attempt_id == Attempt.id)\
         .join(AttemptAnswer, Attempt.id == AttemptAnswer.attempt_id)\
         .join(Question, AttemptAnswer.question_id == Question.id)\
         .join(Topic, Question.topic_id == Topic.id)\
         .filter(Topic.subject_id == subject_id)\
         .group_by(Topic.id, Topic.name)\
         .order_by("avg_accuracy")\
         .limit(5).all()

        # 2. Identify Bottleneck Topics (Low mastery prerequisites)
        # This is simplified. Real logic would trace dependency graphs.
        bottlenecks = self.db.query(
            Topic.name,
            func.avg(Report.accuracy).label("avg_accuracy")
        ).filter(
            Topic.subject_id == subject_id,
            Topic.prerequisites.isnot(None)
        ).group_by(Topic.id, Topic.name)\
         .having(func.avg(Report.accuracy) < 40)\
         .limit(5).all()

        # 3. Conceptual Overload Detection (Topics with high average time spent but low accuracy)
        overloaded = self.db.query(
            Topic.name,
            func.avg(AttemptAnswer.time_taken_seconds).label("avg_time"),
            func.avg(Report.accuracy).label("avg_accuracy")
        ).select_from(AttemptAnswer)\
         .join(Question, AttemptAnswer.question_id == Question.id)\
         .join(Topic, Question.topic_id == Topic.id)\
         .join(Attempt, AttemptAnswer.attempt_id == Attempt.id)\
         .join(Report, Attempt.id == Report.attempt_id)\
         .filter(Topic.subject_id == subject_id)\
         .group_by(Topic.id, Topic.name)\
         .having(func.avg(AttemptAnswer.time_taken_seconds) > 120) \
         .order_by(desc("avg_time"))\
         .limit(5).all()

        return {
            "subject_id": subject_id,
            "weak_regions": [{"topic": r.name, "accuracy": float(r.avg_accuracy)} for r in weak_regions],
            "bottlenecks": [{"topic": b.name, "accuracy": float(b.avg_accuracy)} for b in bottlenecks],
            "overloaded_concepts": [{"topic": o.name, "avg_time": float(o.avg_time), "accuracy": float(o.avg_accuracy)} for o in overloaded],
            "curriculum_stability_index": self._calculate_stability(subject_id)
        }

    def _calculate_stability(self, subject_id: int) -> float:
        """Calculates a heuristic stability index for the curriculum."""
        # Simplified: Ratio of topics with > 60% accuracy
        total_topics = self.db.query(Topic).filter(Topic.subject_id == subject_id).count()
        if total_topics == 0: return 0.0
        
        stable_topics = self.db.query(Topic.id).join(Question).join(AttemptAnswer).join(Attempt).join(Report)\
            .filter(Topic.subject_id == subject_id)\
            .group_by(Topic.id)\
            .having(func.avg(Report.accuracy) > 60).count()
            
        return round((stable_topics / total_topics) * 100, 2)
