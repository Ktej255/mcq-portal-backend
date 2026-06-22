"""Tests for the Geography Mapping module (Task 10 — R10).

Covers:
* seeder can produce UNREVIEWED rows that are GATED from the student view
  (design Property 8 / R17.3) — `GET /{slug}/mapping` returns nothing while
  content is unreviewed;
* seeder defaults to REVIEWED, making the 26-year corpus visible to students;
* reviewed content appears, grouped category-wise (R10.2) with its clickable
  3–4 line detail (R10.3) and year-sorted questions (R10.1);
* unknown subject → 404; auth required → 401.
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
from app.core.optional.models import OptionalSubject, OptionalReviewStatusEnum
from app.core.optional.mapping_models import MapLocation, MapQuestion
from app.core.optional.importer import import_geography_optional
from app.core.optional.mapping_seed import seed_geography_mapping

STUDENT_ID = 1


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
        # Seed with UNREVIEWED for testing the gating behaviour.
        seed_geography_mapping(seed, review_status="UNREVIEWED")
        seed.commit()
    finally:
        seed.close()

    yield engine, SessionLocal
    engine.dispose()


@pytest.fixture()
def client(seeded_engine):
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
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _get_mapping(client):
    resp = client.get("/api/v1/optional/geography/mapping")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# Honesty gate — draft (UNREVIEWED) seed is hidden from students (Property 8)
# ---------------------------------------------------------------------------

def test_draft_seed_is_gated_from_students(client, seeded_engine):
    _, SessionLocal = seeded_engine
    # The seeder created rows...
    db = SessionLocal()
    try:
        assert db.query(MapLocation).count() >= 1
        assert db.query(MapQuestion).count() >= 1
        # ...all UNREVIEWED.
        assert (
            db.query(MapLocation)
            .filter(MapLocation.review_status != OptionalReviewStatusEnum.UNREVIEWED)
            .count()
            == 0
        )
    finally:
        db.close()

    # ...but the student-facing endpoint shows nothing while unreviewed.
    data = _get_mapping(client)
    assert data["category_count"] == 0
    assert data["location_count"] == 0
    assert data["question_count"] == 0
    assert data["categories"] == []


# ---------------------------------------------------------------------------
# Reviewed content appears, grouped category-wise with detail (R10.2/R10.3)
# ---------------------------------------------------------------------------

def test_reviewed_location_and_question_appear_grouped(client, seeded_engine):
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        # Review one River location + its question.
        loc = (
            db.query(MapLocation)
            .filter(MapLocation.category == "River")
            .order_by(MapLocation.id.asc())
            .first()
        )
        loc.review_status = OptionalReviewStatusEnum.REVIEWED
        loc.authored = True
        q = (
            db.query(MapQuestion)
            .filter(MapQuestion.category == "River")
            .order_by(MapQuestion.id.asc())
            .first()
        )
        q.review_status = OptionalReviewStatusEnum.REVIEWED
        db.commit()
        loc_name = loc.name
        loc_detail = loc.detail
    finally:
        db.close()

    data = _get_mapping(client)
    assert data["location_count"] == 1
    assert data["question_count"] == 1
    assert data["category_count"] == 1
    group = data["categories"][0]
    assert group["category"] == "River"
    assert group["locations"][0]["name"] == loc_name
    # The clickable 3–4 line detail is present (R10.3).
    assert group["locations"][0]["detail"] == loc_detail
    assert group["questions"][0]["year"] >= 2000


def test_questions_year_sorted_within_category(client, seeded_engine):
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        subject = db.query(OptionalSubject).filter(OptionalSubject.slug == "geography").one()
        # Two reviewed River questions in different years.
        db.add(
            MapQuestion(
                subject_id=subject.id,
                year=2005,
                category="River",
                question_text="reviewed older",
                beyond_syllabus=False,
                display_order=0,
                review_status=OptionalReviewStatusEnum.REVIEWED,
            )
        )
        db.add(
            MapQuestion(
                subject_id=subject.id,
                year=2020,
                category="River",
                question_text="reviewed newer",
                beyond_syllabus=False,
                display_order=0,
                review_status=OptionalReviewStatusEnum.REVIEWED,
            )
        )
        db.commit()
    finally:
        db.close()

    data = _get_mapping(client)
    river = next(g for g in data["categories"] if g["category"] == "River")
    years = [q["year"] for q in river["questions"]]
    assert years == sorted(years, reverse=True)  # newest first


# ---------------------------------------------------------------------------
# Seeder honesty + 404 / 401
# ---------------------------------------------------------------------------

def test_seeder_marks_everything_unreviewed_when_requested(seeded_engine):
    _, SessionLocal = seeded_engine
    db = SessionLocal()
    try:
        locs = db.query(MapLocation).all()
        assert locs
        assert all(l.review_status == OptionalReviewStatusEnum.UNREVIEWED for l in locs)
        # Content is authored (verified corpus) even when gated as UNREVIEWED
        assert all(l.authored is True for l in locs)
    finally:
        db.close()


def test_unknown_subject_is_404(client):
    assert client.get("/api/v1/optional/not-a-subject/mapping").status_code == 404


def test_mapping_requires_auth():
    bare = TestClient(app)
    assert bare.get("/api/v1/optional/geography/mapping").status_code == 401


# ---------------------------------------------------------------------------
# 26-year reviewed corpus tests (Task 10.1 — production seeding)
# ---------------------------------------------------------------------------

@pytest.fixture()
def reviewed_engine():
    """Engine with the mapping corpus seeded as REVIEWED (production default)."""
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
        # Default = REVIEWED (visible to students)
        seed_geography_mapping(seed)
        seed.commit()
    finally:
        seed.close()

    yield engine, SessionLocal
    engine.dispose()


@pytest.fixture()
def reviewed_client(reviewed_engine):
    _, SessionLocal = reviewed_engine

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
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_reviewed_corpus_has_all_categories(reviewed_client):
    """R10.2: 26-year corpus organized topic-wise by feature category."""
    data = _get_mapping(reviewed_client)
    expected_categories = {
        "River", "Mountain", "Pass", "Lake", "Plateau",
        "Plain", "Island", "Peninsula", "Glacier", "Desert",
    }
    actual_categories = {g["category"] for g in data["categories"]}
    assert expected_categories == actual_categories


def test_reviewed_corpus_has_substantial_coverage(reviewed_client):
    """R10.1: 26 years of mapping questions present."""
    data = _get_mapping(reviewed_client)
    assert data["location_count"] >= 60  # at least 60 locations
    assert data["question_count"] >= 90  # at least 90 questions
    assert data["category_count"] >= 9   # at least 9 feature categories


def test_reviewed_corpus_locations_have_detail(reviewed_client):
    """R10.3: each location has 3-4 line UPSC-style detail."""
    data = _get_mapping(reviewed_client)
    for group in data["categories"]:
        for loc in group["locations"]:
            assert loc["detail"] is not None
            assert len(loc["detail"]) >= 50  # meaningful detail, not a stub


def test_reviewed_corpus_questions_span_26_years(reviewed_engine):
    """R10.1: questions cover 1998-2024 (26 years)."""
    _, SessionLocal = reviewed_engine
    db = SessionLocal()
    try:
        years = {
            y for (y,) in db.query(MapQuestion.year).distinct().all()
        }
        assert min(years) <= 1999
        assert max(years) >= 2024
        assert len(years) >= 20  # at least 20 distinct years represented
    finally:
        db.close()


def test_reviewed_corpus_is_idempotent(reviewed_engine):
    """Re-running the seeder produces the same count (no duplicates)."""
    _, SessionLocal = reviewed_engine
    db = SessionLocal()
    try:
        count_before = db.query(MapLocation).count()
        seed_geography_mapping(db)
        db.flush()
        count_after = db.query(MapLocation).count()
        assert count_before == count_after
    finally:
        db.close()
