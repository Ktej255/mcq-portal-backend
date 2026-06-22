"""Tests for the per-subject configuration endpoint (Task 15.1 — R11 / R19).

Covers `GET /{slug}/config`:
* returns the subject's enabled feature modules + papers/sections shape from the
  DB-backed config (the Geography importer sets these);
* returns safe empty defaults for a subject with no config;
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

STUDENT_ID = 1


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
        # A subject with no config to exercise the safe-defaults path.
        seed.add(
            OptionalSubject(slug="sociology", name="Sociology", display_order=2, config=None)
        )
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

    class _FakeUser:
        id = STUDENT_ID

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_geography_config_exposes_features_and_shape(client):
    data = client.get("/api/v1/optional/geography/config").json()["data"]
    assert data["slug"] == "geography"
    # The importer enables these feature modules.
    for feature in ("read", "pyq", "practice", "answer", "mapping", "diagrams", "gap", "recall"):
        assert feature in data["features"]
    # Papers/sections shape is present (Paper I has Section A/B).
    labels = {p["label"] for p in data["papers"]}
    assert "PAPER_I" in labels
    paper_i = next(p for p in data["papers"] if p["label"] == "PAPER_I")
    assert "SECTION_A" in paper_i["sections"]


def test_subject_without_config_gets_safe_defaults(client):
    data = client.get("/api/v1/optional/sociology/config").json()["data"]
    assert data["slug"] == "sociology"
    assert data["features"] == []
    assert data["papers"] == []
    assert data["is_complete"] is False


def test_unknown_subject_is_404(client):
    assert client.get("/api/v1/optional/not-a-subject/config").status_code == 404


def test_config_requires_auth():
    bare = TestClient(app)
    assert bare.get("/api/v1/optional/geography/config").status_code == 401
