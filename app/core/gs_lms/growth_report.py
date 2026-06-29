"""Growth Report Generator — aggregates all funnel data into a comprehensive
performance report with historical comparison and weakness identification.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.gs_lms.funnel_models import (
    GsLmsReadingTime,
    GsLmsRecallAttempt,
    GsLmsMcqLabSession,
    GsLmsMcqLabAttempt,
    GsLmsWeaknessPattern,
    GsLmsGrowthReport,
    GsLmsSpacedRepSchedule,
)
from app.core.gs_lms.models import GsLmsContentSection, GsLmsSyllabusNode
from app.core.gs_lms.spaced_repetition import (
    compute_initial_interval,
    schedule_after_completion,
)


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SectionMetrics:
    section_label: str
    reading_time_seconds: int
    recall_score: float          # 0.0–1.0
    confidence_score: float      # 0.0–1.0
    is_rushed: bool


@dataclass(frozen=True)
class WeaknessItem:
    category: str                # "rushed_section" | "low_recall" | "weak_type"
    label: str
    value: float
    recommended_action: str


@dataclass
class GrowthReportData:
    student_id: int
    syllabus_node_id: int
    topic_title: str
    generated_at: datetime
    section_metrics: List[SectionMetrics]
    mcq_total_score: float
    mcq_type_breakdown: list
    mains_score: Optional[float]
    mains_max_marks: Optional[int]
    next_recall_date: date
    recall_interval_days: int
    comparison_data: Optional[dict]
    weaknesses: List[WeaknessItem]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUSHED_THRESHOLD = 0.3  # section is rushed if reading time < 30% of estimated
LOW_RECALL_THRESHOLD = 0.5  # recall score < 50% is flagged
SECTION_LABELS = ["BASIC", "NCERT_LEVEL", "ADVANCED", "CURRENT_AFFAIRS", "EXAMINER_TRAPS"]


# ---------------------------------------------------------------------------
# Pure Functions
# ---------------------------------------------------------------------------

def is_section_rushed(reading_time_seconds: int, estimated_duration_seconds: int) -> bool:
    """A section is rushed when reading time < 30% of estimated duration.

    Returns False if estimated_duration is <= 0 (cannot determine).
    """
    if estimated_duration_seconds <= 0:
        return False
    return reading_time_seconds < (RUSHED_THRESHOLD * estimated_duration_seconds)


def identify_weaknesses(
    section_metrics: List[SectionMetrics],
    mcq_type_breakdown: list,
    weakness_patterns: list,
) -> List[WeaknessItem]:
    """Identify weakness areas for the Growth Report.

    Rules:
    - Rushed: reading_time < 30% of estimated → "Re-read this section"
    - Low recall: recall_score < 0.5 → "Review and re-attempt recall"
    - Weak type: accuracy < 0.5 across 3+ attempts → "Practice this question type"
    """
    weaknesses: List[WeaknessItem] = []

    # Rushed sections
    for sm in section_metrics:
        if sm.is_rushed:
            weaknesses.append(WeaknessItem(
                category="rushed_section",
                label=sm.section_label.replace("_", " "),
                value=sm.reading_time_seconds,
                recommended_action="Re-read this section more carefully",
            ))

    # Low recall
    for sm in section_metrics:
        if sm.recall_score < LOW_RECALL_THRESHOLD:
            weaknesses.append(WeaknessItem(
                category="low_recall",
                label=sm.section_label.replace("_", " "),
                value=round(sm.recall_score * 100, 1),
                recommended_action="Review the content and re-attempt spoken recall",
            ))

    # Weak question types
    for wp in weakness_patterns:
        if isinstance(wp, dict) and wp.get("is_weak"):
            weaknesses.append(WeaknessItem(
                category="weak_type",
                label=wp.get("question_type", "Unknown").replace("_", " "),
                value=round(wp.get("accuracy", 0) * 100, 1),
                recommended_action="Practice more questions of this type",
            ))

    return weaknesses


# ---------------------------------------------------------------------------
# Report Generation (Database-dependent)
# ---------------------------------------------------------------------------

def generate_growth_report(
    db: Session,
    student_id: int,
    node_id: int,
) -> GrowthReportData:
    """Aggregate all funnel data into a Growth Report.

    Queries: reading times, recall attempts, MCQ Lab results, weakness patterns,
    and the last 5 growth reports for trend comparison.
    Computes spaced repetition schedule.
    Identifies weaknesses.
    Persists the report snapshot.

    Returns:
        GrowthReportData with all computed metrics.
    """
    now = datetime.now(timezone.utc)
    today = now.date()

    # Get topic title
    node = db.query(GsLmsSyllabusNode).filter(
        GsLmsSyllabusNode.id == node_id
    ).first()
    topic_title = node.title if node else f"Topic {node_id}"

    # --- Gather Section Metrics ---
    section_metrics: List[SectionMetrics] = []

    for section_label in SECTION_LABELS:
        # Get reading time
        reading_time = db.query(GsLmsReadingTime).filter(
            GsLmsReadingTime.student_id == student_id,
            GsLmsReadingTime.syllabus_node_id == node_id,
        ).join(GsLmsContentSection, GsLmsReadingTime.section_id == GsLmsContentSection.id).filter(
            GsLmsContentSection.section_label == section_label,
        ).first()

        duration = reading_time.duration_seconds if reading_time else 0
        estimated = reading_time.estimated_duration_seconds if reading_time and reading_time.estimated_duration_seconds else 300

        # Get latest recall attempt
        recall = (
            db.query(GsLmsRecallAttempt)
            .filter(
                GsLmsRecallAttempt.student_id == student_id,
                GsLmsRecallAttempt.syllabus_node_id == node_id,
                GsLmsRecallAttempt.section_label == section_label,
            )
            .order_by(GsLmsRecallAttempt.attempt_number.desc())
            .first()
        )

        recall_score = recall.recall_score if recall else 0.0
        confidence_score = recall.confidence_score if recall else 0.0

        section_metrics.append(SectionMetrics(
            section_label=section_label,
            reading_time_seconds=duration,
            recall_score=recall_score,
            confidence_score=confidence_score,
            is_rushed=is_section_rushed(duration, estimated),
        ))

    # --- MCQ Lab Results ---
    mcq_session = (
        db.query(GsLmsMcqLabSession)
        .filter(
            GsLmsMcqLabSession.student_id == student_id,
            GsLmsMcqLabSession.syllabus_node_id == node_id,
            GsLmsMcqLabSession.submitted_at.isnot(None),
        )
        .order_by(GsLmsMcqLabSession.submitted_at.desc())
        .first()
    )

    mcq_total_score = (mcq_session.score * 100) if mcq_session and mcq_session.score else 0.0

    # Type breakdown from MCQ Lab attempts
    mcq_type_breakdown = []
    if mcq_session:
        attempts = (
            db.query(GsLmsMcqLabAttempt)
            .filter(GsLmsMcqLabAttempt.session_id == mcq_session.id)
            .all()
        )
        type_stats: dict = {}
        for a in attempts:
            correct, total = type_stats.get(a.question_type, (0, 0))
            total += 1
            if a.is_correct:
                correct += 1
            type_stats[a.question_type] = (correct, total)

        mcq_type_breakdown = [
            {
                "question_type": qtype,
                "total": total,
                "correct": correct,
                "accuracy": round((correct / total * 100) if total > 0 else 0, 1),
            }
            for qtype, (correct, total) in sorted(type_stats.items())
        ]

    # --- Mains Score (if attempted) ---
    # Check for evaluation report via existing answer attempt system
    mains_score: Optional[float] = None
    mains_max_marks: Optional[int] = None

    # --- Spaced Repetition Schedule ---
    avg_recall = (
        sum(sm.recall_score for sm in section_metrics) / len(section_metrics)
        if section_metrics else 0.0
    )
    schedule = schedule_after_completion(avg_recall, today)

    # Persist spaced rep entry
    existing_schedule = db.query(GsLmsSpacedRepSchedule).filter(
        GsLmsSpacedRepSchedule.student_id == student_id,
        GsLmsSpacedRepSchedule.syllabus_node_id == node_id,
        GsLmsSpacedRepSchedule.sequence_number == 1,
    ).first()

    if not existing_schedule:
        sched_entry = GsLmsSpacedRepSchedule(
            student_id=student_id,
            syllabus_node_id=node_id,
            sequence_number=1,
            due_date=schedule.due_date,
            interval_days=schedule.recall_interval_days,
        )
        db.add(sched_entry)

    # --- Historical Comparison (last 5 reports) ---
    prior_reports = (
        db.query(GsLmsGrowthReport)
        .filter(
            GsLmsGrowthReport.student_id == student_id,
            GsLmsGrowthReport.syllabus_node_id != node_id,  # other topics
        )
        .order_by(GsLmsGrowthReport.generated_at.desc())
        .limit(5)
        .all()
    )

    comparison_data = None
    if prior_reports:
        avg_recall_trend = []
        mcq_accuracy_trend = []
        for pr in reversed(prior_reports):
            metrics = pr.section_metrics or []
            if metrics:
                avg_r = sum(m.get("recall_score", 0) for m in metrics) / len(metrics)
                avg_recall_trend.append(round(avg_r * 100, 1))
            mcq_accuracy_trend.append(round((pr.mcq_total_score or 0), 1))

        # Add current topic's scores
        avg_recall_trend.append(round(avg_recall * 100, 1))
        mcq_accuracy_trend.append(round(mcq_total_score, 1))

        comparison_data = {
            "avg_recall_trend": avg_recall_trend,
            "mcq_accuracy_trend": mcq_accuracy_trend,
            "report_count": len(prior_reports) + 1,
        }

    # --- Weakness Identification ---
    weakness_patterns_raw = (
        db.query(GsLmsWeaknessPattern)
        .filter(
            GsLmsWeaknessPattern.student_id == student_id,
            GsLmsWeaknessPattern.is_weak == True,
        )
        .all()
    )
    wp_dicts = [
        {"question_type": wp.question_type, "accuracy": wp.accuracy, "is_weak": wp.is_weak}
        for wp in weakness_patterns_raw
    ]

    weaknesses = identify_weaknesses(section_metrics, mcq_type_breakdown, wp_dicts)

    # --- Persist Growth Report ---
    report_record = GsLmsGrowthReport(
        student_id=student_id,
        syllabus_node_id=node_id,
        section_metrics=[
            {
                "section_label": sm.section_label,
                "reading_time_seconds": sm.reading_time_seconds,
                "recall_score": sm.recall_score,
                "confidence_score": sm.confidence_score,
                "is_rushed": sm.is_rushed,
            }
            for sm in section_metrics
        ],
        mcq_total_score=mcq_total_score,
        mcq_type_breakdown=mcq_type_breakdown,
        mains_score=mains_score,
        mains_max_marks=mains_max_marks,
        next_recall_date=schedule.due_date,
        recall_interval_days=schedule.recall_interval_days,
        weaknesses=[
            {
                "category": w.category,
                "label": w.label,
                "value": w.value,
                "recommended_action": w.recommended_action,
            }
            for w in weaknesses
        ],
        comparison_data=comparison_data,
        generated_at=now,
    )
    db.add(report_record)
    db.flush()

    return GrowthReportData(
        student_id=student_id,
        syllabus_node_id=node_id,
        topic_title=topic_title,
        generated_at=now,
        section_metrics=section_metrics,
        mcq_total_score=mcq_total_score,
        mcq_type_breakdown=mcq_type_breakdown,
        mains_score=mains_score,
        mains_max_marks=mains_max_marks,
        next_recall_date=schedule.due_date,
        recall_interval_days=schedule.recall_interval_days,
        comparison_data=comparison_data,
        weaknesses=weaknesses,
    )


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "SectionMetrics",
    "WeaknessItem",
    "GrowthReportData",
    "RUSHED_THRESHOLD",
    "is_section_rushed",
    "identify_weaknesses",
    "generate_growth_report",
]
