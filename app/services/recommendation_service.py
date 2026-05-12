from sqlalchemy.orm import Session
from app.models.domain import User, Topic, Subject, Test
from typing import List, Dict, Any

def get_personalized_recommendations(db: Session, user_id: int) -> Dict[str, Any]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.topic_mastery:
        return {
            "message": "Start taking tests to get personalized recommendations!",
            "recommendations": []
        }

    weak_topics = []
    for topic_name, data in user.topic_mastery.items():
        if data['mastery_score'] < 60:
            # Find the Topic object to get prerequisites
            topic_obj = db.query(Topic).filter(Topic.name == topic_name).first()
            if topic_obj:
                weak_topics.append(topic_obj)

    recommendations = []
    
    for topic in weak_topics:
        # Check prerequisites
        if topic.prerequisites:
            for pre_id in topic.prerequisites:
                pre_topic = db.query(Topic).filter(Topic.id == pre_id).first()
                if pre_topic:
                    # If prerequisite mastery is also low, recommend prerequisite first
                    pre_mastery = user.topic_mastery.get(pre_topic.name, {}).get('mastery_score', 0)
                    if pre_mastery < 70:
                        recommendations.append({
                            "type": "REVISION",
                            "topic": pre_topic.name,
                            "reason": f"Foundational for {topic.name}",
                            "priority": "HIGH"
                        })
        
        recommendations.append({
            "type": "PRACTICE_DRILL",
            "topic": topic.name,
            "reason": f"Mastery is currently at {user.topic_mastery[topic.name]['mastery_score']:.1f}%",
            "priority": "MEDIUM"
        })

    # Sort by priority and limit
    priority_map = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recommendations.sort(key=lambda x: priority_map.get(x['priority'], 3))

    return {
        "status": "ANALYZED",
        "recommendations": recommendations[:5]
    }
