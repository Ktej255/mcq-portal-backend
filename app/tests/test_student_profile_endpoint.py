"""Tests for the canonical student-profile persistence (Master Plan A3 / GATE-4).

`GET/PUT /api/v1/student/profile` persist the student's self-study profile on
the FastAPI/Postgres backend (the same stack as Optional), replacing the
localStorage/Supabase-only path. Asserts: honest empty before any save, upsert
round-trips, updates overwrite, ownership is scoped per user, and the routes are
auth-gated.
"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.api.dependencies import get_current_user
from app.main import app
from app.models.domain import User, RoleEnum


def _make_env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    setup = SessionLocal()
    a = User(google_uid="stu-a", email="a@example.com", role=RoleEnum.STUDENT)
    b = User(google_uid="stu-b", email="b@example.com", role=RoleEnum.STUDENT)
    setup.add_all([a, b])
    setup.commit()
    setup.refresh(a)
    setup.refresh(b)
    setup.close()

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    return a, b


def _as(user):
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_get_is_honest_empty_before_save():
    a, _ = _make_env()
    try:
        resp = _as(a).get("/api/v1/student/profile")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["profile"] is None
        assert data["updated_at"] is None
    finally:
        _teardown()


def test_put_then_get_round_trips():
    a, _ = _make_env()
    try:
        client = _as(a)
        profile = {"level": "beginner", "studyWindow": "120", "learningStyle": "mixed"}
        put = client.put("/api/v1/student/profile", json={"profile": profile})
        assert put.status_code == 200, put.text
        assert put.json()["data"]["profile"] == profile

        got = client.get("/api/v1/student/profile")
        assert got.json()["data"]["profile"] == profile
        assert got.json()["data"]["updated_at"] is not None
    finally:
        _teardown()


def test_put_overwrites_existing():
    a, _ = _make_env()
    try:
        client = _as(a)
        client.put("/api/v1/student/profile", json={"profile": {"level": "beginner"}})
        client.put("/api/v1/student/profile", json={"profile": {"level": "advanced"}})
        got = client.get("/api/v1/student/profile")
        assert got.json()["data"]["profile"] == {"level": "advanced"}
    finally:
        _teardown()


def test_profile_is_ownership_scoped():
    a, b = _make_env()
    try:
        _as(a).put("/api/v1/student/profile", json={"profile": {"level": "beginner"}})
        # User B must not see A's profile.
        resp = _as(b).get("/api/v1/student/profile")
        assert resp.json()["data"]["profile"] is None
    finally:
        _teardown()


def test_routes_require_auth():
    _make_env()
    try:
        # No get_current_user override → unauthenticated.
        client = TestClient(app)
        assert client.get("/api/v1/student/profile").status_code == 401
        assert client.put("/api/v1/student/profile", json={"profile": {}}).status_code == 401
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# Per-subject GS progress
# ---------------------------------------------------------------------------
def test_progress_is_honest_empty_before_save():
    a, _ = _make_env()
    try:
        resp = _as(a).get("/api/v1/student/progress/geography")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["progress"] is None
        assert data["updated_at"] is None
    finally:
        _teardown()


def test_progress_put_then_get_round_trips_per_subject():
    a, _ = _make_env()
    try:
        client = _as(a)
        geo = {"day1": {"completed": True, "updatedAt": "2026-06-19T00:00:00Z"}}
        client.put("/api/v1/student/progress/geography", json={"progress": geo})
        # A different subject stays independent.
        eco = {"day1": {"completed": False}}
        client.put("/api/v1/student/progress/economy", json={"progress": eco})

        assert client.get("/api/v1/student/progress/geography").json()["data"]["progress"] == geo
        assert client.get("/api/v1/student/progress/economy").json()["data"]["progress"] == eco
    finally:
        _teardown()


def test_progress_is_ownership_scoped():
    a, b = _make_env()
    try:
        _as(a).put("/api/v1/student/progress/geography", json={"progress": {"day1": {"completed": True}}})
        resp = _as(b).get("/api/v1/student/progress/geography")
        assert resp.json()["data"]["progress"] is None
    finally:
        _teardown()


def test_progress_routes_require_auth():
    _make_env()
    try:
        client = TestClient(app)
        assert client.get("/api/v1/student/progress/geography").status_code == 401
        assert client.put("/api/v1/student/progress/geography", json={"progress": {}}).status_code == 401
    finally:
        _teardown()
