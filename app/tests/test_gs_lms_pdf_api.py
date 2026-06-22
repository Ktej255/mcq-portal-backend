"""Tests for GS LMS PDF download endpoint (Task 9.2).

Covers:
- GET /api/v1/gs-lms/geography/topics/{node_id}/pdf
  - Full PDF when all 4 sections complete
  - Partial PDF when some sections complete
  - 422 when no sections completed
  - 404 for non-existent or UNREVIEWED node
  - Content-Disposition header with sanitized filename
  - Correct content-type based on generated output
  - Auth gating (no auth → 401)

Requirements traced: 8.1, 8.4, 8.5
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
from app.models.domain import RoleEnum

# Ensure all models are registered on Base.metadata
from app.core.gs_lms import models as gs_lms_models  # noqa: F401
from app.core.gs_lms import student_models as gs_lms_student_models  # noqa: F401
from app.core.gs import models as gs_models  # noqa: F401
from app.models import domain as domain_models  # noqa: F401

from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
    GsLmsNodeTypeEnum,
    GsLmsSectionLabelEnum,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress

STUDENT_ID = 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_engine():
    """Create an in-memory SQLite engine with GS LMS tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    relevant_prefixes = ("gs_lms_", "gs_subjects", "users")
    relevant_tables = [
        t
        for name, t in Base.metadata.tables.items()
        if any(name.startswith(p) for p in relevant_prefixes)
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(test_engine):
    return sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def seed_data(session_factory):
    """Seed a REVIEWED syllabus node with 4 REVIEWED sections."""
    db = session_factory()
    try:
        # Create a REVIEWED leaf topic node
        node = GsLmsSyllabusNode(
            id=200,
            subject_id=1,
            title="Climatology Fundamentals",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
        )
        db.add(node)

        # Create 4 REVIEWED sections
        sections_data = [
            (10, GsLmsSectionLabelEnum.BASIC, "Basic Concepts", 1),
            (11, GsLmsSectionLabelEnum.ADVANCED, "Advanced Topics", 2),
            (12, GsLmsSectionLabelEnum.NCERT_LEVEL, "NCERT Level", 3),
            (13, GsLmsSectionLabelEnum.EXAMINER_TRAPS, "Examiner Traps", 4),
        ]
        for sec_id, label, title, order in sections_data:
            section = GsLmsContentSection(
                id=sec_id,
                syllabus_node_id=200,
                section_label=label,
                title=title,
                blocks=[{"type": "text", "content": f"Content for {title}"}],
                display_order=order,
                review_status=GsReviewStatusEnum.REVIEWED,
                authored=True,
            )
            db.add(section)

        # Create an UNREVIEWED node (should be invisible)
        unreviewed_node = GsLmsSyllabusNode(
            id=201,
            subject_id=1,
            title="Draft Topic",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=2,
            review_status=GsReviewStatusEnum.UNREVIEWED,
        )
        db.add(unreviewed_node)

        db.commit()
    finally:
        db.close()

    return {"node_id": 200, "section_ids": [10, 11, 12, 13], "unreviewed_node_id": 201}


@pytest.fixture()
def seed_all_sections_complete(session_factory, seed_data):
    """Mark all 4 sections as completed for the student."""
    db = session_factory()
    try:
        for sec_id in seed_data["section_ids"]:
            progress = GsLmsStudentSectionProgress(
                student_id=STUDENT_ID,
                section_id=sec_id,
                syllabus_node_id=seed_data["node_id"],
                completed=True,
            )
            db.add(progress)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def seed_partial_sections_complete(session_factory, seed_data):
    """Mark only the first 2 sections as completed for the student."""
    db = session_factory()
    try:
        for sec_id in seed_data["section_ids"][:2]:
            progress = GsLmsStudentSectionProgress(
                student_id=STUDENT_ID,
                section_id=sec_id,
                syllabus_node_id=seed_data["node_id"],
                completed=True,
            )
            db.add(progress)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client(session_factory, seed_data):
    """TestClient with auth overridden to a fake student."""

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    class _FakeUser:
        id = STUDENT_ID
        email = "student@test.local"
        role = RoleEnum.STUDENT

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    yield TestClient(app)

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# GET /geography/topics/{node_id}/pdf
# ---------------------------------------------------------------------------


class TestDownloadTopicPdf:
    """Tests for the GET PDF download endpoint."""

    def test_returns_404_for_missing_node(self, client):
        """Non-existent node → 404."""
        resp = client.get("/api/v1/gs-lms/geography/topics/9999/pdf")
        assert resp.status_code == 404

    def test_returns_404_for_unreviewed_node(self, client, seed_data):
        """UNREVIEWED node → 404 (review-gate)."""
        resp = client.get(
            f"/api/v1/gs-lms/geography/topics/{seed_data['unreviewed_node_id']}/pdf"
        )
        assert resp.status_code == 404

    def test_returns_422_when_no_sections_completed(self, client, seed_data):
        """No sections completed → 422 error."""
        resp = client.get(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/pdf"
        )
        assert resp.status_code == 422
        assert "No sections completed" in resp.json()["detail"]

    def test_returns_partial_pdf_for_some_sections(
        self, client, seed_data, seed_partial_sections_complete
    ):
        """Some sections completed → partial PDF with completed sections only (R8.4)."""
        resp = client.get(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/pdf"
        )
        assert resp.status_code == 200

        # Should return content (HTML fallback since no PDF library in tests)
        assert len(resp.content) > 0

        # Content-Disposition header should be set for download
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "Climatology_Fundamentals" in resp.headers["Content-Disposition"]

        # Since this is HTML fallback in test, check content-type
        content_type = resp.headers["Content-Type"]
        assert content_type in ("application/pdf", "text/html; charset=utf-8")

        # The HTML should contain only completed sections (Basic, Advanced)
        # but NOT NCERT_LEVEL or EXAMINER_TRAPS
        body_text = resp.content.decode("utf-8")
        assert "Basic Concepts" in body_text
        assert "Advanced Topics" in body_text
        # These should NOT be present since only 2 sections are completed
        assert "NCERT Level" not in body_text
        assert "Examiner Traps" not in body_text

    def test_returns_full_pdf_when_all_sections_complete(
        self, client, seed_data, seed_all_sections_complete
    ):
        """All 4 sections completed → full PDF with all sections (R8.1)."""
        resp = client.get(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/pdf"
        )
        assert resp.status_code == 200

        # Content should be present
        assert len(resp.content) > 0

        # Content-Disposition header
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "Climatology_Fundamentals" in resp.headers["Content-Disposition"]

        # Check that all 4 sections are present in the generated output
        body_text = resp.content.decode("utf-8")
        assert "Basic Concepts" in body_text
        assert "Advanced Topics" in body_text
        assert "NCERT Level" in body_text
        assert "Examiner Traps" in body_text

    def test_content_type_header_set(
        self, client, seed_data, seed_all_sections_complete
    ):
        """Content-Type should be application/pdf or text/html depending on backend."""
        resp = client.get(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/pdf"
        )
        assert resp.status_code == 200
        content_type = resp.headers["Content-Type"]
        # Either PDF or HTML fallback is acceptable
        assert content_type in ("application/pdf", "text/html; charset=utf-8")

    def test_filename_has_correct_extension(
        self, client, seed_data, seed_all_sections_complete
    ):
        """Filename in Content-Disposition matches the content type extension."""
        resp = client.get(
            f"/api/v1/gs-lms/geography/topics/{seed_data['node_id']}/pdf"
        )
        assert resp.status_code == 200
        content_disp = resp.headers["Content-Disposition"]
        content_type = resp.headers["Content-Type"]

        if "application/pdf" in content_type:
            assert ".pdf" in content_disp
        else:
            assert ".html" in content_disp


# ---------------------------------------------------------------------------
# Auth gating (R10.2)
# ---------------------------------------------------------------------------


class TestPdfAuthGating:
    """Auth is enforced at the package router level."""

    def test_unauthenticated_request_rejected(self):
        """No auth → 401 (Property 23)."""
        # Remove dependency overrides to test real auth
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

        bare = TestClient(app)
        resp = bare.get("/api/v1/gs-lms/geography/topics/200/pdf")
        assert resp.status_code == 401
