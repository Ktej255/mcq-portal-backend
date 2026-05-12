from sqlalchemy.orm import Session
from app.models.domain import User, Attempt, Report, StudentEvolution, RoleEnum
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

def update_student_evolution(db: Session, user_id: int):
    # 1. Fetch recent reports (last 10)
    reports = db.query(Report).join(Attempt).filter(Attempt.user_id == user_id).order_by(Report.generated_at.desc()).limit(10).all()
    if not reports:
        return

    # 2. Accuracy Evolution
    accuracy_avg = sum([r.accuracy for r in reports]) / len(reports)
    record_evolution(db, user_id, "ACCURACY_AVG_10", accuracy_avg)

    # 3. Topic Mastery Aggregation
    mastery = {}
    for r in reports:
        if r.topic_wise_analysis:
            for topic, stats in r.topic_wise_analysis.items():
                if topic not in mastery:
                    mastery[topic] = []
                topic_accuracy = (stats['correct'] / stats['total']) * 100 if stats['total'] > 0 else 0
                mastery[topic].append(topic_accuracy)
    
    final_mastery = {}
    for topic, accuracies in mastery.items():
        # Weighted average: more recent tests have higher weight
        weighted_sum = 0
        weight_total = 0
        for i, acc in enumerate(reversed(accuracies)):
            weight = i + 1
            weighted_sum += acc * weight
            weight_total += weight
        final_mastery[topic] = {
            "mastery_score": weighted_sum / weight_total,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.topic_mastery = final_mastery
        db.commit()

def record_evolution(db: Session, user_id: int, metric_type: str, value: float):
    evolution = StudentEvolution(
        user_id=user_id,
        metric_type=metric_type,
        value=value,
        timestamp=datetime.now(timezone.utc)
    )
    db.add(evolution)
    db.commit()

def get_student_mastery_heatmap(db: Session, user_id: int) -> Dict[str, float]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.topic_mastery:
        return {}
    return {topic: data['mastery_score'] for topic, data in user.topic_mastery.items()}
