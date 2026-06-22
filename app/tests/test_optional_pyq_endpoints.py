"""Endpoint tests for the Optional Subjects Platform PYQ explorer API (Task 7.2).

Exercises ``GET /api/v1/optional/{slug}/pyqs`` — the student-facing PYQ listing
that powers the frontend ``PyqExplorer`` (R6.1/R6.2/R6.3/R6.5).

DB strategy (mirrors ``test_optional_content_endpoints.py``): an isolated
in-memory SQLite DB built from the optional models' own metadata, seeded by
running BOTH the real Geography importer (task 4.1 — REVIEWED Section-A PYQs)
AND the task-7.1 PYQ seeder (DRAFT / UNREVIEWED corpus). The app's ``get_db`` and
``get_current_user`` dependencies are overridden so the route runs against that
seeded session under an authenticated test user — hermetic, no Postgres.

Asserts:
* the endpoint returns REVIEWED importer PYQs (student-visible);
* it HIDES the UNREVIEWED draft-seed PYQs (honesty gate / design Property 8);
* year / paper / section filters return only matching PYQs (R6.5);
* default ordering is year-wise (R6.1);
* unknown subject is 404, unauthenticated is 401;
* importer PYQs come back REVIEWED, and the legacy NULL backfill repairs rows
  that pre-date the review_status column.
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
    Pyq,
    PaperLabelEnum,
    SectionLabelEnum,
)
from app.core.optional.importer import (
    import_geography_optional,
    backfill_pyq_review_status,
)
from app.core.optional.pyq_seed import seed_geography_pyqs, SEEDER_ACTOR

IMPORTER_ACTOR = "geo-optional-importer"


# ---------------------------------------------------------------------------
# Fixtures: seeded in-memory DB + auth-overridden TestClient
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_engine():
    """In-memory SQLite seeded with the importer (REVIEWED) + 7.1 seed (DRAFT)."""
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
        # Task 4.1 importer: REVIEWED Section-A PYQs from the deep notes.
        import_geography_optional(seed, review_status="REVIEWED")
        # Task 7.1 seeder: DRAFT / UNREVIEWED corpus across both papers.
        seed_geography_pyqs(seed)
        # Idempotent backfill for any legacy NULL importer PYQ rows.
        backfill_pyq_review_status(seed)
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


def _get_pyqs(client, **params):
    resp = client.get("/api/v1/optional/geography/pyqs", params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


# ---------------------------------------------------------------------------
# Review gate: REVIEWED importer PYQs shown, UNREVIEWED draft seed hidden
# ---------------------------------------------------------------------------

def test_returns_reviewed_importer_pyqs(client, seeded_engine):
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        importer_texts = {
            t for (t,) in db.query(Pyq.question_text)
            .filter(
                Pyq.created_by == IMPORTER_ACTOR,
                Pyq.review_status == OptionalReviewStatusEnum.REVIEWED,
            ).all()
        }
    finally:
        db.close()
    assert importer_texts, "importer must have created REVIEWED PYQs"

    data = _get_pyqs(client)
    returned_texts = {p["question_text"] for p in data["pyqs"]}
    # Every reviewed importer PYQ is present in the student-visible listing.
    assert importer_texts.issubset(returned_texts)
    # And everything returned is REVIEWED.
    assert all(p["review_status"] == "REVIEWED" for p in data["pyqs"])


def test_hides_unreviewed_draft_seed_pyqs(client, seeded_engine):
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        # Identify draft-seed rows by id (NOT by text: a few draft questions
        # share wording with an importer PYQ, so a text comparison would be a
        # false positive — the gate operates per row).
        draft_ids = {
            i for (i,) in db.query(Pyq.id)
            .filter(Pyq.created_by == SEEDER_ACTOR).all()
        }
        # Confirm the draft seed is genuinely UNREVIEWED in the DB.
        statuses = {
            s for (s,) in db.query(Pyq.review_status)
            .filter(Pyq.created_by == SEEDER_ACTOR).all()
        }
    finally:
        db.close()
    assert draft_ids, "task-7.1 seeder must have created draft PYQs"
    assert statuses == {OptionalReviewStatusEnum.UNREVIEWED}

    data = _get_pyqs(client)
    returned_ids = {p["id"] for p in data["pyqs"]}
    # No UNREVIEWED draft-seed row leaks into the student-visible listing.
    leaked = draft_ids & returned_ids
    assert not leaked, f"UNREVIEWED draft PYQs leaked into the listing: {leaked}"


def test_importer_pyqs_are_reviewed_after_backfill(seeded_engine):
    """Legacy NULL importer rows are repaired to REVIEWED by the backfill."""
    engine, SessionLocal = seeded_engine

    db = SessionLocal()
    try:
        # Simulate legacy rows that pre-date the review_status column: set the
        # importer PYQs' review_status back to NULL.
        db.query(Pyq).filter(Pyq.created_by == IMPORTER_ACTOR).update(
            {Pyq.review_status: None}, synchronize_session=False
        )
        db.commit()
        null_count = db.query(Pyq).filter(
            Pyq.created_by == IMPORTER_ACTOR, Pyq.review_status.is_(None)
        ).count()
        assert null_count > 0

        updated = backfill_pyq_review_status(db)
        db.commit()
        assert updated == null_count

        # Re-running is idempotent (touches nothing).
        assert backfill_pyq_review_status(db) == 0

        remaining_null = db.query(Pyq).filter(
            Pyq.created_by == IMPORTER_ACTOR, Pyq.review_status.is_(None)
        ).count()
        assert remaining_null == 0
        # The draft seed is untouched (still UNREVIEWED, never backfilled).
        seed_statuses = {
            s for (s,) in db.query(Pyq.review_status)
            .filter(Pyq.created_by == SEEDER_ACTOR).all()
        }
        assert seed_statuses == {OptionalReviewStatusEnum.UNREVIEWED}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Filters (R6.2 / R6.3 / R6.5) + sort (R6.1)
# ---------------------------------------------------------------------------

def test_default_sort_is_year_descending(client):
    data = _get_pyqs(client)
    years = [p["year"] for p in data["pyqs"]]
    assert years == sorted(years, reverse=True), "default listing must be year-wise (desc)"
    assert data["filters"]["sort"] == "year_desc"


def test_sort_year_ascending(client):
    data = _get_pyqs(client, sort="year_asc")
    years = [p["year"] for p in data["pyqs"]]
    assert years == sorted(years)


def test_facets_expose_available_filter_values(client):
    data = _get_pyqs(client)
    facets = data["facets"]
    assert facets["years"], "expected available years"
    # Importer PYQs are all Paper I / Section A.
    assert PaperLabelEnum.PAPER_I.value in facets["papers"]
    assert SectionLabelEnum.SECTION_A.value in facets["sections"]


def test_filter_by_year_returns_only_matching(client):
    data = _get_pyqs(client)
    target_year = data["facets"]["years"][0]
    filtered = _get_pyqs(client, year=target_year)
    assert filtered["pyqs"], "expected at least one PYQ for an advertised year"
    assert all(p["year"] == target_year for p in filtered["pyqs"])
    assert filtered["filters"]["year"] == target_year


def test_filter_by_paper_returns_only_matching(client):
    data = _get_pyqs(client, paper="PAPER_I")
    assert data["pyqs"], "expected Paper I PYQs"
    assert all(p["paper_label"] == "PAPER_I" for p in data["pyqs"])


def test_filter_by_section_returns_only_matching(client):
    data = _get_pyqs(client, section="SECTION_A")
    assert data["pyqs"], "expected Section A PYQs"
    assert all(p["section_label"] == "SECTION_A" for p in data["pyqs"])


def test_combined_filters_intersect(client):
    data = _get_pyqs(client, paper="PAPER_I", section="SECTION_A")
    assert data["pyqs"]
    for p in data["pyqs"]:
        assert p["paper_label"] == "PAPER_I"
        assert p["section_label"] == "SECTION_A"


def test_filter_with_no_matches_returns_empty_honestly(client):
    # Paper II currently has NO reviewed PYQs (importer only made Paper I A);
    # the draft Paper II seed is UNREVIEWED and gated out.
    data = _get_pyqs(client, paper="PAPER_II")
    assert data["total"] == 0
    assert data["pyqs"] == []


def test_invalid_paper_is_422(client):
    resp = client.get("/api/v1/optional/geography/pyqs", params={"paper": "PAPER_X"})
    assert resp.status_code == 422


def test_invalid_sort_is_422(client):
    resp = client.get("/api/v1/optional/geography/pyqs", params={"sort": "bogus"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 404 / 401
# ---------------------------------------------------------------------------

def test_unknown_subject_is_404(client):
    resp = client.get("/api/v1/optional/not-a-subject/pyqs")
    assert resp.status_code == 404


def test_pyqs_requires_auth():
    # No dependency overrides installed -> the real auth check applies.
    bare = TestClient(app)
    resp = bare.get("/api/v1/optional/geography/pyqs")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Topic-wise grouping (Task 7.3 / R6.4) — GET /{slug}/pyqs/by-topic
# ---------------------------------------------------------------------------

def _get_by_topic(client):
    resp = client.get("/api/v1/optional/geography/pyqs/by-topic")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    return body["data"]


def test_by_topic_groups_reviewed_pyqs_under_topic_nodes(client, seeded_engine):
    """REVIEWED PYQs come back grouped under their syllabus topic node (R6.4)."""
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        # Build the expected node_id -> set(question_text) mapping from the
        # REVIEWED importer corpus directly.
        expected: dict[int, set[str]] = {}
        for node_id, text in (
            db.query(Pyq.topic_node_id, Pyq.question_text)
            .filter(
                Pyq.created_by == IMPORTER_ACTOR,
                Pyq.review_status == OptionalReviewStatusEnum.REVIEWED,
                Pyq.topic_node_id.isnot(None),
            )
            .all()
        ):
            expected.setdefault(node_id, set()).add(text)
    finally:
        db.close()
    assert expected, "importer must have produced REVIEWED, topic-mapped PYQs"

    data = _get_by_topic(client)
    assert data["group_count"] == len(data["groups"])
    assert data["group_count"] > 0

    by_node = {g["node_id"]: g for g in data["groups"]}
    # Every expected topic node is represented with exactly its PYQs.
    for node_id, texts in expected.items():
        assert node_id in by_node, f"topic node {node_id} missing from grouped view"
        group = by_node[node_id]
        returned = {p["question_text"] for p in group["pyqs"]}
        assert texts.issubset(returned)
        assert group["pyq_count"] == len(group["pyqs"])
        # Every grouped PYQ is REVIEWED and carries the group's node id.
        assert all(p["review_status"] == "REVIEWED" for p in group["pyqs"])
        assert all(p["topic_node_id"] == node_id for p in group["pyqs"])
        # The node is located within the syllabus structure (paper/section).
        assert group["paper_label"] in ("PAPER_I", "PAPER_II")
        assert group["title"]


def test_by_topic_hides_unreviewed_draft_seed(client, seeded_engine):
    """No UNREVIEWED draft-seed PYQ appears in any topic group (Property 8)."""
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        draft_ids = {
            i for (i,) in db.query(Pyq.id)
            .filter(Pyq.created_by == SEEDER_ACTOR).all()
        }
    finally:
        db.close()
    assert draft_ids, "task-7.1 seeder must have created draft PYQs"

    data = _get_by_topic(client)
    grouped_ids = {p["id"] for g in data["groups"] for p in g["pyqs"]}
    leaked = draft_ids & grouped_ids
    assert not leaked, f"UNREVIEWED draft PYQs leaked into the topic groups: {leaked}"


def test_by_topic_pyqs_are_year_sorted_within_group(client):
    data = _get_by_topic(client)
    for group in data["groups"]:
        years = [p["year"] for p in group["pyqs"]]
        assert years == sorted(years, reverse=True), (
            f"group {group['node_id']} PYQs must be year-wise (desc)"
        )


def test_topic_node_id_filter_on_flat_listing(client):
    """The /pyqs topic_node_id filter returns only that topic's PYQs (R6.4)."""
    data = _get_by_topic(client)
    assert data["groups"], "expected at least one topic group"
    target = data["groups"][0]
    node_id = target["node_id"]

    resp = client.get(
        "/api/v1/optional/geography/pyqs", params={"topic_node_id": node_id}
    )
    assert resp.status_code == 200, resp.text
    listing = resp.json()["data"]
    assert listing["pyqs"], "expected PYQs for the target topic node"
    assert all(p["topic_node_id"] == node_id for p in listing["pyqs"])
    # The filtered listing matches the group's PYQ set exactly.
    assert {p["id"] for p in listing["pyqs"]} == {p["id"] for p in target["pyqs"]}


def test_topic_node_id_filter_unknown_node_returns_empty(client):
    resp = client.get(
        "/api/v1/optional/geography/pyqs", params={"topic_node_id": 9_999_999}
    )
    assert resp.status_code == 200, resp.text
    listing = resp.json()["data"]
    assert listing["total"] == 0
    assert listing["pyqs"] == []


def test_by_topic_unknown_subject_is_404(client):
    resp = client.get("/api/v1/optional/not-a-subject/pyqs/by-topic")
    assert resp.status_code == 404


def test_by_topic_requires_auth():
    bare = TestClient(app)
    resp = bare.get("/api/v1/optional/geography/pyqs/by-topic")
    assert resp.status_code == 401
