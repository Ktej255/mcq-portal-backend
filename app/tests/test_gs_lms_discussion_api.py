"""Tests for GS LMS AI Discussion API endpoints (Task 5.2).

Covers:
- POST /api/v1/gs-lms/geography/discussion/start
  - Creates a new session for the student+topic
  - Returns existing active session if one exists
  - Returns "already completed" response if discussion was previously completed
  - Skips directly to content on subsequent visits (R5.6)

- POST /api/v1/gs-lms/geography/discussion/{session_id}/turn
  - Adds student turn, generates AI response, returns both
  - Auto-completes session when threshold met
  - 404 for missing sessions
  - 422 for turns on completed sessions
  - Ownership: cannot access another student's session

- GET /api/v1/gs-lms/geography/discussion/{session_id}/status
  - Returns full session state with turns
  - Ownership check (404 for wrong student)

Requirements traced: 5.1, 5.2, 5.3, 5.4, 5.6
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.api.dependencies import get_current_user
from app.main import app
from app.models.domain import RoleEnum

# Ensure all models are registered on Base.metadata
from app.core.gs_lms import models as gs_lms_models  # noqa: F401
from app.core.gs_lms import student_models as gs_lms_student_models  # noqa: F401
from app.core.gs import models as gs_models  # noqa: F401
from app.models import domain as domain_models  # noqa: F401
from app.core.gs.models import GsSubject

from app.core.gs_lms.student_models import (
    GsLmsDiscussionSession,
    GsLmsDiscussionStatusEnum,
    GsLmsDiscussionTurn,
)

STUDENT_ID = 1
OTHER_STUDENT_ID = 2
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
    
    # Seed subject
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
        db.add(subject)
        db.commit()
    finally:
        db.close()
        
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(test_engine):
    return sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def client(session_factory):
    """TestClient with auth overridden to a fake student."""

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class _FakeUser:
        id = STUDENT_ID
        email = "student@test.local"
        role = RoleEnum.STUDENT

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    yield TestClient(app)

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture()
def seed_other_students_session(session_factory):
    """Seed a session owned by OTHER_STUDENT_ID that the primary student cannot access."""
    db = session_factory()
    try:
        from datetime import datetime, timezone

        session = GsLmsDiscussionSession(
            id=70,
            student_id=OTHER_STUDENT_ID,
            syllabus_node_id=NODE_ID + 10,
            status=GsLmsDiscussionStatusEnum.IN_PROGRESS,
            started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db.add(session)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def seed_completed_discussion(session_factory):
    """Seed a COMPLETED discussion session for STUDENT_ID on NODE_ID."""
    db = session_factory()
    try:
        from datetime import datetime, timezone

        session = GsLmsDiscussionSession(
            id=50,
            student_id=STUDENT_ID,
            syllabus_node_id=NODE_ID,
            status=GsLmsDiscussionStatusEnum.COMPLETED,
            started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            completed_at=datetime(2024, 1, 1, 0, 10, tzinfo=timezone.utc),
        )
        db.add(session)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def seed_active_session(session_factory):
    """Seed an IN_PROGRESS discussion session for STUDENT_ID on NODE_ID."""
    db = session_factory()
    try:
        from datetime import datetime, timezone

        session = GsLmsDiscussionSession(
            id=60,
            student_id=STUDENT_ID,
            syllabus_node_id=NODE_ID,
            status=GsLmsDiscussionStatusEnum.IN_PROGRESS,
            started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db.add(session)

        # Add one student turn so it's in IN_PROGRESS
        turn = GsLmsDiscussionTurn(
            id=1,
            session_id=60,
            turn_order=1,
            role="student",
            content="I know something about this topic.",
            created_at=datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc),
        )
        db.add(turn)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /geography/discussion/start
# ---------------------------------------------------------------------------


class TestStartDiscussion:
    """Tests for the POST /geography/discussion/start endpoint."""

    def test_creates_new_session(self, client):
        """Creates a new discussion session for a topic (R5.1)."""
        resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "created" in body["message"].lower()

        data = body["data"]
        assert data["session_id"] is not None
        assert data["syllabus_node_id"] == NODE_ID
        assert data["status"] == "INITIATED"
        assert data["turns"] == []

    def test_returns_existing_active_session(self, client, seed_active_session):
        """Returns existing active session instead of creating a new one."""
        resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "existing" in body["message"].lower() or "active" in body["message"].lower()

        data = body["data"]
        assert data["session_id"] == 60
        assert data["status"] == "IN_PROGRESS"
        # Should include the existing turn
        assert len(data["turns"]) == 1

    def test_already_completed_skips_discussion(self, client, seed_completed_discussion):
        """If already completed, returns gate_passed=True (R5.6)."""
        resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "already completed" in body["message"].lower() or "unlocked" in body["message"].lower()

        data = body["data"]
        assert data["already_completed"] is True
        assert data["gate_passed"] is True

    def test_creates_session_for_different_topic(self, client, seed_completed_discussion):
        """Can create a session for a different topic even if one topic is completed."""
        resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID + 1},
        )
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["syllabus_node_id"] == NODE_ID + 1
        assert data["status"] == "INITIATED"


# ---------------------------------------------------------------------------
# POST /geography/discussion/{session_id}/turn
# ---------------------------------------------------------------------------


class TestSubmitTurn:
    """Tests for the POST /geography/discussion/{session_id}/turn endpoint."""

    def test_submits_turn_and_gets_ai_response(self, client):
        """Student sends message, gets AI counter-question (R5.2)."""
        # First start a session
        start_resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Submit a turn
        resp = client.post(
            f"/api/v1/gs-lms/geography/discussion/{session_id}/turn",
            json={"content": "Geomorphology studies landforms and their formation."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        data = body["data"]
        assert data["session_id"] == session_id
        assert data["status"] == "IN_PROGRESS"

        # Student turn
        assert data["student_turn"]["role"] == "student"
        assert "Geomorphology" in data["student_turn"]["content"]
        assert data["student_turn"]["turn_order"] == 1

        # AI turn
        assert data["ai_turn"]["role"] == "ai"
        assert len(data["ai_turn"]["content"]) > 0
        assert data["ai_turn"]["turn_order"] == 2

        # Gate not passed yet (only 2 turns)
        assert data["gate_passed"] is False

    def test_auto_completes_at_threshold(self, client):
        """Session auto-completes when minimum exchange threshold met (R5.3, R5.4)."""
        # Start a session
        start_resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID + 5},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Submit turns until threshold is reached (5 turns minimum)
        # Turn 1 (student) + Turn 2 (AI) = first submit_turn call
        resp1 = client.post(
            f"/api/v1/gs-lms/geography/discussion/{session_id}/turn",
            json={"content": "I know geomorphology is about landforms."},
        )
        assert resp1.json()["data"]["gate_passed"] is False

        # Turn 3 (student) + Turn 4 (AI) = second submit_turn call
        resp2 = client.post(
            f"/api/v1/gs-lms/geography/discussion/{session_id}/turn",
            json={"content": "Tectonic forces and weathering create landforms."},
        )
        assert resp2.json()["data"]["gate_passed"] is False

        # Turn 5 (student) + Turn 6 (AI) = third submit_turn call
        # After student turn 5 is added, threshold is met (5 turns exist)
        # Then AI turn 6 is added, making it 6 total
        resp3 = client.post(
            f"/api/v1/gs-lms/geography/discussion/{session_id}/turn",
            json={"content": "Rivers carve valleys through erosion processes."},
        )
        data3 = resp3.json()["data"]
        # Gate should pass at threshold (5+ turns)
        assert data3["gate_passed"] is True
        assert data3["status"] == "COMPLETED"

    def test_404_for_nonexistent_session(self, client):
        """Returns 404 for a session that doesn't exist."""
        resp = client.post(
            "/api/v1/gs-lms/geography/discussion/9999/turn",
            json={"content": "Some message."},
        )
        assert resp.status_code == 404

    def test_422_for_completed_session(self, client, seed_completed_discussion):
        """Returns 422 when trying to add turns to a completed session."""
        resp = client.post(
            "/api/v1/gs-lms/geography/discussion/50/turn",
            json={"content": "Trying to add to completed session."},
        )
        assert resp.status_code == 422
        assert "completed" in resp.json()["detail"].lower() or "abandoned" in resp.json()["detail"].lower()

    def test_ownership_check_blocks_other_student(self, client, seed_other_students_session):
        """Cannot access another student's session (ownership check)."""
        # Session 70 is owned by OTHER_STUDENT_ID; current client is STUDENT_ID
        resp = client.post(
            "/api/v1/gs-lms/geography/discussion/70/turn",
            json={"content": "I'm not the owner."},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /geography/discussion/{session_id}/status
# ---------------------------------------------------------------------------


class TestGetDiscussionStatus:
    """Tests for the GET /geography/discussion/{session_id}/status endpoint."""

    def test_returns_session_status(self, client):
        """Returns full session state with turns."""
        # Start and interact
        start_resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID + 20},
        )
        session_id = start_resp.json()["data"]["session_id"]

        # Add a turn
        client.post(
            f"/api/v1/gs-lms/geography/discussion/{session_id}/turn",
            json={"content": "My explanation of the topic."},
        )

        # Get status
        resp = client.get(
            f"/api/v1/gs-lms/geography/discussion/{session_id}/status"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        data = body["data"]
        assert data["session_id"] == session_id
        assert data["status"] == "IN_PROGRESS"
        assert len(data["turns"]) == 2  # student + AI
        assert data["turns"][0]["role"] == "student"
        assert data["turns"][1]["role"] == "ai"

    def test_returns_initiated_session_status(self, client):
        """Returns status for a newly created (INITIATED) session."""
        start_resp = client.post(
            "/api/v1/gs-lms/geography/discussion/start",
            json={"syllabus_node_id": NODE_ID + 21},
        )
        session_id = start_resp.json()["data"]["session_id"]

        resp = client.get(
            f"/api/v1/gs-lms/geography/discussion/{session_id}/status"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "INITIATED"
        assert data["turns"] == []

    def test_returns_completed_session_status(self, client, seed_completed_discussion):
        """Returns status for a completed session."""
        resp = client.get("/api/v1/gs-lms/geography/discussion/50/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "COMPLETED"
        assert data["completed_at"] is not None

    def test_404_for_nonexistent_session(self, client):
        """Returns 404 for a session that doesn't exist."""
        resp = client.get("/api/v1/gs-lms/geography/discussion/9999/status")
        assert resp.status_code == 404

    def test_ownership_check_blocks_other_student(self, client, seed_other_students_session):
        """Cannot view another student's session."""
        # Session 70 is owned by OTHER_STUDENT_ID; current client is STUDENT_ID
        resp = client.get("/api/v1/gs-lms/geography/discussion/70/status")
        assert resp.status_code == 404
