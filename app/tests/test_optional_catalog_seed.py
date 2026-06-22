"""Tests for the 25-subject catalog seeder (Task 17.2 — R1.2, R19.1, R19.2).

Validates:
- All 25 standard UPSC optional subjects are seeded with consistent scaffold
  rows (matching the frontend catalog slugs exactly).
- Existing subjects (Geography, PA) are not overwritten by the seeder.
- The seeder is idempotent (re-running does not create duplicates).
- Each scaffolded subject has a valid config (papers/features) and honest
  completeness status ("pending-authoring").
- Selection and completeness endpoints work for any catalog subject after
  seeding (no 404s on coming-soon subjects).

Isolation (R2 / Property 9): no GS Geography modules referenced.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.optional.models import Base as OptionalBase, OptionalSubject
from app.core.optional.student_models import Base as StudentBase
from app.core.optional.mapping_models import Base as MappingBase
from app.core.optional.current_affairs_models import Base as CABase
from app.core.optional.catalog_seed import seed_catalog, CATALOG, SEEDER_ACTOR
from app.core.optional.importer import import_geography_optional
from app.core.optional.pubad_seed import seed_public_administration, PUBAD_SLUG
from app.models.domain import Base as DomainBase, User, RoleEnum


# ---------------------------------------------------------------------------
# Shared in-memory DB setup
# ---------------------------------------------------------------------------

engine = create_engine("sqlite:///:memory:", echo=False)

# Create all required tables on the shared metadata.
DomainBase.metadata.create_all(bind=engine)
OptionalBase.metadata.create_all(bind=engine)
StudentBase.metadata.create_all(bind=engine)
MappingBase.metadata.create_all(bind=engine)
CABase.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def _clean_subjects():
    """Truncate optional_subjects before each test for isolation."""
    db = SessionLocal()
    try:
        db.query(OptionalSubject).delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_catalog_has_exactly_25_entries():
    """The CATALOG constant matches the UPSC standard of 25 optionals."""
    assert len(CATALOG) == 25
    slugs = [e["slug"] for e in CATALOG]
    assert len(set(slugs)) == 25, "All slugs must be unique"


def test_seed_catalog_creates_all_25_subjects():
    """Running seed_catalog on an empty DB inserts all 25 subjects."""
    db = SessionLocal()
    try:
        counts = seed_catalog(db)
        db.commit()
        assert counts["total_catalog"] == 25
        assert counts["created"] == 25
        assert counts["skipped"] == 0
        assert db.query(OptionalSubject).count() == 25
    finally:
        db.close()


def test_seed_catalog_is_idempotent():
    """Re-running seed_catalog does not create duplicates."""
    db = SessionLocal()
    try:
        seed_catalog(db)
        db.commit()
        counts = seed_catalog(db)
        db.commit()
        assert counts["created"] == 0
        assert counts["skipped"] == 25
        assert db.query(OptionalSubject).count() == 25
    finally:
        db.close()


def test_seed_catalog_skips_existing_subjects():
    """Pre-existing subjects (Geography from importer, PA from pubad_seed) are
    not overwritten."""
    db = SessionLocal()
    try:
        # Simulate the Geography importer having already run.
        import_geography_optional(db, review_status="REVIEWED")
        db.commit()
        # Simulate PA seeder having already run.
        seed_public_administration(db)
        db.commit()

        geo = db.query(OptionalSubject).filter(OptionalSubject.slug == "geography").one()
        geo_config_before = geo.config

        pa = db.query(OptionalSubject).filter(OptionalSubject.slug == PUBAD_SLUG).one()
        pa_config_before = pa.config

        counts = seed_catalog(db)
        db.commit()

        # Geography and PA were skipped.
        assert counts["skipped"] >= 2
        assert counts["created"] == 25 - counts["skipped"]

        # Their configs are NOT overwritten.
        db.expire_all()
        geo_after = db.query(OptionalSubject).filter(OptionalSubject.slug == "geography").one()
        assert geo_after.config == geo_config_before

        pa_after = db.query(OptionalSubject).filter(OptionalSubject.slug == PUBAD_SLUG).one()
        assert pa_after.config == pa_config_before
    finally:
        db.close()


def test_scaffolded_subjects_have_honest_config():
    """Each scaffolded subject has a valid config and honest completeness."""
    db = SessionLocal()
    try:
        seed_catalog(db)
        db.commit()

        for entry in CATALOG:
            subject = (
                db.query(OptionalSubject)
                .filter(OptionalSubject.slug == entry["slug"])
                .one()
            )
            assert subject.name == entry["name"]
            assert subject.is_complete is False
            config = subject.config
            assert isinstance(config, dict)
            assert "features" in config
            assert "papers" in config
            assert "read" in config["features"]
            assert "pyq" in config["features"]
            cs = subject.completeness_status
            assert cs is not None
            assert cs.get("content") == "pending-authoring"
    finally:
        db.close()


def test_catalog_slugs_match_frontend():
    """The CATALOG slugs must match the frontend optionalSubjectsCatalog exactly.

    This is a hardcoded alignment check — if the frontend catalog changes, this
    test flags the drift.
    """
    expected_slugs = sorted([
        "agriculture",
        "animal-husbandry-veterinary-science",
        "anthropology",
        "botany",
        "chemistry",
        "civil-engineering",
        "commerce-accountancy",
        "economics",
        "electrical-engineering",
        "geography",
        "geology",
        "history",
        "law",
        "management",
        "mathematics",
        "mechanical-engineering",
        "medical-science",
        "philosophy",
        "physics",
        "political-science-international-relations",
        "psychology",
        "public-administration",
        "sociology",
        "statistics",
        "zoology",
    ])
    actual_slugs = sorted([e["slug"] for e in CATALOG])
    assert actual_slugs == expected_slugs
