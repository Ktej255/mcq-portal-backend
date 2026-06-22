"""Tests for GS LMS content delivery endpoints (Task 2.3).

Covers:
- GET /api/v1/gs-lms/geography/topics/{node_id}/sections
  - Progressive disclosure: only first section unlocked initially
  - Content blocks hidden for locked sections
  - AI Discussion gate enforcement
  - Review-gate: only REVIEWED sections visible
  - Topic completion status

- POST /api/v1/gs-lms/geography/topics/{node_id}/sections/{section_id}/complete
  - Marks section complete, unlocks next
  - Enforces AI Discussion gate
  - Enforces sequential order (cannot complete locked section)
  - Idempotent completion
  - All 4 completed → topic_completed = True

Requirements traced: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1
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

from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
    GsLmsNodeTypeEnum,
    GsLmsSectionLabelEnum,
)
from app.core.gs_lms.student_models import (
    GsLmsDiscussionSession,
    GsLmsDiscussionStatusEnum,
    GsLmsStudentSectionProgress,
)

STUDENT_ID = 1


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
    # Create only tables relevant to GS LMS + users
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
def session_factory(test_engine):
    return sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def seed_data(session_factory):
    """Seed a syllabus node with 4 REVIEWED sections and one UNREVIEWED section."""
    db = session_factory()
    try:
        # Create a syllabus node (leaf topic)
        node = GsLmsSyllabusNode(
            id=100,
            subject_id=1,
            title="Geomorphology Basics",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        db.add(node)

        # Create 4 REVIEWED sections in order
        sections_data = [
            (1, GsLmsSectionLabelEnum.BASIC, "Basic Concepts", 1),
            (2, GsLmsSectionLabelEnum.ADVANCED, "Advanced Topics", 2),
            (3, GsLmsSectionLabelEnum.NCERT_LEVEL, "NCERT Level", 3),
            (4, GsLmsSectionLabelEnum.EXAMINER_TRAPS, "Examiner Traps", 4),
        ]
        for sec_id, label, title, order in sections_data:
            section = GsLmsContentSection(
                id=sec_id,
                syllabus_node_id=100,
                section_label=label,
                title=title,
                blocks=[{"type": "text", "content": f"Content for {title}"}],
                display_order=order,
                review_status=GsReviewStatusEnum.REVIEWED,
                authored=True,
            )
            db.add(section)

        # Add one UNREVIEWED section (should be invisible to students)
        unreviewed = GsLmsContentSection(
            id=99,
            syllabus_node_id=100,
            section_label=GsLmsSectionLabelEnum.BASIC,
            title="Draft Section",
            blocks=[{"type": "text", "content": "Draft content"}],
            display_order=99,
            review_status=GsReviewStatusEnum.UNREVIEWED,
            authored=False,
        )
        db.add(unreviewed)

        db.commit()
    finally:
        db.close()

    return {"node_id": 100, "section_ids": [1, 2, 3, 4]}


@pytest.fixture()
def seed_discussion_completed(session_factory, seed_data):
    """Add a COMPLETED discussion session for the student on the seeded node."""
    db = session_factory()
    try:
        session = GsLmsDiscussionSession(
            id=1,
            student_id=STUDENT_ID,
            syllabus_node_id=seed_data["node_id"],
            status=GsLmsDiscussionStatusEnum.COMPLETED,
        )
        db.add(session)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client(session_factory, seed_data):
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


# ---------------------------------------------------------------------------
# GET /geography/topics/{node_id}/sections
# ---------------------------------------------------------------------------


class TestGetTopicSections:
    """Tests for the GET sections endpoint."""

    def test_returns_404_for_missing_node(self, client):
        resp = client.get("/api/v1/gs-lms/geography/topics/9999/sections")
        assert resp.status_code == 404

    def test_discussion_gate_blocks_content(self, client, seed_data):
        """Without a COMPLETED discussion, all sections should be locked (R5.1)."""
        resp = client.get(f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["discussion_gate_passed"] is False
        # All sections locked when gate not passed
        for section in data["sections"]:
            assert section["locked"] is True
            assert section["blocks"] is None

    def test_first_section_unlocked_after_discussion(
        self, client, seed_data, seed_discussion_completed
    ):
        """After discussion completes, first section (BASIC) is unlocked (R2.1)."""
        resp = client.get(f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["discussion_gate_passed"] is True

        sections = data["sections"]
        assert len(sections) == 4  # Only REVIEWED sections (R2.3)

        # First section: unlocked, content visible
        assert sections[0]["locked"] is False
        assert sections[0]["section_label"] == "BASIC"
        assert sections[0]["blocks"] is not None

        # Remaining sections: locked, content hidden
        for s in sections[1:]:
            assert s["locked"] is True
            assert s["blocks"] is None

    def test_only_reviewed_sections_returned(
        self, client, seed_data, seed_discussion_completed
    ):
        """Review-gate: UNREVIEWED sections are not returned (R10.3)."""
        resp = client.get(f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections")
        data = resp.json()["data"]
        # We seeded 4 REVIEWED + 1 UNREVIEWED; only 4 should appear
        assert len(data["sections"]) == 4
        # Verify ordering is correct (display_order 1-4)
        orders = [s["display_order"] for s in data["sections"]]
        assert orders == [1, 2, 3, 4]

    def test_section_labels_in_correct_order(
        self, client, seed_data, seed_discussion_completed
    ):
        """Four sections with correct labels in progressive order (R2.3)."""
        resp = client.get(f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections")
        data = resp.json()["data"]
        labels = [s["section_label"] for s in data["sections"]]
        assert labels == ["BASIC", "ADVANCED", "NCERT_LEVEL", "EXAMINER_TRAPS"]

    def test_topic_not_completed_initially(
        self, client, seed_data, seed_discussion_completed
    ):
        """Topic is NOT complete when no sections are completed."""
        resp = client.get(f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections")
        data = resp.json()["data"]
        assert data["topic_completed"] is False


# ---------------------------------------------------------------------------
# POST /geography/topics/{node_id}/sections/{section_id}/complete
# ---------------------------------------------------------------------------


class TestCompleteSection:
    """Tests for the POST complete section endpoint."""

    def test_complete_blocked_without_discussion(self, client, seed_data):
        """Cannot complete section without discussion gate passed (R5.1)."""
        resp = client.post(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections/1/complete"
        )
        assert resp.status_code == 422
        assert "AI Discussion required" in resp.json()["detail"]

    def test_complete_first_section_succeeds(
        self, client, seed_data, seed_discussion_completed
    ):
        """Completing first section works and unlocks second (R2.2)."""
        resp = client.post(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections/1/complete"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "Section completed" in body["message"]

        data = body["data"]
        sections = data["sections"]

        # Section 1: completed
        assert sections[0]["completed"] is True
        assert sections[0]["locked"] is False

        # Section 2: now unlocked
        assert sections[1]["locked"] is False
        assert sections[1]["blocks"] is not None

        # Sections 3, 4: still locked
        assert sections[2]["locked"] is True
        assert sections[3]["locked"] is True

    def test_cannot_complete_locked_section(
        self, client, seed_data, seed_discussion_completed
    ):
        """Cannot complete section 2 before section 1 (R2.2)."""
        resp = client.post(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections/2/complete"
        )
        assert resp.status_code == 422
        assert "Previous section not completed" in resp.json()["detail"]

    def test_complete_section_404_for_wrong_topic(
        self, client, seed_data, seed_discussion_completed
    ):
        """Section must belong to the given topic."""
        resp = client.post(
            "/api/v1/gs-lms/geography/topics/9999/sections/1/complete"
        )
        assert resp.status_code == 404

    def test_complete_section_404_for_nonexistent_section(
        self, client, seed_data, seed_discussion_completed
    ):
        """Non-existent section returns 404."""
        resp = client.post(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections/9999/complete"
        )
        assert resp.status_code == 404

    def test_idempotent_completion(
        self, client, seed_data, seed_discussion_completed
    ):
        """Completing an already-completed section is idempotent."""
        url = f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/sections/1/complete"
        # First completion
        resp1 = client.post(url)
        assert resp1.status_code == 200
        # Second completion
        resp2 = client.post(url)
        assert resp2.status_code == 200
        assert "already completed" in resp2.json()["message"]

    def test_sequential_completion_unlocks_all(
        self, client, seed_data, seed_discussion_completed
    ):
        """Completing sections 1→2→3→4 sequentially unlocks each next (R2.2)."""
        node_id = seed_data["node_id"]
        section_ids = seed_data["section_ids"]

        for i, sid in enumerate(section_ids):
            resp = client.post(
                f"/api/v1/gs-lms/geography/topics/{node_id}/sections/{sid}/complete"
            )
            assert resp.status_code == 200, f"Failed to complete section {sid}"
            data = resp.json()["data"]

            # Current section should be completed
            assert data["sections"][i]["completed"] is True

            # If not the last, next section should be unlocked
            if i < len(section_ids) - 1:
                assert data["sections"][i + 1]["locked"] is False

    def test_all_four_completed_marks_topic_complete(
        self, client, seed_data, seed_discussion_completed
    ):
        """When all 4 sections are completed, topic_completed = True (R2.5)."""
        node_id = seed_data["node_id"]
        section_ids = seed_data["section_ids"]

        # Complete all 4 sections
        for sid in section_ids:
            resp = client.post(
                f"/api/v1/gs-lms/geography/topics/{node_id}/sections/{sid}/complete"
            )
            assert resp.status_code == 200

        # Final response should show topic_completed
        final_data = resp.json()["data"]
        assert final_data["topic_completed"] is True
        assert "topic content-complete" in resp.json()["message"]

        # Also verify via GET
        get_resp = client.get(f"/api/v1/gs-lms/geography/topics/{node_id}/sections")
        assert get_resp.json()["data"]["topic_completed"] is True


# ---------------------------------------------------------------------------
# Auth gating (R10.2)
# ---------------------------------------------------------------------------


class TestAuthGating:
    """Auth is enforced at the package router level."""

    def test_unauthenticated_request_rejected(self):
        """No auth → 401 (Property 23)."""
        # Remove dependency overrides to test real auth
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

        bare = TestClient(app)
        resp = bare.get("/api/v1/gs-lms/geography/topics/100/sections")
        assert resp.status_code == 401
