"""Tests for the GS LMS MCQ scoring engine (Task 4.3).

Tests the pure scoring functions in ``app.core.gs_lms.mcq_scoring``:
* ``compute_score`` — total score = correct / total (Property 11a)
* ``compute_type_accuracy`` — per-type accuracy breakdown (Property 11b)
* ``classify_question_type`` — enum mapping
* ``SessionState`` / ``advance_session`` / ``is_session_complete`` — sequential
  access enforcement (Property 10)
* ``score_session`` — combined scoring result

Requirements traced: 4.1, 4.3, 4.4, 4.5, 4.6
"""

from __future__ import annotations

import pytest

from app.core.gs_lms.models import GsLmsQuestionTypeEnum
from app.core.gs_lms.mcq_scoring import (
    Attempt,
    SessionState,
    ScoringResult,
    TypeAccuracy,
    compute_score,
    compute_type_accuracy,
    classify_question_type,
    advance_session,
    is_session_complete,
    score_session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_attempt(
    question_id: int = 1,
    question_type: GsLmsQuestionTypeEnum = GsLmsQuestionTypeEnum.FACTUAL,
    chosen_answer: str | None = "A",
    correct_answer: str = "A",
    is_correct: bool | None = True,
    time_taken_seconds: float | None = 10.0,
) -> Attempt:
    return Attempt(
        question_id=question_id,
        question_type=question_type,
        chosen_answer=chosen_answer,
        correct_answer=correct_answer,
        is_correct=is_correct,
        time_taken_seconds=time_taken_seconds,
    )


# ===========================================================================
# compute_score — Property 11a: total_score = correct / total
# ===========================================================================

class TestComputeScore:
    """Tests for compute_score (Property 11a)."""

    def test_empty_attempts_returns_zero(self):
        assert compute_score([]) == 0.0

    def test_all_correct(self):
        attempts = [_make_attempt(question_id=i, is_correct=True) for i in range(5)]
        assert compute_score(attempts) == 1.0

    def test_none_correct(self):
        attempts = [_make_attempt(question_id=i, is_correct=False) for i in range(5)]
        assert compute_score(attempts) == 0.0

    def test_partial_correct(self):
        attempts = [
            _make_attempt(question_id=1, is_correct=True),
            _make_attempt(question_id=2, is_correct=True),
            _make_attempt(question_id=3, is_correct=False),
            _make_attempt(question_id=4, is_correct=False),
        ]
        assert compute_score(attempts) == 0.5

    def test_skipped_questions_count_as_incorrect(self):
        """Skipped questions (is_correct=None) do NOT count as correct."""
        attempts = [
            _make_attempt(question_id=1, is_correct=True),
            _make_attempt(question_id=2, is_correct=None, chosen_answer=None),
            _make_attempt(question_id=3, is_correct=False),
        ]
        # Only 1 correct out of 3 total.
        assert compute_score(attempts) == pytest.approx(1 / 3)

    def test_single_correct_attempt(self):
        attempts = [_make_attempt(is_correct=True)]
        assert compute_score(attempts) == 1.0

    def test_single_incorrect_attempt(self):
        attempts = [_make_attempt(is_correct=False)]
        assert compute_score(attempts) == 0.0


# ===========================================================================
# compute_type_accuracy — Property 11b: per-type accuracy
# ===========================================================================

class TestComputeTypeAccuracy:
    """Tests for compute_type_accuracy (Property 11b)."""

    def test_empty_attempts_returns_empty(self):
        assert compute_type_accuracy([]) == []

    def test_single_type_all_correct(self):
        attempts = [
            _make_attempt(question_id=i, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=True)
            for i in range(3)
        ]
        result = compute_type_accuracy(attempts)
        assert len(result) == 1
        assert result[0].question_type == GsLmsQuestionTypeEnum.FACTUAL
        assert result[0].total == 3
        assert result[0].correct == 3
        assert result[0].accuracy == 1.0

    def test_single_type_mixed(self):
        attempts = [
            _make_attempt(question_id=1, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=True),
            _make_attempt(question_id=2, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=False),
            _make_attempt(question_id=3, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=True),
            _make_attempt(question_id=4, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=False),
        ]
        result = compute_type_accuracy(attempts)
        assert len(result) == 1
        assert result[0].accuracy == 0.5

    def test_multiple_types(self):
        attempts = [
            _make_attempt(question_id=1, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=True),
            _make_attempt(question_id=2, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=True),
            _make_attempt(question_id=3, question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED, is_correct=False),
            _make_attempt(question_id=4, question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED, is_correct=True),
            _make_attempt(question_id=5, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=False),
        ]
        result = compute_type_accuracy(attempts)
        # Should have 3 types.
        assert len(result) == 3
        type_map = {r.question_type: r for r in result}
        assert type_map[GsLmsQuestionTypeEnum.FACTUAL].accuracy == 1.0
        assert type_map[GsLmsQuestionTypeEnum.STATEMENT_BASED].accuracy == 0.5
        assert type_map[GsLmsQuestionTypeEnum.MAP_BASED].accuracy == 0.0

    def test_skipped_questions_not_counted_as_correct(self):
        attempts = [
            _make_attempt(question_id=1, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=True),
            _make_attempt(question_id=2, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=None, chosen_answer=None),
        ]
        result = compute_type_accuracy(attempts)
        assert result[0].total == 2
        assert result[0].correct == 1
        assert result[0].accuracy == 0.5

    def test_results_sorted_by_type_value(self):
        """Deterministic ordering by question_type enum value."""
        attempts = [
            _make_attempt(question_id=1, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=True),
            _make_attempt(question_id=2, question_type=GsLmsQuestionTypeEnum.ASSERTION_REASON, is_correct=True),
            _make_attempt(question_id=3, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=True),
        ]
        result = compute_type_accuracy(attempts)
        type_values = [r.question_type.value for r in result]
        assert type_values == sorted(type_values)


# ===========================================================================
# classify_question_type
# ===========================================================================

class TestClassifyQuestionType:
    """Tests for classify_question_type."""

    def test_valid_types(self):
        for qt in GsLmsQuestionTypeEnum:
            assert classify_question_type(qt.value) == qt

    def test_invalid_type_raises_value_error(self):
        with pytest.raises(ValueError):
            classify_question_type("INVALID_TYPE")


# ===========================================================================
# SessionState — Property 10: sequential access control
# ===========================================================================

class TestSessionState:
    """Tests for SessionState and sequential access enforcement."""

    def test_initial_state(self):
        session = SessionState(total_questions=5)
        assert session.current_index == 0
        assert not session.is_complete
        assert session.can_answer_at(0)

    def test_cannot_answer_at_wrong_index(self):
        session = SessionState(total_questions=5, current_index=2)
        assert not session.can_answer_at(0)
        assert not session.can_answer_at(1)
        assert session.can_answer_at(2)
        assert not session.can_answer_at(3)

    def test_advance_increments_index(self):
        session = SessionState(total_questions=5)
        session.advance()
        assert session.current_index == 1
        session.advance()
        assert session.current_index == 2

    def test_advance_stops_at_completion(self):
        session = SessionState(total_questions=2, current_index=1)
        session.advance()
        assert session.current_index == 2
        assert session.is_complete
        # Advancing beyond completion is a no-op.
        session.advance()
        assert session.current_index == 2

    def test_is_complete_at_boundary(self):
        session = SessionState(total_questions=3, current_index=3)
        assert session.is_complete

    def test_is_complete_past_boundary(self):
        session = SessionState(total_questions=3, current_index=5)
        assert session.is_complete

    def test_cannot_answer_when_complete(self):
        session = SessionState(total_questions=3, current_index=3)
        assert not session.can_answer_at(3)
        assert not session.can_answer_at(0)

    def test_zero_questions_session_is_immediately_complete(self):
        session = SessionState(total_questions=0)
        assert session.is_complete
        assert not session.can_answer_at(0)


# ===========================================================================
# advance_session / is_session_complete functions
# ===========================================================================

class TestSessionFunctions:
    """Tests for advance_session and is_session_complete."""

    def test_advance_session_returns_same_session(self):
        session = SessionState(total_questions=5)
        result = advance_session(session)
        assert result is session
        assert result.current_index == 1

    def test_is_session_complete_false(self):
        session = SessionState(total_questions=5, current_index=2)
        assert not is_session_complete(session)

    def test_is_session_complete_true(self):
        session = SessionState(total_questions=5, current_index=5)
        assert is_session_complete(session)


# ===========================================================================
# score_session — combined scoring
# ===========================================================================

class TestScoreSession:
    """Tests for score_session (combined scoring + type accuracy)."""

    def test_empty_session(self):
        session = SessionState(total_questions=0)
        result = score_session(session, [])
        assert result.total_questions == 0
        assert result.correct_count == 0
        assert result.score == 0.0
        assert result.type_accuracies == []

    def test_full_session_scoring(self):
        session = SessionState(total_questions=4, current_index=4)
        attempts = [
            _make_attempt(question_id=1, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=True),
            _make_attempt(question_id=2, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=False),
            _make_attempt(question_id=3, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=True),
            _make_attempt(question_id=4, question_type=GsLmsQuestionTypeEnum.MAP_BASED, is_correct=True),
        ]
        result = score_session(session, attempts)

        assert result.total_questions == 4
        assert result.correct_count == 3
        assert result.score == 0.75

        type_map = {ta.question_type: ta for ta in result.type_accuracies}
        assert type_map[GsLmsQuestionTypeEnum.FACTUAL].accuracy == 0.5
        assert type_map[GsLmsQuestionTypeEnum.MAP_BASED].accuracy == 1.0

    def test_session_with_skipped_questions(self):
        session = SessionState(total_questions=3, current_index=3)
        attempts = [
            _make_attempt(question_id=1, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=True),
            _make_attempt(question_id=2, question_type=GsLmsQuestionTypeEnum.FACTUAL, is_correct=None, chosen_answer=None),
            _make_attempt(question_id=3, question_type=GsLmsQuestionTypeEnum.ASSERTION_REASON, is_correct=False),
        ]
        result = score_session(session, attempts)

        assert result.total_questions == 3
        assert result.correct_count == 1
        assert result.score == pytest.approx(1 / 3)

    def test_score_session_type_accuracies_consistent_with_compute(self):
        """score_session type_accuracies should match compute_type_accuracy."""
        attempts = [
            _make_attempt(question_id=1, question_type=GsLmsQuestionTypeEnum.CHRONOLOGICAL, is_correct=True),
            _make_attempt(question_id=2, question_type=GsLmsQuestionTypeEnum.CHRONOLOGICAL, is_correct=True),
            _make_attempt(question_id=3, question_type=GsLmsQuestionTypeEnum.CAUSE_EFFECT, is_correct=False),
        ]
        session = SessionState(total_questions=3, current_index=3)
        result = score_session(session, attempts)
        direct = compute_type_accuracy(attempts)

        assert len(result.type_accuracies) == len(direct)
        for r, d in zip(result.type_accuracies, direct):
            assert r.question_type == d.question_type
            assert r.total == d.total
            assert r.correct == d.correct
            assert r.accuracy == d.accuracy
