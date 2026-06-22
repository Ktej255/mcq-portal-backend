from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.db.session import get_db
from app.api.dependencies import get_current_user
from app.models.domain import User, RevisionQueue, Question, Topic


router = APIRouter()

@router.get("/", response_model=List[dict])
def get_revision_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the pending revision items for the current user.
    """
    items = db.query(RevisionQueue).filter(
        RevisionQueue.user_id == current_user.id,
        RevisionQueue.next_review_at <= datetime.now(timezone.utc)
    ).order_by(RevisionQueue.priority_score.desc()).all()
    
    result = []
    for item in items:
        result.append({
            "id": item.id,
            "topic": item.topic.name if item.topic else "General",
            "reason": item.reason,
            "priority": item.priority_score,
            "question_id": item.question_id,
            "review_count": item.review_count,
            "mastery": item.mastery_level
        })
    return result

@router.get("/rapid-drill", response_model=List[dict])
def rapid_drill(
    mode: str = "recovery", # recovery, mistakes, weak_topic, high_confidence_mistake
    topic_id: int = None,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Priority 2: Micro-Revision Mode.
    Fast retrieval for daily consistency drills.
    """
    query = db.query(RevisionQueue).filter(RevisionQueue.user_id == current_user.id)
    
    if mode == "mistakes":
        query = query.filter(RevisionQueue.category == "MISTAKE")
    elif mode == "weak_topic" and topic_id:
        query = query.filter(RevisionQueue.topic_id == topic_id)
    elif mode == "recovery":
        # Mix of everything, prioritized by score
        pass
        
    items = query.order_by(RevisionQueue.priority_score.desc()).limit(limit).all()
    
    result = []
    for item in items:
        q = item.question
        if not q: continue
        
        result.append({
            "id": q.id,
            "revision_item_id": item.id,
            "test_id": q.test_id,
            "topic_id": q.topic_id,
            "subject": q.topic.subject.name if q.topic and q.topic.subject else "General",
            "textEn": q.text_en,
            "textHi": q.text_hi,
            "options": [
                {"id": "A", "textEn": q.options_en.get("A", ""), "textHi": q.options_hi.get("A", "") if q.options_hi else ""},
                {"id": "B", "textEn": q.options_en.get("B", ""), "textHi": q.options_hi.get("B", "") if q.options_hi else ""},
                {"id": "C", "textEn": q.options_en.get("C", ""), "textHi": q.options_hi.get("C", "") if q.options_hi else ""},
                {"id": "D", "textEn": q.options_en.get("D", ""), "textHi": q.options_hi.get("D", "") if q.options_hi else ""},
            ],
            "correct_option": q.correct_option,
            "positiveMarks": 1.0, # Default for revision
            "negativeMarks": 0.33,
            "difficulty": q.difficulty,
            "category": item.category,
            "priority": item.priority_score
        })
    return result

@router.post("/{item_id}/complete")
def complete_revision(
    item_id: int,
    mastery_delta: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mark a revision item as completed and schedule next review.
    """
    item = db.query(RevisionQueue).filter(
        RevisionQueue.id == item_id,
        RevisionQueue.user_id == current_user.id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Revision item not found")
        
    item.last_reviewed_at = datetime.now(timezone.utc)
    item.review_count += 1
    item.mastery_level = min(1.0, item.mastery_level + mastery_delta)
    
    # Simple Spaced Repetition logic (Power of 2 days)
    days_to_next = 2 ** item.review_count
    item.next_review_at = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Note: In a real app, I'd use timedelta. For simplicity here:
    from datetime import timedelta
    item.next_review_at += timedelta(days=days_to_next)
    
    db.commit()
@router.post("/bulk-complete")
def bulk_complete_revision(
    payload: List[dict], # [{question_id, is_correct}]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Process multiple revision items at once after a rapid drill.
    """
    from datetime import timedelta
    
    results = []
    for entry in payload:
        q_id = entry.get("question_id")
        is_correct = entry.get("is_correct")
        
        # Find the revision item for this question
        item = db.query(RevisionQueue).filter(
            RevisionQueue.user_id == current_user.id,
            RevisionQueue.question_id == q_id
        ).first()
        
        if not item:
            continue
            
        # Mastery update logic
        mastery_delta = 0.2 if is_correct else -0.1
        item.last_reviewed_at = datetime.now(timezone.utc)
        item.review_count += 1
        item.mastery_level = clamp(item.mastery_level + mastery_delta, 0.0, 1.0)
        
        # Spaced Repetition (simplified)
        days_to_next = 1 if not is_correct else 2 ** item.review_count
        item.next_review_at = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_to_next)
        
        results.append({"question_id": q_id, "next_review": item.next_review_at})
        
    db.commit()
    return {"status": "success", "processed": len(results), "items": results}

def clamp(val, min_val, max_val):
    return max(min_val, min(max_val, val))

@router.get("/recovery-path/{topic_id}")
async def get_recovery_path(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Concept recovery: the student's REAL recorded weak points in this topic.

    Built from the student's own ``RevisionQueue`` items for the topic (the
    questions/reasons actually flagged for them) — never fabricated generic
    prerequisites. When nothing is recorded yet, returns an honest empty path so
    the UI can say so rather than inventing steps.
    """
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    items = (
        db.query(RevisionQueue)
        .filter(
            RevisionQueue.user_id == current_user.id,
            RevisionQueue.topic_id == topic_id,
        )
        .order_by(RevisionQueue.priority_score.desc())
        .limit(5)
        .all()
    )

    reason_titles = {
        "WEAK_TOPIC": "Weak topic — rebuild the fundamentals",
        "INCORRECT_ANSWER": "Mistake to re-attempt",
        "MARKED_FOR_REVIEW": "Flagged for review",
        "SPACED_REPETITION": "Due for spaced recall",
    }

    def _priority(mastery: float) -> str:
        if mastery < 0.34:
            return "CRITICAL"
        if mastery < 0.67:
            return "HIGH"
        return "MEDIUM"

    steps = [
        {
            "title": reason_titles.get(item.reason or "", item.reason) or f"Revise {topic.name}",
            "priority": _priority(item.mastery_level or 0.0),
        }
        for item in items
    ]

    if steps:
        message = (
            f"{len(steps)} recorded weak point(s) in {topic.name}. "
            "Clear these from your revision queue to recover the topic."
        )
    else:
        message = (
            f"No recorded weaknesses in {topic.name} yet. Attempt or revise it "
            "and your recovery path will build from your real results."
        )

    return {
        "primary_topic": topic.name,
        "suggested_prerequisites": steps,
        "message": message,
    }

@router.get("/history", response_model=List[dict])
def get_revision_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Priority 5: Revision History Timeline.
    Tracks continuity and effort over time.
    """
    # Simply return items that have been reviewed
    items = db.query(RevisionQueue).filter(
        RevisionQueue.user_id == current_user.id,
        RevisionQueue.last_reviewed_at != None
    ).order_by(RevisionQueue.last_reviewed_at.desc()).limit(limit).all()
    
    return [{
        "id": item.id,
        "topic": item.topic.name if item.topic else "General",
        "last_reviewed_at": item.last_reviewed_at,
        "mastery_at_time": item.mastery_level,
        "category": item.category
    } for item in items]


