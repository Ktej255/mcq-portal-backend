from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from app.models.domain import AttemptAnswer, ExamEvent

METRIC_VERSION = "inference-reliability.v1"

TEMPORAL_EVENT_TYPES = {
    "HEARTBEAT",
    "FOCUS_STATE_CHANGED",
    "IDLE_STATE_CHANGED",
    "QUESTION_VIEWED",
    "ANSWER_CHANGED",
    "SUBMIT_CLICKED",
}

SAFETY_POLICY = {
    "forbidden_claims": [
        "diagnosis",
        "medical certainty",
        "fixed personality label",
        "psychological certainty",
    ],
    "required_posture": "Describe evidence and uncertainty; avoid treating sparse behavioral telemetry as psychological truth.",
}


@dataclass(frozen=True)
class ReliabilityResult:
    value: float
    signal_confidence: float
    evidence_count: int
    reliability_notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": round(self.value, 4),
            "signal_confidence": round(self.signal_confidence, 4),
            "evidence_count": self.evidence_count,
            "reliability_notes": self.reliability_notes,
            "metric_version": METRIC_VERSION,
        }


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sample_confidence(sample_count: int, medium_threshold: int = 10, high_threshold: int = 50) -> float:
    if sample_count <= 0:
        return 0.0
    if sample_count >= high_threshold:
        return 0.9
    if sample_count >= medium_threshold:
        return 0.65
    return 0.25 + (sample_count / medium_threshold) * 0.25


def event_completeness(events: list[ExamEvent], answers: list[AttemptAnswer]) -> float:
    if not answers:
        return 0.0
    viewed_questions = {event.question_id for event in events if event.event_type == "QUESTION_VIEWED" and event.question_id}
    answered_questions = {answer.question_id for answer in answers}
    if not answered_questions:
        return 0.0
    return len(viewed_questions & answered_questions) / len(answered_questions)


def timing_plausibility(answers: list[AttemptAnswer]) -> tuple[float, list[str]]:
    notes: list[str] = []
    if not answers:
        return 0.0, ["no answer timing evidence"]

    timings = [answer.time_taken_seconds or 0 for answer in answers]
    impossible = [time for time in timings if time < 0 or time > 6 * 60 * 60]
    zero_answered = [
        answer for answer in answers
        if answer.selected_option is not None and (answer.time_taken_seconds or 0) == 0
    ]

    score = 1.0
    if impossible:
        score -= 0.5
        notes.append("impossible timing values detected")
    if zero_answered:
        score -= min(0.4, len(zero_answered) / len(answers))
        notes.append("answered questions with zero recorded time")
    if timings and mean(timings) < 2:
        score -= 0.15
        notes.append("average question time is unusually low")

    return clamp(score), notes


def focus_continuity(events: list[ExamEvent]) -> tuple[float, list[str]]:
    notes: list[str] = []
    if not events:
        return 0.0, ["no event telemetry"]

    focus_losses = [event for event in events if event.event_type in {"TAB_SWITCH", "FULLSCREEN_EXIT"}]
    heartbeat_count = len([event for event in events if event.event_type == "HEARTBEAT"])
    score = 1.0

    if focus_losses:
        score -= min(0.45, len(focus_losses) * 0.08)
        notes.append("focus interruptions detected")
    if heartbeat_count == 0:
        score -= 0.2
        notes.append("heartbeat telemetry missing")

    return clamp(score), notes


def behavioral_data_quality(answers: list[AttemptAnswer], events: list[ExamEvent]) -> dict[str, Any]:
    from app.services.telemetry_reconstruction import reconstruct_attempt_timeline

    timeline = reconstruct_attempt_timeline(events)
    telemetry_quality = timeline["quality"]
    completeness = event_completeness(events, answers)
    timing_score, timing_notes = timing_plausibility(answers)
    focus_score, focus_notes = focus_continuity(events)
    telemetry_score = clamp((telemetry_quality["heartbeat_density"] + telemetry_quality["continuity_score"] + telemetry_quality["temporal_coherence"]) / 3)

    score = (
        completeness * 0.3
        + timing_score * 0.3
        + focus_score * 0.2
        + telemetry_score * 0.2
    )

    return {
        "score": round(clamp(score), 4),
        "event_completeness": round(completeness, 4),
        "timing_plausibility": round(timing_score, 4),
        "focus_continuity": round(focus_score, 4),
        "telemetry_density": round(telemetry_score, 4),
        "telemetry_quality": telemetry_quality,
        "notes": timing_notes + focus_notes,
        "metric_version": METRIC_VERSION,
    }


def timing_signal_confidence(answers: list[AttemptAnswer], events: list[ExamEvent]) -> ReliabilityResult:
    quality = behavioral_data_quality(answers, events)
    sample = sample_confidence(len(answers))
    confidence = clamp(quality["score"] * 0.65 + sample * 0.35)
    return ReliabilityResult(
        value=quality["timing_plausibility"],
        signal_confidence=confidence,
        evidence_count=len(answers),
        reliability_notes=quality["notes"],
    )


def signal_reliability(signal_name: str, evidence_count: int, data_quality_score: float, anomaly_count: int = 0, missing_event_penalty: float = 0.0) -> dict[str, Any]:
    base = sample_confidence(evidence_count)
    confidence = base * 0.55 + data_quality_score * 0.45
    confidence -= min(0.35, anomaly_count * 0.08)
    confidence -= clamp(missing_event_penalty, 0, 0.3)
    return {
        "signal": signal_name,
        "signal_confidence": round(clamp(confidence), 4),
        "evidence_count": evidence_count,
        "anomaly_count": anomaly_count,
        "metric_version": METRIC_VERSION,
    }


def contradiction_detector(metrics: dict[str, Any]) -> dict[str, Any]:
    contradictions: list[dict[str, Any]] = []

    high_confidence = metrics.get("high_confidence_rate", 0) >= 60
    unstable_answers = metrics.get("answer_change_rate", 0) >= 40
    low_hesitation = metrics.get("hesitation_index", 0) <= 10
    high_average_time = metrics.get("average_time_per_question", 0) >= 120
    fatigue_detected = metrics.get("fatigue_score", 0) >= 60
    stable_late_accuracy = metrics.get("late_accuracy_delta", 0) >= -5

    if high_confidence and unstable_answers:
        contradictions.append({
            "type": "CONFIDENCE_INSTABILITY",
            "message": "High stated confidence conflicts with frequent answer changes.",
            "severity": 0.65,
        })
    if low_hesitation and high_average_time:
        contradictions.append({
            "type": "HESITATION_TIMING_MISMATCH",
            "message": "Low hesitation claim conflicts with high average timing.",
            "severity": 0.55,
        })
    if fatigue_detected and stable_late_accuracy:
        contradictions.append({
            "type": "FATIGUE_STABILITY_MISMATCH",
            "message": "Fatigue inference conflicts with stable late-attempt accuracy.",
            "severity": 0.5,
        })

    contradiction_score = clamp(sum(item["severity"] for item in contradictions) / 2)
    reliability_downgrade = clamp(contradiction_score * 0.5)
    return {
        "contradiction_score": round(contradiction_score, 4),
        "reliability_downgrade": round(reliability_downgrade, 4),
        "contradictions": contradictions,
        "metric_version": METRIC_VERSION,
    }


def narrative_uncertainty_guidance(reliability: dict[str, Any]) -> dict[str, Any]:
    quality = reliability.get("behavioral_data_quality", {}).get("score", 0)
    contradiction_score = reliability.get("contradictions", {}).get("contradiction_score", 0)
    if quality < 0.35:
        qualifier = "Telemetry is sparse; treat behavioral interpretations as tentative."
    elif contradiction_score >= 0.4:
        qualifier = "Some behavioral signals conflict; avoid strong conclusions."
    else:
        qualifier = "Behavioral interpretation is supported by available telemetry, with normal uncertainty."

    return {
        "uncertainty_qualifier": qualifier,
        "must_avoid": SAFETY_POLICY["forbidden_claims"],
        "preferred_language": "Use 'may indicate', 'is consistent with', and 'based on available evidence'.",
        "requires_human_review": quality < 0.35 or contradiction_score >= 0.4,
        "metric_version": METRIC_VERSION,
    }


def attempt_reliability_profile(answers: list[AttemptAnswer], events: list[ExamEvent], metrics: dict[str, Any]) -> dict[str, Any]:
    quality = behavioral_data_quality(answers, events)
    contradictions = contradiction_detector(metrics)
    timing = timing_signal_confidence(answers, events)
    reliability = {
        "metric_version": METRIC_VERSION,
        "behavioral_data_quality": quality,
        "timing_trust": timing.as_dict(),
        "signals": {
            "guessing_detection": signal_reliability("guessing_detection", len(answers), quality["score"]),
            "review_dependency": signal_reliability("review_dependency", len([a for a in answers if a.marked_for_review]), quality["score"]),
            "impulsiveness": signal_reliability("impulsiveness", len(answers), quality["score"], missing_event_penalty=0.1 if not events else 0),
            "fatigue": signal_reliability("fatigue", len(answers), quality["score"], missing_event_penalty=0.2),
            "confidence_drift": signal_reliability("confidence_drift", len(answers), quality["score"], missing_event_penalty=0.15),
        },
        "contradictions": contradictions,
    }
    reliability["narrative_safety"] = narrative_uncertainty_guidance(reliability)
    return reliability
