"""
Attempt Reconciliation Engine — Phase 9, Priority 1
====================================================
Reconstructs an attempt's state INDEPENDENTLY from raw ExamEvents and
cross-checks it against the stored AttemptAnswer table.

Governance Rule:
  If a mismatch is found → raise FORENSIC_DIVERGENCE.
  If no ExamEvents exist → raise INSUFFICIENT_DATA (cannot verify).

This is the institutional source of truth for answer state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.models.domain import Attempt, AttemptAnswer, ExamEvent, AttemptStatusEnum


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ReconstructedAnswer:
    question_id: int
    final_option: Optional[str]   # None = skipped
    revision_count: int
    time_seconds: int
    first_set_at: Optional[datetime]
    last_set_at: Optional[datetime]


@dataclass
class ReconciliationReport:
    attempt_id: int
    status: str                   # CLEAN | FORENSIC_DIVERGENCE | INSUFFICIENT_DATA
    divergences: list[dict] = field(default_factory=list)
    reconstructed_answered: int = 0
    reconstructed_skipped: int = 0
    stored_answered: int = 0
    stored_skipped: int = 0
    total_questions: int = 0
    summary: str = ""


# ─── Engine ───────────────────────────────────────────────────────────────────

class AttemptReconciliationEngine:
    """
    Wrapper-first pattern — wraps ExamEvent + AttemptAnswer tables.
    Does NOT mutate any data. Read-only forensic reconstruction.
    """

    ANSWER_EVENT_TYPES = {"ANSWER_SELECTED", "ANSWER_CHANGED", "ANSWER_CLEARED"}

    @classmethod
    def reconstruct_from_events(
        cls, db: Session, attempt_id: int
    ) -> dict[int, ReconstructedAnswer]:
        """
        Walk all ExamEvents in chronological order and derive the final
        answer state purely from the event stream.
        """
        events = (
            db.query(ExamEvent)
            .filter(
                ExamEvent.attempt_id == attempt_id,
                ExamEvent.event_type.in_(cls.ANSWER_EVENT_TYPES),
            )
            .order_by(ExamEvent.timestamp.asc())
            .all()
        )

        reconstructed: dict[int, ReconstructedAnswer] = {}

        for event in events:
            qid = event.question_id
            if qid is None:
                continue

            payload = event.payload or {}
            option = payload.get("selected_option") or payload.get("option")
            ts = event.timestamp

            if qid not in reconstructed:
                reconstructed[qid] = ReconstructedAnswer(
                    question_id=qid,
                    final_option=option,
                    revision_count=0,
                    time_seconds=0,
                    first_set_at=ts,
                    last_set_at=ts,
                )
            else:
                existing = reconstructed[qid]
                if existing.final_option != option:
                    existing.revision_count += 1
                existing.final_option = option
                existing.last_set_at = ts

        return reconstructed

    @classmethod
    def reconcile(cls, db: Session, attempt_id: int) -> ReconciliationReport:
        """
        Core reconciliation: compare event-reconstructed state vs DB answers.

        Returns a ReconciliationReport with status CLEAN | FORENSIC_DIVERGENCE
        | INSUFFICIENT_DATA.
        """
        attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
        if not attempt:
            return ReconciliationReport(
                attempt_id=attempt_id,
                status="INSUFFICIENT_DATA",
                summary="Attempt not found",
            )

        # ── Reconstruct from events ──
        reconstructed = cls.reconstruct_from_events(db, attempt_id)

        # ── Load stored answers ──
        stored_answers: list[AttemptAnswer] = (
            db.query(AttemptAnswer)
            .filter(AttemptAnswer.attempt_id == attempt_id)
            .all()
        )
        stored_map: dict[int, AttemptAnswer] = {a.question_id: a for a in stored_answers}

        total_questions = len(stored_map) if stored_map else len(reconstructed)

        report = ReconciliationReport(
            attempt_id=attempt_id,
            status="CLEAN",
            total_questions=total_questions,
            reconstructed_answered=sum(
                1 for r in reconstructed.values() if r.final_option is not None
            ),
            reconstructed_skipped=sum(
                1 for r in reconstructed.values() if r.final_option is None
            ),
            stored_answered=sum(
                1 for a in stored_answers if a.selected_option is not None
            ),
            stored_skipped=sum(
                1 for a in stored_answers if a.selected_option is None
            ),
        )

        if not reconstructed:
            report.status = "INSUFFICIENT_DATA"
            report.summary = (
                "No ANSWER_SELECTED events found. "
                "Cannot reconstruct attempt from event stream."
            )
            return report

        # ── Cross-check each answer ──
        divergences = []

        all_question_ids = set(reconstructed.keys()) | set(stored_map.keys())
        for qid in all_question_ids:
            rec = reconstructed.get(qid)
            stored = stored_map.get(qid)

            rec_option = rec.final_option if rec else None
            stored_option = stored.selected_option if stored else None

            # Normalize both to uppercase for comparison
            rec_norm = (rec_option or "").strip().upper() or None
            stored_norm = (stored_option or "").strip().upper() or None

            if rec_norm != stored_norm:
                divergences.append(
                    {
                        "question_id": qid,
                        "reconstructed_option": rec_option,
                        "stored_option": stored_option,
                        "revision_count": rec.revision_count if rec else 0,
                        "severity": "HIGH" if stored_norm is None and rec_norm is not None
                                    else "MEDIUM",
                    }
                )

        if divergences:
            report.status = "FORENSIC_DIVERGENCE"
            report.divergences = divergences
            report.summary = (
                f"FORENSIC_DIVERGENCE: {len(divergences)} answer(s) do not match "
                f"between event reconstruction and stored AttemptAnswer table. "
                f"Possible causes: frontend sync failure, race condition, or duplicate save."
            )
        else:
            report.summary = (
                f"CLEAN: {report.reconstructed_answered} answered, "
                f"{report.reconstructed_skipped} skipped — fully reconciled."
            )

        return report
