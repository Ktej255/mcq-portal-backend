"""Endpoint tests for GS LMS Syllabus Tree API (Task 2.1).

Exercises:
* GET /api/v1/gs-lms/geography/syllabus — full tree with completion
* GET /api/v1/gs-lms/geography/syllabus/{node_id} — single node with children

Strategy: isolated in-memory SQLite seeded with a known syllabus tree
structure. App dependencies (get_db, get_current_user) are overridden so
routes run hermetically without Postgres or network.

Validates:
* Only REVIEWED nodes appear (Property 19 / Requirement 10.3)
* Completion annotations are correct (Property 2 / Requirement 1.3)
* Leaf nodes report boolean completion
* Non-leaf nodes report percentage completion
* day_lesson_id bridge is surfaced (Requirement 11.2)
* 404 for non-existent or unreviewed nodes
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
from app.models.domain import User, RoleEnum

# Import models to register tables on Base.metadata.
from app.core.gs.models import GsSubject, GsReviewStatusEnum  # noqa: F401
from app.core.gs_lms.models import (  # noqa: F401
    GsLmsSyllabusNode,
    GsLmsNodeTypeEnum,
    GsLmsContentSection,
    GsLmsSectionLabelEnum,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress  # noqa: F401


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
    """In-memory SQLite with a test syllabus tree for GS Geography.

    Tree structure:
      - Geomorphology (MEGA_TOPIC, REVIEWED)
        - Plate Tectonics (SUB_TOPIC, REVIEWED)
          - Continental Drift (LEAF_TOPIC, REVIEWED, day_lesson_id=1)
          - Sea Floor Spreading (LEAF_TOPIC, REVIEWED)
        - Volcanism (SUB_TOPIC, UNREVIEWED) ← should be filtered out
      - Climatology (MEGA_TOPIC, REVIEWED)
        - Atmosphere (LEAF_TOPIC, REVIEWED)
      - Oceanography (MEGA_TOPIC, UNREVIEWED) ← should be filtered out
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create only the tables we need for this test.
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name
        in (
            "users",
            "gs_subjects",
            "gs_day_lessons",
            "gs_lms_syllabus_nodes",
            "gs_lms_content_sections",
            "gs_lms_student_section_progress",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    session = TestSession()
    try:
        # Create test user
        user = User(
            id=1,
            google_uid="test-student-uid",
            email="test@upsc.local",
            full_name="Test Student",
            role=RoleEnum.STUDENT,
        )
        session.add(user)

        # Create GS Geography subject
        subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
        session.add(subject)
        session.flush()

        # --- Mega topic 1: Geomorphology (REVIEWED) ---
        geomorphology = GsLmsSyllabusNode(
            id=10,
            subject_id=1,
            parent_id=None,
            title="Geomorphology",
            node_type=GsLmsNodeTypeEnum.MEGA_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(geomorphology)

        # Sub-topic: Plate Tectonics (REVIEWED)
        plate_tectonics = GsLmsSyllabusNode(
            id=20,
            subject_id=1,
            parent_id=10,
            title="Plate Tectonics",
            node_type=GsLmsNodeTypeEnum.SUB_TOPIC,
            weight=0.5,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(plate_tectonics)

        # Leaf: Continental Drift (REVIEWED, with day_lesson_id bridge)
        continental_drift = GsLmsSyllabusNode(
            id=30,
            subject_id=1,
            parent_id=20,
            title="Continental Drift",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=0.25,
            display_order=1,
            day_lesson_id=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(continental_drift)

        # Leaf: Sea Floor Spreading (REVIEWED, no day_lesson_id)
        sea_floor = GsLmsSyllabusNode(
            id=31,
            subject_id=1,
            parent_id=20,
            title="Sea Floor Spreading",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=0.25,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(sea_floor)

        # Sub-topic: Volcanism (UNREVIEWED — should be filtered)
        volcanism = GsLmsSyllabusNode(
            id=21,
            subject_id=1,
            parent_id=10,
            title="Volcanism",
            node_type=GsLmsNodeTypeEnum.SUB_TOPIC,
            weight=0.5,
            display_order=2,
            review_status=GsReviewStatusEnum.UNREVIEWED,
        )
        session.add(volcanism)

        # --- Mega topic 2: Climatology (REVIEWED) ---
        climatology = GsLmsSyllabusNode(
            id=11,
            subject_id=1,
            parent_id=None,
            title="Climatology",
            node_type=GsLmsNodeTypeEnum.MEGA_TOPIC,
            weight=1.0,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(climatology)

        # Leaf directly under Climatology
        atmosphere = GsLmsSyllabusNode(
            id=40,
            subject_id=1,
            parent_id=11,
            title="Atmosphere",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        session.add(atmosphere)

        # --- Mega topic 3: Oceanography (UNREVIEWED — should be filtered) ---
        oceanography = GsLmsSyllabusNode(
            id=12,
            subject_id=1,
            parent_id=None,
            title="Oceanography",
            node_type=GsLmsNodeTypeEnum.MEGA_TOPIC,
            weight=1.0,
            display_order=3,
            review_status=GsReviewStatusEnum.UNREVIEWED,
        )
        session.add(oceanography)

        # --- Content sections for Continental Drift (4 sections) ---
        for i, label in enumerate(
            [
                GsLmsSectionLabelEnum.BASIC,
                GsLmsSectionLabelEnum.ADVANCED,
                GsLmsSectionLabelEnum.NCERT_LEVEL,
                GsLmsSectionLabelEnum.EXAMINER_TRAPS,
            ],
            start=1,
        ):
            section = GsLmsContentSection(
                id=100 + i,
                syllabus_node_id=30,
                section_label=label,
                title=f"{label.value} section",
                display_order=i,
                review_status=GsReviewStatusEnum.REVIEWED,
                authored=True,
            )
            session.add(section)

        # --- Content sections for Sea Floor Spreading (4 sections) ---
        for i, label in enumerate(
            [
                GsLmsSectionLabelEnum.BASIC,
                GsLmsSectionLabelEnum.ADVANCED,
                GsLmsSectionLabelEnum.NCERT_LEVEL,
                GsLmsSectionLabelEnum.EXAMINER_TRAPS,
            ],
            start=1,
        ):
            section = GsLmsContentSection(
                id=200 + i,
                syllabus_node_id=31,
                section_label=label,
                title=f"{label.value} section",
                display_order=i,
                review_status=GsReviewStatusEnum.REVIEWED,
                authored=True,
            )
            session.add(section)

        # --- Student progress: complete ALL 4 sections of Continental Drift ---
        for section_id in [101, 102, 103, 104]:
            progress = GsLmsStudentSectionProgress(
                student_id=1,
                section_id=section_id,
                syllabus_node_id=30,
                completed=True,
            )
            session.add(progress)

        # Sea Floor Spreading: only 2 of 4 sections completed (NOT complete)
        for section_id in [201, 202]:
            progress = GsLmsStudentSectionProgress(
                student_id=1,
                section_id=section_id,
                syllabus_node_id=31,
                completed=True,
            )
            session.add(progress)

        session.commit()
    finally:
        session.close()

    yield engine, TestSession
    engine.dispose()


@pytest.fixture()
def client(seeded_engine):
    engine, TestSession = seeded_engine

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    class _FakeUser:
        id = 1
        email = "test@upsc.local"
        google_uid = "test-student-uid"

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
# GET /geography/syllabus — Full tree
# ---------------------------------------------------------------------------

def test_syllabus_tree_returns_reviewed_nodes_only(client):
    """Only REVIEWED nodes appear in the tree (Property 19 / R10.3)."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Root tree should have 2 mega topics (Geomorphology, Climatology).
    # Oceanography (UNREVIEWED) is excluded.
    assert len(data["tree"]) == 2
    titles = [n["title"] for n in data["tree"]]
    assert "Geomorphology" in titles
    assert "Climatology" in titles
    assert "Oceanography" not in titles


def test_syllabus_tree_excludes_unreviewed_children(client):
    """UNREVIEWED child nodes are filtered from the tree (Property 19)."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    data = resp.json()["data"]

    # Geomorphology should only have Plate Tectonics (Volcanism is UNREVIEWED).
    geo = next(n for n in data["tree"] if n["title"] == "Geomorphology")
    assert len(geo["children"]) == 1
    assert geo["children"][0]["title"] == "Plate Tectonics"


def test_syllabus_tree_leaf_completion_boolean(client):
    """Leaf nodes report boolean 'completed' (Property 2 / R1.3)."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    data = resp.json()["data"]

    geo = next(n for n in data["tree"] if n["title"] == "Geomorphology")
    plate_tectonics = geo["children"][0]
    leaves = plate_tectonics["children"]

    # Continental Drift: all 4 sections completed → True
    cd = next(l for l in leaves if l["title"] == "Continental Drift")
    assert cd["completed"] is True
    assert cd["completion_percent"] is None

    # Sea Floor Spreading: only 2/4 sections → False
    sf = next(l for l in leaves if l["title"] == "Sea Floor Spreading")
    assert sf["completed"] is False
    assert sf["completion_percent"] is None


def test_syllabus_tree_non_leaf_completion_percent(client):
    """Non-leaf nodes report completion_percent (Property 2 / R1.3)."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    data = resp.json()["data"]

    geo = next(n for n in data["tree"] if n["title"] == "Geomorphology")
    plate_tectonics = geo["children"][0]

    # Plate Tectonics has 2 leaf children: 1 completed, 1 not → 50%
    assert plate_tectonics["completion_percent"] == 50.0
    assert plate_tectonics["completed"] is None


def test_syllabus_tree_day_lesson_bridge(client):
    """Leaf nodes expose day_lesson_id FK bridge (Requirement 11.2)."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    data = resp.json()["data"]

    geo = next(n for n in data["tree"] if n["title"] == "Geomorphology")
    plate_tectonics = geo["children"][0]
    cd = next(l for l in plate_tectonics["children"] if l["title"] == "Continental Drift")
    sf = next(l for l in plate_tectonics["children"] if l["title"] == "Sea Floor Spreading")

    assert cd["day_lesson_id"] == 1
    assert sf["day_lesson_id"] is None


def test_syllabus_tree_total_nodes_count(client):
    """total_nodes reflects actual count of nodes in the tree."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    data = resp.json()["data"]

    # Expected: Geomorphology + Plate Tectonics + Continental Drift +
    #           Sea Floor Spreading + Climatology + Atmosphere = 6
    assert data["total_nodes"] == 6


def test_syllabus_tree_subject_metadata(client):
    """Response includes subject_id and subject_name."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    data = resp.json()["data"]

    assert data["subject_id"] == 1
    assert data["subject_name"] == "GS Geography"


def test_syllabus_tree_ordered_by_display_order(client):
    """Nodes are returned in display_order sequence (R1.2)."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus")
    data = resp.json()["data"]

    # Geomorphology (order=1) before Climatology (order=2)
    assert data["tree"][0]["title"] == "Geomorphology"
    assert data["tree"][1]["title"] == "Climatology"


# ---------------------------------------------------------------------------
# GET /geography/syllabus/{node_id} — Single node
# ---------------------------------------------------------------------------

def test_single_node_returns_reviewed_node(client):
    """GET /syllabus/{node_id} returns a single REVIEWED node."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus/10")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["node_id"] == 10
    assert data["title"] == "Geomorphology"


def test_single_node_includes_reviewed_children(client):
    """Single node response includes REVIEWED children only."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus/10")
    data = resp.json()["data"]

    # Geomorphology children: only Plate Tectonics (REVIEWED), not Volcanism
    assert len(data["children"]) == 1
    assert data["children"][0]["title"] == "Plate Tectonics"


def test_single_node_not_found_for_unreviewed(client):
    """404 when requesting an UNREVIEWED node (Property 19)."""
    # Volcanism (id=21) is UNREVIEWED
    resp = client.get("/api/v1/gs-lms/geography/syllabus/21")
    assert resp.status_code == 404


def test_single_node_not_found_for_nonexistent(client):
    """404 when node doesn't exist."""
    resp = client.get("/api/v1/gs-lms/geography/syllabus/9999")
    assert resp.status_code == 404


def test_single_node_completion_on_leaf(client):
    """Leaf node shows correct completion boolean."""
    # Continental Drift (id=30) — fully completed
    resp = client.get("/api/v1/gs-lms/geography/syllabus/30")
    data = resp.json()["data"]
    assert data["completed"] is True
    assert data["completion_percent"] is None


def test_single_node_completion_on_subtopic(client):
    """Sub-topic node shows correct completion percentage."""
    # Plate Tectonics (id=20) — 1/2 children completed = 50%
    resp = client.get("/api/v1/gs-lms/geography/syllabus/20")
    data = resp.json()["data"]
    assert data["completion_percent"] == 50.0
    assert data["completed"] is None


# ---------------------------------------------------------------------------
# Auth gating (tested without dependency override)
# ---------------------------------------------------------------------------

def test_syllabus_tree_requires_auth():
    """Without auth, returns 401 (Property 23 / R10.2)."""
    bare = TestClient(app)
    resp = bare.get("/api/v1/gs-lms/geography/syllabus")
    assert resp.status_code == 401
