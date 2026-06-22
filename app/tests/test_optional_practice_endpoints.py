"""Endpoint tests for the Optional Subjects Platform practice board API (Task 8).

Exercises ``GET /api/v1/optional/{slug}/practice/status`` — the per-student
practice status that powers the frontend ``PracticeBoard`` (R7.1/R7.2/R7.3).

DB strategy (mirrors ``test_optional_pyq_endpoints.py``): an isolated in-memory
SQLite DB built from the optional models' own metadata, seeded by running the
real Geography importer (task 4.1). The app's ``get_db`` and ``get_current_user``
dependencies are overridden so the route runs against that seeded session under
an authenticated test student — hermetic, no Postgres.

Asserts:
* the board organizes practice topics under the syllabus tree (papers →
  sections → topics) and flags each topic's ``authored`` honesty state (R7.1);
* with NO attempts every topic returns the honest zero-state (count 0, no
  last-practiced timestamp, NOT_STARTED) — nothing is fabricated (R7.3);
* once the student has attempts the matching topic reflects them (count,
  last-practiced timestamp, IN_PROGRESS vs PRACTICED) (R7.3);
* the status is gated to the requesting student — another student's attempts
  never leak (design Property 10 / ownership);
* unknown subject is 404, unauthenticated is 401.
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

# Importing the models registers every ``optional_*`` table on Base.metadata.
from app.core.optional import models as optional_models  # noqa: F401
from app.core.optional import student_models as optional_student_models  # noqa: F401
from app.core.optional.models import SyllabusNode, OptionalSubject
from app.core.optional.student_models import (
    AnswerAttempt,
    AnswerAttemptStatusEnum,
    AnswerModeEnum,
)
from app.core.optional.importer import import_geography_optional

STUDENT_ID = 1
OTHER_STUDENT_ID = 2


# ---------------------------------------------------------------------------
# Fixtures: seeded in-memory DB + auth-overridden TestClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
    """In-memory SQLite seeded with the importer (REVIEWED Geography tree)."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    optional_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name.startswith("optional_")
    ]
    Base.metadata.create_all(engine, tables=optional_tables)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    seed = SessionLocal()
    try:
        import_geography_optional(seed, review_status="REVIEWED")
        seed.commit()
    finally:
        seed.close()

    yield engine, SessionLocal
    engine.dispose()


@pytest.fixture()
def client(seeded_engine):
    engine, SessionLocal = seeded_engine

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    class _FakeUser:
        id = STUDENT_ID
        email = "test-student@upsc.local"
        google_uid = "test-student"

    def _override_get_current_user():
        return _FakeUser()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _get_status(client):
    resp = client.get("/api/v1/optional/geography/practice/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


def _iter_topics(board):
    for paper in board["papers"]:
        for section in paper["sections"]:
            for topic in section["topics"]:
                yield topic


def _first_authored_topic_node_id(SessionLocal) -> int:
    """Pick a real top-level TOPIC node id from the seeded geography tree."""
    db = SessionLocal()
    try:
        subject = (
            db.query(OptionalSubject)
            .filter(OptionalSubject.slug == "geography")
            .one()
        )
        # Top-level nodes (parent_id is None) are the practice topics.
        node = (
            db.query(SyllabusNode)
            .filter(SyllabusNode.parent_id.is_(None))
            .order_by(SyllabusNode.id.asc())
            .first()
        )
        assert node is not None
        return node.id
    finally:
        db.close()


def _make_attempt(
    SessionLocal, *, student_id: int, subject_slug: str, topic_node_id: int, status
):
    db = SessionLocal()
    try:
        subject = (
            db.query(OptionalSubject)
            .filter(OptionalSubject.slug == subject_slug)
            .one()
        )
        attempt = AnswerAttempt(
            student_id=student_id,
            subject_id=subject.id,
            topic_node_id=topic_node_id,
            mode=AnswerModeEnum.TYPED,
            status=status,
            raw_text="practice attempt",
        )
        db.add(attempt)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# R7.1 — topics organized under the syllabus tree
# ---------------------------------------------------------------------------

def test_board_organizes_topics_under_syllabus_tree(client):
    board = _get_status(client)
    assert board["slug"] == "geography"
    assert board["papers"], "expected at least one paper"
    # Every paper -> section -> topic level is present and shaped.
    topics = list(_iter_topics(board))
    assert topics, "expected practice topics under the tree"
    for topic in topics:
        assert "node_id" in topic
        assert topic["title"]
        assert "authored" in topic
        assert topic["status"] in {"NOT_STARTED", "IN_PROGRESS", "PRACTICED"}
    # Roll-up counters are consistent with the per-topic rows.
    assert board["total_topics"] == len(topics)
    assert board["authored_topics"] == sum(1 for t in topics if t["authored"])
    # The importer authored Geography content, so at least one topic is authored.
    assert board["authored_topics"] >= 1


# ---------------------------------------------------------------------------
# R7.3 — honest zero-state with no attempts
# ---------------------------------------------------------------------------

def test_zero_state_when_no_attempts(client):
    board = _get_status(client)
    topics = list(_iter_topics(board))
    assert topics
    # With no attempts seeded every topic is the honest zero-state.
    for topic in topics:
        assert topic["attempt_count"] == 0
        assert topic["last_practiced_at"] is None
        assert topic["status"] == "NOT_STARTED"
    assert board["practiced_topics"] == 0


# ---------------------------------------------------------------------------
# R7.3 — status reflects the student's own attempts
# ---------------------------------------------------------------------------

def test_in_progress_when_attempt_not_evaluated(client, seeded_engine):
    _, SessionLocal = seeded_engine
    node_id = _first_authored_topic_node_id(SessionLocal)
    _make_attempt(
        SessionLocal,
        student_id=STUDENT_ID,
        subject_slug="geography",
        topic_node_id=node_id,
        status=AnswerAttemptStatusEnum.SUBMITTED,
    )

    board = _get_status(client)
    target = next(t for t in _iter_topics(board) if t["node_id"] == node_id)
    assert target["attempt_count"] == 1
    assert target["last_practiced_at"] is not None
    assert target["status"] == "IN_PROGRESS"
    # Other topics remain untouched.
    others = [t for t in _iter_topics(board) if t["node_id"] != node_id]
    assert all(t["status"] == "NOT_STARTED" for t in others)


def test_practiced_when_attempt_evaluated(client, seeded_engine):
    _, SessionLocal = seeded_engine
    node_id = _first_authored_topic_node_id(SessionLocal)
    _make_attempt(
        SessionLocal,
        student_id=STUDENT_ID,
        subject_slug="geography",
        topic_node_id=node_id,
        status=AnswerAttemptStatusEnum.SUBMITTED,
    )
    _make_attempt(
        SessionLocal,
        student_id=STUDENT_ID,
        subject_slug="geography",
        topic_node_id=node_id,
        status=AnswerAttemptStatusEnum.EVALUATED,
    )

    board = _get_status(client)
    target = next(t for t in _iter_topics(board) if t["node_id"] == node_id)
    assert target["attempt_count"] == 2
    assert target["status"] == "PRACTICED"
    assert board["practiced_topics"] == 1


# ---------------------------------------------------------------------------
# Ownership (design Property 10) — another student's attempts never leak
# ---------------------------------------------------------------------------

def test_other_students_attempts_do_not_leak(client, seeded_engine):
    _, SessionLocal = seeded_engine
    node_id = _first_authored_topic_node_id(SessionLocal)
    # Attempts belong to a DIFFERENT student than the authenticated one.
    _make_attempt(
        SessionLocal,
        student_id=OTHER_STUDENT_ID,
        subject_slug="geography",
        topic_node_id=node_id,
        status=AnswerAttemptStatusEnum.EVALUATED,
    )

    board = _get_status(client)
    # The requesting student (id=1) still sees the honest zero-state.
    for topic in _iter_topics(board):
        assert topic["attempt_count"] == 0
        assert topic["status"] == "NOT_STARTED"
    assert board["practiced_topics"] == 0


# ---------------------------------------------------------------------------
# 404 / 401
# ---------------------------------------------------------------------------

def test_unknown_subject_is_404(client):
    resp = client.get("/api/v1/optional/not-a-subject/practice/status")
    assert resp.status_code == 404


def test_practice_status_requires_auth():
    bare = TestClient(app)
    resp = bare.get("/api/v1/optional/geography/practice/status")
    assert resp.status_code == 401
