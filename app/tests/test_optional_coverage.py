"""Tests for the Optional platform gap/progress coverage (Tasks 11.1/11.2/11.3).

Two layers:

* **Property-2 unit tests** for the pure coverage math
  (``compute_coverage_math``): bounded (``0 ≤ covered% ≤ 100``), exact
  (``covered% + remaining% == 100``), and equal to
  ``Σ weight(covered) / Σ weight(all) × 100`` — including a randomized
  invariant sweep and the equal-weight fallback when all weights are 0.

* **Endpoint tests** (``GET /{slug}/progress`` + ``POST /{slug}/progress/events``):
  the honest zero-state with no activity, coverage rising as events are
  recorded, the two percentages always summing to 100, per-paper breakdown,
  ownership isolation (design Property 10), node/subject validation, bad
  event-type → 422, unknown subject → 404, and auth gating (401).

DB strategy mirrors the other optional endpoint tests: an isolated in-memory
SQLite seeded with the Geography importer; ``get_db`` / ``get_current_user``
overridden so the route runs hermetically.
"""

from __future__ import annotations

import random

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
from app.core.optional.coverage import compute_coverage_math

STUDENT_ID = 1
OTHER_STUDENT_ID = 2


# ===========================================================================
# Property 2 — pure coverage math (bounded + exact + formula)
# ===========================================================================

def test_empty_universe_is_zero_covered_full_remaining():
    m = compute_coverage_math({}, set())
    assert m.covered_percent == 0.0
    assert m.remaining_percent == 100.0
    assert m.total_nodes == 0


def test_nothing_covered_is_zero_state():
    m = compute_coverage_math({1: 2.0, 2: 3.0, 3: 5.0}, set())
    assert m.covered_percent == 0.0
    assert m.remaining_percent == 100.0
    assert m.covered_nodes == 0
    assert m.total_nodes == 3


def test_all_covered_is_full():
    weights = {1: 2.0, 2: 3.0, 3: 5.0}
    m = compute_coverage_math(weights, {1, 2, 3})
    assert m.covered_percent == 100.0
    assert m.remaining_percent == 0.0
    assert m.covered_nodes == 3


def test_weighted_formula_is_exact():
    # Covered weight 2 + 3 = 5 of total 10 → 50%.
    weights = {1: 2.0, 2: 3.0, 3: 5.0}
    m = compute_coverage_math(weights, {1, 2})
    assert m.covered_percent == 50.0
    assert m.remaining_percent == 50.0
    assert m.covered_weight == 5.0


def test_equal_weight_fallback_when_all_zero():
    # All weights zero → equal weighting: 1 of 4 covered → 25%.
    weights = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    m = compute_coverage_math(weights, {3})
    assert m.covered_percent == 25.0
    assert m.remaining_percent == 75.0


def test_covered_id_outside_universe_is_ignored():
    weights = {1: 1.0, 2: 1.0}
    m = compute_coverage_math(weights, {1, 999})  # 999 not in universe
    assert m.covered_percent == 50.0
    assert m.covered_nodes == 1


def test_bounds_and_exactness_randomized():
    """Property 2 invariant sweep over random weights + covered subsets."""
    rng = random.Random(20260619)
    for _ in range(300):
        n = rng.randint(0, 30)
        ids = list(range(1, n + 1))
        # Mix of zero and positive weights (sometimes all-zero → fallback path).
        weights = {i: rng.choice([0.0, 0.0, rng.uniform(0.0, 10.0)]) for i in ids}
        covered = {i for i in ids if rng.random() < 0.5}
        m = compute_coverage_math(weights, covered)
        # Bounded.
        assert 0.0 <= m.covered_percent <= 100.0
        assert 0.0 <= m.remaining_percent <= 100.0
        # Exact (the two always sum to exactly 100).
        assert m.covered_percent + m.remaining_percent == 100.0


# ===========================================================================
# Endpoint fixtures
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
    """Factory: authenticated TestClient for a chosen student id."""
    _, SessionLocal = seeded_engine

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _build(student_id: int = STUDENT_ID) -> TestClient:
        class _FakeUser:
            id = student_id
            email = "test-student@upsc.local"
            google_uid = "test-student"

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()
        return TestClient(app)

    yield _build

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _top_node_ids(SessionLocal, limit: int | None = None) -> list[int]:
    db = SessionLocal()
    try:
        q = (
            db.query(SyllabusNode.id)
            .filter(SyllabusNode.parent_id.is_(None))
            .order_by(SyllabusNode.id.asc())
        )
        ids = [r[0] for r in q.all()]
        return ids[:limit] if limit else ids
    finally:
        db.close()


def _get_progress(client):
    resp = client.get("/api/v1/optional/geography/progress")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ===========================================================================
# R12.3 / R12.4 — endpoint coverage
# ===========================================================================

def test_zero_state_with_no_activity(make_client):
    client = make_client()
    data = _get_progress(client)
    assert data["slug"] == "geography"
    assert data["covered_percent"] == 0.0
    assert data["remaining_percent"] == 100.0
    assert data["covered_nodes"] == 0
    assert data["total_nodes"] >= 1
    assert data["papers"], "expected per-paper breakdown"


def test_percentages_always_sum_to_100(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    client = make_client()
    node_ids = _top_node_ids(SessionLocal)
    # Cover a few nodes and assert the invariant after each.
    for nid in node_ids[:3]:
        resp = client.post(
            "/api/v1/optional/geography/progress/events",
            json={"syllabus_node_id": nid, "event_type": "READ_COMPLETE"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["covered_percent"] + data["remaining_percent"] == 100.0


def test_coverage_rises_as_events_are_recorded(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    client = make_client()
    before = _get_progress(client)["covered_percent"]

    node_ids = _top_node_ids(SessionLocal)
    client.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": node_ids[0], "event_type": "READ_COMPLETE"},
    )
    after = _get_progress(client)["covered_percent"]
    assert after > before


def test_duplicate_events_do_not_double_count(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    client = make_client()
    nid = _top_node_ids(SessionLocal)[0]

    first = client.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": nid, "event_type": "READ_COMPLETE"},
    ).json()["data"]
    # Same node again (and a different qualifying type) — coverage is unchanged
    # because the node is already covered.
    second = client.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": nid, "event_type": "PRACTICE_PASS"},
    ).json()["data"]
    assert second["covered_percent"] == first["covered_percent"]
    assert second["covered_nodes"] == first["covered_nodes"]


# ===========================================================================
# Ownership (design Property 10) — another student's activity never leaks
# ===========================================================================

def test_progress_is_isolated_per_student(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    nid = _top_node_ids(SessionLocal)[0]

    # Student 1 records activity.
    c1 = make_client(STUDENT_ID)
    c1.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": nid, "event_type": "READ_COMPLETE"},
    )
    assert _get_progress(c1)["covered_nodes"] >= 1

    # Student 2 still sees the honest zero-state.
    c2 = make_client(OTHER_STUDENT_ID)
    data2 = _get_progress(c2)
    assert data2["covered_nodes"] == 0
    assert data2["covered_percent"] == 0.0


# ===========================================================================
# Validation + auth
# ===========================================================================

def test_bad_event_type_is_422(make_client, seeded_engine):
    _, SessionLocal = seeded_engine
    client = make_client()
    nid = _top_node_ids(SessionLocal)[0]
    resp = client.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": nid, "event_type": "WATCHED_VIDEO"},
    )
    assert resp.status_code == 422


def test_node_not_in_subject_is_404(make_client):
    client = make_client()
    resp = client.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": 9_999_999, "event_type": "READ_COMPLETE"},
    )
    assert resp.status_code == 404


def test_unknown_subject_is_404(make_client):
    client = make_client()
    assert client.get("/api/v1/optional/not-a-subject/progress").status_code == 404


def test_progress_requires_auth():
    bare = TestClient(app)
    assert bare.get("/api/v1/optional/geography/progress").status_code == 401


def test_event_requires_auth():
    bare = TestClient(app)
    resp = bare.post(
        "/api/v1/optional/geography/progress/events",
        json={"syllabus_node_id": 1, "event_type": "READ_COMPLETE"},
    )
    assert resp.status_code == 401
