"""Honesty regression for the dashboard analytics endpoints (Master Plan C2/E2).

`GET /api/v1/dashboard/evolution` and `/export-journey` previously returned
**fabricated constants** (`accuracy_slope: 0.12`, `consistency_score: 0.85`,
`total_attempts: 42`, `mastery_trend: "UPWARD"`) regardless of the student. This
test pins the fix: both endpoints must reflect the student's REAL attempt
history — honest zero/`INSUFFICIENT_DATA` with no data, computed values with it —
and never the old hardcoded numbers.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.api.dependencies import get_current_user
from app.main import app
from app.models.domain import User, RoleEnum
from app.tests.test_student_longitudinal_profile import seed_longitudinal_history


def _client_for(seed):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    setup_db = SessionLocal()
    user = seed(setup_db)
    setup_db.close()

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _fresh_student(db):
    user = User(google_uid="fresh-uid", email="fresh@example.com", role=RoleEnum.STUDENT)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seeded_student(db):
    seed_longitudinal_history(db)
    return db.query(User).filter(User.google_uid == "long-uid").one()


# ---------------------------------------------------------------------------
# No history → honest zero-state, never the fabricated constants
# ---------------------------------------------------------------------------
def test_evolution_is_honest_zero_state_without_history():
    client = _client_for(_fresh_student)
    try:
        resp = client.get("/api/v1/dashboard/evolution")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["attempt_count"] == 0
        # Real computation yields 0.0 for an empty series — NOT the old 0.12.
        assert data["learning_velocity"]["accuracy_slope"] == 0.0
        assert data["learning_velocity"]["accuracy_slope"] != 0.12
        assert "consistency_score" in data["behavioral_stability"]
    finally:
        _teardown()


def test_export_journey_is_honest_without_history():
    client = _client_for(_fresh_student)
    try:
        resp = client.get("/api/v1/dashboard/export-journey")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # The fabricated 42 / UPWARD must be gone.
        assert data["total_attempts"] == 0
        assert data["total_attempts"] != 42
        assert data["mastery_trend"] == "INSUFFICIENT_DATA"
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# With real history → real counts + a real (non-constant) trend
# ---------------------------------------------------------------------------
def test_export_journey_reflects_real_attempt_count():
    client = _client_for(_seeded_student)
    try:
        resp = client.get("/api/v1/dashboard/export-journey")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total_attempts"] == 4  # seed_longitudinal_history adds 4 attempts
        assert data["mastery_trend"] in {"UPWARD", "STABLE", "DOWNWARD"}
        assert data["mastery_trend"] != "INSUFFICIENT_DATA"
    finally:
        _teardown()


def test_evolution_reflects_real_history():
    client = _client_for(_seeded_student)
    try:
        resp = client.get("/api/v1/dashboard/evolution")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["attempt_count"] == 4
    finally:
        _teardown()
