"""Endpoint tests for the Optional Subjects Platform Read-layer API (Task 6.1).

Exercises the backend-served content endpoints that the frontend ``ReadView``
consumes:

* ``GET /api/v1/optional/{slug}/syllabus-tree``
* ``GET /api/v1/optional/{slug}/topics/{node_id}/content``

DB strategy (mirrors ``test_optional_content_no_loss.py``): an isolated
in-memory SQLite DB is built from the optional models' own metadata and seeded
by running the real Geography importer. The app's ``get_db`` and
``get_current_user`` dependencies are overridden so the routes run against that
seeded session under an authenticated (test) user — hermetic, no Postgres, no
network.

Asserts:
* the Geography syllabus tree returns (papers → sections → topics → subtopics)
  with ``authored`` honesty flags;
* a topic's content includes examiner keywords, answer-language phrasing and
  hidden topics, plus diagram render-slots;
* the honesty gate hides un-reviewed content (design Property 8 / R5.4).
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
    ContentUnit,
)
from app.core.optional.importer import import_geography_optional, load_artifact


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
# Syllabus tree
# ---------------------------------------------------------------------------

def test_syllabus_tree_returns_geography_structure(client):
    resp = client.get("/api/v1/optional/geography/syllabus-tree")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    tree = body["data"]
    assert tree["slug"] == "geography"
    assert tree["papers"], "expected at least Paper I"

    # Paper I -> a section -> topic nodes -> subtopic children.
    paper = tree["papers"][0]
    assert paper["sections"], "expected at least one section"
    section = paper["sections"][0]
    assert section["nodes"], "expected topic nodes under the section"

    topic = section["nodes"][0]
    assert topic["node_type"] == "TOPIC"
    assert "authored" in topic
    assert "review_status" in topic
    # Imported topics are REVIEWED+authored -> honesty flag true.
    assert topic["authored"] is True
    # Topics carry nested subtopics.
    assert topic["children"], "expected subtopic children under a topic"
    assert topic["children"][0]["node_type"] == "SUBTOPIC"


def test_syllabus_tree_unknown_subject_is_404(client):
    resp = client.get("/api/v1/optional/not-a-subject/syllabus-tree")
    assert resp.status_code == 404


def test_syllabus_tree_requires_auth():
    # Without the dependency override, a real auth check applies (no client
    # fixture here -> no overrides installed).
    bare = TestClient(app)
    resp = bare.get("/api/v1/optional/geography/syllabus-tree")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Topic content (keywords / answer-language / hidden topics / diagrams)
# ---------------------------------------------------------------------------

def _first_subtopic_node_id(client) -> int:
    tree = client.get("/api/v1/optional/geography/syllabus-tree").json()["data"]
    topic = tree["papers"][0]["sections"][0]["nodes"][0]
    return topic["children"][0]["node_id"]


def _first_topic_node_id(client) -> int:
    tree = client.get("/api/v1/optional/geography/syllabus-tree").json()["data"]
    return tree["papers"][0]["sections"][0]["nodes"][0]["node_id"]


def test_subtopic_content_includes_keywords_and_answer_language(client):
    node_id = _first_subtopic_node_id(client)
    resp = client.get(f"/api/v1/optional/geography/topics/{node_id}/content")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["node_id"] == node_id
    assert data["authored"] is True
    content = data["content"]
    assert content is not None, "reviewed subtopic must return a content unit"
    # Typed blocks preserved by the importer.
    assert content["blocks"] is not None
    # Examiner keywords + answer-language phrasing (R5.2).
    assert content["exam_keywords"], "expected examiner keywords"
    assert isinstance(content["exam_keywords"], list)
    assert content["answer_language"], "expected answer-language phrasing"
    assert isinstance(content["answer_language"], list)


def test_topic_content_includes_hidden_topics(client):
    node_id = _first_topic_node_id(client)
    resp = client.get(f"/api/v1/optional/geography/topics/{node_id}/content")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["authored"] is True
    content = data["content"]
    assert content is not None
    # Topic-overview units carry inline hidden topics (R4.3 / R5.2).
    assert content["hidden_topics"], "expected hidden topics on the topic overview"
    # And the topic exposes its subtopic children for navigation.
    assert data["children"], "expected subtopic children in the content payload"


def test_topic_content_surfaces_diagram_slots(client):
    """At least one subtopic should carry diagram render-slots (keyed by id)."""
    tree = client.get("/api/v1/optional/geography/syllabus-tree").json()["data"]
    topic = tree["papers"][0]["sections"][0]["nodes"][0]
    found_diagram = False
    for sub in topic["children"]:
        data = client.get(
            f"/api/v1/optional/geography/topics/{sub['node_id']}/content"
        ).json()["data"]
        content = data.get("content")
        if content and content.get("diagrams"):
            slot = content["diagrams"][0]
            assert slot["diagram_id"], "diagram slot must carry a stable id"
            found_diagram = True
            break
    assert found_diagram, "expected at least one diagram render-slot across subtopics"


def test_topic_content_unknown_node_is_404(client):
    resp = client.get("/api/v1/optional/geography/topics/999999/content")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Honesty gate (design Property 8 / R5.4)
# ---------------------------------------------------------------------------

def test_honesty_gate_hides_unreviewed_content(seeded_engine):
    """Flipping a unit to UNREVIEWED hides its content + flips ``authored``."""
    engine, SessionLocal = seeded_engine

    # Demote the first subtopic's content unit to UNREVIEWED.
    db = SessionLocal()
    try:
        sub = (
            db.query(SyllabusNode)
            .filter(SyllabusNode.parent_id.isnot(None))
            .order_by(SyllabusNode.id)
            .first()
        )
        unit = (
            db.query(ContentUnit)
            .filter(ContentUnit.syllabus_node_id == sub.id)
            .first()
        )
        target_node_id = sub.id
        unit.review_status = OptionalReviewStatusEnum.UNREVIEWED
        db.add(unit)
        db.commit()
    finally:
        db.close()

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
        data = c.get(
            f"/api/v1/optional/geography/topics/{target_node_id}/content"
        ).json()["data"]
        assert data["authored"] is False, "unreviewed content must not be authored"
        assert data["content"] is None, "unreviewed content must not be returned"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
