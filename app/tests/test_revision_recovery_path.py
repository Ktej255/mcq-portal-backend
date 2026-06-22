"""Honesty regression for `GET /api/v1/revision/recovery-path/{topic_id}`
(Master Plan C3/E2).

The endpoint previously returned **fabricated** generic prerequisites
("Foundational <topic> Mechanics", "Historical Context & Frameworks", "Current
Affairs Linkages") for every topic. This test pins the fix: the recovery path is
derived from the student's REAL `RevisionQueue` weaknesses, and is an honest
empty path when nothing is recorded — never the invented steps.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.api.dependencies import get_current_user
from app.main import app
from app.models.domain import User, RoleEnum, Subject, Topic, RevisionQueue


def _client(seed):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    setup = SessionLocal()
    ctx = seed(setup)
    setup.close()

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: ctx["user"]
    return TestClient(app), ctx


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


_FABRICATED = {
    "Historical Context & Frameworks",
    "Current Affairs Linkages",
}


def _seed_topic(db, *, with_weakness: bool):
    user = User(google_uid="rec-uid", email="rec@example.com", role=RoleEnum.STUDENT)
    subject = Subject(name="Geography")
    db.add_all([user, subject])
    db.commit()
    topic = Topic(name="Climatology", subject_id=subject.id)
    db.add(topic)
    db.commit()
    if with_weakness:
        db.add(
            RevisionQueue(
                user_id=user.id,
                topic_id=topic.id,
                priority_score=9.0,
                reason="WEAK_TOPIC",
                category="WEAKNESS",
                mastery_level=0.2,
                next_review_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    db.refresh(user)
    return {"user": user, "topic_id": topic.id}


def test_recovery_path_is_honest_empty_without_weaknesses():
    client, ctx = _client(lambda db: _seed_topic(db, with_weakness=False))
    try:
        resp = client.get(f"/api/v1/revision/recovery-path/{ctx['topic_id']}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["suggested_prerequisites"] == []
        assert "No recorded weaknesses" in data["message"]
        titles = {s["title"] for s in data["suggested_prerequisites"]}
        assert not (titles & _FABRICATED)
    finally:
        _teardown()


def test_recovery_path_reflects_real_weakness():
    client, ctx = _client(lambda db: _seed_topic(db, with_weakness=True))
    try:
        resp = client.get(f"/api/v1/revision/recovery-path/{ctx['topic_id']}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        steps = data["suggested_prerequisites"]
        assert len(steps) == 1
        # Derived from the real WEAK_TOPIC item at low mastery -> CRITICAL.
        assert steps[0]["priority"] == "CRITICAL"
        titles = {s["title"] for s in steps}
        assert not (titles & _FABRICATED)  # no invented prerequisites
    finally:
        _teardown()
