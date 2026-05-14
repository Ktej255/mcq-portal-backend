from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import (
    Attempt,
    AttemptAnswer,
    CognitiveSnapshot,
    ConfidenceEnum,
    ExamEvent,
    Report,
    User,
)
from app.core.pedagogy.inference_reliability import METRIC_VERSION, attempt_reliability_profile, clamp
from app.core.pedagogy.telemetry_reconstruction import reconstruct_attempt_timeline

LONGITUDINAL_VERSION = "longitudinal-cognition.v1"


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)
    numerator = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def _volatility(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _stability_score(values: list[float]) -> float:
    if len(values) < 2:
        return 0.25 if values else 0.0
    avg = abs(_safe_mean(values)) or 1
    normalized_volatility = _volatility(values) / max(avg, 1)
    return clamp(1 - normalized_volatility)


def _topic_accuracy(stats: dict[str, Any]) -> float:
    attempted = (stats.get("correct", 0) or 0) + (stats.get("incorrect", 0) or 0)
    if attempted <= 0:
        return 0.0
    return (stats.get("correct", 0) or 0) / attempted * 100


def _confidence_metrics(answers: list[AttemptAnswer]) -> dict[str, float]:
    attempted = [answer for answer in answers if answer.selected_option is not None]
    if not attempted:
        return {
            "blind_guess_rate": 0.0,
            "overconfidence_rate": 0.0,
            "calibration_accuracy": 0.0,
            "high_confidence_rate": 0.0,
        }

    blind = [answer for answer in attempted if answer.confidence_level == ConfidenceEnum.BLIND_GUESS]
    high = [answer for answer in attempted if answer.confidence_level == ConfidenceEnum.HUNDRED_PERCENT]
    high_correct = [answer for answer in high if answer.is_correct is True]
    high_wrong = [answer for answer in high if answer.is_correct is False]
    return {
        "blind_guess_rate": len(blind) / len(attempted) * 100,
        "overconfidence_rate": len(high_wrong) / len(attempted) * 100,
        "calibration_accuracy": len(high_correct) / len(high) * 100 if high else 0.0,
        "high_confidence_rate": len(high) / len(attempted) * 100,
    }


def _attempt_point(db: Session, report: Report) -> dict[str, Any]:
    attempt = report.attempt
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == report.attempt_id).all()
    events = db.query(ExamEvent).filter(ExamEvent.attempt_id == report.attempt_id).order_by(ExamEvent.timestamp.asc()).all()
    confidence = _confidence_metrics(answers)
    timeline = reconstruct_attempt_timeline(events)
    reliability = attempt_reliability_profile(answers, events, {
        "high_confidence_rate": confidence["high_confidence_rate"],
        "answer_change_rate": len([event for event in events if event.event_type == "ANSWER_CHANGED"]) / max(1, len(answers)) * 100,
        "hesitation_index": len([answer for answer in answers if (answer.time_taken_seconds or 0) > 60]) / max(1, len(answers)) * 100,
        "average_time_per_question": report.average_time_per_question or 0,
        "fatigue_score": 0,
        "late_accuracy_delta": 0,
    })
    topic_scores = {
        topic: _topic_accuracy(stats)
        for topic, stats in (report.topic_wise_analysis or {}).items()
    }
    return {
        "attempt_id": report.attempt_id,
        "timestamp": (attempt.end_time or report.generated_at or attempt.start_time).isoformat(),
        "score": report.total_score,
        "accuracy": report.accuracy,
        "average_time_per_question": report.average_time_per_question or 0,
        "topic_scores": topic_scores,
        "confidence": confidence,
        "telemetry_quality": timeline["quality"],
        "reliability": reliability,
        "metric_version": LONGITUDINAL_VERSION,
    }


def learning_velocity(points: list[dict[str, Any]]) -> dict[str, Any]:
    accuracies = [point["accuracy"] for point in points]
    scores = [point["score"] for point in points]
    recent = accuracies[-3:]
    earlier = accuracies[:-3]
    recovery_velocity = _safe_mean(recent) - _safe_mean(earlier) if earlier and recent else 0.0
    stabilization = len(accuracies) >= 4 and _volatility(accuracies[-3:]) < _volatility(accuracies[:-1])
    
    # Calculate most recent delta
    accuracy_delta = 0.0
    trend = "STABLE"
    if len(accuracies) >= 2:
        accuracy_delta = round(accuracies[-1] - accuracies[-2], 2)
        if accuracy_delta > 5:
            trend = "IMPROVING"
        elif accuracy_delta < -5:
            trend = "DECLINING"

    return {
        "accuracy_slope": round(_slope(accuracies), 4),
        "score_slope": round(_slope(scores), 4),
        "recovery_velocity": round(recovery_velocity, 4),
        "accuracy_delta": accuracy_delta,
        "trend": trend,
        "stabilization_detected": stabilization,
        "confidence": longitudinal_reliability_weight(points)["overall_reliability"],
        "metric_version": LONGITUDINAL_VERSION,
    }


def confidence_evolution(points: list[dict[str, Any]]) -> dict[str, Any]:
    blind = [point["confidence"]["blind_guess_rate"] for point in points]
    overconf = [point["confidence"]["overconfidence_rate"] for point in points]
    calibration = [point["confidence"]["calibration_accuracy"] for point in points]
    return {
        "blind_guess_reduction": round((blind[0] - blind[-1]) if len(blind) >= 2 else 0, 4),
        "overconfidence_reduction": round((overconf[0] - overconf[-1]) if len(overconf) >= 2 else 0, 4),
        "calibration_slope": round(_slope(calibration), 4),
        "confidence_stability": round(_stability_score(calibration), 4),
        "confidence_accuracy_correlation_ready": len([value for value in calibration if value > 0]) >= 3,
        "metric_version": LONGITUDINAL_VERSION,
    }


def revision_effectiveness(points: list[dict[str, Any]]) -> dict[str, Any]:
    topic_history: dict[str, list[float]] = defaultdict(list)
    for point in points:
        for topic, score in point["topic_scores"].items():
            topic_history[topic].append(score)

    topic_effectiveness = {}
    for topic, values in topic_history.items():
        if len(values) < 2:
            topic_effectiveness[topic] = {
                "status": "INSUFFICIENT_EVIDENCE",
                "retention_score": 0,
                "improvement": 0,
                "decay": 0,
            }
            continue
        improvement = values[-1] - values[0]
        peak = max(values)
        decay = peak - values[-1]
        retention = clamp((values[-1] / peak) if peak > 0 else 0) * 100
        topic_effectiveness[topic] = {
            "status": "IMPROVING" if improvement > 5 and decay <= 10 else "UNSTABLE" if decay > 10 else "STABLE",
            "retention_score": round(retention, 4),
            "improvement": round(improvement, 4),
            "decay": round(decay, 4),
            "relearning_detected": len(values) >= 3 and values[-2] < values[0] < values[-1],
        }

    return {
        "topics": topic_effectiveness,
        "metric_version": LONGITUDINAL_VERSION,
    }


def behavioral_stability(points: list[dict[str, Any]]) -> dict[str, Any]:
    accuracies = [point["accuracy"] for point in points]
    pacing = [point.get("average_time_per_question", 0) for point in points]
    telemetry = [point["telemetry_quality"].get("temporal_coherence", 0) for point in points]
    consistency = (
        _stability_score(accuracies) * 0.45
        + _stability_score(pacing) * 0.25
        + _safe_mean(telemetry) * 0.30
    )
    return {
        "accuracy_volatility": round(_volatility(accuracies), 4),
        "pacing_volatility": round(_volatility(pacing), 4),
        "consistency_score": round(clamp(consistency), 4),
        "stability_confidence": round(clamp(len(points) / 10), 4),
        "smoothed_accuracy_trend": _moving_average(accuracies, window=3),
        "metric_version": LONGITUDINAL_VERSION,
    }


def _moving_average(values: list[float], window: int = 3) -> list[float]:
    return [
        round(_safe_mean(values[max(0, i - window + 1): i + 1]), 4)
        for i in range(len(values))
    ]


def cognitive_state_transitions(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(points) < 2:
        return []

    first_half = points[: max(1, len(points) // 2)]
    second_half = points[max(1, len(points) // 2):]
    transitions = []
    first_stability = behavioral_stability(first_half)["consistency_score"]
    second_stability = behavioral_stability(second_half)["consistency_score"]
    first_blind = _safe_mean([point["confidence"]["blind_guess_rate"] for point in first_half])
    second_blind = _safe_mean([point["confidence"]["blind_guess_rate"] for point in second_half])
    first_cal = _safe_mean([point["confidence"]["calibration_accuracy"] for point in first_half])
    second_cal = _safe_mean([point["confidence"]["calibration_accuracy"] for point in second_half])
    first_time = _safe_mean([point.get("average_time_per_question", 0) for point in first_half])
    second_time = _safe_mean([point.get("average_time_per_question", 0) for point in second_half])

    if second_stability - first_stability > 0.15:
        transitions.append({"from": "UNSTABLE", "to": "STABLE", "confidence": round(second_stability, 4)})
    if first_blind - second_blind > 10 and second_cal >= first_cal:
        transitions.append({"from": "IMPULSIVE", "to": "CALIBRATED", "confidence": round(clamp((first_blind - second_blind) / 100 + second_cal / 100), 4)})
    if first_time - second_time > 15 and second_cal >= first_cal:
        transitions.append({"from": "HESITANT", "to": "CONFIDENT", "confidence": round(clamp((first_time - second_time) / 120), 4)})

    return transitions


def longitudinal_reliability_weight(points: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_count = len(points)
    attempt_weight = clamp(attempt_count / 10) * 0.55
    telemetry = _safe_mean([point.get("telemetry_quality", {}).get("temporal_coherence", 0) for point in points])
    accuracies = [point["accuracy"] for point in points]
    pacing = [point.get("average_time_per_question", 0) for point in points]
    consistency = (_stability_score(accuracies) * 0.65 + _stability_score(pacing) * 0.35) if points else 0
    repetition = clamp(len(points) / 5)
    overall = attempt_weight + telemetry * 0.2 + consistency * 0.15 + repetition * 0.1
    level = "HIGH" if attempt_count >= 50 and overall >= 0.75 else "MEDIUM" if attempt_count >= 10 and overall >= 0.55 else "LOW"
    return {
        "attempt_count": attempt_count,
        "telemetry_continuity": round(telemetry, 4),
        "behavioral_consistency": round(consistency, 4),
        "signal_repetition": round(repetition, 4),
        "overall_reliability": round(clamp(overall), 4),
        "level": level,
        "metric_version": LONGITUDINAL_VERSION,
    }


def adaptive_recommendation_context(profile: dict[str, Any]) -> dict[str, Any]:
    weak_topics = []
    for topic, data in profile["revision_effectiveness"]["topics"].items():
        if data["status"] in {"UNSTABLE", "INSUFFICIENT_EVIDENCE"} or data["retention_score"] < 65:
            weak_topics.append({
                "topic": topic,
                "reason": data["status"],
                "retention_score": data["retention_score"],
            })

    return {
        "weak_topics": weak_topics,
        "pacing_problem": profile["behavioral_stability"]["pacing_volatility"] > 30,
        "confidence_calibration_needed": profile["confidence_evolution"]["calibration_slope"] < 0,
        "velocity_status": "ACCELERATING" if profile["learning_velocity"]["accuracy_slope"] > 2 else "FLAT_OR_DECLINING",
        "trajectory_reliability": profile["longitudinal_reliability"],
        "metric_version": LONGITUDINAL_VERSION,
    }


def build_student_longitudinal_profile(db: Session, user_id: int) -> dict[str, Any]:
    reports = (
        db.query(Report)
        .join(Attempt)
        .filter(Attempt.user_id == user_id)
        .order_by(Report.generated_at.asc())
        .all()
    )
    points = [_attempt_point(db, report) for report in reports]
    profile = {
        "user_id": user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metric_version": LONGITUDINAL_VERSION,
        "attempt_count": len(points),
        "trajectory_points": points,
        "learning_velocity": learning_velocity(points),
        "confidence_evolution": confidence_evolution(points),
        "revision_effectiveness": revision_effectiveness(points),
        "behavioral_stability": behavioral_stability(points),
        "state_transitions": cognitive_state_transitions(points),
        "longitudinal_reliability": longitudinal_reliability_weight(points),
    }
    profile["adaptive_recommendation_context"] = adaptive_recommendation_context(profile)
    return profile


def create_cognitive_snapshot(db: Session, user_id: int, attempt_id: int, behavioral: dict[str, Any] | None = None) -> CognitiveSnapshot | None:
    report = db.query(Report).filter(Report.attempt_id == attempt_id).first()
    if not report:
        return None

    existing = db.query(CognitiveSnapshot).filter(CognitiveSnapshot.attempt_id == attempt_id).first()
    if existing:
        return existing

    events = db.query(ExamEvent).filter(ExamEvent.attempt_id == attempt_id).order_by(ExamEvent.timestamp.asc()).all()
    answers = db.query(AttemptAnswer).filter(AttemptAnswer.attempt_id == attempt_id).all()
    timeline = reconstruct_attempt_timeline(events)
    reliability = behavioral.get("inference_reliability") if behavioral else None
    if not reliability:
        reliability = attempt_reliability_profile(answers, events, {
            "high_confidence_rate": _confidence_metrics(answers)["high_confidence_rate"],
            "answer_change_rate": len([event for event in events if event.event_type == "ANSWER_CHANGED"]) / max(1, len(answers)) * 100,
            "hesitation_index": len([answer for answer in answers if (answer.time_taken_seconds or 0) > 60]) / max(1, len(answers)) * 100,
            "average_time_per_question": report.average_time_per_question or 0,
            "fatigue_score": 0,
            "late_accuracy_delta": 0,
        })

    snapshot = CognitiveSnapshot(
        user_id=user_id,
        attempt_id=attempt_id,
        cognitive_snapshot={
            "attempt_id": attempt_id,
            "score": report.total_score,
            "accuracy": report.accuracy,
            "topic_wise_analysis": report.topic_wise_analysis,
            "confidence_analysis": report.confidence_analysis,
            "behavioral": behavioral or {},
            "metric_version": LONGITUDINAL_VERSION,
        },
        telemetry_snapshot=timeline,
        reliability_snapshot=reliability,
        metric_version=LONGITUDINAL_VERSION,
        created_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def update_longitudinal_profile(db: Session, user_id: int) -> dict[str, Any]:
    profile = build_student_longitudinal_profile(db, user_id)
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.behavioral_profile = profile
        db.commit()
    return profile
