"""Tests for the Public Administration current-affairs feature (Task 17.1).

Covers (R11.4 / R17.3 / R19.2):
* the PA seeder creates the subject with the `currentAffairs` feature enabled
  in its config, plus a gated DRAFT (UNREVIEWED) current-affairs feed;
* `GET /{slug}/current-affairs` hides the draft (honesty gate) and shows items
  only once REVIEWED;
* the subject config exposes the `currentAffairs` feature; completeness reports
  it unavailable until an item is reviewed, then available;
* the review workflow can publish a current-affairs item;
* unknown subject → 404; auth → 401.
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

from app.core.optional import models as optional_models  # noqa: F401
from app.core.optional import student_models as optional_student_models  # noqa: F401
from app.core.optional import mapping_models as optional_mapping_models  # noqa: F401
from app.core.optional import current_affairs_models as optional_ca_models  # noqa: F401
from app.core.optional.models import OptionalReviewStatusEnum
from app.core.optional.current_affairs_models import CurrentAffairsItem
from app.core.optional.pubad_seed import seed_public_administration, PUBAD_SLUG
from app.models.domain import RoleEnum

ADMIN_ID = 1


@pytest.fixture()
def seeded_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    optional_tables = [
        t for name, t in Base.metadata.tables.items() if name.startswith("optional_")
    ]
    Base.metadata.create_all(engine, tables=optional_tables)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    seed = SessionLocal()
    try:
        seed_public_administration(seed)  # creates PA subject + UNREVIEWED draft feed
        seed.commit()
    finally:
        seed.close()

    yield engine, SessionLocal
    engine.dispose()


@pytest.fixture()
def client(seeded_engine):
    _, SessionLocal = seeded_engine

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    class _FakeAdmin:
        id = ADMIN_ID
        email = "admin@upsc.local"
        role = RoleEnum.ADMIN

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: _FakeAdmin()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _first_ca_id(SessionLocal) -> int:
    db = SessionLocal()
    try:
        return db.query(CurrentAffairsItem).order_by(CurrentAffairsItem.id.asc()).first().id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Seeder + config
# ---------------------------------------------------------------------------

def test_pa_subject_created_with_current_affairs_feature(client):
    cfg = client.get(f"/api/v1/optional/{PUBAD_SLUG}/config").json()["data"]
    assert cfg["slug"] == PUBAD_SLUG
    assert "currentAffairs" in cfg["features"]
    assert cfg["is_complete"] is False


def test_seeded_feed_is_unreviewed(seeded_engine):
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        rows = db.query(CurrentAffairsItem).all()
        assert rows
        assert all(r.review_status == OptionalReviewStatusEnum.UNREVIEWED for r in rows)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Honesty gate + publish flow
# ---------------------------------------------------------------------------

def test_draft_feed_is_gated_then_published(client, seeded_engine):
    _, SessionLocal = seeded_engine
    # Gated: nothing visible while unreviewed.
    before = client.get(f"/api/v1/optional/{PUBAD_SLUG}/current-affairs").json()["data"]
    assert before["total"] == 0
    assert before["items"] == []

    # Publish one item via the review workflow.
    ca_id = _first_ca_id(SessionLocal)
    resp = client.post(
        f"/api/v1/optional/review/current-affairs/{ca_id}",
        json={"review_status": "REVIEWED"},
    )
    assert resp.status_code == 200, resp.text

    after = client.get(f"/api/v1/optional/{PUBAD_SLUG}/current-affairs").json()["data"]
    assert after["total"] == 1
    assert after["items"][0]["id"] == ca_id
    assert after["items"][0]["title"]


def test_completeness_current_affairs_flips_after_review(client, seeded_engine):
    _, SessionLocal = seeded_engine
    before = client.get(f"/api/v1/optional/{PUBAD_SLUG}/completeness").json()["data"]
    by_feature = {f["feature"]: f["available"] for f in before["features"]}
    assert by_feature.get("currentAffairs") is False

    ca_id = _first_ca_id(SessionLocal)
    client.post(
        f"/api/v1/optional/review/current-affairs/{ca_id}",
        json={"review_status": "REVIEWED"},
    )
    after = client.get(f"/api/v1/optional/{PUBAD_SLUG}/completeness").json()["data"]
    by_feature = {f["feature"]: f["available"] for f in after["features"]}
    assert by_feature.get("currentAffairs") is True


def test_review_queue_lists_current_affairs(client):
    data = client.get(f"/api/v1/optional/{PUBAD_SLUG}/review/queue").json()["data"]
    assert data["counts"]["current-affairs"] >= 1


# ---------------------------------------------------------------------------
# 404 / 401
# ---------------------------------------------------------------------------

def test_unknown_subject_is_404(client):
    assert client.get("/api/v1/optional/not-a-subject/current-affairs").status_code == 404


def test_current_affairs_requires_auth():
    bare = TestClient(app)
    assert bare.get(f"/api/v1/optional/{PUBAD_SLUG}/current-affairs").status_code == 401
