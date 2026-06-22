"""Tests for GS LMS onboarding endpoints (Task 9.3).

Covers:
- GET /api/v1/gs-lms/geography/onboarding/status
  - Returns not-completed for new students
  - Returns completed state with bandwidth and first topic for returning students
  - Includes first_topic_title when first_topic_id is set

- POST /api/v1/gs-lms/geography/onboarding/complete
  - Marks onboarding done with bandwidth and first topic
  - Defaults to first REVIEWED leaf node when no first_topic_id provided
  - Validates that specified first_topic_id is a reviewed leaf
  - Idempotent: already-completed onboarding returns success without modification
  - Rejects invalid bandwidth (0 or negative)

Requirements traced: 9.1, 9.2, 9.3, 9.4, 9.5
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
    GsLmsNodeTypeEnum,
)
from app.core.gs_lms.student_models import GsLmsOnboardingStatus

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
def seed_syllabus(session_factory):
    """Seed reviewed leaf nodes for onboarding first-topic resolution."""
    db = session_factory()
    try:
        # Create two reviewed leaf nodes (different display_order)
        node1 = GsLmsSyllabusNode(
            id=10,
            subject_id=1,
            title="Geomorphology Basics",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        node2 = GsLmsSyllabusNode(
            id=20,
            subject_id=1,
            title="Climatology Introduction",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        # One unreviewed leaf (should NOT be selected as default)
        node3 = GsLmsSyllabusNode(
            id=30,
            subject_id=1,
            title="Draft Topic",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=0,  # Lower order but UNREVIEWED
            review_status=GsReviewStatusEnum.UNREVIEWED,
        )
        # One REVIEWED non-leaf (should NOT be selected as default)
        node4 = GsLmsSyllabusNode(
            id=40,
            subject_id=1,
            title="Mega Topic",
            node_type=GsLmsNodeTypeEnum.MEGA_TOPIC,
            weight=1.0,
            display_order=0,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        db.add_all([node1, node2, node3, node4])
        db.commit()
    finally:
        db.close()

    return {"first_leaf_id": 10, "second_leaf_id": 20}


@pytest.fixture()
def seed_onboarding_completed(session_factory, seed_syllabus):
    """Seed a completed onboarding record for the student."""
    db = session_factory()
    try:
        from datetime import datetime, timezone

        record = GsLmsOnboardingStatus(
            id=1,
            student_id=STUDENT_ID,
            completed=True,
            completed_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            bandwidth_selected=3,
            first_topic_id=seed_syllabus["first_leaf_id"],
        )
        db.add(record)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client(session_factory, seed_syllabus):
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
# GET /geography/onboarding/status
# ---------------------------------------------------------------------------


class TestGetOnboardingStatus:
    """Tests for the GET onboarding status endpoint."""

    def test_new_student_not_completed(self, client):
        """New student with no onboarding record → completed=False."""
        resp = client.get("/api/v1/gs-lms/geography/onboarding/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["completed"] is False
        assert data["completed_at"] is None
        assert data["bandwidth_selected"] is None
        assert data["first_topic_id"] is None
        assert data["first_topic_title"] is None

    def test_completed_student_returns_full_status(
        self, client, seed_onboarding_completed
    ):
        """Returning student with completed onboarding → full state returned."""
        resp = client.get("/api/v1/gs-lms/geography/onboarding/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["completed"] is True
        assert data["completed_at"] is not None
        assert data["bandwidth_selected"] == 3
        assert data["first_topic_id"] == 10
        assert data["first_topic_title"] == "Geomorphology Basics"


# ---------------------------------------------------------------------------
# POST /geography/onboarding/complete
# ---------------------------------------------------------------------------


class TestCompleteOnboarding:
    """Tests for the POST onboarding complete endpoint."""

    def test_complete_with_explicit_topic(self, client, seed_syllabus):
        """Complete onboarding with explicit first_topic_id."""
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 5, "first_topic_id": seed_syllabus["second_leaf_id"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "completed" in body["message"].lower()
        data = body["data"]
        assert data["completed"] is True
        assert data["completed_at"] is not None
        assert data["bandwidth_selected"] == 5
        assert data["first_topic_id"] == seed_syllabus["second_leaf_id"]
        assert data["first_topic_title"] == "Climatology Introduction"

    def test_complete_defaults_to_first_reviewed_leaf(self, client, seed_syllabus):
        """When no first_topic_id, defaults to first REVIEWED leaf by display_order."""
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 2},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["completed"] is True
        assert data["first_topic_id"] == seed_syllabus["first_leaf_id"]
        assert data["first_topic_title"] == "Geomorphology Basics"
        assert data["bandwidth_selected"] == 2

    def test_idempotent_already_completed(self, client, seed_onboarding_completed):
        """If already completed, returns success without modification (R9.5)."""
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 10},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "already completed" in body["message"].lower()
        # Original values preserved
        data = body["data"]
        assert data["bandwidth_selected"] == 3  # Original, not 10
        assert data["first_topic_id"] == 10  # Original

    def test_rejects_invalid_first_topic_id(self, client, seed_syllabus):
        """Specifying non-existent or non-reviewed leaf topic → 422."""
        # Non-existent ID
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 3, "first_topic_id": 9999},
        )
        assert resp.status_code == 422

    def test_rejects_unreviewed_topic(self, client, seed_syllabus):
        """Specifying an UNREVIEWED leaf topic → 422."""
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 3, "first_topic_id": 30},  # UNREVIEWED node
        )
        assert resp.status_code == 422

    def test_rejects_non_leaf_topic(self, client, seed_syllabus):
        """Specifying a MEGA_TOPIC node (not leaf) → 422."""
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 3, "first_topic_id": 40},  # MEGA_TOPIC
        )
        assert resp.status_code == 422

    def test_rejects_zero_bandwidth(self, client, seed_syllabus):
        """Bandwidth must be > 0 (Pydantic validation)."""
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 0},
        )
        assert resp.status_code == 422

    def test_rejects_negative_bandwidth(self, client, seed_syllabus):
        """Negative bandwidth is rejected."""
        resp = client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": -5},
        )
        assert resp.status_code == 422

    def test_status_reflects_completion(self, client, seed_syllabus):
        """After completing onboarding, GET status reflects the new state."""
        # Complete onboarding
        client.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 4},
        )

        # Check status
        resp = client.get("/api/v1/gs-lms/geography/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["completed"] is True
        assert data["bandwidth_selected"] == 4
        assert data["first_topic_id"] == seed_syllabus["first_leaf_id"]


# ---------------------------------------------------------------------------
# Auth gating (R10.2)
# ---------------------------------------------------------------------------


class TestOnboardingAuthGating:
    """Auth is enforced at the package router level."""

    def test_unauthenticated_get_rejected(self):
        """No auth on GET → 401 (Property 23)."""
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

        bare = TestClient(app)
        resp = bare.get("/api/v1/gs-lms/geography/onboarding/status")
        assert resp.status_code == 401

    def test_unauthenticated_post_rejected(self):
        """No auth on POST → 401 (Property 23)."""
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

        bare = TestClient(app)
        resp = bare.post(
            "/api/v1/gs-lms/geography/onboarding/complete",
            json={"bandwidth": 3},
        )
        assert resp.status_code == 401
