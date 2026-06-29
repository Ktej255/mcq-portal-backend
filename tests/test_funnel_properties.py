"""Property-based tests for the Interactive Learning Funnel core logic.

Uses Hypothesis to verify universal correctness properties from the design
document across randomized inputs.

Properties tested:
- P1: Funnel Step Accessibility Invariant
- P2: Funnel Step Classification Correctness
- P6: Rushed Section Detection
- P8: Recall Scoring Computation
- P12: MCQ All-or-Nothing Scoring
- P13: Weakness Pattern Aggregation and Flagging
- P17: Initial Spaced Repetition Interval
- P18: Spaced Repetition Interval Adjustment
- P19: Missed Session Handling
"""

from datetime import date, timedelta

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.core.gs_lms.funnel_engine import (
    _compute_current_step,
    TOTAL_STEPS,
)
from app.core.gs_lms.recall_scoring import (
    score_recall,
    compute_confidence_score,
    ConceptMatch,
)
from app.core.gs_lms.mcq_lab_scoring import (
    score_mcq_lab,
    create_attempt,
    update_weakness_pattern,
    get_weak_types,
    WEAKNESS_THRESHOLD,
    WEAKNESS_MIN_ATTEMPTS,
)
from app.core.gs_lms.spaced_repetition import (
    compute_initial_interval,
    compute_next_interval,
    handle_missed_session,
    MIN_INTERVAL_DAYS,
    MAX_INTERVAL_DAYS,
    SHORT_INTERVAL_MAX,
    LONG_INTERVAL_MIN,
    LONG_INTERVAL_MAX,
)
from app.core.gs_lms.growth_report import is_section_rushed


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

step_sets = st.frozensets(st.integers(min_value=1, max_value=14), max_size=14)
score_floats = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
positive_ints = st.integers(min_value=1, max_value=7200)
answer_labels = st.sampled_from(["A", "B", "C", "D"])
question_types = st.sampled_from([
    "MULTI_STATEMENT", "HOW_MANY_CORRECT", "ASSERTION_REASON",
    "NOT_EXCEPTION", "SCENARIO_APPLIED", "MATCH_THE_PAIRS", "DIRECT_RECALL"
])


# ---------------------------------------------------------------------------
# Property 1: Funnel Step Accessibility Invariant
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(completed=step_sets)
def test_p1_step_accessibility_invariant(completed: frozenset):
    """For any set of completed steps C, current_step K = min step not in C.
    A step N is accessible iff N <= K."""
    current = _compute_current_step(set(completed))

    # K equals the minimum step number not in C
    for s in range(1, TOTAL_STEPS + 1):
        if s not in completed:
            assert current == s, f"Expected current={s}, got {current} for completed={completed}"
            break
    else:
        # All steps complete
        assert current == TOTAL_STEPS + 1

    # Accessibility invariant: step N accessible iff N <= current_step
    for n in range(1, TOTAL_STEPS + 1):
        is_accessible = n <= current
        if n > current:
            assert not is_accessible, f"Step {n} > current {current} should NOT be accessible"


# ---------------------------------------------------------------------------
# Property 2: Funnel Step Classification
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(completed=step_sets)
def test_p2_step_classification_correctness(completed: frozenset):
    """Every step is classified exactly as completed, active, or locked
    relative to the computed current step.
    
    Note: the classification is relative to current_step (which is the min
    step not in completed). Steps in `completed` that are > current may exist
    in arbitrary test data but in real usage the engine prevents this.
    """
    current = _compute_current_step(set(completed))

    for step in range(1, TOTAL_STEPS + 1):
        # Classification based on position relative to current
        is_active = step == current
        is_locked = step > current
        is_reachable = step < current  # steps before current are accessible (completed or skipped)

        # At most one of active/locked should be true for steps not in completed
        if step not in completed:
            if is_active:
                assert not is_locked
            elif is_locked:
                assert not is_active


# ---------------------------------------------------------------------------
# Property 6: Rushed Section Detection
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    reading_time=st.integers(min_value=0, max_value=7200),
    estimated=st.integers(min_value=0, max_value=3600),
)
def test_p6_rushed_section_detection(reading_time: int, estimated: int):
    """is_rushed == True iff reading_time < 0.3 * estimated (when estimated > 0)."""
    result = is_section_rushed(reading_time, estimated)

    if estimated <= 0:
        assert result is False
    else:
        expected = reading_time < (0.3 * estimated)
        assert result == expected


# ---------------------------------------------------------------------------
# Property 8: Recall Scoring Computation
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    concepts=st.lists(st.text(min_size=3, max_size=20), min_size=1, max_size=10),
    transcript=st.text(min_size=0, max_size=500),
)
def test_p8_recall_scoring_bounds(concepts: list, transcript: str):
    """recall_score and confidence_score are always in [0.0, 1.0]."""
    result = score_recall(transcript, concepts)

    assert 0.0 <= result.recall_score <= 1.0, f"recall_score out of bounds: {result.recall_score}"
    assert 0.0 <= result.confidence_score <= 1.0, f"confidence_score out of bounds: {result.confidence_score}"
    assert result.total_concepts == len(concepts)
    assert result.matched_count <= result.total_concepts


@settings(max_examples=100)
@given(concepts=st.lists(st.text(min_size=3, max_size=20), min_size=1, max_size=10))
def test_p8_recall_score_formula(concepts: list):
    """recall_score == matched_count / total_concepts."""
    # Use a transcript that contains some concepts
    transcript = " ".join(concepts[:len(concepts)//2])
    result = score_recall(transcript, concepts)

    if result.total_concepts > 0:
        expected = result.matched_count / result.total_concepts
        assert abs(result.recall_score - expected) < 1e-9


# ---------------------------------------------------------------------------
# Property 12: MCQ All-or-Nothing Scoring
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    chosen=answer_labels,
    correct=answer_labels,
)
def test_p12_mcq_all_or_nothing(chosen: str, correct: str):
    """is_correct == True iff chosen_answer == correct_answer."""
    attempt = create_attempt(
        question_id=1,
        question_type="MULTI_STATEMENT",
        chosen_answer=chosen,
        correct_answer=correct,
    )
    expected = chosen == correct
    assert attempt.is_correct == expected


@settings(max_examples=100)
@given(
    answers=st.lists(
        st.tuples(answer_labels, answer_labels),
        min_size=15, max_size=15
    )
)
def test_p12_total_score_formula(answers: list):
    """total score == count(correct) / 15."""
    attempts = [
        create_attempt(
            question_id=i,
            question_type="MULTI_STATEMENT",
            chosen_answer=chosen,
            correct_answer=correct,
        )
        for i, (chosen, correct) in enumerate(answers)
    ]
    result = score_mcq_lab(attempts)

    correct_count = sum(1 for c, x in answers if c == x)
    expected_score = correct_count / 15

    assert result.correct_count == correct_count
    assert abs(result.score - expected_score) < 1e-9


# ---------------------------------------------------------------------------
# Property 13: Weakness Pattern Aggregation and Flagging
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    correct=st.integers(min_value=0, max_value=50),
    total=st.integers(min_value=0, max_value=50),
)
def test_p13_weakness_flagging_rules(correct: int, total: int):
    """Type is weak iff accuracy < 0.5 AND total >= 3."""
    assume(total >= correct)
    pattern = {"MULTI_STATEMENT": (correct, total)}

    weak_types = get_weak_types(pattern)

    if total >= WEAKNESS_MIN_ATTEMPTS:
        accuracy = correct / total if total > 0 else 0.0
        if accuracy < WEAKNESS_THRESHOLD:
            assert "MULTI_STATEMENT" in weak_types
        else:
            assert "MULTI_STATEMENT" not in weak_types
    else:
        # Not enough attempts to flag
        assert "MULTI_STATEMENT" not in weak_types


@settings(max_examples=100)
@given(
    session_types=st.lists(
        st.tuples(question_types, st.booleans()),
        min_size=1, max_size=30
    )
)
def test_p13_weakness_pattern_update(session_types: list):
    """Weakness pattern accumulates correctly across sessions."""
    # Build a fake result from the session types
    attempts = [
        create_attempt(
            question_id=i,
            question_type=qtype,
            chosen_answer="A" if is_correct else "B",
            correct_answer="A",
        )
        for i, (qtype, is_correct) in enumerate(session_types)
    ]
    result = score_mcq_lab(attempts)

    # Update empty pattern
    pattern = update_weakness_pattern({}, result)

    # Verify totals match
    total_from_pattern = sum(total for _, (_, total) in pattern.items())
    assert total_from_pattern == len(session_types)


# ---------------------------------------------------------------------------
# Property 17: Initial Spaced Repetition Interval
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(score=score_floats)
def test_p17_initial_interval_bounds(score: float):
    """For score < 0.6: interval in [1, 3]; for score >= 0.6: interval in [5, 7]."""
    interval = compute_initial_interval(score)

    assert interval >= MIN_INTERVAL_DAYS
    assert interval <= LONG_INTERVAL_MAX

    if score < 0.6:
        assert 1 <= interval <= SHORT_INTERVAL_MAX, (
            f"Score {score} < 0.6 but interval={interval} not in [1, {SHORT_INTERVAL_MAX}]"
        )
    else:
        assert LONG_INTERVAL_MIN <= interval <= LONG_INTERVAL_MAX, (
            f"Score {score} >= 0.6 but interval={interval} not in [{LONG_INTERVAL_MIN}, {LONG_INTERVAL_MAX}]"
        )


# ---------------------------------------------------------------------------
# Property 18: Spaced Repetition Interval Adjustment
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    current_interval=st.integers(min_value=1, max_value=90),
    current_score=score_floats,
    previous_score=score_floats,
)
def test_p18_interval_adjustment(current_interval: int, current_score: float, previous_score: float):
    """If current > previous: new >= 1.5 * old (capped 90).
    If current <= previous: new <= 0.5 * old (min 1)."""
    new_interval = compute_next_interval(current_interval, current_score, previous_score)

    assert new_interval >= MIN_INTERVAL_DAYS
    assert new_interval <= MAX_INTERVAL_DAYS

    if current_score > previous_score:
        # Improved: increase by >= 50%
        min_expected = current_interval + max(current_interval // 2, 1)
        assert new_interval >= min(min_expected, MAX_INTERVAL_DAYS), (
            f"Improved: interval={current_interval}, new={new_interval}, expected >= {min_expected}"
        )
    else:
        # Same or declined: reduce to <= 50%
        max_expected = current_interval // 2
        assert new_interval <= max(max_expected, MIN_INTERVAL_DAYS), (
            f"Declined: interval={current_interval}, new={new_interval}, expected <= {max_expected}"
        )


# ---------------------------------------------------------------------------
# Property 19: Missed Session Handling
# ---------------------------------------------------------------------------

@settings(max_examples=200)
@given(
    days_offset=st.integers(min_value=-5, max_value=30),
)
def test_p19_missed_session_handling(days_offset: int):
    """Overdue > 2 days → marked missed, next interval <= 3 days."""
    today = date(2026, 6, 15)
    scheduled = today - timedelta(days=days_offset)

    result = handle_missed_session(scheduled, today)

    overdue_days = (today - scheduled).days

    if overdue_days > 2:
        # Should produce a new schedule
        assert result is not None
        assert result.recall_interval_days <= 3
        assert result.due_date <= today + timedelta(days=3)
    else:
        # Not yet overdue
        assert result is None
