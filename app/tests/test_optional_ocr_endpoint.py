"""Endpoint tests for the Optional Subjects Platform handwriting-OCR API
(Task 9.3).

Exercises ``POST /api/v1/optional/ocr`` — the upload route that turns a
handwritten-answer image into text for the ``AnswerWorkspace`` (R9.1/R9.3/R20.1).

DB strategy mirrors ``test_optional_transcribe_endpoint.py``: an isolated
in-memory SQLite DB built from the optional models' own metadata, seeded with
the real Geography importer. The app's ``get_db`` / ``get_current_user``
dependencies are overridden so the route runs authenticated; the OCR provider
is injected via ``dependency_overrides`` — hermetic, no Postgres, no model.

Asserts:
* the route runs through the shared ``OcrProvider`` (mock default) and returns
  ``text`` + ``confidence`` + ``blocks`` via StandardResponse (R9.1);
* a high-confidence extraction is NOT flagged low-confidence and carries the
  gating threshold (R9.3 — pass-through path);
* a FORCED low-confidence provider flips ``low_confidence`` True so the UI can
  trigger the review/correct / re-upload fallback (R9.3 / R20.1 / Property 7);
* a not-configured backend surfaces a clear 503 (never a silent bad result);
* empty image is a 400 (never a silent empty extraction);
* the route is auth-gated (401 unauthenticated).
"""

from __future__ import annotations

import io

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
from app.core.optional import student_models as optional_student_models  # noqa: F401
from app.core.optional.importer import import_geography_optional
from app.core.optional.providers import (
    OcrProvider,
    OcrResult,
    OcrBlock,
    OcrNotConfiguredError,
)
from app.api.v1.optional.ocr import get_ocr_provider_dep
from app.api.v1.optional.schemas import OCR_CONFIDENCE_THRESHOLD

STUDENT_ID = 1


# ---------------------------------------------------------------------------
# Test OCR providers — deterministic; capture the mime they were handed
# ---------------------------------------------------------------------------

class _RecordingHighConfidenceProvider(OcrProvider):
    """High-confidence provider that records the mime_type it was given."""

    name = "test-high"

    def __init__(self) -> None:
        self.last_mime = "unset"

    def extract(self, image, *, mime_type=None):
        self.last_mime = mime_type
        return OcrResult(
            text="rivers carve the plateau over millennia",
            confidence=0.93,
            blocks=[
                OcrBlock(text="rivers carve the plateau", confidence=0.93, bbox=[0.0, 0.0, 1.0, 0.5]),
                OcrBlock(text="over millennia", confidence=0.93, bbox=[0.0, 0.5, 1.0, 1.0]),
            ],
            provider="test/high",
        )


class _LowConfidenceProvider(OcrProvider):
    """Forces an under-threshold confidence to exercise the fallback gate."""

    name = "test-low"

    def extract(self, image, *, mime_type=None):
        return OcrResult(
            text="smudged illegible scrawl",
            confidence=0.25,
            blocks=[OcrBlock(text="smudged illegible scrawl", confidence=0.25)],
            provider="test/low",
        )


class _NotConfiguredProvider(OcrProvider):
    """Simulates a selected-but-unavailable backend (no vision creds)."""

    name = "test-unconfigured"

    def extract(self, image, *, mime_type=None):
        raise OcrNotConfiguredError("vision backend not operational")


# ---------------------------------------------------------------------------
# Fixtures: seeded in-memory DB + auth-overridden TestClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
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
def make_client(seeded_engine):
    """Factory: build an authenticated TestClient bound to a chosen OCR provider."""
    _, SessionLocal = seeded_engine

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    class _FakeUser:
        id = STUDENT_ID
        email = "test-student@upsc.local"
        google_uid = "test-student"

    def _build(provider: OcrProvider) -> TestClient:
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        app.dependency_overrides[get_ocr_provider_dep] = lambda: provider
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_ocr_provider_dep, None)


def _image_file():
    return {"image": ("answer.png", io.BytesIO(b"fake-image-bytes"), "image/png")}


# ---------------------------------------------------------------------------
# R9.1 — returns text + confidence + blocks via the shared provider
# ---------------------------------------------------------------------------

def test_ocr_returns_text_confidence_blocks(make_client):
    provider = _RecordingHighConfidenceProvider()
    client = make_client(provider)

    resp = client.post(
        "/api/v1/optional/ocr",
        files=_image_file(),
        data={"subject": "geography"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["text"] == "rivers carve the plateau over millennia"
    assert data["confidence"] == 0.93
    assert isinstance(data["blocks"], list) and len(data["blocks"]) == 2
    assert data["blocks"][0]["text"] == "rivers carve the plateau"
    assert data["blocks"][0]["bbox"] == [0.0, 0.0, 1.0, 0.5]
    assert data["provider"] == "test/high"
    # The image's mime_type was plumbed through to the provider.
    assert provider.last_mime == "image/png"


def test_high_confidence_is_not_flagged_low(make_client):
    client = make_client(_RecordingHighConfidenceProvider())
    resp = client.post("/api/v1/optional/ocr", files=_image_file())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["threshold"] == OCR_CONFIDENCE_THRESHOLD
    assert data["low_confidence"] is False
    assert data["confidence"] >= data["threshold"]


# ---------------------------------------------------------------------------
# R9.3 / R20.1 — forced low confidence flips the fallback gate
# ---------------------------------------------------------------------------

def test_low_confidence_flag_triggers_fallback(make_client):
    client = make_client(_LowConfidenceProvider())
    resp = client.post("/api/v1/optional/ocr", files=_image_file())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["confidence"] < data["threshold"]
    assert data["low_confidence"] is True
    # The text is still returned (so the student can review/correct it), but the
    # flag tells the UI not to commit it silently.
    assert data["text"] == "smudged illegible scrawl"


# ---------------------------------------------------------------------------
# Default mock provider works end-to-end (no override) — dev/test default
# ---------------------------------------------------------------------------

def test_default_mock_provider_extracts(seeded_engine):
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
        client = TestClient(app)
        resp = client.post("/api/v1/optional/ocr", files=_image_file())
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # Mock is high-confidence (0.92) by design -> pass-through path.
        assert data["text"]
        assert data["low_confidence"] is False
        assert data["provider"].startswith("mock")
        assert data["blocks"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Not-configured backend -> clear 503 (never a silent bad result)
# ---------------------------------------------------------------------------

def test_not_configured_backend_is_503(make_client):
    client = make_client(_NotConfiguredProvider())
    resp = client.post("/api/v1/optional/ocr", files=_image_file())
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Empty image is rejected (never a silent empty extraction)
# ---------------------------------------------------------------------------

def test_empty_image_is_400(make_client):
    client = make_client(_RecordingHighConfidenceProvider())
    resp = client.post(
        "/api/v1/optional/ocr",
        files={"image": ("empty.png", io.BytesIO(b""), "image/png")},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------

def test_ocr_requires_auth():
    bare = TestClient(app)
    resp = bare.post("/api/v1/optional/ocr", files=_image_file())
    assert resp.status_code == 401
