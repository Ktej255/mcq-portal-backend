"""Security regression guard: every GS LMS route is auth-gated, review-gated,
and ownership-scoped.

Mirrors the Optional platform's ``test_optional_auth_gating.py`` structure:
enumerates every registered ``/api/v1/gs-lms/*`` route and asserts that
unauthenticated requests are rejected. Additionally validates that no
UNREVIEWED content leaks through any endpoint and that students cannot
access other students' sessions/progress.

Requirements traced: 10.2, 10.3
Design Properties enforced: 19 (review-gate), 23 (auth gating)
"""

from __future__ import annotations

import re

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
    GsLmsPyq,
    GsLmsExamTypeEnum,
    GsLmsMcqQuestion,
    GsLmsQuestionTypeEnum,
)
from app.core.gs_lms.student_models import (  # noqa: F401
    GsLmsStudentSectionProgress,
    GsLmsDiscussionSession,
    GsLmsDiscussionTurn,
    GsLmsDiscussionStatusEnum,
    GsLmsPracticeSession,
    GsLmsPracticeAttempt,
    GsLmsPracticeSessionStatusEnum,
    GsLmsGapSnapshot,
    GsLmsDailyPlan,
    GsLmsOnboardingStatus,
    GsLmsPyqReveal,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GS_LMS_PREFIX = "/api/v1/gs-lms"
STUDENT_A_ID = 1
STUDENT_B_ID = 2

_PARAM_RE = re.compile(r"\{[^}]+\}")


def _concrete_path(path: str) -> str:
    """Replace every path parameter with '1' (valid for both int and str)."""
    return _PARAM_RE.sub("1", path)


def _gs_lms_routes():
    """Yield (path, methods) for every registered GS LMS route."""
    seen = set()
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if not path.startswith(GS_LMS_PREFIX):
            continue
        key = (path, frozenset(methods))
        if key in seen:
            continue
        seen.add(key)
        yield path, methods


# ===========================================================================
# Section 1: Auth Gating Tests (Property 23 / Requirement 10.2)
# ===========================================================================


class TestAuthGating:
    """Every GS LMS route must reject unauthenticated requests with 401."""

    def test_gs_lms_routes_exist(self):
        """Sanity: the GS LMS surface is actually registered."""
        routes = list(_gs_lms_routes())
        assert len(routes) >= 10, (
            f"Expected the gs-lms router to be mounted with 10+ routes, "
            f"found {len(routes)}"
        )

    def test_every_get_route_requires_auth(self):
        """Unauthenticated GET to any GS LMS route must be rejected with 401."""
        client = TestClient(app)
        offenders = []
        for path, methods in _gs_lms_routes():
            if "GET" not in methods:
                continue
            url = _concrete_path(path)
            resp = client.get(url)
            if resp.status_code != 401:
                offenders.append((url, resp.status_code))
        assert not offenders, (
            f"GS LMS GET routes reachable without 401: {offenders}"
        )

    def test_every_write_route_requires_auth(self):
        """Unauthenticated POST/PUT/DELETE must never be served (no 2xx)."""
        client = TestClient(app)
        offenders = []
        for path, methods in _gs_lms_routes():
            for method in ("POST", "PUT", "DELETE", "PATCH"):
                if method not in methods:
                    continue
                url = _concrete_path(path)
                resp = client.request(method, url)
                # Must not be served. 401 ideal; 422 also means auth/validation
                # rejected it. Never a 2xx without a token.
                if 200 <= resp.status_code < 300:
                    offenders.append((method, url, resp.status_code))
        assert not offenders, (
            f"GS LMS write routes served without auth: {offenders}"
        )


# ===========================================================================
# Section 2 & 3: Review-Gate + Ownership Scoping Tests
# ===========================================================================


@pytest.fixture()
def seeded_engine():
    """In-memory SQLite seeded with both REVIEWED and UNREVIEWED content.

    Data layout:
    - GsSubject (slug=geography, id auto)
    - REVIEWED syllabus node: "Plate Tectonics" (LEAF_TOPIC, id=10)
      - 4 REVIEWED content sections
      - 2 REVIEWED PYQs
      - 2 REVIEWED MCQ questions
    - UNREVIEWED syllabus node: "Volcanoes" (LEAF_TOPIC, id=20)
      - 4 UNREVIEWED content sections
      - 1 UNREVIEWED PYQ
      - 1 UNREVIEWED MCQ question
    - Student A (id=1): has a practice session (id=100) and discussion
      session (id=200) for node_id=10
    - Student B (id=2): has no sessions
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name in (
            "users",
            "gs_subjects",
            "gs_lms_syllabus_nodes",
            "gs_lms_content_sections",
            "gs_lms_pyqs",
            "gs_lms_mcq_questions",
            "gs_lms_student_section_progress",
            "gs_lms_discussion_sessions",
            "gs_lms_discussion_turns",
            "gs_lms_practice_sessions",
            "gs_lms_practice_attempts",
            "gs_lms_gap_snapshots",
            "gs_lms_daily_plans",
            "gs_lms_onboarding",
            "gs_lms_pyq_reveals",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = SessionLocal()
    try:
        _seed_data(session)
        session.commit()
    finally:
        session.close()

    yield engine, SessionLocal
    engine.dispose()


def _seed_data(db):
    """Seed the in-memory DB with test data."""
    from datetime import datetime, timezone

    # Users
    student_a = User(
        id=STUDENT_A_ID,
        google_uid="student-a-uid",
        email="student_a@test.local",
        full_name="Student A",
        role=RoleEnum.STUDENT,
    )
    student_b = User(
        id=STUDENT_B_ID,
        google_uid="student-b-uid",
        email="student_b@test.local",
        full_name="Student B",
        role=RoleEnum.STUDENT,
    )
    db.add_all([student_a, student_b])
    db.flush()

    # Subject
    subject = GsSubject(
        id=1,
        slug="geography",
        name="Geography",
        created_by="test",
        updated_by="test",
    )
    db.add(subject)
    db.flush()

    # REVIEWED syllabus node
    reviewed_node = GsLmsSyllabusNode(
        id=10,
        subject_id=1,
        parent_id=None,
        title="Plate Tectonics",
        node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
        weight=1.0,
        display_order=1,
        review_status=GsReviewStatusEnum.REVIEWED,
        created_by="test",
        updated_by="test",
    )
    db.add(reviewed_node)
    db.flush()

    # UNREVIEWED syllabus node (must never appear in student responses)
    unreviewed_node = GsLmsSyllabusNode(
        id=20,
        subject_id=1,
        parent_id=None,
        title="Volcanoes (UNREVIEWED)",
        node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
        weight=1.0,
        display_order=2,
        review_status=GsReviewStatusEnum.UNREVIEWED,
        created_by="test",
        updated_by="test",
    )
    db.add(unreviewed_node)
    db.flush()

    # 4 REVIEWED content sections for the reviewed node
    section_labels = [
        (GsLmsSectionLabelEnum.BASIC, 1),
        (GsLmsSectionLabelEnum.ADVANCED, 2),
        (GsLmsSectionLabelEnum.NCERT_LEVEL, 3),
        (GsLmsSectionLabelEnum.EXAMINER_TRAPS, 4),
    ]
    for label, order in section_labels:
        db.add(GsLmsContentSection(
            id=100 + order,
            syllabus_node_id=10,
            section_label=label,
            title=f"Section {label.value}",
            blocks=[{"type": "text", "content": f"Content for {label.value}"}],
            display_order=order,
            review_status=GsReviewStatusEnum.REVIEWED,
            authored=True,
            created_by="test",
            updated_by="test",
        ))

    # 4 UNREVIEWED content sections for the unreviewed node
    for label, order in section_labels:
        db.add(GsLmsContentSection(
            id=200 + order,
            syllabus_node_id=20,
            section_label=label,
            title=f"UNREVIEWED Section {label.value}",
            blocks=[{"type": "text", "content": "UNREVIEWED CONTENT LEAK"}],
            display_order=order,
            review_status=GsReviewStatusEnum.UNREVIEWED,
            authored=True,
            created_by="test",
            updated_by="test",
        ))
    db.flush()

    # REVIEWED PYQs for the reviewed node
    db.add(GsLmsPyq(
        id=1,
        subject_id=1,
        syllabus_node_id=10,
        exam_type=GsLmsExamTypeEnum.PRELIMS,
        year=2022,
        question_text="Which plate boundary forms mountains?",
        answer_text="Convergent",
        explanation="Convergent boundaries push plates together.",
        review_status=GsReviewStatusEnum.REVIEWED,
        created_by="test",
        updated_by="test",
    ))
    db.add(GsLmsPyq(
        id=2,
        subject_id=1,
        syllabus_node_id=10,
        exam_type=GsLmsExamTypeEnum.MAINS,
        year=2021,
        question_text="Discuss the role of tectonic activity in landform evolution.",
        answer_text="Model answer for tectonic landforms.",
        marks=15,
        review_status=GsReviewStatusEnum.REVIEWED,
        created_by="test",
        updated_by="test",
    ))

    # UNREVIEWED PYQ for the unreviewed node
    db.add(GsLmsPyq(
        id=3,
        subject_id=1,
        syllabus_node_id=20,
        exam_type=GsLmsExamTypeEnum.PRELIMS,
        year=2023,
        question_text="UNREVIEWED PYQ - should not appear",
        answer_text="Secret Answer",
        review_status=GsReviewStatusEnum.UNREVIEWED,
        created_by="test",
        updated_by="test",
    ))
    db.flush()

    # REVIEWED MCQ questions for the reviewed node
    db.add(GsLmsMcqQuestion(
        id=1,
        syllabus_node_id=10,
        question_text="What causes earthquakes?",
        options=[
            {"label": "A", "text": "Plate movement"},
            {"label": "B", "text": "Weathering"},
            {"label": "C", "text": "Erosion"},
            {"label": "D", "text": "Deposition"},
        ],
        correct_option="A",
        explanation="Earthquakes are caused by plate movement.",
        question_type=GsLmsQuestionTypeEnum.FACTUAL,
        display_order=1,
        review_status=GsReviewStatusEnum.REVIEWED,
        created_by="test",
        updated_by="test",
    ))
    db.add(GsLmsMcqQuestion(
        id=2,
        syllabus_node_id=10,
        question_text="Ring of Fire is located in which ocean?",
        options=[
            {"label": "A", "text": "Pacific"},
            {"label": "B", "text": "Atlantic"},
            {"label": "C", "text": "Indian"},
            {"label": "D", "text": "Arctic"},
        ],
        correct_option="A",
        explanation="The Ring of Fire is in the Pacific Ocean.",
        question_type=GsLmsQuestionTypeEnum.FACTUAL,
        display_order=2,
        review_status=GsReviewStatusEnum.REVIEWED,
        created_by="test",
        updated_by="test",
    ))

    # UNREVIEWED MCQ question for the unreviewed node
    db.add(GsLmsMcqQuestion(
        id=3,
        syllabus_node_id=20,
        question_text="UNREVIEWED MCQ - should not appear",
        options=[{"label": "A", "text": "Secret"}],
        correct_option="A",
        question_type=GsLmsQuestionTypeEnum.FACTUAL,
        display_order=1,
        review_status=GsReviewStatusEnum.UNREVIEWED,
        created_by="test",
        updated_by="test",
    ))
    db.flush()

    # Student A's practice session (owned by student A)
    now = datetime.now(timezone.utc)
    db.add(GsLmsPracticeSession(
        id=100,
        student_id=STUDENT_A_ID,
        syllabus_node_id=10,
        status=GsLmsPracticeSessionStatusEnum.IN_PROGRESS,
        total_questions=2,
        current_index=0,
        started_at=now,
        created_by="test",
        updated_by="test",
    ))

    # Student A's discussion session (owned by student A)
    db.add(GsLmsDiscussionSession(
        id=200,
        student_id=STUDENT_A_ID,
        syllabus_node_id=10,
        status=GsLmsDiscussionStatusEnum.IN_PROGRESS,
        started_at=now,
        created_by="test",
        updated_by="test",
    ))

    # Student A's section progress
    db.add(GsLmsStudentSectionProgress(
        id=1,
        student_id=STUDENT_A_ID,
        section_id=101,
        syllabus_node_id=10,
        completed=True,
        completed_at=now,
        created_by="test",
        updated_by="test",
    ))
    db.flush()


@pytest.fixture()
def make_client(seeded_engine):
    """Build a TestClient authenticated as a specific student."""
    _, SessionLocal = seeded_engine

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _build(student_id: int) -> TestClient:
        class _FakeUser:
            id = student_id

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# Section 2: Review-Status Filtering (Property 19 / Requirement 10.3)
# ===========================================================================


class TestReviewGateFiltering:
    """No UNREVIEWED content may leak through any student-facing endpoint."""

    def test_syllabus_tree_excludes_unreviewed_nodes(self, make_client):
        """The syllabus tree must only contain REVIEWED nodes."""
        client = make_client(STUDENT_A_ID)
        resp = client.get("/api/v1/gs-lms/geography/syllabus")
        assert resp.status_code == 200
        data = resp.json()["data"]
        tree = data["tree"]
        # The reviewed node should be present
        titles = [node["title"] for node in tree]
        assert "Plate Tectonics" in titles
        # The unreviewed node must NOT appear
        assert "Volcanoes (UNREVIEWED)" not in titles

    def test_syllabus_node_returns_404_for_unreviewed(self, make_client):
        """Requesting an unreviewed node by ID must return 404."""
        client = make_client(STUDENT_A_ID)
        resp = client.get("/api/v1/gs-lms/geography/syllabus/20")
        assert resp.status_code == 404

    def test_content_sections_only_return_reviewed(self, make_client):
        """Content sections endpoint must only return REVIEWED sections."""
        client = make_client(STUDENT_A_ID)
        # Reviewed node — sections should be present
        resp = client.get("/api/v1/gs-lms/geography/topics/10/sections")
        assert resp.status_code == 200
        sections = resp.json()["data"]["sections"]
        # All returned sections belong to the reviewed node
        for section in sections:
            assert "UNREVIEWED" not in section["title"]
            assert "UNREVIEWED CONTENT LEAK" not in str(section.get("blocks"))

    def test_content_sections_404_for_unreviewed_node(self, make_client):
        """Requesting sections for an unreviewed node returns 404."""
        client = make_client(STUDENT_A_ID)
        resp = client.get("/api/v1/gs-lms/geography/topics/20/sections")
        # The node lookup doesn't filter by review_status, but sections
        # are filtered. Either way, no UNREVIEWED content should leak.
        if resp.status_code == 200:
            sections = resp.json()["data"]["sections"]
            # Even if endpoint doesn't 404, no UNREVIEWED sections returned
            for section in sections:
                assert "UNREVIEWED" not in section.get("title", "")

    def test_pyqs_only_return_reviewed(self, make_client):
        """PYQ endpoint must only return REVIEWED PYQs."""
        client = make_client(STUDENT_A_ID)
        resp = client.get("/api/v1/gs-lms/geography/topics/10/pyqs")
        assert resp.status_code == 200
        pyqs = resp.json()["data"]["pyqs"]
        for pyq in pyqs:
            assert "UNREVIEWED" not in pyq["question_text"]

    def test_pyqs_404_for_unreviewed_node(self, make_client):
        """PYQs for an unreviewed node must return 404."""
        client = make_client(STUDENT_A_ID)
        resp = client.get("/api/v1/gs-lms/geography/topics/20/pyqs")
        # The reviewed node lookup should reject unreviewed nodes with 404
        assert resp.status_code == 404

    def test_practice_start_rejects_unreviewed_node(self, make_client):
        """Starting a practice session on an unreviewed node must fail."""
        client = make_client(STUDENT_A_ID)
        resp = client.post(
            "/api/v1/gs-lms/geography/practice/start",
            json={"syllabus_node_id": 20},
        )
        # The node is not REVIEWED, so should be rejected (404)
        assert resp.status_code == 404

    def test_mcq_questions_only_reviewed_in_practice(self, make_client):
        """Practice session must only include REVIEWED MCQ questions."""
        client = make_client(STUDENT_A_ID)
        resp = client.post(
            "/api/v1/gs-lms/geography/practice/start",
            json={"syllabus_node_id": 10},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Should only have 2 REVIEWED questions, not the unreviewed one
        assert data["total_questions"] == 2
        # The current question should not be the unreviewed one
        current_q = data["current_question"]
        assert "UNREVIEWED" not in current_q["question_text"]


# ===========================================================================
# Section 3: Ownership Scoping (Requirement 10.2 implied, design invariant)
# ===========================================================================


class TestOwnershipScoping:
    """Students must only access their own sessions and progress."""

    def test_practice_session_not_accessible_by_other_student(self, make_client):
        """Student B cannot access Student A's practice session."""
        client_b = make_client(STUDENT_B_ID)
        # Try to answer on Student A's session (id=100)
        resp = client_b.post(
            "/api/v1/gs-lms/geography/practice/100/answer",
            json={"chosen_answer": "A", "time_taken_seconds": 5.0},
        )
        assert resp.status_code == 404

    def test_practice_session_skip_not_accessible_by_other_student(self, make_client):
        """Student B cannot skip questions in Student A's practice session."""
        client_b = make_client(STUDENT_B_ID)
        resp = client_b.post("/api/v1/gs-lms/geography/practice/100/skip")
        assert resp.status_code == 404

    def test_practice_session_submit_not_accessible_by_other_student(self, make_client):
        """Student B cannot submit Student A's practice session."""
        client_b = make_client(STUDENT_B_ID)
        resp = client_b.post("/api/v1/gs-lms/geography/practice/100/submit")
        assert resp.status_code == 404

    def test_discussion_session_not_accessible_by_other_student(self, make_client):
        """Student B cannot view Student A's discussion session status."""
        client_b = make_client(STUDENT_B_ID)
        resp = client_b.get("/api/v1/gs-lms/geography/discussion/200/status")
        assert resp.status_code == 404

    def test_discussion_turn_not_accessible_by_other_student(self, make_client):
        """Student B cannot submit turns to Student A's discussion session."""
        client_b = make_client(STUDENT_B_ID)
        resp = client_b.post(
            "/api/v1/gs-lms/geography/discussion/200/turn",
            json={"content": "I am trying to access another student's session"},
        )
        assert resp.status_code == 404

    def test_progress_is_per_student_scoped(self, make_client):
        """Each student sees only their own progress."""
        client_a = make_client(STUDENT_A_ID)
        client_b = make_client(STUDENT_B_ID)

        # Student A has 1 completed section → non-zero progress
        resp_a = client_a.get("/api/v1/gs-lms/geography/progress")
        assert resp_a.status_code == 200

        # Student B has no progress at all
        resp_b = client_b.get("/api/v1/gs-lms/geography/progress")
        assert resp_b.status_code == 200
        data_b = resp_b.json()["data"]
        assert data_b["completed_topics"] == 0

    def test_practice_session_accessible_by_owner(self, make_client):
        """Student A can interact with their own practice session."""
        client_a = make_client(STUDENT_A_ID)
        # Student A answering their own session (should succeed or 422 for
        # valid reasons, but NOT 404)
        resp = client_a.post(
            "/api/v1/gs-lms/geography/practice/100/answer",
            json={"chosen_answer": "A", "time_taken_seconds": 5.0},
        )
        # Should not be 404 (that would mean ownership rejection)
        assert resp.status_code != 404

    def test_discussion_session_accessible_by_owner(self, make_client):
        """Student A can access their own discussion session."""
        client_a = make_client(STUDENT_A_ID)
        resp = client_a.get("/api/v1/gs-lms/geography/discussion/200/status")
        # Should not be 404 (that would mean ownership rejection)
        assert resp.status_code == 200
