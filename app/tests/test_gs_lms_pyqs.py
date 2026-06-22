"""Endpoint tests for GS LMS PYQ API (Task 4.1).

Exercises:
* GET /api/v1/gs-lms/geography/topics/{node_id}/pyqs — PYQs for a topic
* POST /api/v1/gs-lms/geography/pyqs/{id}/reveal — Reveal answer

Strategy: isolated in-memory SQLite seeded with known PYQ data.
App dependencies (get_db, get_current_user) are overridden so routes
run hermetically without Postgres or network.

Validates:
* Only REVIEWED PYQs are visible (Property 19 / Requirement 10.3)
* Answer/explanation hidden until revealed (Property 8 / R3.2, R3.3, R3.4)
* Filtering by exam_type works (R3.1)
* Reveal endpoint persists reveal event and returns full PYQ
* Empty-state: no PYQs message (R3.6)
* Under-review message when only unreviewed PYQs exist (R3.7)
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
from app.models.domain import User, RoleEnum

# Import models to register tables on Base.metadata.
from app.core.gs.models import GsSubject, GsReviewStatusEnum  # noqa: F401
from app.core.gs_lms.models import (  # noqa: F401
    GsLmsSyllabusNode,
    GsLmsNodeTypeEnum,
    GsLmsPyq,
    GsLmsExamTypeEnum,
    GsLmsQuestionTypeEnum,
)
from app.core.gs_lms.student_models import GsLmsPyqReveal  # noqa: F401


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
    """In-memory SQLite with test PYQ data for GS Geography.

    Setup:
    - 1 subject (Geography)
    - 1 REVIEWED leaf node (Continental Drift, id=30)
    - 1 REVIEWED leaf node with no PYQs (Atmosphere, id=40)
    - 1 REVIEWED leaf node with only UNREVIEWED PYQs (Sea Floor, id=31)
    - PYQs for Continental Drift:
        - id=1: PRELIMS 2022, REVIEWED
        - id=2: PRELIMS 2021, REVIEWED
        - id=3: MAINS 2020, REVIEWED
        - id=4: PRELIMS 2019, UNREVIEWED (should be hidden)
    - PYQs for Sea Floor Spreading:
        - id=5: PRELIMS 2023, UNREVIEWED (only unreviewed exist)
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create only the tables we need for this test.
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name
        in (
            "users",
            "gs_subjects",
            "gs_day_lessons",
            "gs_lms_syllabus_nodes",
            "gs_lms_pyqs",
            "gs_lms_pyq_reveals",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = TestSession()
    try:
        # Create test user
        user = User(
            id=1,
            google_uid="test-student-uid",
            email="test@upsc.local",
            full_name="Test Student",
            role=RoleEnum.STUDENT,
        )
        session.add(user)

        # Create GS Geography subject
        subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
        session.add(subject)
        session.flush()

        # Syllabus nodes
        continental_drift = GsLmsSyllabusNode(
            id=30,
            subject_id=1,
            parent_id=None,
            title="Continental Drift",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=0.25,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(continental_drift)

        sea_floor = GsLmsSyllabusNode(
            id=31,
            subject_id=1,
            parent_id=None,
            title="Sea Floor Spreading",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=0.25,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(sea_floor)

        atmosphere = GsLmsSyllabusNode(
            id=40,
            subject_id=1,
            parent_id=None,
            title="Atmosphere",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=3,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(atmosphere)
        session.flush()

        # PYQs for Continental Drift (id=30)
        pyq1 = GsLmsPyq(
            id=1,
            subject_id=1,
            syllabus_node_id=30,
            exam_type=GsLmsExamTypeEnum.PRELIMS,
            year=2022,
            question_text="Which of the following about continental drift is correct?",
            answer_text="Option B",
            explanation="Wegener proposed the theory in 1912.",
            marks=None,
            question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(pyq1)

        pyq2 = GsLmsPyq(
            id=2,
            subject_id=1,
            syllabus_node_id=30,
            exam_type=GsLmsExamTypeEnum.PRELIMS,
            year=2021,
            question_text="Pangaea broke apart during which period?",
            answer_text="Option A",
            explanation="During the Jurassic period.",
            marks=None,
            question_type=GsLmsQuestionTypeEnum.FACTUAL,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(pyq2)

        pyq3 = GsLmsPyq(
            id=3,
            subject_id=1,
            syllabus_node_id=30,
            exam_type=GsLmsExamTypeEnum.MAINS,
            year=2020,
            question_text="Discuss the evidences supporting continental drift theory.",
            answer_text="Model answer discussing geological, biological, and climatological evidences.",
            explanation="Key points: jigsaw fit, fossil distribution, rock matching.",
            marks=15,
            question_type=None,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(pyq3)

        # UNREVIEWED PYQ for Continental Drift — should NOT be visible
        pyq4 = GsLmsPyq(
            id=4,
            subject_id=1,
            syllabus_node_id=30,
            exam_type=GsLmsExamTypeEnum.PRELIMS,
            year=2019,
            question_text="This question is under review.",
            answer_text="Option C",
            explanation="Draft explanation.",
            marks=None,
            question_type=GsLmsQuestionTypeEnum.FACTUAL,
            review_status=GsReviewStatusEnum.UNREVIEWED,
        )
        session.add(pyq4)

        # UNREVIEWED PYQ for Sea Floor Spreading (only unreviewed exist)
        pyq5 = GsLmsPyq(
            id=5,
            subject_id=1,
            syllabus_node_id=31,
            exam_type=GsLmsExamTypeEnum.PRELIMS,
            year=2023,
            question_text="Sea floor question under review.",
            answer_text="Option A",
            explanation="Draft.",
            marks=None,
            question_type=GsLmsQuestionTypeEnum.FACTUAL,
            review_status=GsReviewStatusEnum.UNREVIEWED,
        )
        session.add(pyq5)

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


# ---------------------------------------------------------------------------
# GET /geography/topics/{node_id}/pyqs — List PYQs
# ---------------------------------------------------------------------------

def test_get_pyqs_returns_reviewed_only(client):
    """Only REVIEWED PYQs are returned (Property 19 / R10.3)."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Should have 3 REVIEWED PYQs (ids 1, 2, 3). UNREVIEWED id=4 excluded.
    assert data["total"] == 3
    pyq_ids = [p["id"] for p in data["pyqs"]]
    assert 4 not in pyq_ids


def test_get_pyqs_answers_hidden_by_default(client):
    """Answer and explanation are None until revealed (Property 8 / R3.2, R3.4)."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs")
    data = resp.json()["data"]

    for pyq in data["pyqs"]:
        assert pyq["answer_text"] is None
        assert pyq["explanation"] is None
        assert pyq["revealed"] is False


def test_get_pyqs_returns_visible_fields(client):
    """Unrevealed PYQs still include year, question_text, exam_type, marks, question_type."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs")
    data = resp.json()["data"]

    # Find the MAINS PYQ (id=3)
    mains_pyq = next(p for p in data["pyqs"] if p["id"] == 3)
    assert mains_pyq["year"] == 2020
    assert mains_pyq["exam_type"] == "MAINS"
    assert mains_pyq["marks"] == 15
    assert mains_pyq["question_text"] is not None
    assert len(mains_pyq["question_text"]) > 0


def test_get_pyqs_filter_by_prelims(client):
    """Filter by exam_type=PRELIMS returns only Prelims PYQs (R3.1)."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs?exam_type=PRELIMS")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["exam_type_filter"] == "PRELIMS"
    assert data["total"] == 2
    for pyq in data["pyqs"]:
        assert pyq["exam_type"] == "PRELIMS"


def test_get_pyqs_filter_by_mains(client):
    """Filter by exam_type=MAINS returns only Mains PYQs (R3.1)."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs?exam_type=MAINS")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["exam_type_filter"] == "MAINS"
    assert data["total"] == 1
    assert data["pyqs"][0]["exam_type"] == "MAINS"


def test_get_pyqs_filter_case_insensitive(client):
    """exam_type filter works case-insensitively."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs?exam_type=prelims")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 2


def test_get_pyqs_invalid_exam_type(client):
    """Invalid exam_type returns 422."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs?exam_type=INVALID")
    assert resp.status_code == 422


def test_get_pyqs_node_not_found(client):
    """404 for non-existent topic node."""
    resp = client.get("/api/v1/gs-lms/geography/topics/9999/pyqs")
    assert resp.status_code == 404


def test_get_pyqs_empty_state_no_pyqs(client):
    """Empty state message when no PYQs exist at all for a topic (R3.6)."""
    resp = client.get("/api/v1/gs-lms/geography/topics/40/pyqs")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]

    assert data["total"] == 0
    assert data["pyqs"] == []
    assert "no pyqs available" in body["message"].lower()


def test_get_pyqs_under_review_message(client):
    """Under-review message when only unreviewed PYQs exist (R3.7)."""
    resp = client.get("/api/v1/gs-lms/geography/topics/31/pyqs")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]

    assert data["total"] == 0
    assert data["pyqs"] == []
    assert "under review" in body["message"].lower()


def test_get_pyqs_ordered_by_year_desc(client):
    """PYQs are returned ordered by year descending."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs")
    data = resp.json()["data"]

    years = [p["year"] for p in data["pyqs"]]
    assert years == sorted(years, reverse=True)


def test_get_pyqs_node_metadata(client):
    """Response includes node_id and title."""
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs")
    data = resp.json()["data"]

    assert data["node_id"] == 30
    assert data["title"] == "Continental Drift"


# ---------------------------------------------------------------------------
# POST /geography/pyqs/{id}/reveal — Reveal PYQ answer
# ---------------------------------------------------------------------------

def test_reveal_pyq_returns_answer(client):
    """Reveal endpoint returns the PYQ with answer and explanation (R3.2, R3.3)."""
    resp = client.post("/api/v1/gs-lms/geography/pyqs/1/reveal")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["id"] == 1
    assert data["revealed"] is True
    assert data["answer_text"] == "Option B"
    assert data["explanation"] == "Wegener proposed the theory in 1912."


def test_reveal_pyq_persists_reveal(client):
    """After revealing, GET returns the PYQ as revealed."""
    # Reveal PYQ 1
    client.post("/api/v1/gs-lms/geography/pyqs/1/reveal")

    # GET should now show PYQ 1 as revealed
    resp = client.get("/api/v1/gs-lms/geography/topics/30/pyqs")
    data = resp.json()["data"]

    pyq1 = next(p for p in data["pyqs"] if p["id"] == 1)
    assert pyq1["revealed"] is True
    assert pyq1["answer_text"] == "Option B"
    assert pyq1["explanation"] is not None

    # Other PYQs remain unrevealed
    pyq2 = next(p for p in data["pyqs"] if p["id"] == 2)
    assert pyq2["revealed"] is False
    assert pyq2["answer_text"] is None


def test_reveal_pyq_idempotent(client):
    """Revealing same PYQ twice succeeds without error."""
    resp1 = client.post("/api/v1/gs-lms/geography/pyqs/1/reveal")
    assert resp1.status_code == 200

    resp2 = client.post("/api/v1/gs-lms/geography/pyqs/1/reveal")
    assert resp2.status_code == 200
    assert resp2.json()["data"]["revealed"] is True


def test_reveal_pyq_not_found(client):
    """404 when PYQ doesn't exist."""
    resp = client.post("/api/v1/gs-lms/geography/pyqs/9999/reveal")
    assert resp.status_code == 404


def test_reveal_unreviewed_pyq_not_found(client):
    """404 when trying to reveal an UNREVIEWED PYQ (Property 19)."""
    resp = client.post("/api/v1/gs-lms/geography/pyqs/4/reveal")
    assert resp.status_code == 404


def test_reveal_mains_pyq_shows_marks(client):
    """Revealing a Mains PYQ includes marks in the response."""
    resp = client.post("/api/v1/gs-lms/geography/pyqs/3/reveal")
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["marks"] == 15
    assert data["exam_type"] == "MAINS"
    assert data["answer_text"] is not None


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------

def test_pyqs_require_auth():
    """Without auth, returns 401 (Property 23 / R10.2)."""
    bare = TestClient(app)
    resp = bare.get("/api/v1/gs-lms/geography/topics/30/pyqs")
    assert resp.status_code == 401


def test_reveal_requires_auth():
    """Without auth, reveal returns 401 (Property 23 / R10.2)."""
    bare = TestClient(app)
    resp = bare.post("/api/v1/gs-lms/geography/pyqs/1/reveal")
    assert resp.status_code == 401
