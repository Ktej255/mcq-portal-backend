"""
AttemptLockManager — Phase 9, Priority 2
==========================================
Enforces single authoritative active session per user+test pair.

Governance Rules:
  RULE 1 — Single active attempt per user+test. No duplicates.
  RULE 2 — Submit is idempotent. Double-submit returns existing report.
  RULE 3 — Lock is session-scoped via attempt_id. Stale tabs cannot overwrite.
  RULE 4 — Timer drift protection: server-authoritative elapsed time.
  RULE 5 — Multi-tab conflict: second tab resumes, never creates new attempt.

Wrapper-first: wraps Attempt model with locking semantics.
Does NOT rewrite test_engine_service — adds a governance layer around it.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.domain import Attempt, AttemptStatusEnum, Test


class AttemptLockError(Exception):
    """Raised when an attempt lock rule is violated."""
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


class AttemptLockManager:
    """
    Governance wrapper for the exam attempt lifecycle.
    Call before start_attempt() and submit_attempt() in API handlers.
    """

    @staticmethod
    def get_active_attempt(db: Session, user_id: int, test_id: int) -> Optional[Attempt]:
        """Returns an existing IN_PROGRESS attempt if one exists."""
        return (
            db.query(Attempt)
            .filter(
                Attempt.user_id == user_id,
                Attempt.test_id == test_id,
                Attempt.status == AttemptStatusEnum.IN_PROGRESS,
            )
            .first()
        )

    @staticmethod
    def assert_attempt_belongs_to_user(attempt: Attempt, user_id: int) -> None:
        """RULE 3: Lock is session-scoped. Stale tabs cannot own a foreign attempt."""
        if attempt.user_id != user_id:
            raise AttemptLockError(
                "LOCK_VIOLATION",
                f"Attempt {attempt.id} does not belong to user {user_id}.",
            )

    @staticmethod
    def assert_attempt_in_progress(attempt: Attempt) -> None:
        """Guard: attempt must be IN_PROGRESS for any write operations."""
        if attempt.status != AttemptStatusEnum.IN_PROGRESS:
            raise AttemptLockError(
                "ALREADY_SUBMITTED",
                f"Attempt {attempt.id} is already {attempt.status.value}. "
                "Submit is idempotent — do not retry with new data.",
            )

    @staticmethod
    def get_server_elapsed_seconds(attempt: Attempt) -> int:
        """
        RULE 4 — Server-authoritative timer.
        Returns elapsed seconds from attempt.start_time, ignoring client-reported time.
        """
        if not attempt.start_time:
            return 0
        now = datetime.now(timezone.utc)
        start = attempt.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        return max(0, int((now - start).total_seconds()))

    @staticmethod
    def is_timer_expired(attempt: Attempt, db: Session) -> bool:
        """
        RULE 4 — Timer drift protection.
        Compares server elapsed time against test duration.
        """
        test: Optional[Test] = db.query(Test).filter(Test.id == attempt.test_id).first()
        if not test or not test.duration_minutes:
            return False
        elapsed = AttemptLockManager.get_server_elapsed_seconds(attempt)
        allowed_seconds = test.duration_minutes * 60
        # Allow 60s grace period for network latency
        return elapsed > (allowed_seconds + 60)

    @staticmethod
    def check_idempotent_submit(db: Session, attempt_id: int, user_id: int) -> Optional[Attempt]:
        """
        RULE 2 — Idempotent submit guard.
        If attempt is already SUBMITTED, return it immediately.
        The caller should return the existing report without re-processing.
        """
        attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
        if attempt and attempt.status == AttemptStatusEnum.SUBMITTED:
            return attempt  # Caller: return existing report, do not re-process
        return None

    @classmethod
    def lock_for_submit(cls, db: Session, attempt_id: int, user_id: int) -> Attempt:
        """
        Complete pre-submit governance check.
        Returns the locked attempt if all rules pass.
        Raises AttemptLockError or HTTPException on any violation.
        """
        attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
        if not attempt:
            raise HTTPException(status_code=404, detail="Attempt not found")

        cls.assert_attempt_belongs_to_user(attempt, user_id)

        # Already submitted → idempotent path
        if attempt.status == AttemptStatusEnum.SUBMITTED:
            return attempt

        cls.assert_attempt_in_progress(attempt)
        return attempt

    @classmethod
    def lock_for_save(cls, db: Session, attempt_id: int, user_id: int) -> Attempt:
        """
        Pre-save governance check. Stale tabs (wrong attempt_id) are rejected.
        """
        attempt = db.query(Attempt).filter(Attempt.id == attempt_id).first()
        if not attempt:
            raise HTTPException(status_code=404, detail="Attempt not found")

        cls.assert_attempt_belongs_to_user(attempt, user_id)
        cls.assert_attempt_in_progress(attempt)

        # Timer expiry check — prevent saves after time is up
        if cls.is_timer_expired(attempt, db):
            raise AttemptLockError(
                "TIMER_EXPIRED",
                "Exam time has expired. No further answers can be saved.",
            )

        return attempt
