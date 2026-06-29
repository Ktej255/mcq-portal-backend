"""Endpoint tests for GS LMS Progress/Gap API (Task 7.2).

Exercises:
* GET /api/v1/gs-lms/geography/progress — Overall + per-mega-topic coverage
* GET /api/v1/gs-lms/geography/gaps — Prioritized weak topics and weak question types

Strategy: isolated in-memory SQLite seeded with known syllabus, section progress,
and practice attempt data. App dependencies (get_db, get_current_user) are
overridden so routes run hermetically without Postgres or network.

Validates:
* Progress computation from section completion data (R6.1)
* Gap profile with weak topics below 60% threshold (Property 14 / R6.2)
* Gap profile weak question types (R6.3)
* Empty-state guarantee — always renders either weak list or empty (R6.4)
* Ordering by severity — lowest accuracy first (Property 15)
* Auth gating (Property 23 / R10.2)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.api.dependencies import get_current_user
from app.main import app
from app.models.domain import User, RoleEnum

# Import models to register tables on Base.metadata.
from app.core.gs.models import GsSubject, GsReviewStatusEnum  # noqa: F401
from app.core.gs_lms.models import (  # noqa: F401
    GsLmsSyllabusNode,
    GsLmsNodeTypeEnum,
    GsLmsContentSection,
    GsLmsSectionLabelEnum,
    GsLmsMcqQuestion,
    GsLmsQuestionTypeEnum,
)
from app.core.gs_lms.student_models import (  # noqa: F401
    GsLmsStudentSectionProgress,
    GsLmsPracticeSession,
    GsLmsPracticeAttempt,
    GsLmsPracticeSessionStatusEnum,
    GsLmsGapSnapshot,
    GsLmsRevisitSchedule,
)


# ---------------------------------------------------------------------------
# Table list for test DB creation
# ---------------------------------------------------------------------------

REQUIRED_TABLES = [
    "users",
    "gs_subjects",
    "gs_day_lessons",
    "gs_lms_syllabus_nodes",
    "gs_lms_content_sections",
    "gs_lms_mcq_questions",
    "gs_lms_student_section_progress",
    "gs_lms_practice_sessions",
    "gs_lms_practice_attempts",
    "gs_lms_gap_snapshots",
    "gs_lms_revisit_schedule",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_engine():
    """In-memory SQLite with test data for progress/gap tests.

    Setup:
    - 1 subject (Geography)
    - 1 MEGA_TOPIC node (Geomorphology, id=10) with 2 LEAF_TOPIC children:
        - Continental Drift (id=30) — fully completed by student
        - Plate Tectonics (id=31) — NOT completed
    - 1 MEGA_TOPIC node (Climatology, id=20) with 1 LEAF_TOPIC child:
        - Atmosphere (id=40) — NOT completed
    - Each leaf topic has 4 content sections
    - Student has completed all 4 sections for node 30
    - Practice attempts for node 30: 2 correct, 1 wrong (accuracy = 66.7%)
    - Practice attempts for node 31: 1 correct, 4 wrong (accuracy = 20%)
      → this topic should appear in weak_topics
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create only the tables we need.
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name in REQUIRED_TABLES
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = TestSession()
    try:
        # Users
        student = User(
            id=1,
            google_uid="test-student-uid",
            email="test@upsc.local",
            full_name="Test Student",
            role=RoleEnum.STUDENT,
        )
        session.add(student)

        # Subject
        subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
        session.add(subject)
        session.flush()

        # Mega-topic nodes
        geomorphology = GsLmsSyllabusNode(
            id=10,
            subject_id=1,
            parent_id=None,
            title="Geomorphology",
            node_type=GsLmsNodeTypeEnum.MEGA_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(geomorphology)

        climatology = GsLmsSyllabusNode(
            id=20,
            subject_id=1,
            parent_id=None,
            title="Climatology",
            node_type=GsLmsNodeTypeEnum.MEGA_TOPIC,
            weight=1.0,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(climatology)
        session.flush()

        # Leaf topics under Geomorphology
        continental_drift = GsLmsSyllabusNode(
            id=30,
            subject_id=1,
            parent_id=10,
            title="Continental Drift",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=0.5,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(continental_drift)

        plate_tectonics = GsLmsSyllabusNode(
            id=31,
            subject_id=1,
            parent_id=10,
            title="Plate Tectonics",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=0.5,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(plate_tectonics)

        # Leaf topic under Climatology
        atmosphere = GsLmsSyllabusNode(
            id=40,
            subject_id=1,
            parent_id=20,
            title="Atmosphere",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(atmosphere)
        session.flush()

        # Content sections for node 30 (Continental Drift)
        for i, label in enumerate(
            [
                GsLmsSectionLabelEnum.BASIC,
                GsLmsSectionLabelEnum.ADVANCED,
                GsLmsSectionLabelEnum.NCERT_LEVEL,
                GsLmsSectionLabelEnum.EXAMINER_TRAPS,
            ],
            start=1,
        ):
            sec = GsLmsContentSection(
                id=100 + i,
                syllabus_node_id=30,
                section_label=label,
                title=f"Section {label.value}",
                blocks=[{"type": "text", "content": "..."}],
                display_order=i,
                review_status=GsReviewStatusEnum.REVIEWED,
            )
            session.add(sec)

        # Content sections for node 31 (Plate Tectonics)
        for i, label in enumerate(
            [
                GsLmsSectionLabelEnum.BASIC,
                GsLmsSectionLabelEnum.ADVANCED,
                GsLmsSectionLabelEnum.NCERT_LEVEL,
                GsLmsSectionLabelEnum.EXAMINER_TRAPS,
            ],
            start=1,
        ):
            sec = GsLmsContentSection(
                id=200 + i,
                syllabus_node_id=31,
                section_label=label,
                title=f"Section {label.value}",
                blocks=[{"type": "text", "content": "..."}],
                display_order=i,
                review_status=GsReviewStatusEnum.REVIEWED,
            )
            session.add(sec)

        # Content sections for node 40 (Atmosphere)
        for i, label in enumerate(
            [
                GsLmsSectionLabelEnum.BASIC,
                GsLmsSectionLabelEnum.ADVANCED,
                GsLmsSectionLabelEnum.NCERT_LEVEL,
                GsLmsSectionLabelEnum.EXAMINER_TRAPS,
            ],
            start=1,
        ):
            sec = GsLmsContentSection(
                id=300 + i,
                syllabus_node_id=40,
                section_label=label,
                title=f"Section {label.value}",
                blocks=[{"type": "text", "content": "..."}],
                display_order=i,
                review_status=GsReviewStatusEnum.REVIEWED,
            )
            session.add(sec)

        session.flush()

        # Student has completed all 4 sections of node 30 (Continental Drift)
        for i in range(1, 5):
            progress = GsLmsStudentSectionProgress(
                student_id=1,
                section_id=100 + i,
                syllabus_node_id=30,
                completed=True,
                completed_at=datetime(2024, 1, i, tzinfo=timezone.utc),
            )
            session.add(progress)

        session.flush()

        # Practice sessions and attempts for node 30: 2 correct, 1 wrong = 66.7%
        ps1 = GsLmsPracticeSession(
            id=1,
            student_id=1,
            syllabus_node_id=30,
            status=GsLmsPracticeSessionStatusEnum.SUBMITTED,
            total_questions=3,
            current_index=3,
            started_at=datetime(2024, 1, 5, tzinfo=timezone.utc),
            submitted_at=datetime(2024, 1, 5, 0, 30, tzinfo=timezone.utc),
        )
        session.add(ps1)
        session.flush()

        # Attempts for session 1 (node 30)
        session.add(GsLmsPracticeAttempt(
            id=1, session_id=1, question_id=1, student_id=1,
            chosen_answer="B", is_correct=True, time_taken_seconds=10.0,
            question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED,
        ))
        session.add(GsLmsPracticeAttempt(
            id=2, session_id=1, question_id=2, student_id=1,
            chosen_answer="A", is_correct=True, time_taken_seconds=8.0,
            question_type=GsLmsQuestionTypeEnum.FACTUAL,
        ))
        session.add(GsLmsPracticeAttempt(
            id=3, session_id=1, question_id=3, student_id=1,
            chosen_answer="A", is_correct=False, time_taken_seconds=15.0,
            question_type=GsLmsQuestionTypeEnum.ASSERTION_REASON,
        ))

        # Practice session for node 31: 1 correct, 4 wrong = 20%
        ps2 = GsLmsPracticeSession(
            id=2,
            student_id=1,
            syllabus_node_id=31,
            status=GsLmsPracticeSessionStatusEnum.SUBMITTED,
            total_questions=5,
            current_index=5,
            started_at=datetime(2024, 1, 6, tzinfo=timezone.utc),
            submitted_at=datetime(2024, 1, 6, 0, 30, tzinfo=timezone.utc),
        )
        session.add(ps2)
        session.flush()

        # Attempts for session 2 (node 31)
        session.add(GsLmsPracticeAttempt(
            id=4, session_id=2, question_id=4, student_id=1,
            chosen_answer="B", is_correct=True, time_taken_seconds=12.0,
            question_type=GsLmsQuestionTypeEnum.MAP_BASED,
        ))
        for i in range(5, 9):
            session.add(GsLmsPracticeAttempt(
                id=i, session_id=2, question_id=i, student_id=1,
                chosen_answer="A", is_correct=False, time_taken_seconds=10.0,
                question_type=GsLmsQuestionTypeEnum.MAP_BASED,
            ))

        # We need dummy MCQ questions so the FK relationships work
        for qid in range(1, 9):
            session.add(GsLmsMcqQuestion(
                id=qid,
                syllabus_node_id=30 if qid <= 3 else 31,
                question_text=f"Question {qid}",
                options=[
                    {"label": "A", "text": "Option A"},
                    {"label": "B", "text": "Option B"},
                    {"label": "C", "text": "Option C"},
                    {"label": "D", "text": "Option D"},
                ],
                correct_option="B",
                question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED,
                display_order=qid,
                review_status=GsReviewStatusEnum.REVIEWED,
            ))

        session.commit()
    finally:
        session.close()

    yield engine, TestSession
    engine.dispose()


@pytest.fixture()
def client(seeded_engine):
    engine, TestSession = seeded_engine

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    class _FakeUser:
        id = 1
        email = "test@upsc.local"
        google_uid = "test-student-uid"

    def _override_get_current_user():
        return _FakeUser()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def empty_engine():
    """In-memory SQLite with no practice data — tests empty-state rendering."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name in REQUIRED_TABLES
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = TestSession()
    try:
        # Just a student and a subject
        student = User(
            id=1,
            google_uid="test-student-uid",
            email="test@upsc.local",
            full_name="Test Student",
            role=RoleEnum.STUDENT,
        )
        session.add(student)
        subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
        session.add(subject)
        session.commit()
    finally:
        session.close()

    yield engine, TestSession
    engine.dispose()


@pytest.fixture()
def empty_client(empty_engine):
    engine, TestSession = empty_engine

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    class _FakeUser:
        id = 1
        email = "test@upsc.local"
        google_uid = "test-student-uid"

    def _override_get_current_user():
        return _FakeUser()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# GET /geography/progress
# ---------------------------------------------------------------------------


class TestGetProgress:
    """Tests for GET /api/v1/gs-lms/geography/progress."""

    def test_returns_overall_progress(self, client):
        """Returns total topics, completed topics, and overall percent."""
        resp = client.get("/api/v1/gs-lms/geography/progress")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # 3 leaf topics total, 1 completed (node 30)
        assert data["total_topics"] == 3
        assert data["completed_topics"] == 1
        # 1/3 ≈ 33.33%
        assert abs(data["overall_percent"] - 33.33) < 0.1

    def test_returns_mega_topic_breakdown(self, client):
        """Returns per-mega-topic progress."""
        resp = client.get("/api/v1/gs-lms/geography/progress")
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert len(data["mega_topics"]) == 2

        # Geomorphology: 2 leaf children, 1 completed
        geo = next(m for m in data["mega_topics"] if m["title"] == "Geomorphology")
        assert geo["total_children"] == 2
        assert geo["completed_children"] == 1
        assert abs(geo["completion_percent"] - 50.0) < 0.1

        # Climatology: 1 leaf child, 0 completed
        clim = next(m for m in data["mega_topics"] if m["title"] == "Climatology")
        assert clim["total_children"] == 1
        assert clim["completed_children"] == 0
        assert clim["completion_percent"] == 0.0

    def test_empty_state_no_topics(self, empty_client):
        """With no syllabus nodes, returns 0 topics."""
        resp = empty_client.get("/api/v1/gs-lms/geography/progress")
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["total_topics"] == 0
        assert data["completed_topics"] == 0
        assert data["overall_percent"] == 0.0
        assert data["mega_topics"] == []

    def test_requires_auth(self):
        """Without auth, returns 401 (Property 23 / R10.2)."""
        bare = TestClient(app)
        resp = bare.get("/api/v1/gs-lms/geography/progress")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /geography/gaps
# ---------------------------------------------------------------------------


class TestGetGaps:
    """Tests for GET /api/v1/gs-lms/geography/gaps."""

    def test_returns_gap_profile(self, client):
        """Returns overall accuracy, weak topics, and weak types."""
        resp = client.get("/api/v1/gs-lms/geography/gaps")
        assert resp.status_code == 200
        data = resp.json()["data"]

        # Overall accuracy: 3 correct / 8 total answered = 0.375
        assert abs(data["overall_accuracy"] - 0.375) < 0.01
        assert "weak_topics" in data
        assert "weak_question_types" in data
        assert "recommended_actions" in data
        assert "computed_at" in data

    def test_weak_topics_below_threshold(self, client):
        """Topics with accuracy < 60% appear in weak_topics (Property 14)."""
        resp = client.get("/api/v1/gs-lms/geography/gaps")
        data = resp.json()["data"]

        weak_topics = data["weak_topics"]
        # Node 31 (Plate Tectonics): 1/5 = 20% — should be weak
        # Node 30 (Continental Drift): 2/3 = 66.7% — should NOT be weak
        weak_node_ids = [t["node_id"] for t in weak_topics]
        assert 31 in weak_node_ids
        assert 30 not in weak_node_ids

    def test_weak_topics_ordered_by_severity(self, client):
        """Weak topics ordered by lowest accuracy first (Property 15)."""
        resp = client.get("/api/v1/gs-lms/geography/gaps")
        data = resp.json()["data"]

        weak_topics = data["weak_topics"]
        if len(weak_topics) > 1:
            for i in range(len(weak_topics) - 1):
                assert weak_topics[i]["accuracy"] <= weak_topics[i + 1]["accuracy"]

    def test_weak_question_types(self, client):
        """Question types with accuracy < 60% appear in weak types (R6.3)."""
        resp = client.get("/api/v1/gs-lms/geography/gaps")
        data = resp.json()["data"]

        weak_types = data["weak_question_types"]
        # MAP_BASED: 1 correct / 5 total = 20% — should be weak
        weak_type_names = [t["question_type"] for t in weak_types]
        assert "MAP_BASED" in weak_type_names

    def test_recommended_actions_present(self, client):
        """Gap profile includes recommended actions."""
        resp = client.get("/api/v1/gs-lms/geography/gaps")
        data = resp.json()["data"]

        # With weak areas, there should be recommended actions
        assert len(data["recommended_actions"]) > 0
        action = data["recommended_actions"][0]
        assert "action" in action
        assert "reason" in action

    def test_empty_state_no_attempts(self, empty_client):
        """With no practice data, returns empty weak lists (R6.4)."""
        resp = empty_client.get("/api/v1/gs-lms/geography/gaps")
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["overall_accuracy"] == 0.0
        assert data["weak_topics"] == []
        assert data["weak_question_types"] == []
        assert data["recommended_actions"] == []

    def test_uses_snapshot_when_available(self, seeded_engine):
        """When a gap snapshot exists, uses it instead of recomputing."""
        engine, TestSession = seeded_engine

        # Pre-create a gap snapshot
        session = TestSession()
        try:
            snapshot = GsLmsGapSnapshot(
                student_id=1,
                computed_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
                overall_accuracy=0.45,
                weak_topics=[
                    {"node_id": 31, "title": "Plate Tectonics", "accuracy": 0.2, "attempts": 5}
                ],
                weak_question_types=[
                    {"type": "MAP_BASED", "accuracy": 0.2, "attempts": 5}
                ],
                recommended_actions=[
                    {"action": "Practice more", "target_node_id": 31, "reason": "Low accuracy"}
                ],
            )
            session.add(snapshot)
            session.commit()
        finally:
            session.close()

        def _override_get_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        class _FakeUser:
            id = 1
            email = "test@upsc.local"
            google_uid = "test-student-uid"

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        try:
            test_client = TestClient(app)
            resp = test_client.get("/api/v1/gs-lms/geography/gaps")
            assert resp.status_code == 200
            data = resp.json()["data"]

            # Should use snapshot values
            assert data["overall_accuracy"] == 0.45
            assert "2024-02-01" in data["computed_at"]
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)

    def test_requires_auth(self):
        """Without auth, returns 401 (Property 23 / R10.2)."""
        bare = TestClient(app)
        resp = bare.get("/api/v1/gs-lms/geography/gaps")
        assert resp.status_code == 401
