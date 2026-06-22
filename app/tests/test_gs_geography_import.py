"""Tests for the GS Geography content importer (Master Plan A3/B3, GATE-1).

The importer is the backend half of the no-loss migration that moves GS
Geography content onto FastAPI/Postgres. These tests pin:
- counts parity with the committed extractor artifact (no content loss),
- the faithful session<->lesson join (days 1..20 carry session metadata; the
  scene-only authored lessons 21..30 do not fabricate session data),
- idempotency (re-import replaces, never duplicates),
- that the full authored payload (incl. day-specific drills) is preserved.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base

# Importing the models registers every ``gs_*`` table on Base.metadata.
from app.core.gs import models as gs_models  # noqa: F401
from app.core.gs.models import GsSubject, GsDayLesson, GsReviewStatusEnum
from app.core.gs.importer import (
    import_gs_geography,
    load_artifact,
    _build_source_report,
)


def _make_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_import_matches_artifact_counts_no_loss():
    db = _make_session()
    try:
        counts = import_gs_geography(db)
        source = _build_source_report(load_artifact())

        assert counts["subjects"] == 1
        for key, expected in source.items():
            assert counts[key] == expected, f"{key}: imported {counts[key]} != source {expected}"

        # Geography ships 30 authored lesson modules and a 20-day session plan.
        assert counts["day_lessons"] == 30
        assert counts["lessons_with_session"] == 20
        assert counts["lessons_scene_only"] == 10
    finally:
        db.close()


def test_subject_and_rows_persisted():
    db = _make_session()
    try:
        import_gs_geography(db)
        subject = db.query(GsSubject).filter(GsSubject.slug == "geography").one()
        assert subject.name == "Geography"

        rows = db.query(GsDayLesson).filter(GsDayLesson.subject_id == subject.id).all()
        assert len(rows) == 30
        # day_number covers 1..30 with no gaps/dupes.
        assert sorted(r.day_number for r in rows) == list(range(1, 31))
        # Authored content imported as student-visible REVIEWED by default.
        assert all(r.review_status == GsReviewStatusEnum.REVIEWED for r in rows)
        # Every lesson carries its Watch scenes.
        assert all(r.scenes and len(r.scenes) >= 1 for r in rows)
    finally:
        db.close()


def test_session_join_is_faithful():
    db = _make_session()
    try:
        import_gs_geography(db)
        by_day = {
            r.day_number: r
            for r in db.query(GsDayLesson).all()
        }
        # Day 1 has a session -> session metadata present.
        d1 = by_day[1]
        assert d1.has_session is True
        assert d1.session_title  # curriculum title
        assert d1.subtopics and len(d1.subtopics) >= 1
        assert d1.content["session"] is not None
        assert d1.content["session"]["chapter"]

        # Days 21..30 are authored scene-only lessons (no session) -> no
        # fabricated session metadata.
        d25 = by_day[25]
        assert d25.has_session is False
        assert d25.session_title is None
        assert d25.subtopics is None
        assert d25.content["session"] is None
        assert d25.scenes  # still has authored scenes
    finally:
        db.close()


def test_full_authored_payload_preserved():
    db = _make_session()
    try:
        import_gs_geography(db)
        d1 = db.query(GsDayLesson).filter(GsDayLesson.day_number == 1).one()
        exports = d1.content["lesson"]
        # Both the primary lesson export and the day-specific drills survive.
        assert "geographyDay1PortalLesson" in exports
        assert "geographyDay1MapRelationshipDrills" in exports
        assert len(exports["geographyDay1MapRelationshipDrills"]) >= 1
    finally:
        db.close()


def test_import_is_idempotent():
    db = _make_session()
    try:
        first = import_gs_geography(db)
        second = import_gs_geography(db)
        assert first == second
        # Exactly one subject and 30 lessons after two runs (no duplication).
        assert db.query(GsSubject).count() == 1
        assert db.query(GsDayLesson).count() == 30
    finally:
        db.close()


def test_review_status_can_gate_content():
    db = _make_session()
    try:
        import_gs_geography(db, review_status="UNREVIEWED")
        rows = db.query(GsDayLesson).all()
        assert rows and all(r.review_status == GsReviewStatusEnum.UNREVIEWED for r in rows)
    finally:
        db.close()
