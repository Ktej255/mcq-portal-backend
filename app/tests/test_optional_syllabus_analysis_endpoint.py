"""Endpoint tests for the per-segment syllabus analysis API (Task 7.4).

Exercises the backend-served three-layer syllabus contract that the frontend
``SyllabusView`` consumes:

* ``GET /api/v1/optional/{slug}/syllabus-analysis``

For each **reviewed+authored** syllabus segment the endpoint returns the three
layers a student sees on opening that segment (R4.4 / R4.5):

* "Official says"  — official printed syllabus phrasing.
* "Trend says"     — the question trend (theme + insight + frequency).
* "Hidden topics"  — themes asked beyond the printed syllabus, with rationale.

DB strategy (mirrors ``test_optional_content_endpoints.py``): an isolated
in-memory SQLite DB built from the optional models' metadata and seeded by
running the real Geography importer; the app's ``get_db`` and
``get_current_user`` dependencies are overridden so routes run against that
seeded session under an authenticated test user.

Asserts:
* every reviewed segment returns official / trend / hidden layers;
* the trend layer (theme + insight + frequency) is present (the layer the Read
  view did not surface);
* the honesty gate hides un-reviewed segments (design Property 8 / R17.3).
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
from app.core.optional.models import (
    OptionalReviewStatusEnum,
    SyllabusNode,
    SyllabusNodeTypeEnum,
    ContentUnit,
)
from app.core.optional.importer import import_geography_optional


# ---------------------------------------------------------------------------
# Fixtures: seeded in-memory DB + auth-overridden TestClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
    """In-memory SQLite seeded with the Geography optional tree (REVIEWED)."""
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
        id = 1
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


# ---------------------------------------------------------------------------
# Happy path: official + trend + hidden per reviewed segment
# ---------------------------------------------------------------------------

def test_syllabus_analysis_returns_three_layers_per_segment(client):
    resp = client.get("/api/v1/optional/geography/syllabus-analysis")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]

    assert data["slug"] == "geography"
    assert data["segment_count"] >= 1
    assert data["segments"], "expected at least one reviewed syllabus segment"
    assert data["segment_count"] == len(data["segments"])

    # Every returned segment is a reviewed TOPIC and carries the three layers.
    for seg in data["segments"]:
        assert seg["node_type"] == "TOPIC"
        assert "official" in seg
        assert "trend_says" in seg
        assert "hidden_topics" in seg
        # Locator fields for paper → section grouping (R4.4).
        assert seg["paper_label"], "segment must locate its paper"

    # At least one segment surfaces all three layers populated, including the
    # trend layer (theme + insight + frequency) — the layer the Read view did
    # not surface.
    seg = next(
        s
        for s in data["segments"]
        if s["official"] and s["trend_says"] and s["hidden_topics"]
    )
    assert seg["official"], "expected official phrasing lines"
    trend = seg["trend_says"][0]
    assert trend["theme"], "trend point must carry a theme"
    assert "insight" in trend
    assert "frequency" in trend
    hidden = seg["hidden_topics"][0]
    assert hidden["topic"], "hidden topic must carry a theme"
    assert "why" in hidden, "hidden topic must carry its rationale"


def test_syllabus_analysis_segments_ordered_by_syllabus_position(client):
    """Segments come back grouped/ordered by paper → section → topic (R4.4)."""
    data = client.get("/api/v1/optional/geography/syllabus-analysis").json()["data"]
    # Paper labels appear in contiguous blocks (no interleaving) → stable order.
    seen_papers: list[str] = []
    for seg in data["segments"]:
        label = seg["paper_label"]
        if not seen_papers or seen_papers[-1] != label:
            seen_papers.append(label)
    assert len(seen_papers) == len(set(seen_papers)), (
        "papers must appear in contiguous syllabus-ordered blocks"
    )


def test_syllabus_analysis_unknown_subject_is_404(client):
    resp = client.get("/api/v1/optional/not-a-subject/syllabus-analysis")
    assert resp.status_code == 404


def test_syllabus_analysis_requires_auth():
    bare = TestClient(app)
    resp = bare.get("/api/v1/optional/geography/syllabus-analysis")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Honesty gate (design Property 8 / R17.3): unreviewed segments are gated out
# ---------------------------------------------------------------------------

def test_syllabus_analysis_gates_unreviewed_segments(seeded_engine):
    """Demoting a topic's overview unit to UNREVIEWED removes that segment."""
    engine, SessionLocal = seeded_engine

    # Identify the reviewed segments before demotion.
    def _override_get_db():
        d = SessionLocal()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: object()
    try:
        c = TestClient(app)
        before = c.get("/api/v1/optional/geography/syllabus-analysis").json()["data"]
        assert before["segment_count"] >= 1
        target_node_id = before["segments"][0]["node_id"]
        before_ids = {s["node_id"] for s in before["segments"]}
        assert target_node_id in before_ids

        # Demote that topic's overview content unit to UNREVIEWED.
        db = SessionLocal()
        try:
            topic = (
                db.query(SyllabusNode)
                .filter(SyllabusNode.id == target_node_id)
                .one()
            )
            assert topic.node_type == SyllabusNodeTypeEnum.TOPIC
            unit = (
                db.query(ContentUnit)
                .filter(ContentUnit.syllabus_node_id == topic.id)
                .first()
            )
            assert unit is not None
            unit.review_status = OptionalReviewStatusEnum.UNREVIEWED
            db.add(unit)
            db.commit()
        finally:
            db.close()

        after = c.get("/api/v1/optional/geography/syllabus-analysis").json()["data"]
        after_ids = {s["node_id"] for s in after["segments"]}
        assert target_node_id not in after_ids, (
            "unreviewed segment must be gated out of the analysis"
        )
        assert after["segment_count"] == before["segment_count"] - 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
