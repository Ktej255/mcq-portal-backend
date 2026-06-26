"""Tests for GS LMS AI Discussion Engine (Task 5.1).

Covers the core discussion engine logic:
- Session lifecycle: INITIATED → IN_PROGRESS → COMPLETED
- Minimum exchange threshold enforcement (5 turns minimum)
- Gate flag setting on completion (unlocks Topic_Page content)
- Transcript persistence for gap analysis
- Active session retrieval
- AI response generation (mock provider)

Requirements traced: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
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
    GsLmsDiscussionTurn,
)
from app.core.gs_lms.discussion import (
    MINIMUM_TURN_THRESHOLD,
    MockAIResponseProvider,
    create_session,
    add_student_turn,
    add_ai_turn,
    generate_ai_response,
    check_threshold,
    complete_session,
    has_completed_discussion,
    get_session_transcript,
    get_active_session,
)


STUDENT_ID = 1
NODE_ID = 100


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


@pytest.fixture()
def discussion_session(db_session):
    """Create and return a fresh discussion session."""
    session = create_session(db_session, STUDENT_ID, NODE_ID)
    db_session.commit()
    return session


def _simulate_full_exchange(db_session, session):
    """Simulate a complete 5-turn exchange (student + AI + student + AI + student)."""
    # Turn 1: Student explanation
    add_student_turn(db_session, session, "I know that geomorphology is about landforms.")
    # Turn 2: AI counter-question 1
    add_ai_turn(db_session, session, "Can you explain what causes these landforms?")
    # Turn 3: Student response 1
    add_student_turn(db_session, session, "Tectonic forces and weathering create them.")
    # Turn 4: AI counter-question 2
    add_ai_turn(db_session, session, "What about the role of water erosion?")
    # Turn 5: Student response 2
    add_student_turn(db_session, session, "Rivers carve valleys through erosion over time.")
    db_session.commit()


# ---------------------------------------------------------------------------
# Session Creation Tests
# ---------------------------------------------------------------------------


class TestCreateSession:
    """Tests for create_session()."""

    def test_creates_session_with_initiated_status(self, db_session):
        """New session starts in INITIATED status."""
        session = create_session(db_session, STUDENT_ID, NODE_ID)
        db_session.commit()

        assert session.id is not None
        assert session.student_id == STUDENT_ID
        assert session.syllabus_node_id == NODE_ID
        assert session.status == GsLmsDiscussionStatusEnum.INITIATED
        assert session.started_at is not None
        assert session.completed_at is None

    def test_creates_multiple_sessions_for_different_topics(self, db_session):
        """Can create sessions for different topics."""
        s1 = create_session(db_session, STUDENT_ID, NODE_ID)
        s2 = create_session(db_session, STUDENT_ID, NODE_ID + 1)
        db_session.commit()

        assert s1.id != s2.id
        assert s1.syllabus_node_id == NODE_ID
        assert s2.syllabus_node_id == NODE_ID + 1


# ---------------------------------------------------------------------------
# Session Lifecycle Tests
# ---------------------------------------------------------------------------


class TestSessionLifecycle:
    """Tests for session state transitions."""

    def test_first_student_turn_transitions_to_in_progress(
        self, db_session, discussion_session
    ):
        """INITIATED → IN_PROGRESS on first student message (R5.1)."""
        assert discussion_session.status == GsLmsDiscussionStatusEnum.INITIATED

        add_student_turn(db_session, discussion_session, "I think geomorphology covers landforms.")
        db_session.commit()

        assert discussion_session.status == GsLmsDiscussionStatusEnum.IN_PROGRESS

    def test_subsequent_turns_stay_in_progress(
        self, db_session, discussion_session
    ):
        """Status remains IN_PROGRESS during the conversation."""
        add_student_turn(db_session, discussion_session, "First message.")
        add_ai_turn(db_session, discussion_session, "Counter question.")
        add_student_turn(db_session, discussion_session, "Response.")
        db_session.commit()

        assert discussion_session.status == GsLmsDiscussionStatusEnum.IN_PROGRESS

    def test_cannot_add_turn_to_completed_session(self, db_session, discussion_session):
        """Cannot add turns to a COMPLETED session."""
        # Simulate full exchange and complete
        _simulate_full_exchange(db_session, discussion_session)
        complete_session(db_session, discussion_session)
        db_session.commit()

        with pytest.raises(ValueError, match="COMPLETED"):
            add_student_turn(db_session, discussion_session, "After completion.")

    def test_cannot_add_turn_to_abandoned_session(self, db_session, discussion_session):
        """Cannot add turns to an ABANDONED session."""
        discussion_session.status = GsLmsDiscussionStatusEnum.ABANDONED
        db_session.commit()

        with pytest.raises(ValueError, match="ABANDONED"):
            add_student_turn(db_session, discussion_session, "After abandonment.")


# ---------------------------------------------------------------------------
# Minimum Exchange Threshold Tests
# ---------------------------------------------------------------------------


class TestThresholdEnforcement:
    """Tests for minimum exchange threshold (Property 13, R5.3)."""

    def test_threshold_constant_is_five(self):
        """The minimum threshold is exactly 5 turns."""
        assert MINIMUM_TURN_THRESHOLD == 5

    def test_threshold_not_met_with_fewer_turns(self, db_session, discussion_session):
        """Threshold not met with fewer than 5 turns."""
        # Add only 3 turns
        add_student_turn(db_session, discussion_session, "Explanation.")
        add_ai_turn(db_session, discussion_session, "Counter-question 1.")
        add_student_turn(db_session, discussion_session, "Response 1.")
        db_session.commit()

        assert check_threshold(discussion_session, turn_count=3) is False

    def test_threshold_met_with_exactly_five_turns(self, db_session, discussion_session):
        """Threshold met with exactly 5 turns."""
        _simulate_full_exchange(db_session, discussion_session)

        assert check_threshold(discussion_session, turn_count=5) is True

    def test_threshold_met_with_more_than_five_turns(self, db_session, discussion_session):
        """Threshold met with more than 5 turns."""
        assert check_threshold(discussion_session, turn_count=7) is True

    def test_cannot_complete_below_threshold(self, db_session, discussion_session):
        """Cannot complete session without meeting the threshold (R5.3)."""
        # Add only 3 turns (below threshold)
        add_student_turn(db_session, discussion_session, "Explanation.")
        add_ai_turn(db_session, discussion_session, "Counter-question 1.")
        add_student_turn(db_session, discussion_session, "Response 1.")
        db_session.commit()

        with pytest.raises(ValueError, match="minimum"):
            complete_session(db_session, discussion_session)

    def test_can_complete_at_threshold(self, db_session, discussion_session):
        """Can complete session when threshold is met."""
        _simulate_full_exchange(db_session, discussion_session)
        result = complete_session(db_session, discussion_session)
        db_session.commit()

        assert result.status == GsLmsDiscussionStatusEnum.COMPLETED
        assert result.completed_at is not None


# ---------------------------------------------------------------------------
# Gate Flag Tests
# ---------------------------------------------------------------------------


class TestGateFlag:
    """Tests for gate flag (discussion completion unlocks content, R5.4, R5.6)."""

    def test_gate_not_passed_without_completed_session(self, db_session):
        """Gate not passed when no session exists."""
        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is False

    def test_gate_not_passed_with_initiated_session(self, db_session, discussion_session):
        """Gate not passed when session is still INITIATED."""
        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is False

    def test_gate_not_passed_with_in_progress_session(
        self, db_session, discussion_session
    ):
        """Gate not passed when session is IN_PROGRESS."""
        add_student_turn(db_session, discussion_session, "Starting discussion.")
        db_session.commit()

        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is False

    def test_gate_passed_after_completion(self, db_session, discussion_session):
        """Gate is passed (True) after session completes (R5.4)."""
        _simulate_full_exchange(db_session, discussion_session)
        complete_session(db_session, discussion_session)
        db_session.commit()

        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is True

    def test_gate_scoped_to_student_and_topic(self, db_session):
        """Gate check is scoped to specific student+topic pair."""
        # Complete a session for student 1, topic 100
        s = create_session(db_session, STUDENT_ID, NODE_ID)
        db_session.commit()
        _simulate_full_exchange(db_session, s)
        complete_session(db_session, s)
        db_session.commit()

        # Student 1, topic 100: gate passed
        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is True
        # Student 1, topic 101: gate NOT passed
        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID + 1) is False
        # Student 2, topic 100: gate NOT passed
        assert has_completed_discussion(db_session, STUDENT_ID + 1, NODE_ID) is False

    def test_subsequent_visits_skip_discussion(self, db_session, discussion_session):
        """Once gate is passed, subsequent checks return True (R5.6)."""
        _simulate_full_exchange(db_session, discussion_session)
        complete_session(db_session, discussion_session)
        db_session.commit()

        # Multiple checks all return True (no re-discussion needed)
        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is True
        assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is True


# ---------------------------------------------------------------------------
# Transcript Persistence Tests
# ---------------------------------------------------------------------------


class TestTranscriptPersistence:
    """Tests for transcript storage and retrieval (R5.5)."""

    def test_transcript_stores_all_turns(self, db_session, discussion_session):
        """All turns are persisted in order for gap analysis."""
        _simulate_full_exchange(db_session, discussion_session)

        transcript = get_session_transcript(db_session, discussion_session.id)

        assert len(transcript) == 5
        # Verify alternating pattern: student, ai, student, ai, student
        expected_roles = ["student", "ai", "student", "ai", "student"]
        actual_roles = [t["role"] for t in transcript]
        assert actual_roles == expected_roles

    def test_transcript_preserves_content(self, db_session, discussion_session):
        """Turn content is preserved exactly."""
        add_student_turn(db_session, discussion_session, "My explanation here.")
        add_ai_turn(db_session, discussion_session, "Why do you think that?")
        db_session.commit()

        transcript = get_session_transcript(db_session, discussion_session.id)

        assert transcript[0]["content"] == "My explanation here."
        assert transcript[1]["content"] == "Why do you think that?"

    def test_transcript_ordered_by_turn_order(self, db_session, discussion_session):
        """Transcript returns turns in correct sequence."""
        _simulate_full_exchange(db_session, discussion_session)

        transcript = get_session_transcript(db_session, discussion_session.id)

        orders = [t["turn_order"] for t in transcript]
        assert orders == [1, 2, 3, 4, 5]

    def test_empty_transcript_for_new_session(self, db_session, discussion_session):
        """New session has an empty transcript."""
        transcript = get_session_transcript(db_session, discussion_session.id)
        assert transcript == []


# ---------------------------------------------------------------------------
# AI Response Generation Tests
# ---------------------------------------------------------------------------


class TestAIResponseGeneration:
    """Tests for generate_ai_response() with mock provider."""

    def test_generates_first_counter_question(self, db_session, discussion_session):
        """First AI response is a counter-question probing depth (R5.3)."""
        response = generate_ai_response(
            discussion_session,
            "I know geomorphology is about landforms.",
            transcript=[],
            provider=MockAIResponseProvider(),
        )

        assert isinstance(response, str)
        assert len(response) > 0
        # Should contain a question-like response about elaboration
        assert "elaborate" in response.lower() or "mechanism" in response.lower()

    def test_generates_second_counter_question(self, db_session, discussion_session):
        """Second AI response asks for examples/applications."""
        transcript = [
            {"role": "student", "content": "Geomorphology is about landforms."},
            {"role": "ai", "content": "Can you elaborate on the mechanisms?"},
            {"role": "student", "content": "Tectonic forces and weathering."},
        ]
        response = generate_ai_response(
            discussion_session,
            "Tectonic forces and weathering.",
            transcript=transcript,
            provider=MockAIResponseProvider(),
        )

        assert isinstance(response, str)
        assert len(response) > 0
        assert "example" in response.lower() or "practical" in response.lower()

    def test_custom_provider_can_be_injected(self, db_session, discussion_session):
        """A custom provider can override the mock."""

        class CustomProvider:
            def generate_response(self, topic_title, transcript, student_message, **kwargs):
                return "Custom AI response."

        response = generate_ai_response(
            discussion_session,
            "Anything.",
            transcript=[],
            provider=CustomProvider(),
        )
        assert response == "Custom AI response."

    def test_concepts_missed_passed_to_provider(self, db_session, discussion_session):
        """When concepts_missed is provided, it is forwarded to the provider (R2.6)."""
        received_kwargs = {}

        class TrackingProvider:
            def generate_response(self, topic_title, transcript, student_message,
                                  concepts_missed=None, match_percentage=None):
                received_kwargs["concepts_missed"] = concepts_missed
                received_kwargs["match_percentage"] = match_percentage
                return "Targeted follow-up."

        response = generate_ai_response(
            discussion_session,
            "I know about plate tectonics.",
            transcript=[],
            provider=TrackingProvider(),
            concepts_missed=["continental drift", "seafloor spreading"],
            match_percentage=0.4,
        )

        assert response == "Targeted follow-up."
        assert received_kwargs["concepts_missed"] == ["continental drift", "seafloor spreading"]
        assert received_kwargs["match_percentage"] == 0.4

    def test_no_concepts_missed_passes_none(self, db_session, discussion_session):
        """When no concepts_missed provided, None is passed to provider."""
        received_kwargs = {}

        class TrackingProvider:
            def generate_response(self, topic_title, transcript, student_message,
                                  concepts_missed=None, match_percentage=None):
                received_kwargs["concepts_missed"] = concepts_missed
                received_kwargs["match_percentage"] = match_percentage
                return "General response."

        response = generate_ai_response(
            discussion_session,
            "General explanation.",
            transcript=[],
            provider=TrackingProvider(),
        )

        assert response == "General response."
        assert received_kwargs["concepts_missed"] is None
        assert received_kwargs["match_percentage"] is None

    def test_mock_provider_accepts_concepts_missed_gracefully(self, db_session, discussion_session):
        """MockAIResponseProvider handles concepts_missed without error."""
        provider = MockAIResponseProvider()
        response = provider.generate_response(
            topic_title="Geomorphology",
            transcript=[],
            student_message="My explanation.",
            concepts_missed=["erosion", "weathering"],
            match_percentage=0.5,
        )
        # Should still return a valid response (ignores concepts_missed)
        assert isinstance(response, str)
        assert len(response) > 0


# ---------------------------------------------------------------------------
# Active Session Tests
# ---------------------------------------------------------------------------


class TestActiveSession:
    """Tests for get_active_session()."""

    def test_returns_none_when_no_session(self, db_session):
        """No active session returns None."""
        result = get_active_session(db_session, STUDENT_ID, NODE_ID)
        assert result is None

    def test_returns_initiated_session(self, db_session, discussion_session):
        """Returns an INITIATED session as active."""
        result = get_active_session(db_session, STUDENT_ID, NODE_ID)
        assert result is not None
        assert result.id == discussion_session.id

    def test_returns_in_progress_session(self, db_session, discussion_session):
        """Returns an IN_PROGRESS session as active."""
        add_student_turn(db_session, discussion_session, "Starting.")
        db_session.commit()

        result = get_active_session(db_session, STUDENT_ID, NODE_ID)
        assert result is not None
        assert result.status == GsLmsDiscussionStatusEnum.IN_PROGRESS

    def test_does_not_return_completed_session(self, db_session, discussion_session):
        """Completed session is not returned as active."""
        _simulate_full_exchange(db_session, discussion_session)
        complete_session(db_session, discussion_session)
        db_session.commit()

        result = get_active_session(db_session, STUDENT_ID, NODE_ID)
        assert result is None

    def test_does_not_return_abandoned_session(self, db_session, discussion_session):
        """Abandoned session is not returned as active."""
        discussion_session.status = GsLmsDiscussionStatusEnum.ABANDONED
        db_session.commit()

        result = get_active_session(db_session, STUDENT_ID, NODE_ID)
        assert result is None


# ---------------------------------------------------------------------------
# Session Completion Tests
# ---------------------------------------------------------------------------


class TestCompleteSession:
    """Tests for complete_session()."""

    def test_cannot_complete_initiated_session(self, db_session, discussion_session):
        """Cannot complete a session still in INITIATED status."""
        with pytest.raises(ValueError, match="IN_PROGRESS"):
            complete_session(db_session, discussion_session)

    def test_sets_completed_at_timestamp(self, db_session, discussion_session):
        """Completion sets the completed_at timestamp."""
        _simulate_full_exchange(db_session, discussion_session)
        result = complete_session(db_session, discussion_session)
        db_session.commit()

        assert result.completed_at is not None

    def test_idempotent_gate_check_after_completion(self, db_session, discussion_session):
        """Gate remains passed indefinitely after completion."""
        _simulate_full_exchange(db_session, discussion_session)
        complete_session(db_session, discussion_session)
        db_session.commit()

        # Check multiple times
        for _ in range(3):
            assert has_completed_discussion(db_session, STUDENT_ID, NODE_ID) is True


# ---------------------------------------------------------------------------
# Turn Ordering Tests
# ---------------------------------------------------------------------------


class TestTurnOrdering:
    """Tests for correct turn order assignment."""

    def test_turns_assigned_sequential_orders(self, db_session, discussion_session):
        """Turns get sequential turn_order values starting at 1."""
        t1 = add_student_turn(db_session, discussion_session, "First.")
        t2 = add_ai_turn(db_session, discussion_session, "Second.")
        t3 = add_student_turn(db_session, discussion_session, "Third.")
        db_session.commit()

        assert t1.turn_order == 1
        assert t2.turn_order == 2
        assert t3.turn_order == 3

    def test_turn_roles_persisted_correctly(self, db_session, discussion_session):
        """Student turns have role='student', AI turns have role='ai'."""
        t1 = add_student_turn(db_session, discussion_session, "Student msg.")
        t2 = add_ai_turn(db_session, discussion_session, "AI msg.")
        db_session.commit()

        assert t1.role == "student"
        assert t2.role == "ai"
