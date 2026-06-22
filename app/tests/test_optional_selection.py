"""Tests for subject-selection persistence + the entitlement seam
(Task 13.1 / 13.2 — R1.3 / R15 / R16).

Selection:
* GET /selection is the honest "none selected" state for a fresh student;
* PUT /selection persists the choice and GET reloads it (R15.3);
* switching deactivates the prior selection (one active at a time);
* selection is per-student (ownership — design Property 10);
* unknown subject → 404; auth required → 401.

Entitlement seam (GET /{slug}/access):
* a non-premium subject is always allowed (R16.3);
* a premium subject is allowed under the open default, and restricted with an
  upgrade path when the default is flipped to deny (R16.2);
* unknown subject → 404; auth required → 401.
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
from app.core.optional.models import OptionalSubject
from app.core.optional.importer import import_geography_optional
from app.core.optional.entitlement import DefaultEntitlementProvider
from app.api.v1.optional.selection import get_entitlement_provider_dep

STUDENT_ID = 1
OTHER_STUDENT_ID = 2


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
        # A second, premium subject to exercise the entitlement seam.
        seed.add(
            OptionalSubject(
                slug="public-administration",
                name="Public Administration",
                display_order=1,
                config={"premium": True},
                is_complete=False,
            )
        )
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

    def _build(student_id: int = STUDENT_ID, *, entitlement=None) -> TestClient:
        class _FakeUser:
            id = student_id

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        if entitlement is not None:
            app.dependency_overrides[get_entitlement_provider_dep] = lambda: entitlement
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_entitlement_provider_dep, None)


# ---------------------------------------------------------------------------
# Selection persistence (R1.3 / R15)
# ---------------------------------------------------------------------------

def test_fresh_student_has_no_selection(make_client):
    client = make_client()
    data = client.get("/api/v1/optional/selection").json()["data"]
    assert data["selected"] is False
    assert data["slug"] is None


def test_set_and_reload_selection(make_client):
    client = make_client()
    put = client.put("/api/v1/optional/selection", json={"slug": "geography"})
    assert put.status_code == 200, put.text
    assert put.json()["data"]["slug"] == "geography"

    # Reload (a fresh request) returns the persisted selection (R15.3).
    data = client.get("/api/v1/optional/selection").json()["data"]
    assert data["selected"] is True
    assert data["slug"] == "geography"
    assert data["name"]  # the persisted subject's display name


def test_switching_selection_replaces_active(make_client):
    client = make_client()
    client.put("/api/v1/optional/selection", json={"slug": "geography"})
    client.put("/api/v1/optional/selection", json={"slug": "public-administration"})
    data = client.get("/api/v1/optional/selection").json()["data"]
    assert data["slug"] == "public-administration"


def test_selection_is_per_student(make_client):
    c1 = make_client(STUDENT_ID)
    c1.put("/api/v1/optional/selection", json={"slug": "geography"})
    # Student 2 has their own (empty) selection state.
    c2 = make_client(OTHER_STUDENT_ID)
    assert c2.get("/api/v1/optional/selection").json()["data"]["selected"] is False


def test_set_selection_unknown_subject_is_404(make_client):
    client = make_client()
    resp = client.put("/api/v1/optional/selection", json={"slug": "not-a-subject"})
    assert resp.status_code == 404


def test_selection_requires_auth():
    bare = TestClient(app)
    assert bare.get("/api/v1/optional/selection").status_code == 401
    assert bare.put("/api/v1/optional/selection", json={"slug": "geography"}).status_code == 401


# ---------------------------------------------------------------------------
# Entitlement seam (R16)
# ---------------------------------------------------------------------------

def test_non_premium_subject_is_allowed(make_client):
    client = make_client()
    data = client.get("/api/v1/optional/geography/access").json()["data"]
    assert data["allowed"] is True
    assert data["premium"] is False
    assert data["upgrade_path"] is None


def test_premium_subject_open_by_default(make_client):
    # Default provider is open during early access.
    client = make_client(entitlement=DefaultEntitlementProvider(default_allow=True))
    data = client.get("/api/v1/optional/public-administration/access").json()["data"]
    assert data["premium"] is True
    assert data["allowed"] is True


def test_premium_subject_gated_when_default_denies(make_client):
    # Flip the safe default to deny → restricted + upgrade path (R16.2).
    client = make_client(entitlement=DefaultEntitlementProvider(default_allow=False))
    data = client.get("/api/v1/optional/public-administration/access").json()["data"]
    assert data["premium"] is True
    assert data["allowed"] is False
    assert data["upgrade_path"]


def test_access_unknown_subject_is_404(make_client):
    client = make_client()
    assert client.get("/api/v1/optional/not-a-subject/access").status_code == 404


def test_access_requires_auth():
    bare = TestClient(app)
    assert bare.get("/api/v1/optional/geography/access").status_code == 401
