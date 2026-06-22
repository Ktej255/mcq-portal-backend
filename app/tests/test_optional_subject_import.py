"""Tests for the subject content upload (syllabus + PYQs) — Task 17.2 enabler.

Covers (R19.1 / R19.2 / R17.3):
* the importer creates the subject skeleton (papers → sections → topics →
  subtopics) + PYQs, mapping PYQs to topic nodes;
* everything is ingested as gated UNREVIEWED draft (hidden from students until
  reviewed — design Property 8);
* the admin `POST /import-subject` endpoint ingests a payload and is admin-only;
* re-import replaces the subject's tree (idempotent);
* a missing slug/name is rejected (422).
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
from app.core.optional.models import OptionalSubject, SyllabusNode, Pyq, OptionalReviewStatusEnum
from app.core.optional.subject_importer import import_subject_from_payload
from app.models.domain import RoleEnum

ADMIN_ID = 1

SAMPLE = {
    "slug": "test-history",
    "name": "History",
    "features": ["read", "pyq", "practice", "answer", "gap"],
    "papers": [
        {
            "label": "PAPER_I",
            "name": "Paper I",
            "sections": [
                {
                    "label": "SECTION_A",
                    "name": "Section A",
                    "topics": [
                        {
                            "title": "Sources",
                            "official_phrasing": "Sources: archaeological and literary.",
                            "subtopics": [{"title": "Archaeological sources"}],
                        }
                    ],
                }
            ],
        },
        {
            "label": "PAPER_II",
            "name": "Paper II",
            "sections": [
                {"label": None, "name": "Paper II", "topics": [{"title": "Modern India"}]}
            ],
        },
    ],
    "pyqs": [
        {
            "year": 2021,
            "paper": "PAPER_I",
            "section": "SECTION_A",
            "topic_title": "Sources",
            "question": "Discuss the archaeological sources of ancient Indian history.",
            "marks": 15,
        }
    ],
}


@pytest.fixture()
def engine_session():
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
    yield engine, SessionLocal
    engine.dispose()


# ---------------------------------------------------------------------------
# Importer (unit)
# ---------------------------------------------------------------------------

def test_importer_creates_skeleton_and_pyqs_gated(engine_session):
    _, SessionLocal = engine_session
    db = SessionLocal()
    try:
        counts = import_subject_from_payload(db, SAMPLE)
        db.commit()
        assert counts["subjects"] == 1
        assert counts["papers"] == 2
        assert counts["topic_nodes"] == 2
        assert counts["subtopic_nodes"] == 1
        assert counts["pyqs"] == 1

        subject = db.query(OptionalSubject).filter(OptionalSubject.slug == "test-history").one()
        # All nodes + PYQs are gated UNREVIEWED.
        nodes = db.query(SyllabusNode).all()
        assert nodes and all(n.review_status == OptionalReviewStatusEnum.UNREVIEWED for n in nodes)
        pyqs = db.query(Pyq).filter(Pyq.subject_id == subject.id).all()
        assert pyqs and all(p.review_status == OptionalReviewStatusEnum.UNREVIEWED for p in pyqs)
        # The PYQ mapped to its topic node.
        assert pyqs[0].topic_node_id is not None
    finally:
        db.close()


def test_importer_is_idempotent(engine_session):
    _, SessionLocal = engine_session
    db = SessionLocal()
    try:
        import_subject_from_payload(db, SAMPLE)
        db.commit()
        import_subject_from_payload(db, SAMPLE)  # re-import
        db.commit()
        # Exactly one subject, no duplicate trees.
        assert db.query(OptionalSubject).filter(OptionalSubject.slug == "test-history").count() == 1
        assert db.query(Pyq).count() == 1
    finally:
        db.close()


def test_importer_requires_slug_and_name(engine_session):
    _, SessionLocal = engine_session
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            import_subject_from_payload(db, {"slug": "", "name": ""})
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Admin upload endpoint
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_client(engine_session):
    _, SessionLocal = engine_session

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _build(*, admin: bool) -> TestClient:
        class _FakeUser:
            id = ADMIN_ID
            email = "admin@upsc.local"
            role = RoleEnum.ADMIN if admin else RoleEnum.STUDENT

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def test_admin_can_upload_subject(make_client):
    admin = make_client(admin=True)
    resp = admin.post("/api/v1/optional/import-subject", json=SAMPLE)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["slug"] == "test-history"
    assert data["review_status"] == "UNREVIEWED"
    assert data["counts"]["topic_nodes"] == 2

    # Gated: the student syllabus tree shows the structure but nothing authored.
    tree = admin.get("/api/v1/optional/test-history/syllabus-tree").json()["data"]
    assert tree["slug"] == "test-history"
    # Topics exist but are not authored (gated) → not student-visible content.
    paper_i = next(p for p in tree["papers"] if p["label"] == "PAPER_I")
    section_a = paper_i["sections"][0]
    assert section_a["nodes"]
    assert all(n["authored"] is False for n in section_a["nodes"])


def test_upload_requires_admin(make_client):
    student = make_client(admin=False)
    resp = student.post("/api/v1/optional/import-subject", json=SAMPLE)
    assert resp.status_code == 403


def test_upload_missing_fields_is_422(make_client):
    admin = make_client(admin=True)
    resp = admin.post("/api/v1/optional/import-subject", json={"papers": []})
    assert resp.status_code == 422


def test_upload_requires_auth():
    bare = TestClient(app)
    assert bare.post("/api/v1/optional/import-subject", json=SAMPLE).status_code == 401
