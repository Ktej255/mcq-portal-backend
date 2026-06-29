"""Endpoint tests for GS LMS Daily Planner API (Task 7.5).

Exercises:
* GET /api/v1/gs-lms/geography/plan/today — current day's plan
* PUT /api/v1/gs-lms/geography/plan/bandwidth — set/update bandwidth
* POST /api/v1/gs-lms/geography/plan/replan — manual replanning

Strategy: isolated in-memory SQLite seeded with a known syllabus and plan
state. App dependencies (get_db, get_current_user) are overridden so
routes run hermetically without Postgres or network.

Validates:
* Today's plan is auto-created from current position (Req 7.1, 7.2)
* Bandwidth must be > 0 (Error handling / Req 7.1)
* Replan records an event and regenerates the plan (Req 7.4, 7.6)
* Projected completion is included (Req 7.5)
* Streak days are returned (Req 7.3 context)
* Auth gating (Property 23 / Req 10.2)
"""

from __future__ import annotations

from datetime import date, timedelta

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
)
from app.core.gs_lms.student_models import (  # noqa: F401
    GsLmsStudentSectionProgress,
    GsLmsDailyPlan,
    GsLmsReplanEvent,
    GsLmsOnboardingStatus,
    GsLmsRevisitSchedule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
    """In-memory SQLite with a test syllabus for planner testing.

    Tree structure (all REVIEWED LEAF_TOPICs for planning):
      - Topic 1: Continental Drift (display_order=1) — COMPLETED
      - Topic 2: Sea Floor Spreading (display_order=2) — NOT completed
      - Topic 3: Plate Boundaries (display_order=3) — NOT completed
      - Topic 4: Volcanism (display_order=4) — NOT completed
      - Topic 5: Earthquakes (display_order=5) — NOT completed

    Student has completed Topic 1 (all 4 sections done). Current position = 1.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create tables.
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name
        in (
            "users",
            "gs_subjects",
            "gs_day_lessons",
            "gs_lms_syllabus_nodes",
            "gs_lms_content_sections",
            "gs_lms_student_section_progress",
            "gs_lms_daily_plans",
            "gs_lms_replan_events",
            "gs_lms_onboarding",
            "gs_lms_revisit_schedule",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = TestSession()
    try:
        # Create test user.
        user = User(
            id=1,
            google_uid="test-planner-uid",
            email="planner@upsc.local",
            full_name="Test Planner Student",
            role=RoleEnum.STUDENT,
        )
        session.add(user)

        # Create GS Geography subject.
        subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
        session.add(subject)
        session.flush()

        # Create 5 leaf topics (directly under subject, no parent for simplicity).
        topics = [
            ("Continental Drift", 1),
            ("Sea Floor Spreading", 2),
            ("Plate Boundaries", 3),
            ("Volcanism", 4),
            ("Earthquakes", 5),
        ]
        for i, (title, order) in enumerate(topics, start=1):
            node = GsLmsSyllabusNode(
                id=i,
                subject_id=1,
                parent_id=None,
                title=title,
                node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                weight=1.0,
                display_order=order,
                review_status=GsReviewStatusEnum.REVIEWED,
            )
            session.add(node)

        session.flush()

        # Create 4 content sections per topic.
        section_id = 100
        for topic_id in range(1, 6):
            for j, label in enumerate(
                [
                    GsLmsSectionLabelEnum.BASIC,
                    GsLmsSectionLabelEnum.ADVANCED,
                    GsLmsSectionLabelEnum.NCERT_LEVEL,
                    GsLmsSectionLabelEnum.EXAMINER_TRAPS,
                ],
                start=1,
            ):
                section = GsLmsContentSection(
                    id=section_id,
                    syllabus_node_id=topic_id,
                    section_label=label,
                    title=f"{label.value} section",
                    display_order=j,
                    review_status=GsReviewStatusEnum.REVIEWED,
                    authored=True,
                )
                session.add(section)
                section_id += 1

        session.flush()

        # Mark Topic 1 as completed (all 4 sections).
        for sec_id in [100, 101, 102, 103]:
            progress = GsLmsStudentSectionProgress(
                student_id=1,
                section_id=sec_id,
                syllabus_node_id=1,
                completed=True,
            )
            session.add(progress)

        # Create an onboarding record with bandwidth=2.
        onboarding = GsLmsOnboardingStatus(
            student_id=1,
            completed=True,
            bandwidth_selected=2,
        )
        session.add(onboarding)

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
        email = "planner@upsc.local"
        google_uid = "test-planner-uid"

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
# GET /geography/plan/today
# ---------------------------------------------------------------------------

def test_get_today_plan_creates_plan_if_none(client):
    """GET /plan/today creates a plan if none exists for today (Req 7.1, 7.2)."""
    resp = client.get("/api/v1/gs-lms/geography/plan/today")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["plan_date"] == date.today().isoformat()
    # Bandwidth should be from onboarding (2).
    assert data["bandwidth"] == 2
    # Should have 2 items (bandwidth=2, remaining=4 starting at position 1).
    assert len(data["planned_items"]) == 2
    # Items should start from position 1 (Sea Floor Spreading).
    assert data["planned_items"][0]["node_id"] == 2
    assert data["planned_items"][1]["node_id"] == 3


def test_get_today_plan_returns_existing_plan(client):
    """Calling GET /plan/today twice returns the same plan."""
    resp1 = client.get("/api/v1/gs-lms/geography/plan/today")
    assert resp1.status_code == 200
    data1 = resp1.json()["data"]

    resp2 = client.get("/api/v1/gs-lms/geography/plan/today")
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]

    # Same plan returned.
    assert data1["plan_date"] == data2["plan_date"]
    assert data1["bandwidth"] == data2["bandwidth"]
    assert len(data1["planned_items"]) == len(data2["planned_items"])


def test_get_today_plan_includes_projected_completion(client):
    """Plan response includes projected_completion_date (Req 7.5)."""
    resp = client.get("/api/v1/gs-lms/geography/plan/today")
    data = resp.json()["data"]

    # With 4 remaining items and bandwidth=2, projected = today + ceil(4/2) = today + 2 days.
    expected_date = (date.today() + timedelta(days=2)).isoformat()
    assert data["projected_completion_date"] == expected_date


def test_get_today_plan_includes_streak_and_completion_count(client):
    """Plan response includes streak_days and completed_count."""
    resp = client.get("/api/v1/gs-lms/geography/plan/today")
    data = resp.json()["data"]

    assert "streak_days" in data
    assert data["streak_days"] >= 0
    assert "completed_count" in data
    assert data["completed_count"] == 0  # No items completed yet.


# ---------------------------------------------------------------------------
# PUT /geography/plan/bandwidth
# ---------------------------------------------------------------------------

def test_update_bandwidth_success(client):
    """PUT /plan/bandwidth updates bandwidth and regenerates plan (Req 7.1)."""
    resp = client.put(
        "/api/v1/gs-lms/geography/plan/bandwidth",
        json={"bandwidth": 3},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["bandwidth"] == 3
    # With bandwidth=3 and 4 remaining items, should have 3 planned items.
    assert len(data["planned_items"]) == 3


def test_update_bandwidth_invalid_zero(client):
    """PUT /plan/bandwidth rejects bandwidth=0 (Error handling)."""
    resp = client.put(
        "/api/v1/gs-lms/geography/plan/bandwidth",
        json={"bandwidth": 0},
    )
    assert resp.status_code == 422


def test_update_bandwidth_invalid_negative(client):
    """PUT /plan/bandwidth rejects negative bandwidth (Error handling)."""
    resp = client.put(
        "/api/v1/gs-lms/geography/plan/bandwidth",
        json={"bandwidth": -1},
    )
    assert resp.status_code == 422


def test_update_bandwidth_updates_projected_completion(client):
    """Changing bandwidth updates projected completion date (Req 7.5)."""
    # First create a plan with default bandwidth.
    client.get("/api/v1/gs-lms/geography/plan/today")

    # Then update bandwidth to 4.
    resp = client.put(
        "/api/v1/gs-lms/geography/plan/bandwidth",
        json={"bandwidth": 4},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]

    # With 4 remaining and bandwidth=4: projected = today + ceil(4/4) = today + 1.
    expected_date = (date.today() + timedelta(days=1)).isoformat()
    assert data["projected_completion_date"] == expected_date


def test_update_bandwidth_creates_plan_if_none(client):
    """PUT /plan/bandwidth creates today's plan if it doesn't exist yet."""
    resp = client.put(
        "/api/v1/gs-lms/geography/plan/bandwidth",
        json={"bandwidth": 2},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["plan_date"] == date.today().isoformat()
    assert data["bandwidth"] == 2


# ---------------------------------------------------------------------------
# POST /geography/plan/replan
# ---------------------------------------------------------------------------

def test_replan_success(client):
    """POST /plan/replan records event and returns replan data (Req 7.4, 7.6)."""
    # First create a plan.
    client.get("/api/v1/gs-lms/geography/plan/today")

    resp = client.post("/api/v1/gs-lms/geography/plan/replan")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["reason"] == "manual"
    assert data["old_bandwidth"] == 2
    assert data["new_bandwidth"] == 2  # Manual replan doesn't change bandwidth.
    assert "triggered_at" in data


def test_replan_creates_plan_if_none(client):
    """POST /plan/replan works even if no plan exists for today."""
    resp = client.post("/api/v1/gs-lms/geography/plan/replan")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["reason"] == "manual"


def test_replan_includes_projected_dates(client):
    """Replan response includes old and new projected dates (Req 7.5)."""
    client.get("/api/v1/gs-lms/geography/plan/today")

    resp = client.post("/api/v1/gs-lms/geography/plan/replan")
    data = resp.json()["data"]

    # Both should be the same since bandwidth doesn't change on manual replan.
    assert data["old_projected_date"] is not None
    assert data["new_projected_date"] is not None
    assert data["old_projected_date"] == data["new_projected_date"]


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------

def test_plan_today_requires_auth():
    """GET /plan/today without auth returns 401 (Property 23 / R10.2)."""
    bare = TestClient(app)
    resp = bare.get("/api/v1/gs-lms/geography/plan/today")
    assert resp.status_code == 401


def test_bandwidth_requires_auth():
    """PUT /plan/bandwidth without auth returns 401."""
    bare = TestClient(app)
    resp = bare.put(
        "/api/v1/gs-lms/geography/plan/bandwidth",
        json={"bandwidth": 3},
    )
    assert resp.status_code == 401


def test_replan_requires_auth():
    """POST /plan/replan without auth returns 401."""
    bare = TestClient(app)
    resp = bare.post("/api/v1/gs-lms/geography/plan/replan")
    assert resp.status_code == 401
