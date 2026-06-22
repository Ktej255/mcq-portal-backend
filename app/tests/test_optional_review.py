"""Tests for the content review workflow + completeness surface (Task 16).

Review workflow (16.1 — R17.1–R17.4, admin-gated):
* the review queue lists not-yet-REVIEWED items (the gated mapping draft);
* an admin can publish a draft map location → it then appears in the student
  `GET /{slug}/mapping` view (the gate flips on REVIEWED);
* a content unit can be transitioned with an authoritative source recorded;
* bad kind → 404, bad status → 422, unknown id → 404;
* a non-admin is forbidden (403); unauthenticated is 401.

Completeness surface (16.2 — R3.5/R19.3):
* reports honest reviewed-vs-total counts and per-feature availability;
* the mapping feature flips to available only after its content is reviewed.
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
from app.core.optional.models import OptionalReviewStatusEnum
from app.core.optional.mapping_models import MapLocation
from app.core.optional.importer import import_geography_optional
from app.core.optional.mapping_seed import seed_geography_mapping
from app.models.domain import RoleEnum

ADMIN_ID = 1
STUDENT_ID = 2


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
        import_geography_optional(seed, review_status="REVIEWED")
        seed_geography_mapping(seed, review_status="UNREVIEWED")  # gated for review tests
        seed.commit()
    finally:
        seed.close()

    yield engine, SessionLocal
    engine.dispose()


@pytest.fixture()
def make_client(seeded_engine):
    _, SessionLocal = seeded_engine

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _build(*, admin: bool) -> TestClient:
        class _FakeUser:
            id = ADMIN_ID if admin else STUDENT_ID
            email = "admin@upsc.local" if admin else "student@upsc.local"
            role = RoleEnum.ADMIN if admin else RoleEnum.STUDENT

        # Override only get_current_user; the real get_current_admin runs its
        # role check against this user (so the 403 path is genuinely exercised).
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _first_draft_location_id(SessionLocal) -> int:
    db = SessionLocal()
    try:
        loc = db.query(MapLocation).order_by(MapLocation.id.asc()).first()
        return loc.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Review queue + publish flow (16.1)
# ---------------------------------------------------------------------------

def test_review_queue_lists_gated_mapping_draft(make_client):
    admin = make_client(admin=True)
    data = admin.get("/api/v1/optional/geography/review/queue").json()["data"]
    # Geography content/PYQs are REVIEWED; the mapping draft is pending.
    assert data["total_pending"] >= 1
    assert data["counts"]["map-location"] >= 1
    assert data["counts"]["map-question"] >= 1
    kinds = {item["kind"] for item in data["items"]}
    assert "map-location" in kinds


def test_admin_can_publish_a_map_location(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    loc_id = _first_draft_location_id(SessionLocal)
    admin = make_client(admin=True)

    # Before: the student mapping view is empty (draft is gated).
    before = admin.get("/api/v1/optional/geography/mapping").json()["data"]
    assert before["location_count"] == 0

    # Publish the location.
    resp = admin.post(
        f"/api/v1/optional/review/map-location/{loc_id}",
        json={"review_status": "REVIEWED"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["review_status"] == "REVIEWED"

    # After: it now appears to students.
    after = admin.get("/api/v1/optional/geography/mapping").json()["data"]
    assert after["location_count"] == 1


def test_content_unit_transition_records_source(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    # Find a content unit (importer-created, currently REVIEWED) and move it
    # through review again, attaching a source.
    from app.core.optional.models import ContentUnit

    db = SessionLocal()
    try:
        cu_id = db.query(ContentUnit).order_by(ContentUnit.id.asc()).first().id
    finally:
        db.close()

    admin = make_client(admin=True)
    resp = admin.post(
        f"/api/v1/optional/review/content-unit/{cu_id}",
        json={
            "review_status": "REVIEWED",
            "source": {"title": "NCERT Geography", "source_type": "STANDARD_TEXT"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["review_status"] == "REVIEWED"
    assert body["source_recorded"] is True


def test_bad_kind_is_404(make_client):
    admin = make_client(admin=True)
    resp = admin.post("/api/v1/optional/review/banana/1", json={"review_status": "REVIEWED"})
    assert resp.status_code == 404


def test_bad_status_is_422(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    loc_id = _first_draft_location_id(SessionLocal)
    admin = make_client(admin=True)
    resp = admin.post(
        f"/api/v1/optional/review/map-location/{loc_id}",
        json={"review_status": "PUBLISHED"},
    )
    assert resp.status_code == 422


def test_unknown_id_is_404(make_client):
    admin = make_client(admin=True)
    resp = admin.post(
        "/api/v1/optional/review/map-location/999999", json={"review_status": "REVIEWED"}
    )
    assert resp.status_code == 404


def test_non_admin_is_forbidden(make_client):
    student = make_client(admin=False)
    assert student.get("/api/v1/optional/geography/review/queue").status_code == 403


def test_review_requires_auth():
    bare = TestClient(app)
    assert bare.get("/api/v1/optional/geography/review/queue").status_code == 401


# ---------------------------------------------------------------------------
# Completeness surface (16.2)
# ---------------------------------------------------------------------------

def test_completeness_reports_honest_counts(make_client):
    client = make_client(admin=False)  # any authenticated user
    data = client.get("/api/v1/optional/geography/completeness").json()["data"]
    assert data["slug"] == "geography"
    assert data["total_topics"] >= 1
    assert data["reviewed_topics"] >= 1  # importer authored + reviewed
    assert data["reviewed_content_units"] >= 1
    # Feature availability: read/pyq available; mapping NOT (draft gated); recall not seeded.
    by_feature = {f["feature"]: f["available"] for f in data["features"]}
    assert by_feature.get("read") is True
    assert by_feature.get("pyq") is True
    assert by_feature.get("mapping") is False


def test_completeness_mapping_flips_after_review(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    loc_id = _first_draft_location_id(SessionLocal)
    admin = make_client(admin=True)

    admin.post(
        f"/api/v1/optional/review/map-location/{loc_id}",
        json={"review_status": "REVIEWED"},
    )
    data = admin.get("/api/v1/optional/geography/completeness").json()["data"]
    by_feature = {f["feature"]: f["available"] for f in data["features"]}
    assert by_feature.get("mapping") is True
