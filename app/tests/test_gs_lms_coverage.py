"""Tests for the GS LMS gap/coverage computation engine (Task 7.1).

Two layers:

* **Pure function tests** for the coverage logic (``identify_weak_topics``,
  ``identify_weak_types``, ``generate_recommended_actions``): verifying the
  60% threshold, severity ordering, and action generation.

* **DB integration tests** using an in-memory SQLite database: verifying
  ``compute_topic_accuracy``, ``compute_type_accuracy_from_db``,
  ``compute_overall_accuracy``, and ``create_gap_snapshot`` with realistic
  practice attempt data.

Design Properties validated:
  - Property 14: every topic/type with accuracy < 60% in weak list; none >= 60%
  - Property 15: lists ordered by severity (lowest accuracy first)

Requirements traced: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.domain import User, RoleEnum  # noqa: F401
from app.core.gs.models import GsSubject, GsDayLesson, GsReviewStatusEnum  # noqa: F401
from app.core.gs_lms.models import (
    GsLmsQuestionTypeEnum,
    GsLmsSyllabusNode,
    GsLmsNodeTypeEnum,
    GsLmsMcqQuestion,
)
from app.core.gs_lms.student_models import (
    GsLmsPracticeSession,
    GsLmsPracticeSessionStatusEnum,
    GsLmsPracticeAttempt,
    GsLmsGapSnapshot,
)
from app.core.gs_lms.coverage import (
    TopicAccuracy,
    TypeAccuracyResult,
    RecommendedAction,
    identify_weak_topics,
    identify_weak_types,
    generate_recommended_actions,
    compute_topic_accuracy,
    compute_type_accuracy_from_db,
    compute_overall_accuracy,
    create_gap_snapshot,
    get_latest_gap_snapshot,
    compute_gap_profile,
)

# We need to import models so all tables are registered on Base.metadata
from app.core.gs_lms import models as _gs_lms_models  # noqa: F401
from app.core.gs_lms import student_models as _gs_lms_student_models  # noqa: F401


STUDENT_ID = 1


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def db_session():
    """Create an in-memory SQLite DB with required tables and return a session."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create the tables we need, including referenced tables (users, etc.).
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name in (
            "users",
            "gs_subjects",
            "gs_day_lessons",
            "gs_lms_syllabus_nodes",
            "gs_lms_content_sections",
            "gs_lms_mcq_questions",
            "gs_lms_practice_sessions",
            "gs_lms_practice_attempts",
            "gs_lms_gap_snapshots",
            "gs_lms_student_section_progress",
            "gs_lms_discussion_sessions",
            "gs_lms_discussion_turns",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture()
def seeded_db(db_session):
    """Seed the DB with syllabus nodes, questions, and practice data."""
    db = db_session

    # Create a subject (required FK for syllabus nodes).
    from app.core.gs.models import GsSubject
    subject = GsSubject(id=1, name="Geography", slug="geography")
    db.add(subject)
    db.flush()

    # Create syllabus nodes (topics).
    nodes = []
    for i in range(1, 5):
        node = GsLmsSyllabusNode(
            id=i,
            subject_id=1,
            title=f"Topic {i}",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=i,
            review_status="REVIEWED",
        )
        db.add(node)
        nodes.append(node)

    db.flush()

    # Create MCQ questions for each topic.
    question_id = 1
    for node in nodes:
        for j in range(5):
            q = GsLmsMcqQuestion(
                id=question_id,
                syllabus_node_id=node.id,
                question_text=f"Question {question_id}",
                options=[
                    {"label": "A", "text": "Option A"},
                    {"label": "B", "text": "Option B"},
                    {"label": "C", "text": "Option C"},
                    {"label": "D", "text": "Option D"},
                ],
                correct_option="A",
                question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED
                if j < 2
                else GsLmsQuestionTypeEnum.MATCH_THE_FOLLOWING
                if j < 4
                else GsLmsQuestionTypeEnum.ASSERTION_REASON,
                display_order=j,
                review_status="REVIEWED",
            )
            db.add(q)
            question_id += 1

    db.flush()

    # Create practice sessions and attempts with varying accuracies.
    # Topic 1: 100% accuracy (5/5 correct) — NOT weak
    # Topic 2: 40% accuracy (2/5 correct) — WEAK
    # Topic 3: 60% accuracy (3/5 correct) — NOT weak (exactly at threshold)
    # Topic 4: 20% accuracy (1/5 correct) — WEAK (most severe)
    accuracy_patterns = {
        1: [True, True, True, True, True],
        2: [True, True, False, False, False],
        3: [True, True, True, False, False],
        4: [True, False, False, False, False],
    }

    attempt_id = 1
    for node_id, correct_pattern in accuracy_patterns.items():
        session = GsLmsPracticeSession(
            id=node_id,
            student_id=STUDENT_ID,
            syllabus_node_id=node_id,
            status=GsLmsPracticeSessionStatusEnum.SUBMITTED,
            total_questions=5,
            current_index=5,
        )
        db.add(session)
        db.flush()

        q_id_start = (node_id - 1) * 5 + 1
        for j, is_correct in enumerate(correct_pattern):
            question_id_local = q_id_start + j
            # Look up question type from the question.
            q_obj = db.query(GsLmsMcqQuestion).get(question_id_local)
            attempt = GsLmsPracticeAttempt(
                id=attempt_id,
                session_id=node_id,
                question_id=question_id_local,
                student_id=STUDENT_ID,
                chosen_answer="A" if is_correct else "B",
                is_correct=is_correct,
                time_taken_seconds=10.0,
                question_type=q_obj.question_type if q_obj else GsLmsQuestionTypeEnum.STATEMENT_BASED,
            )
            db.add(attempt)
            attempt_id += 1

    db.commit()
    return db


# ===========================================================================
# Property 14 & 15 — Pure function tests
# ===========================================================================

class TestIdentifyWeakTopics:
    """Tests for identify_weak_topics (Properties 14, 15)."""

    def test_empty_input_returns_empty(self):
        assert identify_weak_topics([]) == []

    def test_all_above_threshold_returns_empty(self):
        topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.8, total_attempts=10, correct_count=8),
            TopicAccuracy(node_id=2, title="T2", accuracy=0.7, total_attempts=10, correct_count=7),
        ]
        assert identify_weak_topics(topics, threshold=0.6) == []

    def test_exactly_at_threshold_not_weak(self):
        """Property 14: accuracy >= 60% must NOT appear in weak list."""
        topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.6, total_attempts=10, correct_count=6),
        ]
        result = identify_weak_topics(topics, threshold=0.6)
        assert len(result) == 0

    def test_below_threshold_is_weak(self):
        """Property 14: accuracy < 60% MUST appear in weak list."""
        topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.59, total_attempts=10, correct_count=5),
        ]
        result = identify_weak_topics(topics, threshold=0.6)
        assert len(result) == 1
        assert result[0].node_id == 1

    def test_severity_ordering(self):
        """Property 15: ordered by severity (lowest accuracy first)."""
        topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.5, total_attempts=10, correct_count=5),
            TopicAccuracy(node_id=2, title="T2", accuracy=0.2, total_attempts=10, correct_count=2),
            TopicAccuracy(node_id=3, title="T3", accuracy=0.4, total_attempts=10, correct_count=4),
        ]
        result = identify_weak_topics(topics, threshold=0.6)
        assert len(result) == 3
        assert result[0].node_id == 2  # 0.2 — most severe
        assert result[1].node_id == 3  # 0.4
        assert result[2].node_id == 1  # 0.5

    def test_mixed_above_and_below(self):
        """Property 14: only those below threshold included."""
        topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.9, total_attempts=10, correct_count=9),
            TopicAccuracy(node_id=2, title="T2", accuracy=0.3, total_attempts=10, correct_count=3),
            TopicAccuracy(node_id=3, title="T3", accuracy=0.6, total_attempts=10, correct_count=6),
            TopicAccuracy(node_id=4, title="T4", accuracy=0.1, total_attempts=10, correct_count=1),
        ]
        result = identify_weak_topics(topics, threshold=0.6)
        assert len(result) == 2
        weak_ids = [r.node_id for r in result]
        assert 2 in weak_ids
        assert 4 in weak_ids
        assert 1 not in weak_ids
        assert 3 not in weak_ids

    def test_custom_threshold(self):
        """Threshold is configurable."""
        topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.7, total_attempts=10, correct_count=7),
        ]
        # With 0.8 threshold, 0.7 is weak.
        result = identify_weak_topics(topics, threshold=0.8)
        assert len(result) == 1

    def test_zero_accuracy(self):
        topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.0, total_attempts=10, correct_count=0),
        ]
        result = identify_weak_topics(topics, threshold=0.6)
        assert len(result) == 1
        assert result[0].accuracy == 0.0


class TestIdentifyWeakTypes:
    """Tests for identify_weak_types (Properties 14, 15)."""

    def test_empty_input_returns_empty(self):
        assert identify_weak_types([]) == []

    def test_all_above_threshold_returns_empty(self):
        types = [
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED,
                accuracy=0.8, total_attempts=10, correct_count=8,
            ),
        ]
        assert identify_weak_types(types, threshold=0.6) == []

    def test_exactly_at_threshold_not_weak(self):
        """Property 14: type accuracy >= 60% must NOT appear."""
        types = [
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.FACTUAL,
                accuracy=0.6, total_attempts=10, correct_count=6,
            ),
        ]
        assert identify_weak_types(types, threshold=0.6) == []

    def test_below_threshold_is_weak(self):
        """Property 14: type accuracy < 60% MUST appear."""
        types = [
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.MAP_BASED,
                accuracy=0.3, total_attempts=10, correct_count=3,
            ),
        ]
        result = identify_weak_types(types, threshold=0.6)
        assert len(result) == 1
        assert result[0].question_type == GsLmsQuestionTypeEnum.MAP_BASED

    def test_severity_ordering(self):
        """Property 15: ordered by severity (lowest first)."""
        types = [
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED,
                accuracy=0.5, total_attempts=10, correct_count=5,
            ),
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.MAP_BASED,
                accuracy=0.1, total_attempts=10, correct_count=1,
            ),
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.ASSERTION_REASON,
                accuracy=0.3, total_attempts=10, correct_count=3,
            ),
        ]
        result = identify_weak_types(types, threshold=0.6)
        assert len(result) == 3
        # Verify ascending order.
        for i in range(len(result) - 1):
            assert result[i].accuracy <= result[i + 1].accuracy


class TestGenerateRecommendedActions:
    """Tests for generate_recommended_actions."""

    def test_empty_inputs_returns_empty(self):
        assert generate_recommended_actions([], []) == []

    def test_topic_actions_generated(self):
        weak_topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.2, total_attempts=10, correct_count=2),
        ]
        actions = generate_recommended_actions(weak_topics, [])
        assert len(actions) == 1
        assert actions[0].target_node_id == 1
        assert "Re-study" in actions[0].action  # < 0.3 threshold

    def test_type_actions_generated(self):
        weak_types = [
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.MAP_BASED,
                accuracy=0.4, total_attempts=10, correct_count=4,
            ),
        ]
        actions = generate_recommended_actions([], weak_types)
        assert len(actions) == 1
        assert actions[0].target_node_id is None
        assert "MAP_BASED" in actions[0].action

    def test_combined_actions_order(self):
        """Topic actions come before type actions."""
        weak_topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.4, total_attempts=10, correct_count=4),
        ]
        weak_types = [
            TypeAccuracyResult(
                question_type=GsLmsQuestionTypeEnum.MAP_BASED,
                accuracy=0.3, total_attempts=10, correct_count=3,
            ),
        ]
        actions = generate_recommended_actions(weak_topics, weak_types)
        assert len(actions) == 2
        # First action is topic-based.
        assert actions[0].target_node_id == 1
        # Second is type-based.
        assert actions[1].target_node_id is None

    def test_severity_levels(self):
        """Different severity levels produce different action texts."""
        weak_topics = [
            TopicAccuracy(node_id=1, title="T1", accuracy=0.2, total_attempts=10, correct_count=2),
            TopicAccuracy(node_id=2, title="T2", accuracy=0.4, total_attempts=10, correct_count=4),
            TopicAccuracy(node_id=3, title="T3", accuracy=0.55, total_attempts=10, correct_count=5),
        ]
        actions = generate_recommended_actions(weak_topics, [])
        assert "Re-study" in actions[0].action  # < 0.3
        assert "Practice more" in actions[1].action  # 0.3-0.5
        assert "Review" in actions[2].action  # 0.5-0.6


# ===========================================================================
# DB integration tests
# ===========================================================================

class TestComputeTopicAccuracy:
    """Tests for compute_topic_accuracy (DB helper)."""

    def test_no_attempts_returns_empty(self, db_session):
        result = compute_topic_accuracy(db_session, STUDENT_ID)
        assert result == []

    def test_returns_correct_accuracies(self, seeded_db):
        result = compute_topic_accuracy(seeded_db, STUDENT_ID)
        accuracy_by_node = {t.node_id: t.accuracy for t in result}

        # Topic 1: 5/5 = 1.0
        assert accuracy_by_node[1] == 1.0
        # Topic 2: 2/5 = 0.4
        assert accuracy_by_node[2] == 0.4
        # Topic 3: 3/5 = 0.6
        assert accuracy_by_node[3] == 0.6
        # Topic 4: 1/5 = 0.2
        assert accuracy_by_node[4] == 0.2

    def test_isolation_by_student(self, seeded_db):
        """Another student has no data."""
        result = compute_topic_accuracy(seeded_db, student_id=999)
        assert result == []


class TestComputeTypeAccuracy:
    """Tests for compute_type_accuracy_from_db."""

    def test_no_attempts_returns_empty(self, db_session):
        result = compute_type_accuracy_from_db(db_session, STUDENT_ID)
        assert result == []

    def test_returns_per_type_accuracy(self, seeded_db):
        result = compute_type_accuracy_from_db(seeded_db, STUDENT_ID)
        accuracy_by_type = {t.question_type: t for t in result}

        # We have 4 topics × 5 questions:
        # Each topic has 2 STATEMENT_BASED, 2 MATCH_THE_FOLLOWING, 1 ASSERTION_REASON.
        # STATEMENT_BASED: 8 total, correct depends on patterns.
        # Topic 1: 2 correct, Topic 2: 2 correct, Topic 3: 2 correct, Topic 4: 1 correct = 7/8
        assert GsLmsQuestionTypeEnum.STATEMENT_BASED in accuracy_by_type
        assert GsLmsQuestionTypeEnum.MATCH_THE_FOLLOWING in accuracy_by_type
        assert GsLmsQuestionTypeEnum.ASSERTION_REASON in accuracy_by_type


class TestComputeOverallAccuracy:
    """Tests for compute_overall_accuracy."""

    def test_no_attempts_returns_zero(self, db_session):
        assert compute_overall_accuracy(db_session, STUDENT_ID) == 0.0

    def test_returns_correct_overall(self, seeded_db):
        # Total: 20 attempts, correct: 5+2+3+1 = 11
        result = compute_overall_accuracy(seeded_db, STUDENT_ID)
        assert result == 11 / 20


class TestCreateGapSnapshot:
    """Tests for create_gap_snapshot (persistence)."""

    def test_creates_snapshot_with_correct_data(self, seeded_db):
        snapshot = create_gap_snapshot(seeded_db, STUDENT_ID)
        seeded_db.commit()

        assert snapshot.id is not None
        assert snapshot.student_id == STUDENT_ID
        assert snapshot.computed_at is not None
        assert snapshot.overall_accuracy == round(11 / 20, 4)

        # Weak topics: Topic 2 (0.4) and Topic 4 (0.2).
        assert snapshot.weak_topics is not None
        assert len(snapshot.weak_topics) == 2
        # Ordered by severity: Topic 4 (0.2) first, then Topic 2 (0.4).
        assert snapshot.weak_topics[0]["node_id"] == 4
        assert snapshot.weak_topics[1]["node_id"] == 2

        # Weak question types.
        assert snapshot.weak_question_types is not None

        # Recommended actions.
        assert snapshot.recommended_actions is not None
        assert len(snapshot.recommended_actions) > 0

    def test_snapshot_persisted_in_db(self, seeded_db):
        create_gap_snapshot(seeded_db, STUDENT_ID)
        seeded_db.commit()

        # Retrieve via helper.
        latest = get_latest_gap_snapshot(seeded_db, STUDENT_ID)
        assert latest is not None
        assert latest.student_id == STUDENT_ID

    def test_no_attempts_produces_empty_snapshot(self, db_session):
        """With no practice data, snapshot has 0 accuracy and empty weak lists."""
        # Need at least the table to exist.
        snapshot = create_gap_snapshot(db_session, STUDENT_ID)
        db_session.commit()

        assert snapshot.overall_accuracy == 0.0
        assert snapshot.weak_topics == []
        assert snapshot.weak_question_types == []
        assert snapshot.recommended_actions == []


class TestComputeGapProfile:
    """Tests for compute_gap_profile (non-persisting)."""

    def test_no_attempts_returns_zero_profile(self, db_session):
        profile = compute_gap_profile(db_session, STUDENT_ID)
        assert profile.overall_accuracy == 0.0
        assert profile.weak_topics == []
        assert profile.weak_question_types == []
        assert profile.recommended_actions == []

    def test_returns_correct_profile(self, seeded_db):
        profile = compute_gap_profile(seeded_db, STUDENT_ID)
        assert profile.overall_accuracy == 11 / 20
        # Weak topics: accuracy < 0.6 → Topic 2 (0.4) and Topic 4 (0.2).
        assert len(profile.weak_topics) == 2
        # Property 15: ordered by severity.
        assert profile.weak_topics[0].accuracy <= profile.weak_topics[1].accuracy


class TestGetLatestGapSnapshot:
    """Tests for get_latest_gap_snapshot."""

    def test_returns_none_when_no_snapshots(self, db_session):
        assert get_latest_gap_snapshot(db_session, STUDENT_ID) is None

    def test_returns_most_recent(self, seeded_db):
        # Create two snapshots.
        create_gap_snapshot(seeded_db, STUDENT_ID)
        seeded_db.commit()
        snap2 = create_gap_snapshot(seeded_db, STUDENT_ID)
        seeded_db.commit()

        latest = get_latest_gap_snapshot(seeded_db, STUDENT_ID)
        assert latest.id == snap2.id
