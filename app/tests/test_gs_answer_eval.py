"""Tests for the GS LMS answer-writing + evaluation feature (DB + HTTP).

Covers storage, multi-page assembly, confidence gating, cache idempotence,
ownership/authorization, override preservation, upload validation, exam-type
gating, and GS↔Optional domain isolation.

Feature: unified-answer-evaluation-engine
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base

# Register the full model graph on Base.metadata.
import app.models.domain as domain_models  # noqa: F401
import app.core.gs.models as gs_models  # noqa: F401
import app.core.gs_lms.models as gs_lms_models  # noqa: F401
import app.core.gs_lms.student_models as gs_lms_student_models  # noqa: F401

from app.core.gs_lms.models import (
    GsLmsAnswerAttempt,
    GsLmsAnswerAttemptStatusEnum,
    GsLmsAnswerModeEnum,
    GsLmsAnswerSheetImage,
    GsLmsExamTypeEnum,
    GsLmsPyq,
    GsLmsPaperEnum,
)
from app.core.gs_lms.evaluation import service as eval_service
from app.core.storage.media_store import InMemoryMediaStore, LocalMediaStore, MediaStoreError


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    prefixes = ("gs_lms_", "gs_subjects", "users", "job_execution_registry")
    tables = [
        t for name, t in Base.metadata.tables.items()
        if any(name.startswith(p) for p in prefixes)
    ]
    Base.metadata.create_all(engine, tables=tables)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    Session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    s = Session()
    yield s
    s.close()


def _make_mains_pyq(db, *, marks=15, paper=GsLmsPaperEnum.GS1) -> GsLmsPyq:
    pyq = GsLmsPyq(
        subject_id=1,
        syllabus_node_id=1,
        exam_type=GsLmsExamTypeEnum.MAINS,
        year=2023,
        gs_paper=paper,
        question_text="Discuss the Big Bang.",
        answer_text="Model answer points.",
        marks=marks,
    )
    db.add(pyq)
    db.flush()
    return pyq


# ---------------------------------------------------------------------------
# Property 15: server-authored media reference round-trip + authorization
# ---------------------------------------------------------------------------
def test_property15_media_ref_server_authored_round_trip():
    store = InMemoryMediaStore()
    ref = store.put(b"PAGE-BYTES", content_type="image/png", owner_id=7, attempt_id=3, page_order=1)
    # Server-minted key (client never supplies it); encodes owner/attempt/page.
    assert ref.key.startswith("gslms/7/3/")
    assert store.open(ref.key, requester_id=7, is_evaluator=False, owner_id=7) == b"PAGE-BYTES"


def test_property15_media_authorization():
    store = InMemoryMediaStore()
    ref = store.put(b"X", content_type="image/png", owner_id=7, attempt_id=3, page_order=1)
    # A different, non-evaluator student cannot read.
    with pytest.raises(MediaStoreError):
        store.open(ref.key, requester_id=8, is_evaluator=False, owner_id=7)
    # An evaluator can.
    assert store.open(ref.key, requester_id=8, is_evaluator=True, owner_id=7) == b"X"


# ---------------------------------------------------------------------------
# Property 17: multi-page ascending-order assembly
# ---------------------------------------------------------------------------
def test_property17_multipage_ascending_assembly(db_session, tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORE_BACKEND", "local")
    monkeypatch.setenv("MEDIA_STORE_DIR", str(tmp_path))
    store = LocalMediaStore(str(tmp_path))

    attempt = GsLmsAnswerAttempt(
        student_id=1, mode=GsLmsAnswerModeEnum.HANDWRITTEN,
        status=GsLmsAnswerAttemptStatusEnum.DRAFT, review_acknowledged=True,
    )
    db_session.add(attempt)
    db_session.flush()

    # Upload pages OUT of order (3, 1, 2).
    for order, content in [(3, b"three"), (1, b"one"), (2, b"two")]:
        ref = store.put(content, content_type="image/png", owner_id=1, attempt_id=attempt.id, page_order=order)
        db_session.add(GsLmsAnswerSheetImage(
            attempt_id=attempt.id, student_id=1, media_ref=ref.key, page_order=order
        ))
    db_session.flush()

    images = eval_service._load_images(db_session, attempt)
    assert images == [b"one", b"two", b"three"]


# ---------------------------------------------------------------------------
# Property 18: confidence gating
# ---------------------------------------------------------------------------
def test_property18_confidence_gate(monkeypatch):
    monkeypatch.setattr(eval_service, "GS_OCR_CONFIDENCE_THRESHOLD", 0.6)
    low = GsLmsAnswerAttempt(
        student_id=1, mode=GsLmsAnswerModeEnum.HANDWRITTEN,
        status=GsLmsAnswerAttemptStatusEnum.DRAFT,
        ocr_confidence=0.4, review_acknowledged=False,
    )
    assert eval_service.confidence_gate_blocks(low) is True
    # Acknowledged review clears the gate.
    low.review_acknowledged = True
    assert eval_service.confidence_gate_blocks(low) is False
    # High confidence is never gated.
    high = GsLmsAnswerAttempt(
        student_id=1, mode=GsLmsAnswerModeEnum.HANDWRITTEN,
        status=GsLmsAnswerAttemptStatusEnum.DRAFT,
        ocr_confidence=0.95, review_acknowledged=False,
    )
    assert eval_service.confidence_gate_blocks(high) is False
    # Typed answers are never gated.
    typed = GsLmsAnswerAttempt(
        student_id=1, mode=GsLmsAnswerModeEnum.TYPED,
        status=GsLmsAnswerAttemptStatusEnum.SUBMITTED, review_acknowledged=False,
    )
    assert eval_service.confidence_gate_blocks(typed) is False


# ---------------------------------------------------------------------------
# Property 21: cache idempotence
# ---------------------------------------------------------------------------
def test_property21_cache_idempotence():
    from app.core.inference.contracts import IInferenceProvider, InferenceResponse
    from app.core.evaluation.cache import InMemoryReportCache
    from app.core.evaluation.engine import EvaluationEngine, EvaluationInput
    from app.core.evaluation.providers.registry import ProviderRegistry
    from app.core.evaluation.rubric import PrebuiltRubricStrategy
    from app.core.evaluation.providers.evaluation import MockEvaluationInferenceProvider

    class _Counting(IInferenceProvider):
        def __init__(self):
            self.calls = 0
            self._inner = MockEvaluationInferenceProvider()
        def generate(self, request):
            self.calls += 1
            return self._inner.generate(request)
        async def generate_async(self, request):
            return self.generate(request)

    prov = _Counting()
    reg = ProviderRegistry()
    reg.register("mock", lambda _cfg: prov)
    eng = EvaluationEngine(reg, cache=InMemoryReportCache())
    inp = EvaluationInput(answer_text="same answer", rubric_strategy=PrebuiltRubricStrategy("r"), provider_key="mock")
    r1 = eng.evaluate(inp)
    r2 = eng.evaluate(EvaluationInput(answer_text="same answer", rubric_strategy=PrebuiltRubricStrategy("r"), provider_key="mock"))
    assert r1.is_complete and r2.is_complete
    assert prov.calls == 1  # second evaluation served from cache, no new call


# ---------------------------------------------------------------------------
# HTTP tests (ownership, empty rejection, upload validation, exam-type gating)
# ---------------------------------------------------------------------------
class _FakeUser:
    def __init__(self, uid, role=""):
        self.id = uid
        self.role = role


@pytest.fixture()
def client(db_session, monkeypatch):
    monkeypatch.setenv("MEDIA_STORE_BACKEND", "memory")
    from app.api.dependencies import get_current_user
    from app.db.session import get_db
    import app.main as main

    def _override_db():
        yield db_session

    main.app.dependency_overrides[get_db] = _override_db
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser(1)
    c = TestClient(main.app)
    c._db = db_session  # type: ignore[attr-defined]
    yield c
    main.app.dependency_overrides.clear()


def test_property23_empty_typed_rejected(client):
    r = client.post("/api/v1/gs-lms/geography/answers/typed", json={"raw_text": "   "})
    assert r.status_code == 400


def test_property14_exam_type_gating(client, db_session):
    # A PRELIMS PYQ cannot accept a descriptive answer.
    prelims = GsLmsPyq(
        subject_id=1, syllabus_node_id=1, exam_type=GsLmsExamTypeEnum.PRELIMS,
        year=2022, question_text="MCQ-style", marks=None,
    )
    db_session.add(prelims)
    db_session.flush()
    r = client.post(
        "/api/v1/gs-lms/geography/answers/typed",
        json={"raw_text": "an answer", "pyq_id": prelims.id},
    )
    assert r.status_code == 422


def test_typed_answer_end_to_end(client, db_session):
    pyq = _make_mains_pyq(db_session)
    r = client.post(
        "/api/v1/gs-lms/geography/answers/typed",
        json={"raw_text": "The Big Bang was an expansion of space. " * 10, "pyq_id": pyq.id},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] in ("completed", "degraded")
    attempt_id = data["attempt_id"]
    # Report is retrievable and marks-normalized within bounds.
    rep = client.get(f"/api/v1/gs-lms/geography/answers/{attempt_id}/report").json()["data"]
    assert rep["max_marks"] == 15
    if rep["marks_awarded"] is not None:
        assert 0.0 <= rep["marks_awarded"] <= 15.0


def test_property20_ownership_404_for_other_student(client, db_session, monkeypatch):
    pyq = _make_mains_pyq(db_session)
    r = client.post(
        "/api/v1/gs-lms/geography/answers/typed",
        json={"raw_text": "x " * 20, "pyq_id": pyq.id},
    )
    attempt_id = r.json()["data"]["attempt_id"]

    # Switch the authenticated user to a different student.
    from app.api.dependencies import get_current_user
    import app.main as main
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser(999)

    r2 = client.get(f"/api/v1/gs-lms/geography/answers/{attempt_id}/report")
    assert r2.status_code == 404


def test_property19_override_preserves_original(client, db_session):
    pyq = _make_mains_pyq(db_session)
    r = client.post(
        "/api/v1/gs-lms/geography/answers/typed",
        json={"raw_text": "x " * 20, "pyq_id": pyq.id},
    )
    attempt_id = r.json()["data"]["attempt_id"]

    # Become an evaluator and override.
    from app.api.dependencies import get_current_user
    import app.main as main
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser(2, role="EVALUATOR")

    ov = client.post(
        f"/api/v1/gs-lms/geography/answers/{attempt_id}/override",
        json={
            "sections": {"introduction": {"feedback": "overridden", "score": 9.0}},
            "incomplete_sections": [],
            "marks_awarded": 12.0,
        },
    )
    assert ov.status_code == 200
    assert ov.json()["data"]["overridden"] is True

    # Original machine report preserved on the row.
    from app.core.gs_lms.models import GsLmsEvaluationReport
    report = (
        db_session.query(GsLmsEvaluationReport)
        .filter(GsLmsEvaluationReport.attempt_id == attempt_id)
        .one()
    )
    assert report.original_report is not None
    assert "sections" in report.original_report
    assert report.overridden_by == 2


def test_property19_override_denied_for_non_evaluator(client, db_session):
    pyq = _make_mains_pyq(db_session)
    r = client.post(
        "/api/v1/gs-lms/geography/answers/typed",
        json={"raw_text": "x " * 20, "pyq_id": pyq.id},
    )
    attempt_id = r.json()["data"]["attempt_id"]
    ov = client.post(
        f"/api/v1/gs-lms/geography/answers/{attempt_id}/override",
        json={"sections": {}, "incomplete_sections": []},
    )
    assert ov.status_code == 403


def test_property16_upload_rejects_bad_extension(client, db_session):
    pyq = _make_mains_pyq(db_session)
    r = client.post(
        "/api/v1/gs-lms/geography/answers/handwritten",
        json={"pyq_id": pyq.id},
    )
    attempt_id = r.json()["data"]["attempt_id"]
    files = {"image": ("answer.txt", b"not an image", "text/plain")}
    up = client.post(
        f"/api/v1/gs-lms/geography/answers/{attempt_id}/pages",
        files=files,
        data={"page_order": "1"},
    )
    assert up.status_code == 422


# ---------------------------------------------------------------------------
# Domain isolation (Requirement 2 / Property: import discipline)
# ---------------------------------------------------------------------------
def _imports_of(module_name: str) -> set[str]:
    import ast, pathlib
    spec = importlib.util.find_spec(module_name)
    assert spec and spec.origin
    src = pathlib.Path(spec.origin).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_shared_core_does_not_import_domains():
    import app.core.evaluation as pkg
    for mod in pkgutil.walk_packages(pkg.__path__, prefix="app.core.evaluation."):
        imports = _imports_of(mod.name)
        assert not any(i.startswith("app.core.gs_lms") for i in imports), mod.name
        assert not any(i.startswith("app.core.optional") for i in imports), mod.name


def test_gs_evaluation_does_not_import_optional():
    for mod_name in [
        "app.core.gs_lms.evaluation.rubric",
        "app.core.gs_lms.evaluation.service",
        "app.api.v1.gs_lms.answers",
    ]:
        imports = _imports_of(mod_name)
        assert not any(i.startswith("app.core.optional") for i in imports), mod_name
        assert not any(i.startswith("app.api.v1.optional") for i in imports), mod_name
