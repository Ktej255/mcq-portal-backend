import sys
import os
from datetime import datetime, timezone, timedelta
import random

# Add app to path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.models.domain import User, Attempt, AttemptAnswer, Question, ExamEvent, Report
from app.services.report_service import run_async_cognitive_pipeline
from app.services.revision_service import populate_revision_queue_from_attempt

def create_persona_attempt(db, user_id, test_id, persona_name, accuracy_rate, avg_time_sec, variance_sec=5):
    print(f"--- Simulating Persona: {persona_name} ---")
    
    # 1. Create Attempt
    attempt = Attempt(
        user_id=user_id,
        test_id=test_id,
        status="SUBMITTED",
        start_time=datetime.now(timezone.utc) - timedelta(minutes=60),
        end_time=datetime.now(timezone.utc),
        is_simulation=True
    )
    db.add(attempt)
    db.flush()
    
    questions = db.query(Question).filter(Question.test_id == test_id).all()
    
    for i, q in enumerate(questions):
        # Determine if correct based on accuracy_rate
        is_correct = random.random() < accuracy_rate
        selected_option = q.correct_option if is_correct else (
            "A" if q.correct_option != "A" else "B"
        )
        
        # Pacing
        time_taken = max(1, random.gauss(avg_time_sec, variance_sec))
        
        # Confidence logic based on persona
        if persona_name == "Panic Student":
            confidence = "BLIND_GUESS" if random.random() > 0.5 else "EDUCATED_GUESS"
        elif persona_name == "Fragile Topper":
            confidence = "HUNDRED_PERCENT" if random.random() > 0.8 else "FAIRLY_SURE"
        else:
            confidence = "EDUCATED_GUESS"
            
        ans = AttemptAnswer(
            attempt_id=attempt.id,
            question_id=q.id,
            selected_option=selected_option,
            is_correct=is_correct,
            is_skipped=False,
            time_taken_seconds=time_taken,
            confidence_level=confidence,
            marked_for_review=(random.random() < 0.3 if persona_name == "Panic Student" else False)
        )
        db.add(ans)
        
        # Add some events for telemetry
        event = ExamEvent(
            attempt_id=attempt.id,
            event_type="QUESTION_VIEWED",
            question_id=q.id,
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=(50-i)*avg_time_sec),
            payload={"duration": time_taken}
        )
        db.add(event)
    
    db.commit()
    print(f"Created Attempt {attempt.id} for {persona_name}")
    
    # 2. Trigger Report & Revision
    from app.services.report_service import generate_report
    generate_report(db, attempt.id, user_id)
    run_async_cognitive_pipeline(attempt.id, user_id)
    print(f"Report and Revision generated for Attempt {attempt.id}")
    return attempt.id

def main():
    db = SessionLocal()
    test_id = 1 # Environment Batch 1
    
    # Create or get users
    personas = [
        {"name": "Panic Student", "accuracy": 0.3, "time": 8, "email": "panic@antigravity.dev"},
        {"name": "Slow Serious Student", "accuracy": 0.6, "time": 150, "email": "slow@antigravity.dev"},
        {"name": "Fragile Topper", "accuracy": 0.85, "time": 45, "email": "topper@antigravity.dev"},
        {"name": "Recovery Student", "accuracy": 0.4, "time": 60, "email": "recovery@antigravity.dev"}
    ]
    
    for p in personas:
        user = db.query(User).filter(User.email == p["email"]).first()
        if not user:
            user = User(email=p["email"], full_name=p["name"], google_uid=f"sim_{p['name'].lower().replace(' ', '_')}")
            db.add(user)
            db.commit()
            db.refresh(user)
        
        create_persona_attempt(db, user.id, test_id, p["name"], p["accuracy"], p["time"])
    
    # Simulate 2nd attempt for Recovery Student
    recovery_user = db.query(User).filter(User.email == "recovery@antigravity.dev").first()
    if recovery_user:
        create_persona_attempt(db, recovery_user.id, test_id, "Recovery Student (Attempt 2)", 0.85, 45)

if __name__ == "__main__":
    main()
