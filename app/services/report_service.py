from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timezone
from app.models.domain import Attempt, AttemptStatusEnum, AttemptAnswer, Question, Report, Topic, Subject

def generate_report(db: Session, attempt_id: int, user_id: int) -> Report:
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == user_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
        
    if attempt.status != AttemptStatusEnum.SUBMITTED:
        attempt.status = AttemptStatusEnum.SUBMITTED
        attempt.end_time = datetime.now(timezone.utc)
        db.commit()

    # Check if report already exists
    existing_report = db.query(Report).filter(Report.attempt_id == attempt_id).first()
    if existing_report:
        return existing_report

    test = attempt.test
    questions = db.query(Question).filter(Question.test_id == test.id).all()
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    
    ans_map = {ans.question_id: ans for ans in answers}
    
    correct_count = 0
    incorrect_count = 0
    unattempted_count = 0
    
    topic_wise = {}
    subject_wise = {}
    confidence_stats = {}
    total_time = 0
    
    for q in questions:
        ans = ans_map.get(q.id)
        
        # Build topic/subject trackers
        topic_name = q.topic.name
        subject_name = q.topic.subject.name
        
        if topic_name not in topic_wise:
            topic_wise[topic_name] = {"correct": 0, "incorrect": 0, "unattempted": 0, "total": 0}
        if subject_name not in subject_wise:
            subject_wise[subject_name] = {"correct": 0, "incorrect": 0, "unattempted": 0, "total": 0}
            
        topic_wise[topic_name]["total"] += 1
        subject_wise[subject_name]["total"] += 1
        
        if not ans or ans.is_skipped or ans.selected_option is None:
            unattempted_count += 1
            topic_wise[topic_name]["unattempted"] += 1
            subject_wise[subject_name]["unattempted"] += 1
        else:
            total_time += ans.time_taken_seconds
            is_correct = (ans.selected_option == q.correct_option)
            ans.is_correct = is_correct  # Save back evaluation
            
            conf = ans.confidence_level.value if ans.confidence_level else "UNKNOWN"
            if conf not in confidence_stats:
                confidence_stats[conf] = {"correct": 0, "incorrect": 0, "total": 0}
            confidence_stats[conf]["total"] += 1
            
            if is_correct:
                correct_count += 1
                topic_wise[topic_name]["correct"] += 1
                subject_wise[subject_name]["correct"] += 1
                confidence_stats[conf]["correct"] += 1
            else:
                incorrect_count += 1
                topic_wise[topic_name]["incorrect"] += 1
                subject_wise[subject_name]["incorrect"] += 1
                confidence_stats[conf]["incorrect"] += 1

    total_score = (correct_count * test.correct_marks) - (incorrect_count * test.negative_marking_value)
    total_qs = len(questions)
    accuracy = (correct_count / (correct_count + incorrect_count)) * 100 if (correct_count + incorrect_count) > 0 else 0
    avg_time = total_time / total_qs if total_qs > 0 else 0
    
    report = Report(
        attempt_id=attempt_id,
        total_score=total_score,
        accuracy=accuracy,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        unattempted_count=unattempted_count,
        topic_wise_analysis=topic_wise,
        confidence_analysis=confidence_stats,
        generated_at=datetime.now(timezone.utc)
    )
    # Save the evaluation of answers back
    db.add(report)
    db.commit()
    db.refresh(report)
    
    # Injected average time manually into the dict to be returned by schema
    setattr(report, "subject_wise_performance", subject_wise)
    setattr(report, "average_time_per_question", avg_time)
    
    return report
