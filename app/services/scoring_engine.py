from typing import Dict, List, Any

class ScoringEngine:
    @staticmethod
    def calculate_score(test: Any, questions: list, answers: list) -> Dict[str, Any]:
        """
        Centralized Single Scoring Authority.
        All score math must come from this one governed engine.
        No frontend score calculations.
        """
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
            
            topic_name = q.topic.name if q.topic else "Unknown Topic"
            subject_name = q.topic.subject.name if q.topic and q.topic.subject else "Unknown Subject"
            
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
                total_time += ans.time_taken_seconds or 0
                topic_wise[topic_name]["time"] += ans.time_taken_seconds or 0
                subject_wise[subject_name]["time"] += ans.time_taken_seconds or 0
                
                is_correct = (ans.selected_option == q.correct_option)
                
                conf_obj = getattr(ans, 'confidence_level', None)
                conf = conf_obj.value if hasattr(conf_obj, 'value') and conf_obj else (str(conf_obj) if conf_obj else "UNKNOWN")
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

        total_questions = len(questions)
        actual_sum = correct_count + incorrect_count + unattempted_count
        
        if total_questions != actual_sum:
            # This should theoretically be impossible given the loop structure, 
            # but we catch it here to prevent downstream forensic mismatches.
            import logging
            logging.error(f"ScoringEngine Integrity Violation: Total={total_questions} != Sum({actual_sum}) [C:{correct_count}, I:{incorrect_count}, U:{unattempted_count}]")
            # We don't raise here to allow the report service to handle it with more context
            
        attempted_count = correct_count + incorrect_count
        
        # Accuracy is Correct / Attempted (Standard student expectation)
        accuracy_on_attempts = (correct_count / attempted_count * 100) if attempted_count > 0 else 0.0
        
        # Mastery is Correct / Total
        mastery_percentage = (correct_count / total_questions * 100) if total_questions > 0 else 0.0
        
        # Test config marking scheme
        correct_marks = getattr(test, "correct_marks", 1.0)
        negative_marking_value = getattr(test, "negative_marking_value", 0.0)
        
        negative_marks = incorrect_count * negative_marking_value
        total_score = (correct_count * correct_marks) - negative_marks
        max_possible_score = total_questions * correct_marks
        
        score_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0.0

        avg_time = total_time / attempted_count if attempted_count > 0 else 0.0

        evaluations = {}
        for q in questions:
            ans = ans_map.get(q.id)
            if not ans or ans.is_skipped or ans.selected_option is None:
                evaluations[q.id] = False
            else:
                evaluations[q.id] = (ans.selected_option == q.correct_option)

        return {
            "total_score": total_score,
            "max_possible_score": max_possible_score,
            "score_percentage": score_percentage,
            "accuracy": accuracy_on_attempts,      # REDEFINED: Correct / Attempted
            "mastery_percentage": mastery_percentage, # NEW: Correct / Total
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "unattempted_count": unattempted_count,
            "total_count": total_questions,
            "attempted_count": attempted_count,
            "negative_marks": negative_marks,
            "topic_wise": topic_wise,
            "subject_wise": subject_wise,
            "confidence_stats": confidence_stats,
            "average_time_per_question": avg_time,
            "evaluations": evaluations
        }
