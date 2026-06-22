"""Endpoint tests for GS LMS MCQ Practice API (Task 4.4).

Exercises:
* POST /api/v1/gs-lms/geography/practice/start — Start a practice session
* POST /api/v1/gs-lms/geography/practice/{session_id}/answer — Answer question
* POST /api/v1/gs-lms/geography/practice/{session_id}/skip — Skip question
* POST /api/v1/gs-lms/geography/practice/{session_id}/submit — Submit session

Strategy: isolated in-memory SQLite seeded with known MCQ data.
App dependencies (get_db, get_current_user) are overridden so routes
run hermetically without Postgres or network.

Validates:
* Sequential access control (Property 10 / R4.1)
* Scoring and per-type accuracy on submission (Property 11 / R4.3, R4.4, R4.5)
* Full attempt record persistence (R4.6)
* 409 on already submitted session
* 422 on premature submit
* Auth + ownership enforcement
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
    GsLmsMcqQuestion,
    GsLmsQuestionTypeEnum,
)
from app.core.gs_lms.student_models import (  # noqa: F401
    GsLmsPracticeSession,
    GsLmsPracticeAttempt,
    GsLmsPracticeSessionStatusEnum,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
    """In-memory SQLite with test MCQ data for GS Geography.

    Setup:
    - 1 subject (Geography)
    - 1 REVIEWED leaf node (Continental Drift, id=30) with 3 MCQ questions
    - 1 REVIEWED leaf node (Atmosphere, id=40) with 0 MCQ questions
    - MCQ Questions for Continental Drift:
        - id=1: STATEMENT_BASED, correct=B
        - id=2: FACTUAL, correct=A
        - id=3: ASSERTION_REASON, correct=C
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
            "gs_lms_mcq_questions",
            "gs_lms_practice_sessions",
            "gs_lms_practice_attempts",
            "gs_lms_gap_snapshots",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = TestSession()
    try:
        # Create test users
        student = User(
            id=1,
            google_uid="test-student-uid",
            email="test@upsc.local",
            full_name="Test Student",
            role=RoleEnum.STUDENT,
        )
        session.add(student)

        other_student = User(
            id=2,
            google_uid="other-student-uid",
            email="other@upsc.local",
            full_name="Other Student",
            role=RoleEnum.STUDENT,
        )
        session.add(other_student)

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

        atmosphere = GsLmsSyllabusNode(
            id=40,
            subject_id=1,
            parent_id=None,
            title="Atmosphere",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(atmosphere)
        session.flush()

        # MCQ Questions for Continental Drift (id=30)
        q1 = GsLmsMcqQuestion(
            id=1,
            syllabus_node_id=30,
            question_text="Which theory explains the movement of continents?",
            options=[
                {"label": "A", "text": "Plate Tectonics"},
                {"label": "B", "text": "Continental Drift"},
                {"label": "C", "text": "Sea Floor Spreading"},
                {"label": "D", "text": "Convection Currents"},
            ],
            correct_option="B",
            explanation="Wegener proposed the continental drift theory in 1912.",
            question_type=GsLmsQuestionTypeEnum.STATEMENT_BASED,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(q1)

        q2 = GsLmsMcqQuestion(
            id=2,
            syllabus_node_id=30,
            question_text="Pangaea broke apart during which period?",
            options=[
                {"label": "A", "text": "Jurassic"},
                {"label": "B", "text": "Cretaceous"},
                {"label": "C", "text": "Triassic"},
                {"label": "D", "text": "Permian"},
            ],
            correct_option="A",
            explanation="The breakup began during the Jurassic period.",
            question_type=GsLmsQuestionTypeEnum.FACTUAL,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(q2)

        q3 = GsLmsMcqQuestion(
            id=3,
            syllabus_node_id=30,
            question_text="Assertion: Continents were once joined. Reason: Fossil evidence.",
            options=[
                {"label": "A", "text": "Both correct, R explains A"},
                {"label": "B", "text": "Both correct, R does not explain A"},
                {"label": "C", "text": "A correct, R incorrect"},
                {"label": "D", "text": "A incorrect"},
            ],
            correct_option="C",
            explanation="The fossil evidence alone doesn't fully explain drift.",
            question_type=GsLmsQuestionTypeEnum.ASSERTION_REASON,
            display_order=3,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(q3)

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
def client_pair(seeded_engine):
    """Two clients (student 1 and student 2) sharing the same DB for ownership tests."""
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

    class _FakeOtherUser:
        id = 2
        email = "other@upsc.local"
        google_uid = "other-student-uid"

    # Client for user 1
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    client1 = TestClient(app)

    def switch_to_other_user():
        app.dependency_overrides[get_current_user] = lambda: _FakeOtherUser()

    def switch_to_main_user():
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    try:
        yield client1, switch_to_other_user, switch_to_main_user
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _start_session(client, node_id: int = 30) -> dict:
    """Start a practice session and return the response data."""
    resp = client.post(
        "/api/v1/gs-lms/geography/practice/start",
        json={"syllabus_node_id": node_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# POST /geography/practice/start
# ---------------------------------------------------------------------------

def test_start_session_creates_session(client):
    """Start returns a practice session with first question."""
    data = _start_session(client)

    assert data["session_id"] is not None
    assert data["syllabus_node_id"] == 30
    assert data["status"] == "IN_PROGRESS"
    assert data["total_questions"] == 3
    assert data["current_index"] == 0
    assert data["current_question"] is not None
    assert data["current_question"]["question_id"] == 1
    assert len(data["current_question"]["options"]) == 4


def test_start_session_topic_not_found(client):
    """404 when topic doesn't exist."""
    resp = client.post(
        "/api/v1/gs-lms/geography/practice/start",
        json={"syllabus_node_id": 9999},
    )
    assert resp.status_code == 404


def test_start_session_no_questions(client):
    """422 when topic has no REVIEWED MCQ questions."""
    resp = client.post(
        "/api/v1/gs-lms/geography/practice/start",
        json={"syllabus_node_id": 40},
    )
    assert resp.status_code == 422


def test_start_session_shows_question_details(client):
    """First question includes all expected fields."""
    data = _start_session(client)
    q = data["current_question"]

    assert q["question_text"] is not None
    assert q["question_type"] == "STATEMENT_BASED"
    assert q["display_order"] == 1
    assert len(q["options"]) == 4
    # Options have label and text
    assert q["options"][0]["label"] == "A"
    assert q["options"][0]["text"] == "Plate Tectonics"


# ---------------------------------------------------------------------------
# POST /geography/practice/{session_id}/answer
# ---------------------------------------------------------------------------

def test_answer_correct(client):
    """Correct answer is recorded and session advances."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    resp = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "B", "time_taken_seconds": 12.5},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Attempt result
    assert data["attempt_result"]["is_correct"] is True
    assert data["attempt_result"]["chosen_answer"] == "B"
    assert data["attempt_result"]["correct_answer"] == "B"
    assert data["attempt_result"]["question_type"] == "STATEMENT_BASED"
    assert data["attempt_result"]["time_taken_seconds"] == 12.5

    # Session advances to next question
    assert data["session"]["current_index"] == 1
    assert data["session"]["current_question"]["question_id"] == 2


def test_answer_incorrect(client):
    """Incorrect answer is recorded with is_correct=False."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    resp = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["attempt_result"]["is_correct"] is False
    assert data["attempt_result"]["chosen_answer"] == "A"
    assert data["attempt_result"]["correct_answer"] == "B"


def test_answer_advances_sequentially(client):
    """Answering all questions advances through sequential order (Property 10)."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer Q1
    resp1 = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "B"},
    )
    data1 = resp1.json()["data"]
    assert data1["session"]["current_index"] == 1
    assert data1["session"]["current_question"]["question_id"] == 2

    # Answer Q2
    resp2 = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A"},
    )
    data2 = resp2.json()["data"]
    assert data2["session"]["current_index"] == 2
    assert data2["session"]["current_question"]["question_id"] == 3

    # Answer Q3 (last)
    resp3 = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "C"},
    )
    data3 = resp3.json()["data"]
    assert data3["session"]["current_index"] == 3
    assert data3["session"]["status"] == "COMPLETED"
    assert data3["session"]["current_question"] is None


def test_answer_after_completed_returns_422(client):
    """Cannot answer after all questions are traversed."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer all 3 questions
    for answer in ["B", "A", "C"]:
        client.post(
            f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
            json={"chosen_answer": answer},
        )

    # Try to answer again
    resp = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A"},
    )
    assert resp.status_code == 422


def test_answer_session_not_found(client):
    """404 for non-existent session."""
    resp = client.post(
        "/api/v1/gs-lms/geography/practice/9999/answer",
        json={"chosen_answer": "A"},
    )
    assert resp.status_code == 404


def test_answer_ownership_enforced(client_pair):
    """Student cannot answer another student's session."""
    client, switch_to_other, switch_to_main = client_pair
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Switch to a different user and try to answer
    switch_to_other()
    resp = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /geography/practice/{session_id}/skip
# ---------------------------------------------------------------------------

def test_skip_question(client):
    """Skip records attempt with chosen_answer=None and advances session."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/skip")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["current_index"] == 1
    assert data["current_question"]["question_id"] == 2


def test_skip_all_questions_marks_completed(client):
    """Skipping all questions transitions session to COMPLETED."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Skip all 3 questions
    for _ in range(3):
        resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/skip")
    data = resp.json()["data"]

    assert data["status"] == "COMPLETED"
    assert data["current_index"] == 3
    assert data["current_question"] is None


def test_skip_after_completed_returns_422(client):
    """Cannot skip after all questions are traversed."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Skip all 3
    for _ in range(3):
        client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/skip")

    # Try to skip again
    resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/skip")
    assert resp.status_code == 422


def test_skip_ownership_enforced(client_pair):
    """Student cannot skip in another student's session."""
    client, switch_to_other, switch_to_main = client_pair
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Switch to a different user and try to skip
    switch_to_other()
    resp = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/skip"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /geography/practice/{session_id}/submit
# ---------------------------------------------------------------------------

def test_submit_scores_session(client):
    """Submit computes score and per-type accuracy (Property 11 / R4.3, R4.4, R4.5)."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer: Q1 correct(B), Q2 correct(A), Q3 wrong(A instead of C)
    client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "B", "time_taken_seconds": 10.0},
    )
    client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A", "time_taken_seconds": 8.0},
    )
    client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A", "time_taken_seconds": 15.0},
    )

    # Submit
    resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/submit")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Scoring
    assert data["session_id"] == session_id
    assert data["total_questions"] == 3
    assert data["correct_count"] == 2
    # score = 2/3 ≈ 0.6667
    assert abs(data["score"] - 2 / 3) < 0.001

    # Attempts
    assert len(data["attempts"]) == 3

    # Per-type accuracy
    assert len(data["type_accuracy"]) == 3  # 3 distinct types
    # STATEMENT_BASED: 1/1 = 1.0
    stmt_type = next(
        t for t in data["type_accuracy"] if t["question_type"] == "STATEMENT_BASED"
    )
    assert stmt_type["total"] == 1
    assert stmt_type["correct"] == 1
    assert stmt_type["accuracy"] == 1.0

    # FACTUAL: 1/1 = 1.0
    factual_type = next(
        t for t in data["type_accuracy"] if t["question_type"] == "FACTUAL"
    )
    assert factual_type["total"] == 1
    assert factual_type["correct"] == 1

    # ASSERTION_REASON: 0/1 = 0.0
    ar_type = next(
        t for t in data["type_accuracy"] if t["question_type"] == "ASSERTION_REASON"
    )
    assert ar_type["total"] == 1
    assert ar_type["correct"] == 0
    assert ar_type["accuracy"] == 0.0

    # submitted_at present
    assert data["submitted_at"] is not None


def test_submit_with_skipped_questions(client):
    """Skipped questions are handled correctly in scoring."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer Q1 correctly, skip Q2, answer Q3 wrong
    client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "B"},
    )
    client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/skip")
    client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A"},
    )

    # Submit
    resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/submit")
    assert resp.status_code == 200
    data = resp.json()["data"]

    # Only 1 correct out of 3
    assert data["correct_count"] == 1
    # score = 1/3
    assert abs(data["score"] - 1 / 3) < 0.001

    # Check the skipped attempt
    skipped = next(a for a in data["attempts"] if a["chosen_answer"] is None)
    assert skipped["is_correct"] is None


def test_submit_before_all_answered_returns_422(client):
    """422 if trying to submit before all questions answered/skipped."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Only answer 1 of 3
    client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "B"},
    )

    resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/submit")
    assert resp.status_code == 422


def test_submit_already_submitted_returns_409(client):
    """409 if session already submitted."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer all
    for answer in ["B", "A", "C"]:
        client.post(
            f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
            json={"chosen_answer": answer},
        )

    # Submit first time
    resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/submit")
    assert resp.status_code == 200

    # Submit again
    resp2 = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/submit")
    assert resp2.status_code == 409


def test_submit_ownership_enforced(client_pair):
    """Student cannot submit another student's session."""
    client, switch_to_other, switch_to_main = client_pair
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer all with the owning user
    for answer in ["B", "A", "C"]:
        client.post(
            f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
            json={"chosen_answer": answer},
        )

    # Switch to a different user and try to submit
    switch_to_other()
    resp = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/submit"
    )
    assert resp.status_code == 404


def test_answer_after_submitted_returns_409(client):
    """Cannot answer a question after session is submitted."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer all and submit
    for answer in ["B", "A", "C"]:
        client.post(
            f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
            json={"chosen_answer": answer},
        )
    client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/submit")

    # Try to answer
    resp = client.post(
        f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
        json={"chosen_answer": "A"},
    )
    assert resp.status_code == 409


def test_skip_after_submitted_returns_409(client):
    """Cannot skip a question after session is submitted."""
    session_data = _start_session(client)
    session_id = session_data["session_id"]

    # Answer all and submit
    for answer in ["B", "A", "C"]:
        client.post(
            f"/api/v1/gs-lms/geography/practice/{session_id}/answer",
            json={"chosen_answer": answer},
        )
    client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/submit")

    # Try to skip
    resp = client.post(f"/api/v1/gs-lms/geography/practice/{session_id}/skip")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------

def test_practice_start_requires_auth():
    """Without auth, returns 401 (Property 23 / R10.2)."""
    bare = TestClient(app)
    resp = bare.post(
        "/api/v1/gs-lms/geography/practice/start",
        json={"syllabus_node_id": 30},
    )
    assert resp.status_code == 401


def test_practice_answer_requires_auth():
    """Without auth, answer returns 401."""
    bare = TestClient(app)
    resp = bare.post(
        "/api/v1/gs-lms/geography/practice/1/answer",
        json={"chosen_answer": "A"},
    )
    assert resp.status_code == 401


def test_practice_skip_requires_auth():
    """Without auth, skip returns 401."""
    bare = TestClient(app)
    resp = bare.post("/api/v1/gs-lms/geography/practice/1/skip")
    assert resp.status_code == 401


def test_practice_submit_requires_auth():
    """Without auth, submit returns 401."""
    bare = TestClient(app)
    resp = bare.post("/api/v1/gs-lms/geography/practice/1/submit")
    assert resp.status_code == 401
