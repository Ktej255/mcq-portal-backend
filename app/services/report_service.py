from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime, timezone
from app.models.domain import Attempt, AttemptStatusEnum, AttemptAnswer, Question, Report, Topic, Subject
from app.services.narrative_service import generate_performance_narrative
from app.services.longitudinal_service import update_student_evolution
from app.services.domain_contracts import detect_analytics_anomalies

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
            topic_wise[topic_name] = {"correct": 0, "incorrect": 0, "skipped": 0, "total": 0, "time": 0}
        if subject_name not in subject_wise:
            subject_wise[subject_name] = {"correct": 0, "incorrect": 0, "skipped": 0, "total": 0, "time": 0}
            
        topic_wise[topic_name]["total"] += 1
        subject_wise[subject_name]["total"] += 1
        
        if not ans or ans.is_skipped or ans.selected_option is None:
            unattempted_count += 1
            topic_wise[topic_name]["skipped"] += 1
            subject_wise[subject_name]["skipped"] += 1
        else:
            total_time += ans.time_taken_seconds
            topic_wise[topic_name]["time"] += ans.time_taken_seconds
            subject_wise[subject_name]["time"] += ans.time_taken_seconds
            
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

    total_qs = len(questions)
    attempted_count = correct_count + incorrect_count
    
    # FORENSIC RECONCILIATION: Total must equal sum of outcomes
    if total_qs != (correct_count + incorrect_count + unattempted_count):
        raise HTTPException(status_code=500, detail="Forensic Mismatch: Total != Correct + Incorrect + Skipped")

    # Accuracy relative to total questions as per Directive
    accuracy = (correct_count / total_qs) * 100 if total_qs > 0 else 0
    total_score = (correct_count * test.correct_marks) - (incorrect_count * test.negative_marking_value)
    avg_time = total_time / total_qs if total_qs > 0 else 0
    
    # Build Forensic Metadata
    forensic_data = {
        "total_questions": total_qs,
        "attempted_count": attempted_count,
        "skipped_count": unattempted_count,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "final_score": total_score,
        "accuracy_formula": "Correct / Total",
        "raw_accuracy": accuracy,
        "negative_marks": incorrect_count * test.negative_marking_value
    }
    
    report = Report(
        attempt_id=attempt_id,
        total_score=total_score,
        accuracy=accuracy,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        unattempted_count=unattempted_count,
        topic_wise_analysis=topic_wise,
        subject_wise_performance=subject_wise,
        confidence_analysis=confidence_stats,
        average_time_per_question=avg_time,
        forensic_data=forensic_data,
        processing_status="PENDING",
        generated_at=datetime.now(timezone.utc)
    )
    
    db.add(report)
    db.commit()
    db.refresh(report)
    
    return report

def run_async_cognitive_pipeline(attempt_id: int, user_id: int):
    """
    Handles heavy cognitive analysis, AI narratives, and mastery updates.
    Run in background tasks.
    """
    from app.db.session import SessionLocal
    from app.services.cognitive_engine import cognitive_engine
    from app.services.narrative_evaluator import narrative_evaluator
    from app.services.student_longitudinal_profile import create_cognitive_snapshot, update_longitudinal_profile
    
    db = SessionLocal()
    try:
        report = db.query(Report).filter(Report.attempt_id == attempt_id).first()
        if not report: return

        # 1. Advanced Telemetry Reconstruction
        events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).all()
        from app.services.telemetry_reconstruction import reconstruct_attempt_timeline
        telemetry = reconstruct_attempt_timeline(events)
        report.telemetry_summary = telemetry
        
        # 2. Advanced Cognitive Analysis
        behavioral = cognitive_engine.analyze_attempt(db, attempt_id)
        report.behavioral_analysis = behavioral.dict()
        
        # 3. AI Narrative Generation
        narrative_input = {
            "total_score": report.total_score, 
            "accuracy": report.accuracy, 
            "correct_count": report.correct_count, 
            "incorrect_count": report.incorrect_count, 
            "unattempted_count": report.unattempted_count,
            "topic_wise_analysis": report.topic_wise_analysis
        }
        report.narrative = generate_performance_narrative(narrative_input, behavioral.dict())
        
        # 4. Narrative Evaluation (Phase 6C)
        evaluation = narrative_evaluator.evaluate(report.narrative, narrative_input, behavioral.dict())
        report.evaluation_metadata = evaluation.dict()
        
        # 5. Immutable cognitive snapshot + longitudinal evolution update
        create_cognitive_snapshot(db, user_id, attempt_id, behavioral.dict())
        update_student_evolution(db, user_id)
        update_longitudinal_profile(db, user_id)
        
        report.processing_status = "COMPLETED"
        db.commit()
    except Exception as e:
        import traceback
        print(f"Async Pipeline Error: {str(e)}")
        traceback.print_exc()
        if report:
            report.processing_status = "FAILED"
            db.commit()
    finally:
        db.close()

def get_detailed_review(db: Session, attempt_id: int, user_id: int):
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == user_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
        
    questions = db.query(Question).filter(Question.test_id == attempt.test_id).all()
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).order_by(ExamEvent.timestamp.asc()).all()
    
    ans_map = {ans.question_id: ans for ans in answers}
    event_map = {}
    for ev in events:
        qid = ev.question_id
        if qid not in event_map: event_map[qid] = []
        event_map[qid].append(ev)
    
    review_data = []
    avg_time = sum(a.time_taken_seconds for a in answers) / len(answers) if answers else 30
    
    for q in questions:
        ans = ans_map.get(q.id)
        q_events = event_map.get(q.id, [])
        
        # Operational Classification (Phase 2)
        interaction_type = "SKIPPED"
        if ans and not ans.is_skipped:
            is_fast = ans.time_taken_seconds < (avg_time * 0.5)
            is_slow = ans.time_taken_seconds > (avg_time * 1.5)
            is_correct = ans.is_correct
            has_revisions = len([e for e in q_events if e.event_type == "ANSWER_CHANGED"]) > 0
            is_high_conf = ans.confidence_level == ConfidenceEnum.HUNDRED_PERCENT
            
            if is_correct:
                if is_fast: interaction_type = "FAST_CORRECT"
                elif is_slow: interaction_type = "SLOW_CORRECT"
                else: interaction_type = "STABLE_CORRECT"
                
                if has_revisions: interaction_type = "RECOVERY_CORRECT"
            else:
                if is_fast: interaction_type = "FAST_INCORRECT"
                elif is_slow: interaction_type = "SLOW_INCORRECT"
                else: interaction_type = "STABLE_INCORRECT"
                
                if is_high_conf: interaction_type = "CONFIDENCE_TRAP"
                if has_revisions: interaction_type = "REVISION_FAILURE"

        # Forensic Evidence (Phase 3)
        first_view = q_events[0].timestamp if q_events else None
        last_action = q_events[-1].timestamp if q_events else None
        revisions = len([e for e in q_events if e.event_type == "ANSWER_CHANGED"])
        
        review_data.append({
            "id": q.id,
            "text_en": q.text_en,
            "text_hi": q.text_hi,
            "options_en": q.options_en,
            "options_hi": q.options_hi,
            "correct_option": q.correct_option,
            "explanation_en": q.explanation_en,
            "explanation_hi": q.explanation_hi,
            "topic": q.topic.name,
            "subject": q.topic.subject.name,
            "difficulty": getattr(q, 'difficulty', 'MEDIUM'),
            "selected_option": ans.selected_option if ans else None,
            "is_correct": ans.is_correct if ans else False,
            "time_taken_seconds": ans.time_taken_seconds if ans else 0,
            "confidence_level": ans.confidence_level.value if ans and ans.confidence_level else "UNKNOWN",
            "marked_for_review": ans.marked_for_review if ans else False,
            "interaction_type": interaction_type,
            "forensic_evidence": {
                "first_view": first_view.isoformat() if first_view else None,
                "last_action": last_action.isoformat() if last_action else None,
                "revisions": revisions,
                "dwell_time": ans.time_taken_seconds if ans else 0
            }
        })
    return review_data

def get_behavioral_analysis(db: Session, attempt_id: int, user_id: int):
    # This would typically be part of generate_report or a separate analysis engine
    # For now, let's just return a template of what we can derive
    attempt = db.query(Attempt).filter(Attempt.id == attempt_id, Attempt.user_id == user_id).first()
    if not attempt: return {}
    
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    
    analysis = {
        "guessing_rate": 0,
        "hesitation_index": 0,
        "overconfidence_rate": 0,
        "anxiety_index": 0
    }
    
    if not answers: return analysis
    
    from app.models.domain import ConfidenceEnum
    blind_guesses = [a for a in answers if a.confidence_level == ConfidenceEnum.BLIND_GUESS]
    sure_wrong = [a for a in answers if a.confidence_level == ConfidenceEnum.HUNDRED_PERCENT and a.is_correct == False]
    long_time_right = [a for a in answers if a.time_taken_seconds > 60 and a.is_correct == True]
    
    analysis["guessing_rate"] = len(blind_guesses) / len(answers) * 100
    analysis["overconfidence_rate"] = len(sure_wrong) / len(answers) * 100
    analysis["hesitation_index"] = len(long_time_right) / len(answers) * 100
    
    return analysis
