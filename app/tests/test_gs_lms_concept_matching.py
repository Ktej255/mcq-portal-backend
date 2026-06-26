"""Tests for GS LMS Concept Extraction and Matching (Task 4.3).

Covers the concept-level scoring logic added to the discussion engine:
- extract_matched_concepts: local substring matching (case-insensitive, plural handling)
- compute_concept_match_percentage: percentage calculation
- check_concept_gate: combined gate check (match% + minimum turns)
- check_threshold: updated to support concept-based gating alongside turn fallback
- process_turn_concepts: integrated turn processing with concept matching

Requirements traced: 2.1, 2.3, 2.4, 2.5
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base

# Ensure all models are registered on Base.metadata
from app.core.gs_lms import models as gs_lms_models  # noqa: F401
from app.core.gs_lms import student_models as gs_lms_student_models  # noqa: F401
from app.core.gs import models as gs_models  # noqa: F401
from app.models import domain as domain_models  # noqa: F401

from app.core.gs_lms.student_models import (
    GsLmsDiscussionSession,
    GsLmsDiscussionStatusEnum,
)
from app.core.gs_lms.models import GsLmsSyllabusNode, GsLmsNodeTypeEnum
from app.core.gs_lms.discussion import (
    MINIMUM_TURN_THRESHOLD,
    CONCEPT_GATE_MINIMUM_TURNS,
    CONCEPT_GATE_THRESHOLD,
    extract_matched_concepts,
    compute_concept_match_percentage,
    check_concept_gate,
    check_threshold,
    update_session_concepts,
    get_student_messages_from_transcript,
    get_topic_concept_checklist,
    process_turn_concepts,
    create_session,
    add_student_turn,
    add_ai_turn,
    complete_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_engine():
    """Create an in-memory SQLite engine with GS LMS tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    relevant_prefixes = ("gs_lms_", "gs_subjects", "users")
    relevant_tables = [
        t
        for name, t in Base.metadata.tables.items()
        if any(name.startswith(p) for p in relevant_prefixes)
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    """Provide a clean database session for each test."""
    Session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------


class TestConceptConstants:
    """Tests for concept-related constants."""

    def test_concept_gate_minimum_turns_is_three(self):
        """Concept gate requires at least 3 turns."""
        assert CONCEPT_GATE_MINIMUM_TURNS == 3

    def test_concept_gate_threshold_is_eighty(self):
        """Concept gate threshold is 80%."""
        assert CONCEPT_GATE_THRESHOLD == 80.0

    def test_turn_threshold_still_five(self):
        """Turn-count fallback still requires 5 turns."""
        assert MINIMUM_TURN_THRESHOLD == 5


# ---------------------------------------------------------------------------
# extract_matched_concepts Tests
# ---------------------------------------------------------------------------


class TestExtractMatchedConcepts:
    """Tests for extract_matched_concepts() (R2.1, R2.3)."""

    def test_exact_match_case_insensitive(self):
        """Matches concepts regardless of case."""
        messages = ["I know about PLATE TECTONICS and how it works."]
        checklist = ["plate tectonics"]
        matched, missed = extract_matched_concepts(messages, checklist)
        assert matched == ["plate tectonics"]
        assert missed == []

    def test_multiple_concepts_matched(self):
        """Matches multiple concepts from a single message."""
        messages = ["Plate tectonics drives continental drift through seafloor spreading."]
        checklist = ["plate tectonics", "continental drift", "seafloor spreading"]
        matched, missed = extract_matched_concepts(messages, checklist)
        assert set(matched) == {"plate tectonics", "continental drift", "seafloor spreading"}
        assert missed == []

    def test_partial_match_across_messages(self):
        """Concepts can be matched across different messages."""
        messages = [
            "Plate tectonics is fundamental.",
            "Continental drift explains landmass movement.",
        ]
        checklist = ["plate tectonics", "continental drift", "subduction"]
        matched, missed = extract_matched_concepts(messages, checklist)
        assert "plate tectonics" in matched
        assert "continental drift" in matched
        assert "subduction" in missed

    def test_plural_matching_concept_has_s(self):
        """Concept with trailing 's' matches text without it."""
        messages = ["I understand plate tectonic as a theory."]
        checklist = ["plate tectonics"]  # has 's'
        matched, missed = extract_matched_concepts(messages, checklist)
        assert "plate tectonics" in matched

    def test_plural_matching_concept_without_s(self):
        """Concept without trailing 's' matches text with it."""
        messages = ["Volcanoes are formed at plate boundaries."]
        checklist = ["volcano"]  # no 's'
        matched, missed = extract_matched_concepts(messages, checklist)
        assert "volcano" in matched

    def test_empty_checklist_returns_empty(self):
        """Empty checklist returns empty matched and missed."""
        matched, missed = extract_matched_concepts(["some message"], [])
        assert matched == []
        assert missed == []

    def test_empty_messages_returns_all_missed(self):
        """Empty messages means all concepts are missed."""
        checklist = ["concept1", "concept2"]
        matched, missed = extract_matched_concepts([], checklist)
        assert matched == []
        assert set(missed) == {"concept1", "concept2"}

    def test_substring_matching(self):
        """Concepts match as substrings within longer text."""
        messages = ["The theory of continental drift was proposed by Wegener."]
        checklist = ["continental drift"]
        matched, missed = extract_matched_concepts(messages, checklist)
        assert "continental drift" in matched

    def test_no_false_positive_partial_words(self):
        """Concepts don't match inside unrelated words (substring semantics)."""
        messages = ["The atomic structure is interesting."]
        checklist = ["atom"]  # "atom" IS a substring of "atomic"
        matched, missed = extract_matched_concepts(messages, checklist)
        # substring matching means "atom" is found within "atomic"
        assert "atom" in matched

    def test_whitespace_in_concepts_handled(self):
        """Concepts with extra whitespace are trimmed."""
        messages = ["mid-ocean ridge formation is key"]
        checklist = ["  mid-ocean ridge  "]
        matched, missed = extract_matched_concepts(messages, checklist)
        assert len(matched) == 1

    def test_empty_concept_string_skipped(self):
        """Empty concept strings in checklist are skipped."""
        messages = ["plate tectonics is important"]
        checklist = ["", "plate tectonics", "  "]
        matched, missed = extract_matched_concepts(messages, checklist)
        assert matched == ["plate tectonics"]
        assert missed == []


# ---------------------------------------------------------------------------
# compute_concept_match_percentage Tests
# ---------------------------------------------------------------------------


class TestComputeConceptMatchPercentage:
    """Tests for compute_concept_match_percentage()."""

    def test_all_matched(self):
        """100% when all concepts matched."""
        result = compute_concept_match_percentage(
            ["a", "b", "c"], ["a", "b", "c"]
        )
        assert result == 100.0

    def test_none_matched(self):
        """0% when no concepts matched."""
        result = compute_concept_match_percentage([], ["a", "b", "c"])
        assert result == 0.0

    def test_partial_match(self):
        """Correct percentage for partial match."""
        result = compute_concept_match_percentage(
            ["a", "b"], ["a", "b", "c", "d", "e"]
        )
        assert result == 40.0

    def test_exactly_eighty_percent(self):
        """80% threshold case."""
        result = compute_concept_match_percentage(
            ["a", "b", "c", "d"], ["a", "b", "c", "d", "e"]
        )
        assert result == 80.0

    def test_empty_checklist_returns_zero(self):
        """Empty checklist returns 0.0 (not division by zero)."""
        result = compute_concept_match_percentage(["a"], [])
        assert result == 0.0


# ---------------------------------------------------------------------------
# check_concept_gate Tests
# ---------------------------------------------------------------------------


class TestCheckConceptGate:
    """Tests for check_concept_gate() combined gate logic (R2.3, R2.4)."""

    def test_gate_passes_at_threshold(self):
        """Gate passes at exactly 80% match with enough turns."""
        checklist = ["a", "b", "c", "d", "e"]
        messages = ["a b c d"]  # matches 4/5 = 80%
        gate, matched, missed, pct = check_concept_gate(
            messages, checklist, turn_count=3
        )
        assert gate is True
        assert pct == 80.0
        assert len(matched) == 4
        assert len(missed) == 1

    def test_gate_fails_below_threshold(self):
        """Gate doesn't pass below 80% even with many turns."""
        checklist = ["a", "b", "c", "d", "e"]
        messages = ["a b"]  # matches 2/5 = 40%
        gate, matched, missed, pct = check_concept_gate(
            messages, checklist, turn_count=10
        )
        assert gate is False
        assert pct == 40.0

    def test_gate_fails_with_insufficient_turns(self):
        """Gate doesn't pass with less than 3 turns even at 100% match."""
        checklist = ["a", "b", "c"]
        messages = ["a b c"]  # 100% match
        gate, matched, missed, pct = check_concept_gate(
            messages, checklist, turn_count=2
        )
        assert gate is False
        assert pct == 100.0

    def test_gate_passes_above_threshold(self):
        """Gate passes above 80%."""
        checklist = ["plate tectonics", "drift", "spreading"]
        messages = ["plate tectonics and continental drift and seafloor spreading"]
        gate, matched, missed, pct = check_concept_gate(
            messages, checklist, turn_count=4
        )
        assert gate is True
        assert pct == 100.0


# ---------------------------------------------------------------------------
# check_threshold (updated) Tests
# ---------------------------------------------------------------------------


class TestCheckThresholdWithConcepts:
    """Tests for the updated check_threshold supporting concept gating (R2.3, R2.4)."""

    def test_no_concept_data_uses_turn_fallback(self):
        """When match_percentage is None, uses 5-turn threshold."""

        class FakeSession:
            match_percentage = None
            turns = None

        s = FakeSession()
        assert check_threshold(s, turn_count=4) is False
        assert check_threshold(s, turn_count=5) is True

    def test_concept_gate_overrides_turn_count(self):
        """When match_percentage is set, concept gate logic takes over."""

        class FakeSession:
            match_percentage = 85.0
            turns = None

        s = FakeSession()
        # 85% >= 80% and 3 >= 3 → gate passes
        assert check_threshold(s, turn_count=3) is True
        # Even though turn_count < 5

    def test_concept_gate_requires_minimum_turns(self):
        """Concept gate still requires CONCEPT_GATE_MINIMUM_TURNS."""

        class FakeSession:
            match_percentage = 100.0
            turns = None

        s = FakeSession()
        assert check_threshold(s, turn_count=2) is False
        assert check_threshold(s, turn_count=3) is True

    def test_low_concept_match_blocks_gate(self):
        """Low concept match percentage blocks gate regardless of turns."""

        class FakeSession:
            match_percentage = 60.0
            turns = None

        s = FakeSession()
        assert check_threshold(s, turn_count=10) is False

    def test_backward_compatible_no_concepts(self):
        """Without concept data, existing 5-turn logic works unchanged."""

        class FakeSession:
            match_percentage = None
            turns = [1, 2, 3, 4, 5]  # len = 5

        s = FakeSession()
        # When turn_count is None, falls back to len(turns)
        assert check_threshold(s) is True

    def test_backward_compatible_under_threshold(self):
        """Without concept data, under 5 turns fails."""

        class FakeSession:
            match_percentage = None
            turns = [1, 2, 3]  # len = 3

        s = FakeSession()
        assert check_threshold(s) is False


# ---------------------------------------------------------------------------
# update_session_concepts Tests
# ---------------------------------------------------------------------------


class TestUpdateSessionConcepts:
    """Tests for update_session_concepts() (R2.5)."""

    def test_updates_session_fields(self):
        """Sets matched, missed, and percentage on session object."""

        class FakeSession:
            concepts_matched = None
            concepts_missed = None
            match_percentage = None

        session = FakeSession()
        update_session_concepts(
            session,
            matched=["a", "b"],
            missed=["c"],
            match_percentage=66.7,
        )

        assert session.concepts_matched == ["a", "b"]
        assert session.concepts_missed == ["c"]
        assert session.match_percentage == 66.7


# ---------------------------------------------------------------------------
# get_student_messages_from_transcript Tests
# ---------------------------------------------------------------------------


class TestGetStudentMessages:
    """Tests for get_student_messages_from_transcript()."""

    def test_extracts_student_messages_only(self):
        """Only returns messages with role='student'."""
        transcript = [
            {"role": "student", "content": "msg1"},
            {"role": "ai", "content": "response1"},
            {"role": "student", "content": "msg2"},
        ]
        result = get_student_messages_from_transcript(transcript)
        assert result == ["msg1", "msg2"]

    def test_empty_transcript(self):
        """Empty transcript returns empty list."""
        result = get_student_messages_from_transcript([])
        assert result == []

    def test_no_student_messages(self):
        """Transcript with only AI messages returns empty."""
        transcript = [{"role": "ai", "content": "hello"}]
        result = get_student_messages_from_transcript(transcript)
        assert result == []


# ---------------------------------------------------------------------------
# get_topic_concept_checklist Tests
# ---------------------------------------------------------------------------


class TestGetTopicConceptChecklist:
    """Tests for get_topic_concept_checklist()."""

    def test_returns_checklist_when_present(self):
        """Returns the concept checklist from syllabus node."""

        class FakeNode:
            concept_checklist = ["a", "b", "c"]

        class FakeSession:
            syllabus_node = FakeNode()

        result = get_topic_concept_checklist(FakeSession())
        assert result == ["a", "b", "c"]

    def test_returns_none_when_no_node(self):
        """Returns None when syllabus_node is None."""

        class FakeSession:
            syllabus_node = None

        result = get_topic_concept_checklist(FakeSession())
        assert result is None

    def test_returns_none_when_checklist_is_none(self):
        """Returns None when concept_checklist is None."""

        class FakeNode:
            concept_checklist = None

        class FakeSession:
            syllabus_node = FakeNode()

        result = get_topic_concept_checklist(FakeSession())
        assert result is None

    def test_returns_none_when_checklist_is_empty(self):
        """Returns None when concept_checklist is empty list."""

        class FakeNode:
            concept_checklist = []

        class FakeSession:
            syllabus_node = FakeNode()

        result = get_topic_concept_checklist(FakeSession())
        assert result is None


# ---------------------------------------------------------------------------
# process_turn_concepts Integration Tests (with DB)
# ---------------------------------------------------------------------------


class TestProcessTurnConcepts:
    """Integration tests for process_turn_concepts() with DB (R2.1, R2.3, R2.5)."""

    def test_no_checklist_returns_inactive(self, db_session):
        """When no concept_checklist, returns (False, None, None)."""
        session = create_session(db_session, 1, 999)
        db_session.commit()

        transcript = [{"role": "student", "content": "hello"}]
        active, missed, pct = process_turn_concepts(db_session, session, transcript)

        assert active is False
        assert missed is None
        assert pct is None

    def test_with_checklist_computes_matching(self, db_session, test_engine):
        """With a concept_checklist on the node, computes matching."""
        # Create a syllabus node with concept_checklist
        from app.core.gs_lms.models import GsLmsSyllabusNode, GsLmsNodeTypeEnum

        node = GsLmsSyllabusNode(
            id=200,
            subject_id=1,
            title="Plate Tectonics",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            concept_checklist=["plate tectonics", "continental drift", "subduction"],
        )
        db_session.add(node)
        db_session.flush()

        session = create_session(db_session, 1, 200)
        db_session.commit()
        db_session.refresh(session)

        # Simulate a transcript where student mentions 2 of 3 concepts
        transcript = [
            {"role": "student", "content": "Plate tectonics explains Earth's crust movement."},
            {"role": "ai", "content": "What about continental drift?"},
            {"role": "student", "content": "Continental drift was proposed by Wegener."},
        ]

        active, missed, pct = process_turn_concepts(db_session, session, transcript)

        assert active is True
        assert missed == ["subduction"]
        assert pct == pytest.approx(66.67, abs=0.1)
        # Session columns updated
        assert session.concepts_matched == ["plate tectonics", "continental drift"]
        assert session.concepts_missed == ["subduction"]
        assert session.match_percentage == pytest.approx(66.67, abs=0.1)

    def test_gate_passes_when_enough_concepts_matched(self, db_session, test_engine):
        """Gate passes when ≥80% concepts matched and enough turns."""
        node = GsLmsSyllabusNode(
            id=201,
            subject_id=1,
            title="Volcanism",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            concept_checklist=["magma", "lava", "eruption", "volcanic arc", "hotspot"],
        )
        db_session.add(node)
        db_session.flush()

        session = create_session(db_session, 1, 201)
        db_session.commit()
        db_session.refresh(session)

        # Student covers 4/5 = 80% concepts across 3+ turns
        transcript = [
            {"role": "student", "content": "Magma rises from the mantle."},
            {"role": "ai", "content": "What happens when it reaches surface?"},
            {"role": "student", "content": "Lava flows during an eruption from volcanic arcs."},
        ]

        active, missed, pct = process_turn_concepts(db_session, session, transcript)

        assert active is True
        assert pct == 80.0
        assert missed == ["hotspot"]

        # Now check_threshold should pass (80% >= 80%, 3 turns >= 3)
        assert check_threshold(session, turn_count=3) is True


# ---------------------------------------------------------------------------
# complete_session with concept gate Tests
# ---------------------------------------------------------------------------


class TestCompleteSessionWithConcepts:
    """Tests that complete_session respects concept-based gate."""

    def test_complete_with_concept_gate_passes(self, db_session, test_engine):
        """Session can be completed when concept gate is satisfied."""
        node = GsLmsSyllabusNode(
            id=300,
            subject_id=1,
            title="Weathering",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            concept_checklist=["weathering", "erosion", "sediment"],
        )
        db_session.add(node)
        db_session.flush()

        session = create_session(db_session, 1, 300)
        db_session.commit()

        # Add 3 turns
        add_student_turn(db_session, session, "Weathering breaks rocks.")
        add_ai_turn(db_session, session, "What types exist?")
        add_student_turn(db_session, session, "Erosion moves sediment downstream.")
        db_session.commit()

        # Set concept match data (simulating process_turn_concepts result)
        session.match_percentage = 100.0
        session.concepts_matched = ["weathering", "erosion", "sediment"]
        session.concepts_missed = []
        db_session.flush()

        # Should succeed: 100% >= 80% and 3 turns >= 3
        result = complete_session(db_session, session)
        assert result.status == GsLmsDiscussionStatusEnum.COMPLETED

    def test_complete_fails_with_low_concept_match(self, db_session, test_engine):
        """Session cannot be completed when concept match is too low."""
        node = GsLmsSyllabusNode(
            id=301,
            subject_id=1,
            title="Erosion",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            concept_checklist=["erosion", "river", "wind", "glacier", "waves"],
        )
        db_session.add(node)
        db_session.flush()

        session = create_session(db_session, 1, 301)
        db_session.commit()

        # Add 5 turns but low concept match
        add_student_turn(db_session, session, "Erosion is a process.")
        add_ai_turn(db_session, session, "What causes it?")
        add_student_turn(db_session, session, "Water and wind.")
        add_ai_turn(db_session, session, "Any other agents?")
        add_student_turn(db_session, session, "Not sure.")
        db_session.commit()

        # Set low concept match
        session.match_percentage = 40.0
        session.concepts_matched = ["erosion", "wind"]
        session.concepts_missed = ["river", "glacier", "waves"]
        db_session.flush()

        # Should fail: 40% < 80%
        with pytest.raises(ValueError, match="concept match"):
            complete_session(db_session, session)
