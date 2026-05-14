from sqlalchemy.orm import Session
from app.models.domain import RevisionQueue, Attempt, AttemptAnswer, Question
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

def populate_revision_queue_from_attempt(db: Session, attempt_id: int, user_id: int):
    """
    Analyzes an attempt and populates the revision queue with incorrect or flagged questions.
    """
    logger.info(f"FORENSIC | Populating Revision Queue for Attempt {attempt_id}")
    
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    
    for ans in answers:
        # 1. Handle Incorrect Answers
        if ans.is_correct == False and not ans.is_skipped:
            _upsert_revision_item(
                db, user_id, ans.question.topic_id, ans.question_id, 
                reason="INCORRECT_ANSWER", 
                category="MISTAKE",
                priority=1.0
            )
        
        # 2. Handle Marked for Review
        elif ans.marked_for_review:
            _upsert_revision_item(
                db, user_id, ans.question.topic_id, ans.question_id,
                reason="MARKED_FOR_REVIEW",
                category="WEAKNESS",
                priority=0.5
            )

def _upsert_revision_item(db: Session, user_id: int, topic_id: int, question_id: int, reason: str, category: str, priority: float):
    # Check if already in queue
    existing = db.query(RevisionQueue).filter(
        RevisionQueue.user_id == user_id,
        RevisionQueue.question_id == question_id
    ).first()
    
    if existing:
        existing.priority_score = max(existing.priority_score, priority)
        # If they got it wrong again, move it to the front of the queue
        existing.next_review_at = datetime.now(timezone.utc)
        logger.info(f"FORENSIC | Updated Revision Item for Q{question_id}")
    else:
        new_item = RevisionQueue(
            user_id=user_id,
            topic_id=topic_id,
            question_id=question_id,
            reason=reason,
            category=category,
            priority_score=priority,
            next_review_at=datetime.now(timezone.utc),
            mastery_level=0.0,
            review_count=0
        )
        db.add(new_item)
        logger.info(f"FORENSIC | Created Revision Item for Q{question_id}")
    
    db.commit()
