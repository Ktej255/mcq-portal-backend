import sys
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.domain import Question, Attempt, AttemptAnswer, Test, AttemptStatusEnum
from app.services.scoring_engine import ScoringEngine
from app.services.report_service import generate_report

def run_validation():
    db = SessionLocal()
    try:
        # 1. Setup Environment Batch 1 Test (ID 1)
        test = db.query(Test).filter(Test.id == 1).first()
        if not test:
            print("ERROR: Environment Batch 1 (Test ID 1) not found.")
            return

        questions = db.query(Question).filter(Question.test_id == test.id).all()
        q_count = len(questions)
        print(f"Validating {test.title} with {q_count} questions.")

        scenarios = [
            {"name": "PERFECT", "correct": q_count, "incorrect": 0, "skipped": 0},
            {"name": "ZERO", "correct": 0, "incorrect": q_count, "skipped": 0},
            {"name": "MIXED", "correct": 20, "incorrect": 20, "skipped": 10},
            {"name": "SKIPPED", "correct": 0, "incorrect": 0, "skipped": q_count},
        ]

        for scenario in scenarios:
            print(f"\n--- Testing Scenario: {scenario['name']} ---")
            
            # Create a mock attempt
            attempt = Attempt(
                user_id=1, # Admin/Default User
                test_id=test.id,
                status=AttemptStatusEnum.IN_PROGRESS,
                start_time=datetime.now(timezone.utc)
            )
            db.add(attempt)
            db.flush()

            # Create answers based on scenario
            answers = []
            for i, q in enumerate(questions):
                if i < scenario['correct']:
                    # Correct Answer
                    ans = AttemptAnswer(
                        attempt_id=attempt.id,
                        question_id=q.id,
                        selected_option=q.correct_option,
                        is_skipped=False,
                        time_taken_seconds=30
                    )
                elif i < (scenario['correct'] + scenario['incorrect']):
                    # Incorrect Answer
                    wrong_option = "B" if q.correct_option == "A" else "A"
                    ans = AttemptAnswer(
                        attempt_id=attempt.id,
                        question_id=q.id,
                        selected_option=wrong_option,
                        is_skipped=False,
                        time_taken_seconds=45
                    )
                else:
                    # Skipped
                    ans = AttemptAnswer(
                        attempt_id=attempt.id,
                        question_id=q.id,
                        selected_option=None,
                        is_skipped=True,
                        time_taken_seconds=5
                    )
                db.add(ans)
                answers.append(ans)
            
            db.flush()
            
            # Submit Attempt
            attempt.status = AttemptStatusEnum.SUBMITTED
            attempt.end_time = datetime.now(timezone.utc)
            db.commit()

            # Generate Report
            report = generate_report(db, attempt.id, 1)
            
            # VERIFY MATH
            print(f"Report Generated: ID {report.id}")
            print(f"Counts: C:{report.correct_count}, I:{report.incorrect_count}, U:{report.unattempted_count}")
            
            total_sum = report.correct_count + report.incorrect_count + report.unattempted_count
            if total_sum != q_count:
                print(f"!!! MATH FAILURE: Sum {total_sum} != Total {q_count}")
            else:
                print(f"SUCCESS: Math reconciled (Sum = {total_sum})")

            # Check Score
            expected_score = (report.correct_count * 2.0) - (report.incorrect_count * 0.66)
            if abs(report.total_score - expected_score) > 0.01:
                print(f"!!! SCORE FAILURE: Found {report.total_score}, expected {expected_score}")
            else:
                print(f"SUCCESS: Score reconciled ({report.total_score})")

    finally:
        db.close()

if __name__ == "__main__":
    run_validation()
