"""Endpoint tests for the Optional Subjects Platform speak-to-fill API (Task 9.2).

Exercises ``POST /api/v1/optional/transcribe`` — the transcription route that
turns a spoken answer into text for the ``AnswerWorkspace`` (R8.2/R8.3/R8.4/R20.3).

DB strategy (mirrors ``test_optional_practice_endpoints.py``): an isolated
in-memory SQLite DB built from the optional models' own metadata, seeded with
the real Geography importer so the per-subject vocabulary-hint lookup has a
known subject. The app's ``get_db`` / ``get_current_user`` dependencies are
overridden so the route runs authenticated against that session — hermetic, no
Postgres, no audio model.

Asserts:
* the route runs through the shared ``SttProvider`` (mock default) and returns
  ``text`` + ``confidence`` + ``segments`` via StandardResponse (R8.2);
* a high-confidence transcript is NOT flagged low-confidence and carries the
  gating threshold (R8.4 — pass-through path);
* a FORCED low-confidence provider flips ``low_confidence`` True so the UI can
  trigger the review/correct step (R8.4 / R20.3 / design Property 7);
* a per-subject ``vocabulary_hint`` is plumbed through to the provider (R20.2);
* empty audio is a 400 (never a silent empty transcript);
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
from app.core.optional.providers import SttProvider, SttResult, SttSegment
from app.api.v1.optional.transcribe import get_stt_provider_dep
from app.api.v1.optional.schemas import STT_CONFIDENCE_THRESHOLD

STUDENT_ID = 1


# ---------------------------------------------------------------------------
# Test STT providers — deterministic, capture the vocabulary_hint
# ---------------------------------------------------------------------------

class _RecordingHighConfidenceProvider(SttProvider):
    """High-confidence provider that records the hint it was given."""

    name = "test-high"

    def __init__(self) -> None:
        self.last_hint = None
        self.last_mime_type = None

    def transcribe(self, audio, *, vocabulary_hint=None, mime_type=None):
        self.last_hint = vocabulary_hint
        self.last_mime_type = mime_type
        return SttResult(
            text="rivers shape the plateau",
            confidence=0.95,
            segments=[SttSegment(text="rivers shape the plateau", start=0.0, end=1.2, confidence=0.95)],
            provider="test/high",
        )


class _LowConfidenceProvider(SttProvider):
    """Forces an under-threshold confidence to exercise the review/correct gate."""

    name = "test-low"

    def transcribe(self, audio, *, vocabulary_hint=None, mime_type=None):
        return SttResult(
            text="muffled uncertain words",
            confidence=0.30,
            segments=[SttSegment(text="muffled uncertain words", start=0.0, end=1.0, confidence=0.30)],
            provider="test/low",
        )


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
    """Factory: build an authenticated TestClient bound to a chosen STT provider."""
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

    def _build(provider: SttProvider) -> TestClient:
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        app.dependency_overrides[get_stt_provider_dep] = lambda: provider
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_stt_provider_dep, None)


def _audio_file():
    return {"audio": ("answer.webm", io.BytesIO(b"fake-audio-bytes"), "audio/webm")}


# ---------------------------------------------------------------------------
# R8.2 / R8.3 — returns text + confidence + segments via the shared provider
# ---------------------------------------------------------------------------

def test_transcribe_returns_text_confidence_segments(make_client):
    provider = _RecordingHighConfidenceProvider()
    client = make_client(provider)

    resp = client.post(
        "/api/v1/optional/transcribe",
        files=_audio_file(),
        data={"subject": "geography"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["text"] == "rivers shape the plateau"
    assert data["confidence"] == 0.95
    assert isinstance(data["segments"], list) and data["segments"]
    assert data["segments"][0]["text"] == "rivers shape the plateau"
    assert data["provider"] == "test/high"
    # The uploaded clip's MIME type must be forwarded to the provider so a
    # gateway-backed STT (e.g. Gemini) can decode the real encoding (webm here).
    assert provider.last_mime_type == "audio/webm"


def test_high_confidence_is_not_flagged_low(make_client):
    client = make_client(_RecordingHighConfidenceProvider())
    resp = client.post("/api/v1/optional/transcribe", files=_audio_file())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["threshold"] == STT_CONFIDENCE_THRESHOLD
    assert data["low_confidence"] is False
    assert data["confidence"] >= data["threshold"]


# ---------------------------------------------------------------------------
# R8.4 / R20.3 — forced low confidence flips the review/correct gate
# ---------------------------------------------------------------------------

def test_low_confidence_flag_triggers_review_path(make_client):
    client = make_client(_LowConfidenceProvider())
    resp = client.post("/api/v1/optional/transcribe", files=_audio_file())
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["confidence"] < data["threshold"]
    assert data["low_confidence"] is True
    # The transcript is still returned (so the student can review/correct it),
    # but the flag tells the UI not to commit it silently.
    assert data["text"] == "muffled uncertain words"


# ---------------------------------------------------------------------------
# Default mock provider works end-to-end (no override) — dev/test default
# ---------------------------------------------------------------------------

def test_default_mock_provider_transcribes(seeded_engine):
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
        resp = client.post("/api/v1/optional/transcribe", files=_audio_file())
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # Mock is high-confidence (0.95) by design -> pass-through path.
        assert data["text"]
        assert data["low_confidence"] is False
        assert data["provider"].startswith("mock")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# R20.2 — per-subject vocabulary hint is plumbed through to the provider
# ---------------------------------------------------------------------------

def test_vocabulary_hint_is_passed_to_provider(make_client):
    provider = _RecordingHighConfidenceProvider()
    client = make_client(provider)
    resp = client.post(
        "/api/v1/optional/transcribe",
        files=_audio_file(),
        data={"subject": "geography", "vocabulary_hint": "isostasy, monsoon"},
    )
    assert resp.status_code == 200, resp.text
    assert provider.last_hint is not None
    # Caller-supplied terms are present...
    assert "isostasy" in provider.last_hint
    assert "monsoon" in provider.last_hint
    # ...and the subject name contributed at least one token (e.g. "Geography").
    assert any("eograph" in term.lower() for term in provider.last_hint)


# ---------------------------------------------------------------------------
# Empty audio is rejected (never a silent empty transcript)
# ---------------------------------------------------------------------------

def test_empty_audio_is_400(make_client):
    client = make_client(_RecordingHighConfidenceProvider())
    resp = client.post(
        "/api/v1/optional/transcribe",
        files={"audio": ("empty.webm", io.BytesIO(b""), "audio/webm")},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------

def test_transcribe_requires_auth():
    bare = TestClient(app)
    resp = bare.post("/api/v1/optional/transcribe", files=_audio_file())
    assert resp.status_code == 401
