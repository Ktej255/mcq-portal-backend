from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Dict, Any
from app.models.domain import User, Attempt, AttemptAnswer, Question, Topic, CohortMembership, Report

class CohortIntelligenceEngine:
    def __init__(self, db: Session):
        self.db = db

    def get_cohort_summary(self, cohort_id: int) -> Dict[str, Any]:
        """Aggregates high-level intelligence for a specific cohort."""
        # Get all student IDs in the cohort
        student_ids = [m.user_id for m in self.db.query(CohortMembership).filter(
            CohortMembership.cohort_id == cohort_id,
            CohortMembership.role == 'STUDENT'
        ).all()]

        if not student_ids:
            return {"message": "No students found in cohort", "data": {}}

        # Aggregate total attempts and average accuracy
        stats = self.db.query(
            func.count(Attempt.id).label("total_attempts"),
            func.avg(Report.accuracy).label("avg_accuracy")
        ).join(Report, Attempt.id == Report.attempt_id)\
         .filter(Attempt.user_id.in_(student_ids)).first()

        # Identify shared weaknesses (Topics with lowest average accuracy)
        weaknesses = self.db.query(
            Topic.name,
            func.avg(Report.accuracy).label("avg_accuracy")
        ).select_from(Report)\
         .join(Attempt, Report.attempt_id == Attempt.attempt_id)\
         .join(AttemptAnswer, Attempt.id == AttemptAnswer.attempt_id)\
         .join(Question, AttemptAnswer.question_id == Question.id)\
         .join(Topic, Question.topic_id == Topic.id)\
         .filter(Attempt.user_id.in_(student_ids))\
         .group_by(Topic.name)\
         .order_by("avg_accuracy")\
         .limit(5).all()

        return {
            "cohort_id": cohort_id,
            "total_students": len(student_ids),
            "total_attempts": stats.total_attempts if stats else 0,
            "average_accuracy": float(stats.avg_accuracy) if stats and stats.avg_accuracy else 0.0,
            "top_weaknesses": [{"topic": w[0], "accuracy": float(w[1])} for w in weaknesses]
        }

    def detect_shared_misconceptions(self, cohort_id: int) -> List[Dict[str, Any]]:
        """Identifies patterns of incorrect options chosen by a significant % of the cohort."""
        student_ids = [m.user_id for m in self.db.query(CohortMembership).filter(
            CohortMembership.cohort_id == cohort_id,
            CohortMembership.role == 'STUDENT'
        ).all()]

        # Find questions where multiple students chose the SAME incorrect option
        misconceptions = self.db.query(
            Question.id.label("question_id"),
            Question.text_en.label("question_text"),
            AttemptAnswer.selected_option.label("chosen_option"),
            func.count(AttemptAnswer.id).label("count")
        ).join(Attempt, AttemptAnswer.attempt_id == Attempt.id)\
         .join(Question, AttemptAnswer.question_id == Question.id)\
         .filter(
             Attempt.user_id.in_(student_ids),
             AttemptAnswer.is_correct == False,
             AttemptAnswer.selected_option.isnot(None)
         )\
         .group_by(Question.id, Question.text_en, AttemptAnswer.selected_option)\
         .having(func.count(AttemptAnswer.id) > 1)\
         .order_by(desc("count"))\
         .limit(10).all()

        return [
            {
                "question_id": m.question_id,
                "question_text": m.question_text,
                "misconception_option": m.chosen_option,
                "student_count": m.count
            } for m in misconceptions
        ]

    def analyze_topic_volatility(self, cohort_id: int) -> List[Dict[str, Any]]:
        """Identifies topics where performance fluctuates wildly across the cohort."""
        # Implementation of volatility analysis (standard deviation of scores)
        student_ids = [m.user_id for m in self.db.query(CohortMembership).filter(
            CohortMembership.cohort_id == cohort_id,
            CohortMembership.role == 'STUDENT'
        ).all()]

        volatility = self.db.query(
            Topic.name,
            func.stddev(Report.accuracy).label("accuracy_stddev")
        ).select_from(Report)\
         .join(Attempt, Report.attempt_id == Attempt.attempt_id)\
         .join(AttemptAnswer, Attempt.id == AttemptAnswer.attempt_id)\
         .join(Question, AttemptAnswer.question_id == Question.id)\
         .join(Topic, Question.topic_id == Topic.id)\
         .filter(Attempt.user_id.in_(student_ids))\
         .group_by(Topic.name)\
         .having(func.stddev(Report.accuracy) > 0)\
         .order_by(desc("accuracy_stddev"))\
         .limit(5).all()

        return [
            {
                "topic": v.name,
                "volatility_index": float(v.accuracy_stddev) if v.accuracy_stddev else 0.0
            } for v in volatility
        ]
