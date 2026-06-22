"""Regression tests: GS Geography isolation (P9) + record ownership (P10)
(Task 13.3 — R2 / R15.4).

Property 9 (GS isolation): the optional-platform backend modules never import
from or couple to GS Geography (``/upsc/geography``). GS Geography has no backend
module of its own (it is a frontend route), so the structural guarantee is that
every optional backend module imports only from an allow-list of platform
packages — any drift toward a GS (or other foreign) module is caught here.

Property 10 (ownership): every student-owned read/write is authorized against
the requesting student. This consolidates the per-feature ownership checks into
one cross-feature regression: a second student can never read another student's
answer report, recall session, or progress, and never see their selection.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

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
from app.core.optional.models import OptionalSubject, SyllabusNode
from app.core.optional.student_models import VideoSegment, ConceptPoint
from app.core.optional.importer import import_geography_optional

STUDENT_ID = 1
OTHER_STUDENT_ID = 2

# Optional backend modules may import only from these app.* package prefixes.
# Anything outside this allow-list (e.g. a GS-geography module) is a coupling
# violation (design Property 9 / R2).
_ALLOWED_APP_PREFIXES = (
    "app.core.optional",
    "app.api.v1.optional",
    "app.core.inference",
    "app.core.observability",
    "app.db",
    "app.models",
    "app.schemas",
    "app.api.dependencies",
)

# Backend roots that make up the optional platform.
_OPTIONAL_ROOTS = (
    Path(__file__).resolve().parents[1] / "core" / "optional",
    Path(__file__).resolve().parents[1] / "api" / "v1" / "optional",
)


def _optional_source_files():
    for root in _OPTIONAL_ROOTS:
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def _imported_app_modules(source: str):
    """Yield every ``app.*`` module imported by the given source."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    yield alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and mod.startswith("app."):
                yield mod


# ===========================================================================
# Property 9 — GS isolation (import allow-list)
# ===========================================================================

def test_optional_modules_only_import_allowed_packages():
    violations = []
    for path in _optional_source_files():
        source = path.read_text(encoding="utf-8")
        for mod in _imported_app_modules(source):
            if not mod.startswith(_ALLOWED_APP_PREFIXES):
                violations.append((path.name, mod))
    assert not violations, f"Disallowed cross-package imports in optional modules: {violations}"


def test_no_optional_module_imports_a_geography_named_module():
    """No optional module imports any ``app.*geography*`` module (GS coupling)."""
    offenders = []
    for path in _optional_source_files():
        source = path.read_text(encoding="utf-8")
        for mod in _imported_app_modules(source):
            # The optional subject's own importer/content lives under
            # app.core.optional — that's allowed. Any *other* geography-named
            # module would be GS coupling.
            if "geography" in mod.lower() and not mod.startswith("app.core.optional"):
                offenders.append((path.name, mod))
    assert not offenders, f"Optional modules must not import GS geography: {offenders}"


# ===========================================================================
# Property 10 — ownership (consolidated cross-feature regression)
# ===========================================================================

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
        subject = seed.query(OptionalSubject).filter(OptionalSubject.slug == "geography").one()
        segment = VideoSegment(
            subject_id=subject.id,
            title="Seg 1",
            segment_order=0,
            script="alpha beta gamma",
        )
        seed.add(segment)
        seed.flush()
        seed.add(ConceptPoint(video_segment_id=segment.id, text="alpha", weight=1.0, display_order=0))
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

    def _build(student_id: int) -> TestClient:
        class _FakeUser:
            id = student_id

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _audio(text: str):
    return {"audio": ("a.webm", io.BytesIO(text.encode("utf-8")), "audio/webm")}


def _first_node_id(SessionLocal) -> int:
    db = SessionLocal()
    try:
        return (
            db.query(SyllabusNode)
            .filter(SyllabusNode.parent_id.is_(None))
            .order_by(SyllabusNode.id.asc())
            .first()
            .id
        )
    finally:
        db.close()


def _segment_id(SessionLocal) -> int:
    db = SessionLocal()
    try:
        return db.query(VideoSegment).order_by(VideoSegment.id.asc()).first().id
    finally:
        db.close()


def test_answer_report_is_owner_scoped(make_client):
    c1 = make_client(STUDENT_ID)
    attempt_id = c1.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "student one private answer"},
    ).json()["data"]["attempt_id"]
    assert c1.get(f"/api/v1/optional/answers/{attempt_id}/report").status_code == 200

    c2 = make_client(OTHER_STUDENT_ID)
    assert c2.get(f"/api/v1/optional/answers/{attempt_id}/report").status_code == 404


def test_recall_session_is_owner_scoped(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    sid = _segment_id(SessionLocal)
    c1 = make_client(STUDENT_ID)
    session_id = c1.post(
        f"/api/v1/optional/segments/{sid}/recall", files=_audio("alpha")
    ).json()["data"]["session_id"]

    c2 = make_client(OTHER_STUDENT_ID)
    assert c2.get(f"/api/v1/optional/recall/{session_id}").status_code == 404
    assert (
        c2.post(f"/api/v1/optional/recall/{session_id}/respond", files=_audio("x")).status_code
        == 404
    )


def test_progress_is_owner_scoped(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    nid = _first_node_id(SessionLocal)
    c1 = make_client(STUDENT_ID)
    c1.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": nid, "event_type": "READ_COMPLETE"},
    )
    assert c1.get("/api/v1/optional/geography/progress").json()["data"]["covered_nodes"] >= 1

    c2 = make_client(OTHER_STUDENT_ID)
    assert c2.get("/api/v1/optional/geography/progress").json()["data"]["covered_nodes"] == 0


def test_selection_is_owner_scoped(make_client):
    c1 = make_client(STUDENT_ID)
    c1.put("/api/v1/optional/selection", json={"slug": "geography"})
    c2 = make_client(OTHER_STUDENT_ID)
    assert c2.get("/api/v1/optional/selection").json()["data"]["selected"] is False
