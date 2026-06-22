"""Tests for the Optional platform answer-evaluation endpoint + providers
(Tasks 9.4 / 9.5 — Phase 1E, R9.2 / R9.4 / R9.5 / R20.1 / R20.3).

Two layers:

* **Provider unit tests** — the deterministic ``MockEvaluationProvider``
  produces a *complete* schema-valid report, and the ``GatewayEvaluationProvider``
  degrades *honestly* to an all-incomplete report when the gateway returns
  non-conforming output. These pin design **Property 6** (report-completeness
  honesty) at the provider seam.

* **Endpoint property tests** (``POST /api/v1/optional/{slug}/answers`` +
  ``GET /api/v1/optional/answers/{id}/report``):
    - P6: an evaluated report is "complete" iff ``incomplete_sections`` is empty;
      an injected all-incomplete provider yields an honest incomplete report,
      never a fabricated complete one;
    - P7: a low-confidence, unreviewed spoken/handwritten draft is NOT
      auto-graded (review required), while an acknowledged one IS graded, and a
      typed answer is never gated;
    - persistence + ownership (P10): the report is retrievable and never leaks
      across students;
    - input validation (400 empty / 422 bad mode / 404 unknown subject) and
      auth gating (401).

DB strategy mirrors ``test_optional_transcribe_endpoint.py``: an isolated
in-memory SQLite seeded with the real Geography importer; ``get_db`` /
``get_current_user`` / the evaluation-provider dependency are overridden so the
route runs hermetically (no Postgres, no model).
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
from app.core.optional import student_models as optional_student_models  # noqa: F401
from app.core.optional.models import OptionalSubject, SyllabusNode
from app.core.optional.importer import import_geography_optional
from app.core.optional.prompts import (
    REQUIRED_EVALUATION_SECTIONS,
    EvaluationReportSchema,
)
from app.core.optional.providers import (
    EvaluationProvider,
    MockEvaluationProvider,
    GatewayEvaluationProvider,
)
from app.core.optional.providers.evaluation import _all_incomplete
from app.core.inference.contracts import InferenceResponse
from app.api.v1.optional.answers import get_evaluation_provider_dep

STUDENT_ID = 1
OTHER_STUDENT_ID = 2


# ===========================================================================
# Provider unit tests — Property 6 at the provider seam
# ===========================================================================

def test_mock_evaluation_provider_produces_complete_report():
    provider = MockEvaluationProvider()
    report = provider.evaluate(answer_text="rivers shape the plateau", rubric="r")
    assert isinstance(report, EvaluationReportSchema)
    # Complete: every required section produced, none flagged incomplete (P6).
    assert report.is_complete is True
    assert report.incomplete_sections == []
    assert set(report.sections.keys()) == set(REQUIRED_EVALUATION_SECTIONS)
    assert report.overall_score is not None


def test_mock_evaluation_provider_is_deterministic():
    provider = MockEvaluationProvider()
    a = provider.evaluate(answer_text="same answer text", rubric="r")
    b = provider.evaluate(answer_text="same answer text", rubric="r")
    assert a.overall_score == b.overall_score
    assert {k: v.score for k, v in a.sections.items()} == {
        k: v.score for k, v in b.sections.items()
    }


def test_all_incomplete_is_honest_not_complete():
    report = _all_incomplete(REQUIRED_EVALUATION_SECTIONS)
    # Honest degradation: nothing produced, everything flagged incomplete (P6).
    assert report.is_complete is False
    assert set(report.incomplete_sections) == set(REQUIRED_EVALUATION_SECTIONS)
    assert report.sections == {}


def test_gateway_provider_degrades_honestly_on_bad_output(monkeypatch):
    """A non-JSON gateway response must NOT become a fabricated complete report."""
    provider = GatewayEvaluationProvider(provider_name="gemini")

    class _BadProvider:
        def generate(self, request):
            # The default inference mock returns prose, not JSON — exactly the
            # case that must degrade honestly rather than parse into a report.
            return InferenceResponse(text="[MOCK RESPONSE] not json", provider="mock")

    from app.core.inference.gateway import InferenceGateway

    monkeypatch.setattr(InferenceGateway, "get_provider", lambda name=None: _BadProvider())

    report = provider.evaluate(answer_text="answer", rubric="rubric")
    assert report.is_complete is False
    assert set(report.incomplete_sections) == set(REQUIRED_EVALUATION_SECTIONS)


def test_gateway_provider_degrades_honestly_on_call_failure(monkeypatch):
    provider = GatewayEvaluationProvider(provider_name="gemini")

    from app.core.inference.gateway import InferenceGateway

    def _boom(name=None):
        raise RuntimeError("backend down")

    monkeypatch.setattr(InferenceGateway, "get_provider", _boom)

    report = provider.evaluate(answer_text="answer", rubric="rubric")
    assert report.is_complete is False
    assert set(report.incomplete_sections) == set(REQUIRED_EVALUATION_SECTIONS)


# ===========================================================================
# Endpoint fixtures
# ===========================================================================

class _CompleteProvider(EvaluationProvider):
    """Always returns a complete report (mirrors the mock, but explicit)."""

    name = "test-complete"

    def evaluate(self, *, answer_text, rubric, question=None,
                 required_sections=REQUIRED_EVALUATION_SECTIONS):
        return MockEvaluationProvider().evaluate(
            answer_text=answer_text, rubric=rubric, question=question,
            required_sections=required_sections,
        )


class _IncompleteProvider(EvaluationProvider):
    """Always returns an honest all-incomplete report (simulated model failure)."""

    name = "test-incomplete"

    def evaluate(self, *, answer_text, rubric, question=None,
                 required_sections=REQUIRED_EVALUATION_SECTIONS):
        return _all_incomplete(required_sections)


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
    """Factory: authenticated TestClient bound to a chosen evaluation provider."""
    _, SessionLocal = seeded_engine

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _build(provider: EvaluationProvider, *, student_id: int = STUDENT_ID) -> TestClient:
        class _FakeUser:
            id = student_id
            email = "test-student@upsc.local"
            google_uid = "test-student"

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        app.dependency_overrides[get_evaluation_provider_dep] = lambda: provider
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_evaluation_provider_dep, None)


def _first_topic_node_id(SessionLocal) -> int:
    db = SessionLocal()
    try:
        node = (
            db.query(SyllabusNode)
            .filter(SyllabusNode.parent_id.is_(None))
            .order_by(SyllabusNode.id.asc())
            .first()
        )
        assert node is not None
        return node.id
    finally:
        db.close()


# ===========================================================================
# P6 — report completeness honesty (endpoint)
# ===========================================================================

def test_typed_answer_is_evaluated_with_complete_report(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={
            "mode": "TYPED",
            "intro_text": "Plateaus are elevated landforms.",
            "body_text": "They form through uplift and erosion over geological time.",
            "conclusion_text": "Thus plateaus are key to drainage and resources.",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["review_required"] is False
    assert data["status"] == "EVALUATED"
    report = data["report"]
    assert report is not None
    assert report["is_complete"] is True
    assert report["incomplete_sections"] == []
    assert set(report["sections"].keys()) == set(REQUIRED_EVALUATION_SECTIONS)
    assert report["overall_score"] is not None


def test_incomplete_report_is_flagged_not_faked(make_client):
    client = make_client(_IncompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "A short answer."},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    report = data["report"]
    # P6: not complete, and EXACTLY the missing sections are listed.
    assert report["is_complete"] is False
    assert set(report["incomplete_sections"]) == set(REQUIRED_EVALUATION_SECTIONS)
    assert report["sections"] == {}
    assert data["message"]  # honest explanation surfaced


# ===========================================================================
# P7 — confidence gating (endpoint)
# ===========================================================================

def test_low_confidence_spoken_is_not_auto_graded(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={
            "mode": "SPOKEN",
            "raw_text": "muffled uncertain words",
            "stt_confidence": 0.30,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # P7: refused to grade a shaky, unreviewed transcript.
    assert data["review_required"] is True
    assert data["low_confidence"] is True
    assert data["status"] == "DRAFT"
    assert data["report"] is None


def test_low_confidence_handwritten_is_not_auto_graded(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={
            "mode": "HANDWRITTEN",
            "raw_text": "barely legible scrawl",
            "ocr_confidence": 0.25,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["review_required"] is True
    assert data["report"] is None


def test_acknowledged_low_confidence_is_graded(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={
            "mode": "SPOKEN",
            "raw_text": "reviewed and corrected transcript",
            "stt_confidence": 0.30,
            "confidence_acknowledged": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # Once the student has reviewed it, it is graded normally.
    assert data["review_required"] is False
    assert data["status"] == "EVALUATED"
    assert data["report"] is not None


def test_high_confidence_spoken_is_graded(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={
            "mode": "SPOKEN",
            "raw_text": "a clearly transcribed answer about rivers",
            "stt_confidence": 0.95,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["review_required"] is False
    assert data["status"] == "EVALUATED"


def test_typed_answer_is_never_gated(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "typed answer, no confidence at all"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["review_required"] is False
    assert data["status"] == "EVALUATED"


# ===========================================================================
# Persistence + ownership (Property 10)
# ===========================================================================

def test_report_is_persisted_and_retrievable(make_client):
    client = make_client(_CompleteProvider())
    submit = client.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "an answer worth grading"},
    )
    assert submit.status_code == 200, submit.text
    attempt_id = submit.json()["data"]["attempt_id"]

    fetch = client.get(f"/api/v1/optional/answers/{attempt_id}/report")
    assert fetch.status_code == 200, fetch.text
    report = fetch.json()["data"]
    assert report["attempt_id"] == attempt_id
    assert report["is_complete"] is True
    assert report["report_id"] is not None


def test_attempt_is_filed_under_topic(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    node_id = _first_topic_node_id(SessionLocal)
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "topic answer", "topic_node_id": node_id},
    )
    assert resp.status_code == 200, resp.text
    attempt_id = resp.json()["data"]["attempt_id"]

    db = SessionLocal()
    try:
        from app.core.optional.student_models import AnswerAttempt

        attempt = db.query(AnswerAttempt).filter(AnswerAttempt.id == attempt_id).one()
        assert attempt.topic_node_id == node_id
        assert attempt.student_id == STUDENT_ID
    finally:
        db.close()


def test_report_does_not_leak_across_students(make_client):
    # Student 1 submits and gets an attempt id.
    client1 = make_client(_CompleteProvider(), student_id=STUDENT_ID)
    submit = client1.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "student one's private answer"},
    )
    assert submit.status_code == 200, submit.text
    attempt_id = submit.json()["data"]["attempt_id"]

    # Student 2 must NOT be able to read student 1's report (ownership / P10).
    client2 = make_client(_CompleteProvider(), student_id=OTHER_STUDENT_ID)
    fetch = client2.get(f"/api/v1/optional/answers/{attempt_id}/report")
    assert fetch.status_code == 404


# ===========================================================================
# Validation + auth
# ===========================================================================

def test_empty_answer_is_400(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "   "},
    )
    assert resp.status_code == 400


def test_bad_mode_is_422(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TELEPATHY", "body_text": "answer"},
    )
    assert resp.status_code == 422


def test_unknown_subject_is_404(make_client):
    client = make_client(_CompleteProvider())
    resp = client.post(
        "/api/v1/optional/not-a-subject/answers",
        json={"mode": "TYPED", "body_text": "answer"},
    )
    assert resp.status_code == 404


def test_missing_report_is_404(make_client):
    client = make_client(_CompleteProvider())
    resp = client.get("/api/v1/optional/answers/999999/report")
    assert resp.status_code == 404


def test_submit_requires_auth():
    bare = TestClient(app)
    resp = bare.post(
        "/api/v1/optional/geography/answers",
        json={"mode": "TYPED", "body_text": "answer"},
    )
    assert resp.status_code == 401


def test_report_requires_auth():
    bare = TestClient(app)
    resp = bare.get("/api/v1/optional/answers/1/report")
    assert resp.status_code == 401
