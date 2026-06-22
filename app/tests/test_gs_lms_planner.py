"""Tests for the GS LMS daily planner engine (Task 7.4).

Tests the pure scheduling functions in ``app.core.gs_lms.planner``:
* ``generate_day_plan`` — position + bandwidth → day plan items (Property 16)
* ``check_replan_needed`` — 2 consecutive misses trigger replan (Property 17)
* ``should_suggest_bandwidth_increase`` — 5 consecutive hits → suggest increase
* ``compute_projected_completion`` — today + ceil(R/B) days (Property 18)

Also tests the DTOs: PlanItem, DayPlan, PlanHistoryEntry.

Requirements traced: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.gs_lms.planner import (
    PlanItem,
    DayPlan,
    PlanHistoryEntry,
    generate_day_plan,
    check_replan_needed,
    should_suggest_bandwidth_increase,
    compute_projected_completion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_items(count: int) -> list[PlanItem]:
    """Create a sequence of test PlanItems."""
    return [
        PlanItem(node_id=i + 1, title=f"Topic {i + 1}", item_type="section")
        for i in range(count)
    ]


def _make_history(
    outcomes: list[bool | None], start_date: date | None = None
) -> list[PlanHistoryEntry]:
    """Create plan history from a list of outcomes (True/False/None)."""
    if start_date is None:
        start_date = date(2024, 1, 1)
    return [
        PlanHistoryEntry(
            plan_date=start_date + timedelta(days=i),
            is_target_met=outcome,
        )
        for i, outcome in enumerate(outcomes)
    ]


# ===========================================================================
# generate_day_plan — Property 16: min(B, remaining) items from position P
# ===========================================================================


class TestGenerateDayPlan:
    """Tests for generate_day_plan (Property 16)."""

    def test_basic_plan_generation(self):
        """Plan with bandwidth < remaining yields bandwidth items."""
        items = _make_items(10)
        plan = generate_day_plan(items, current_position=0, bandwidth=3)

        assert len(plan.items) == 3
        assert plan.items[0].node_id == 1
        assert plan.items[1].node_id == 2
        assert plan.items[2].node_id == 3
        assert plan.bandwidth == 3
        assert plan.remaining_items == 10

    def test_plan_from_middle_position(self):
        """Plan starting from a non-zero position."""
        items = _make_items(10)
        plan = generate_day_plan(items, current_position=5, bandwidth=3)

        assert len(plan.items) == 3
        assert plan.items[0].node_id == 6
        assert plan.items[1].node_id == 7
        assert plan.items[2].node_id == 8
        assert plan.remaining_items == 5

    def test_bandwidth_exceeds_remaining(self):
        """When bandwidth > remaining, plan contains only remaining items."""
        items = _make_items(5)
        plan = generate_day_plan(items, current_position=3, bandwidth=10)

        assert len(plan.items) == 2  # min(10, 2) = 2
        assert plan.items[0].node_id == 4
        assert plan.items[1].node_id == 5
        assert plan.remaining_items == 2

    def test_position_at_end(self):
        """Position at the end of syllabus yields empty plan."""
        items = _make_items(5)
        plan = generate_day_plan(items, current_position=5, bandwidth=3)

        assert len(plan.items) == 0
        assert plan.remaining_items == 0

    def test_position_beyond_end(self):
        """Position beyond the end is handled gracefully."""
        items = _make_items(5)
        plan = generate_day_plan(items, current_position=10, bandwidth=3)

        assert len(plan.items) == 0
        assert plan.remaining_items == 0

    def test_empty_syllabus(self):
        """Empty syllabus yields empty plan."""
        plan = generate_day_plan([], current_position=0, bandwidth=5)

        assert len(plan.items) == 0
        assert plan.remaining_items == 0

    def test_zero_bandwidth(self):
        """Zero bandwidth yields empty plan with no projection."""
        items = _make_items(10)
        plan = generate_day_plan(items, current_position=0, bandwidth=0)

        assert len(plan.items) == 0
        assert plan.remaining_items == 10
        assert plan.projected_completion is None

    def test_negative_bandwidth(self):
        """Negative bandwidth treated as zero."""
        items = _make_items(10)
        plan = generate_day_plan(items, current_position=0, bandwidth=-5)

        assert len(plan.items) == 0
        assert plan.projected_completion is None

    def test_plan_has_projected_completion(self):
        """Plan includes projected completion date."""
        items = _make_items(10)
        plan = generate_day_plan(items, current_position=0, bandwidth=3)

        assert plan.projected_completion is not None

    def test_plan_item_count_invariant(self):
        """Property 16: len(items) == min(B, remaining)."""
        items = _make_items(20)
        for pos in range(0, 21, 5):
            for bw in [1, 3, 5, 10, 25]:
                plan = generate_day_plan(items, current_position=pos, bandwidth=bw)
                remaining = max(0, 20 - pos)
                expected_count = min(bw, remaining)
                assert len(plan.items) == expected_count

    def test_plan_items_start_from_position(self):
        """Items are taken sequentially from current_position."""
        items = _make_items(10)
        plan = generate_day_plan(items, current_position=4, bandwidth=3)

        expected_ids = [5, 6, 7]
        actual_ids = [item.node_id for item in plan.items]
        assert actual_ids == expected_ids


# ===========================================================================
# check_replan_needed — Property 17: 2 consecutive misses trigger replan
# ===========================================================================


class TestCheckReplanNeeded:
    """Tests for check_replan_needed (Property 17)."""

    def test_two_consecutive_misses_triggers_replan(self):
        """Two consecutive False entries at the end → True."""
        history = _make_history([True, True, False, False])
        assert check_replan_needed(history) is True

    def test_single_miss_does_not_trigger(self):
        """A single miss does NOT trigger."""
        history = _make_history([True, True, True, False])
        assert check_replan_needed(history) is False

    def test_miss_followed_by_hit_does_not_trigger(self):
        """A miss then a hit does NOT trigger."""
        history = _make_history([True, False, True])
        assert check_replan_needed(history) is False

    def test_hit_followed_by_miss_does_not_trigger(self):
        """A hit then a miss does NOT trigger."""
        history = _make_history([False, False, True, False])
        assert check_replan_needed(history) is False

    def test_empty_history(self):
        """Empty history → no replan."""
        assert check_replan_needed([]) is False

    def test_single_entry(self):
        """Single entry → no replan (need at least 2)."""
        history = _make_history([False])
        assert check_replan_needed(history) is False

    def test_all_misses(self):
        """All misses → triggers (last two are consecutive misses)."""
        history = _make_history([False, False, False])
        assert check_replan_needed(history) is True

    def test_none_entries_ignored(self):
        """Entries with is_target_met=None are filtered out."""
        history = _make_history([True, False, None, False])
        # After filtering None: [True, False, False] → last two are [False, False]
        assert check_replan_needed(history) is True

    def test_only_none_entries(self):
        """All None entries → no evaluated entries → False."""
        history = _make_history([None, None, None])
        assert check_replan_needed(history) is False

    def test_two_misses_separated_by_none(self):
        """Two misses separated by None still count (None is filtered)."""
        history = _make_history([False, None, False])
        # After filtering: [False, False] → triggers
        assert check_replan_needed(history) is True

    def test_two_misses_not_at_end_does_not_trigger(self):
        """Two consecutive misses earlier but a hit at end → no trigger."""
        history = _make_history([False, False, True])
        assert check_replan_needed(history) is False


# ===========================================================================
# should_suggest_bandwidth_increase — 5 consecutive hits
# ===========================================================================


class TestShouldSuggestBandwidthIncrease:
    """Tests for should_suggest_bandwidth_increase."""

    def test_five_consecutive_hits(self):
        """Exactly 5 consecutive hits at the end → True."""
        history = _make_history([False, True, True, True, True, True])
        assert should_suggest_bandwidth_increase(history) is True

    def test_four_consecutive_hits_not_enough(self):
        """4 consecutive hits → False."""
        history = _make_history([True, True, True, True])
        assert should_suggest_bandwidth_increase(history) is False

    def test_five_hits_with_miss_in_middle(self):
        """A miss breaking the streak → False."""
        history = _make_history([True, True, False, True, True, True])
        # Last 5: [True, False, True, True, True] → False
        assert should_suggest_bandwidth_increase(history) is False

    def test_empty_history(self):
        """Empty → False."""
        assert should_suggest_bandwidth_increase([]) is False

    def test_all_hits_long_history(self):
        """Many consecutive hits → True."""
        history = _make_history([True] * 10)
        assert should_suggest_bandwidth_increase(history) is True

    def test_none_entries_ignored(self):
        """None entries filtered; only evaluated entries count."""
        history = _make_history([True, None, True, True, True, True, True])
        # After filtering: [True, True, True, True, True, True] → last 5 all True
        assert should_suggest_bandwidth_increase(history) is True

    def test_five_misses_returns_false(self):
        """5 consecutive misses → False."""
        history = _make_history([False, False, False, False, False])
        assert should_suggest_bandwidth_increase(history) is False

    def test_exactly_five_entries_all_hits(self):
        """Exactly 5 entries, all hits → True."""
        history = _make_history([True, True, True, True, True])
        assert should_suggest_bandwidth_increase(history) is True


# ===========================================================================
# compute_projected_completion — Property 18: today + ceil(R/B) days
# ===========================================================================


class TestComputeProjectedCompletion:
    """Tests for compute_projected_completion (Property 18)."""

    def test_basic_projection(self):
        """10 remaining items at bandwidth 3 → ceil(10/3) = 4 days."""
        ref = date(2024, 6, 1)
        result = compute_projected_completion(10, 3, reference_date=ref)
        assert result == date(2024, 6, 5)  # June 1 + 4 days

    def test_exact_division(self):
        """12 remaining items at bandwidth 4 → ceil(12/4) = 3 days."""
        ref = date(2024, 6, 1)
        result = compute_projected_completion(12, 4, reference_date=ref)
        assert result == date(2024, 6, 4)

    def test_single_item_remaining(self):
        """1 remaining at bandwidth 5 → ceil(1/5) = 1 day."""
        ref = date(2024, 6, 1)
        result = compute_projected_completion(1, 5, reference_date=ref)
        assert result == date(2024, 6, 2)

    def test_zero_remaining(self):
        """0 remaining → already complete (returns reference date)."""
        ref = date(2024, 6, 1)
        result = compute_projected_completion(0, 5, reference_date=ref)
        assert result == ref

    def test_zero_bandwidth_returns_none(self):
        """Bandwidth 0 → None (no projection possible)."""
        result = compute_projected_completion(10, 0, reference_date=date(2024, 6, 1))
        assert result is None

    def test_negative_bandwidth_returns_none(self):
        """Negative bandwidth → None."""
        result = compute_projected_completion(10, -1, reference_date=date(2024, 6, 1))
        assert result is None

    def test_large_remaining(self):
        """Large remaining count with small bandwidth."""
        ref = date(2024, 1, 1)
        # 100 items / 3 bandwidth = ceil(33.33) = 34 days
        result = compute_projected_completion(100, 3, reference_date=ref)
        assert result == date(2024, 2, 4)  # Jan 1 + 34 days

    def test_bandwidth_equals_remaining(self):
        """Bandwidth == remaining → exactly 1 day."""
        ref = date(2024, 6, 1)
        result = compute_projected_completion(5, 5, reference_date=ref)
        assert result == date(2024, 6, 2)

    def test_bandwidth_exceeds_remaining(self):
        """Bandwidth > remaining → ceil(3/10) = 1 day."""
        ref = date(2024, 6, 1)
        result = compute_projected_completion(3, 10, reference_date=ref)
        assert result == date(2024, 6, 2)

    def test_defaults_to_today(self):
        """When no reference_date, defaults to today."""
        result = compute_projected_completion(10, 5)
        expected = date.today() + timedelta(days=2)  # ceil(10/5) = 2
        assert result == expected


# ===========================================================================
# DayPlan / PlanItem DTO tests
# ===========================================================================


class TestDTOs:
    """Tests for the data transfer objects."""

    def test_plan_item_creation(self):
        item = PlanItem(node_id=1, title="Test Topic", item_type="section")
        assert item.node_id == 1
        assert item.title == "Test Topic"
        assert item.item_type == "section"

    def test_plan_item_default_type(self):
        item = PlanItem(node_id=1, title="Test")
        assert item.item_type == "section"

    def test_day_plan_defaults(self):
        plan = DayPlan()
        assert plan.items == []
        assert plan.bandwidth == 0
        assert plan.remaining_items == 0
        assert plan.projected_completion is None

    def test_plan_history_entry(self):
        entry = PlanHistoryEntry(plan_date=date(2024, 1, 1), is_target_met=True)
        assert entry.plan_date == date(2024, 1, 1)
        assert entry.is_target_met is True

    def test_plan_item_frozen(self):
        """PlanItem is immutable."""
        item = PlanItem(node_id=1, title="Test")
        with pytest.raises(Exception):
            item.node_id = 2  # type: ignore

    def test_day_plan_frozen(self):
        """DayPlan is immutable."""
        plan = DayPlan()
        with pytest.raises(Exception):
            plan.bandwidth = 5  # type: ignore
