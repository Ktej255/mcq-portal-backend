"""Tests for GS LMS day-lesson bridge and progress migration (Task 10.3).

Validates:
  - Property 21: Day-lesson bridge mapping integrity (no two nodes share the
    same day_lesson_id, all references valid)
  - Property 22: Progress migration data preservation (no data loss)
  - R11.5: Atomic rollback on migration failure

Requirements traced: 11.1, 11.2, 11.4, 11.5
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.core.gs.models import GsSubject, GsDayLesson, GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
    GsLmsNodeTypeEnum,
    GsLmsSectionLabelEnum,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress
from app.core.gs_lms.migration import (
    validate_bridge_mapping,
    migrate_progress,
    rollback_migration,
    MigrationError,
    _extract_completed_day_numbers,
)

# Ensure all models are registered on Base.metadata.
from app.models.domain import User, RoleEnum, StudentSubjectProgress  # noqa: F401
from app.core.gs_lms import models as _gs_lms_models  # noqa: F401
from app.core.gs_lms import student_models as _gs_lms_student  # noqa: F401


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def db_session():
    """Create an in-memory SQLite DB with required tables and return a session."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name in (
            "users",
            "gs_subjects",
            "gs_day_lessons",
            "gs_lms_syllabus_nodes",
            "gs_lms_content_sections",
            "gs_lms_student_section_progress",
            "student_subject_progress",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    # Seed required entities.
    subject = GsSubject(id=1, name="Geography", slug="geography")
    session.add(subject)

    # Create a test user.
    user = User(
        id=100,
        email="student@test.com",
        role=RoleEnum.STUDENT,
        google_uid="test-uid-100",
    )
    session.add(user)
    session.commit()

    yield session

    session.close()
    engine.dispose()


def _create_day_lesson(db_session, day_number: int, lesson_id: int | None = None) -> GsDayLesson:
    """Helper: create a GsDayLesson record."""
    lesson = GsDayLesson(
        id=lesson_id or day_number,
        subject_id=1,
        day_number=day_number,
        title=f"Day {day_number} Lesson",
        has_session=True,
        review_status=GsReviewStatusEnum.REVIEWED,
        display_order=day_number,
        created_by="test",
        updated_by="test",
    )
    db_session.add(lesson)
    db_session.flush()
    return lesson


def _create_syllabus_node_with_bridge(
    db_session,
    day_lesson_id: int,
    title: str = "Test Leaf",
    node_id: int | None = None,
) -> GsLmsSyllabusNode:
    """Helper: create a leaf syllabus node bridged to a day_lesson."""
    kwargs = {
        "subject_id": 1,
        "day_lesson_id": day_lesson_id,
        "title": title,
        "node_type": GsLmsNodeTypeEnum.LEAF_TOPIC,
        "weight": 1.0,
        "display_order": 1,
        "review_status": GsReviewStatusEnum.REVIEWED,
        "created_by": "test",
        "updated_by": "test",
    }
    if node_id is not None:
        kwargs["id"] = node_id
    node = GsLmsSyllabusNode(**kwargs)
    db_session.add(node)
    db_session.flush()
    return node


def _create_basic_section(db_session, node_id: int) -> GsLmsContentSection:
    """Helper: create a BASIC content section for a syllabus node."""
    section = GsLmsContentSection(
        syllabus_node_id=node_id,
        section_label=GsLmsSectionLabelEnum.BASIC,
        title="Basic Concepts",
        blocks=[{"type": "text", "content": "Basic content"}],
        display_order=1,
        review_status=GsReviewStatusEnum.REVIEWED,
        authored=True,
        created_by="test",
        updated_by="test",
    )
    db_session.add(section)
    db_session.flush()
    return section


# ===========================================================================
# Test: validate_bridge_mapping
# ===========================================================================

class TestValidateBridgeMapping:
    """Tests for bridge mapping integrity validation (Property 21)."""

    def test_empty_tree_is_valid(self, db_session):
        """No syllabus nodes → valid mapping (vacuously true)."""
        result = validate_bridge_mapping(db_session)
        assert result["valid"] is True
        assert result["total_bridges"] == 0
        assert result["duplicates"] == []
        assert result["orphans"] == []

    def test_single_bridge_is_valid(self, db_session):
        """One node bridged to one day_lesson → valid."""
        lesson = _create_day_lesson(db_session, day_number=1)
        _create_syllabus_node_with_bridge(db_session, day_lesson_id=lesson.id)
        db_session.commit()

        result = validate_bridge_mapping(db_session)
        assert result["valid"] is True
        assert result["total_bridges"] == 1
        assert result["duplicates"] == []
        assert result["orphans"] == []

    def test_multiple_unique_bridges_valid(self, db_session):
        """Multiple nodes, each bridged to a different day_lesson → valid."""
        for i in range(1, 4):
            lesson = _create_day_lesson(db_session, day_number=i, lesson_id=i)
            _create_syllabus_node_with_bridge(
                db_session, day_lesson_id=lesson.id, title=f"Node {i}"
            )
        db_session.commit()

        result = validate_bridge_mapping(db_session)
        assert result["valid"] is True
        assert result["total_bridges"] == 3
        assert result["duplicates"] == []

    def test_duplicate_bridge_detected(self, db_session):
        """Two nodes referencing the same day_lesson_id → invalid."""
        lesson = _create_day_lesson(db_session, day_number=1)

        # Create two nodes pointing to the same day_lesson.
        node1 = GsLmsSyllabusNode(
            subject_id=1,
            day_lesson_id=lesson.id,
            title="Node A",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
            created_by="test",
            updated_by="test",
        )
        node2 = GsLmsSyllabusNode(
            subject_id=1,
            day_lesson_id=lesson.id,
            title="Node B",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=2,
            review_status=GsReviewStatusEnum.REVIEWED,
            created_by="test",
            updated_by="test",
        )
        db_session.add_all([node1, node2])
        db_session.commit()

        result = validate_bridge_mapping(db_session)
        assert result["valid"] is False
        assert len(result["duplicates"]) == 1
        assert result["duplicates"][0]["day_lesson_id"] == lesson.id
        assert result["duplicates"][0]["node_count"] == 2

    def test_orphan_bridge_detected(self, db_session):
        """Node references a non-existent day_lesson → orphan detected."""
        # Create a node pointing to a day_lesson_id that doesn't exist.
        node = GsLmsSyllabusNode(
            subject_id=1,
            day_lesson_id=9999,  # nonexistent
            title="Orphan Node",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
            created_by="test",
            updated_by="test",
        )
        db_session.add(node)
        db_session.commit()

        result = validate_bridge_mapping(db_session)
        assert result["valid"] is False
        assert len(result["orphans"]) == 1
        assert result["orphans"][0]["day_lesson_id"] == 9999

    def test_nodes_without_bridge_not_counted(self, db_session):
        """Nodes with day_lesson_id=None are ignored."""
        # Create a node without a bridge.
        node = GsLmsSyllabusNode(
            subject_id=1,
            day_lesson_id=None,
            title="No Bridge",
            node_type=GsLmsNodeTypeEnum.MEGA_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.REVIEWED,
            created_by="test",
            updated_by="test",
        )
        db_session.add(node)
        db_session.commit()

        result = validate_bridge_mapping(db_session)
        assert result["valid"] is True
        assert result["total_bridges"] == 0


# ===========================================================================
# Test: migrate_progress
# ===========================================================================

class TestMigrateProgress:
    """Tests for progress migration (Property 22, R11.5)."""

    def test_no_progress_records_returns_zero(self, db_session):
        """Student with no progress → zero records created."""
        result = migrate_progress(db_session, student_id=100)
        assert result["student_id"] == 100
        assert result["records_created"] == 0
        assert result["records_skipped"] == 0

    def test_migrates_completed_lessons_to_basic_sections(self, db_session):
        """Completed day_lessons map to BASIC section progress records."""
        # Setup: day lessons 1 and 2.
        lesson1 = _create_day_lesson(db_session, day_number=1, lesson_id=1)
        lesson2 = _create_day_lesson(db_session, day_number=2, lesson_id=2)

        # Syllabus nodes bridged to those lessons.
        node1 = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson1.id, title="Topic 1"
        )
        node2 = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson2.id, title="Topic 2"
        )

        # BASIC sections for both nodes.
        section1 = _create_basic_section(db_session, node1.id)
        section2 = _create_basic_section(db_session, node2.id)

        # Student progress (old system): days 1 and 2 completed.
        old_progress = StudentSubjectProgress(
            user_id=100,
            subject_slug="geography",
            progress={"1": True, "2": True, "3": False},
        )
        db_session.add(old_progress)
        db_session.commit()

        # Migrate.
        result = migrate_progress(db_session, student_id=100)
        db_session.commit()

        assert result["records_created"] == 2
        assert result["records_skipped"] == 0
        assert result["day_lessons_without_bridge"] == []
        assert result["day_lessons_without_basic_section"] == []

        # Verify progress records exist.
        progress_records = (
            db_session.query(GsLmsStudentSectionProgress)
            .filter(GsLmsStudentSectionProgress.student_id == 100)
            .all()
        )
        assert len(progress_records) == 2
        for rec in progress_records:
            assert rec.completed is True
            assert rec.completed_at is not None
            assert rec.created_by == "migration"

    def test_idempotent_migration(self, db_session):
        """Running migration twice doesn't create duplicate records."""
        lesson = _create_day_lesson(db_session, day_number=1, lesson_id=1)
        node = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson.id, title="Topic 1"
        )
        _create_basic_section(db_session, node.id)

        old_progress = StudentSubjectProgress(
            user_id=100,
            subject_slug="geography",
            progress={"1": True},
        )
        db_session.add(old_progress)
        db_session.commit()

        # First migration.
        result1 = migrate_progress(db_session, student_id=100)
        db_session.commit()
        assert result1["records_created"] == 1

        # Second migration (should skip).
        result2 = migrate_progress(db_session, student_id=100)
        db_session.commit()
        assert result2["records_created"] == 0
        assert result2["records_skipped"] == 1

        # Only one progress record exists.
        count = (
            db_session.query(GsLmsStudentSectionProgress)
            .filter(GsLmsStudentSectionProgress.student_id == 100)
            .count()
        )
        assert count == 1

    def test_reports_day_lessons_without_bridge(self, db_session):
        """Completed day_lessons with no bridged syllabus node are reported."""
        # Create a day_lesson but no syllabus node bridges to it.
        _create_day_lesson(db_session, day_number=5, lesson_id=5)

        old_progress = StudentSubjectProgress(
            user_id=100,
            subject_slug="geography",
            progress={"5": True},
        )
        db_session.add(old_progress)
        db_session.commit()

        result = migrate_progress(db_session, student_id=100)
        db_session.commit()

        assert result["records_created"] == 0
        assert 5 in result["day_lessons_without_bridge"]

    def test_reports_nodes_without_basic_section(self, db_session):
        """Bridged nodes missing a BASIC section are reported."""
        lesson = _create_day_lesson(db_session, day_number=1, lesson_id=1)
        node = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson.id, title="No Section Node"
        )
        # Don't create a BASIC section.

        old_progress = StudentSubjectProgress(
            user_id=100,
            subject_slug="geography",
            progress={"1": True},
        )
        db_session.add(old_progress)
        db_session.commit()

        result = migrate_progress(db_session, student_id=100)
        db_session.commit()

        assert result["records_created"] == 0
        assert node.id in result["day_lessons_without_basic_section"]

    def test_progress_json_shape_completed_lessons_list(self, db_session):
        """Handles progress JSON shape: {"completedLessons": [1, 2]}."""
        lesson = _create_day_lesson(db_session, day_number=1, lesson_id=1)
        node = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson.id, title="Topic 1"
        )
        _create_basic_section(db_session, node.id)

        old_progress = StudentSubjectProgress(
            user_id=100,
            subject_slug="geography",
            progress={"completedLessons": [1, 2, 3]},
        )
        db_session.add(old_progress)
        db_session.commit()

        result = migrate_progress(db_session, student_id=100)
        db_session.commit()

        # Only day 1 is bridged, so only 1 record created.
        assert result["records_created"] == 1

    def test_progress_json_shape_nested_days(self, db_session):
        """Handles progress JSON shape: {"day1": {"completed": true}}."""
        lesson = _create_day_lesson(db_session, day_number=1, lesson_id=1)
        node = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson.id, title="Topic 1"
        )
        _create_basic_section(db_session, node.id)

        old_progress = StudentSubjectProgress(
            user_id=100,
            subject_slug="geography",
            progress={"day1": {"completed": True}, "day2": {"completed": False}},
        )
        db_session.add(old_progress)
        db_session.commit()

        result = migrate_progress(db_session, student_id=100)
        db_session.commit()

        assert result["records_created"] == 1


# ===========================================================================
# Test: rollback_migration
# ===========================================================================

class TestRollbackMigration:
    """Tests for migration rollback (R11.5)."""

    def test_rollback_removes_migration_records(self, db_session):
        """Rollback deletes all migration-created progress records."""
        lesson = _create_day_lesson(db_session, day_number=1, lesson_id=1)
        node = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson.id, title="Topic 1"
        )
        _create_basic_section(db_session, node.id)

        old_progress = StudentSubjectProgress(
            user_id=100,
            subject_slug="geography",
            progress={"1": True},
        )
        db_session.add(old_progress)
        db_session.commit()

        # Migrate.
        migrate_progress(db_session, student_id=100)
        db_session.commit()

        # Verify record exists.
        count_before = (
            db_session.query(GsLmsStudentSectionProgress)
            .filter(GsLmsStudentSectionProgress.student_id == 100)
            .count()
        )
        assert count_before == 1

        # Rollback.
        result = rollback_migration(db_session, student_id=100)
        db_session.commit()

        assert result["records_deleted"] == 1

        # Verify record is gone.
        count_after = (
            db_session.query(GsLmsStudentSectionProgress)
            .filter(GsLmsStudentSectionProgress.student_id == 100)
            .count()
        )
        assert count_after == 0

    def test_rollback_preserves_non_migration_records(self, db_session):
        """Rollback only removes records with created_by='migration'."""
        lesson = _create_day_lesson(db_session, day_number=1, lesson_id=1)
        node = _create_syllabus_node_with_bridge(
            db_session, day_lesson_id=lesson.id, title="Topic 1"
        )
        section = _create_basic_section(db_session, node.id)

        # Create a manually-created progress record (not from migration).
        manual_progress = GsLmsStudentSectionProgress(
            student_id=100,
            section_id=section.id,
            syllabus_node_id=node.id,
            completed=True,
            completed_at=datetime.now(timezone.utc),
            created_by="student_action",
            updated_by="student_action",
        )
        db_session.add(manual_progress)
        db_session.commit()

        # Rollback should not touch it.
        result = rollback_migration(db_session, student_id=100)
        db_session.commit()

        assert result["records_deleted"] == 0

        # Manual record still exists.
        count = (
            db_session.query(GsLmsStudentSectionProgress)
            .filter(GsLmsStudentSectionProgress.student_id == 100)
            .count()
        )
        assert count == 1

    def test_rollback_no_records_returns_zero(self, db_session):
        """Rollback with no migration records → zero deleted."""
        result = rollback_migration(db_session, student_id=100)
        assert result["records_deleted"] == 0


# ===========================================================================
# Test: _extract_completed_day_numbers
# ===========================================================================

class TestExtractCompletedDayNumbers:
    """Tests for the internal helper that parses progress JSON shapes."""

    def test_shape_simple_truthy_keys(self):
        """Shape 1: {"1": true, "2": true, "3": false}."""
        rows = [_mock_progress({"1": True, "2": True, "3": False})]
        result = _extract_completed_day_numbers(rows)
        assert result == [1, 2]

    def test_shape_completed_lessons_list(self):
        """Shape 2: {"completedLessons": [1, 2, 3]}."""
        rows = [_mock_progress({"completedLessons": [1, 2, 3]})]
        result = _extract_completed_day_numbers(rows)
        assert result == [1, 2, 3]

    def test_shape_nested_day_objects(self):
        """Shape 3: {"day1": {"completed": true}, "day2": {"completed": false}}."""
        rows = [_mock_progress({"day1": {"completed": True}, "day2": {"completed": False}})]
        result = _extract_completed_day_numbers(rows)
        assert result == [1]

    def test_shape_lessons_wrapper(self):
        """Shape 4: {"lessons": {"1": {"completed": true}}}."""
        rows = [_mock_progress({"lessons": {"1": {"completed": True}, "2": {"completed": False}}})]
        result = _extract_completed_day_numbers(rows)
        assert result == [1]

    def test_empty_progress(self):
        """Empty dict → no completions."""
        rows = [_mock_progress({})]
        result = _extract_completed_day_numbers(rows)
        assert result == []

    def test_multiple_rows_merged(self):
        """Progress from multiple subject records is merged."""
        rows = [
            _mock_progress({"1": True}),
            _mock_progress({"2": True, "3": True}),
        ]
        result = _extract_completed_day_numbers(rows)
        assert result == [1, 2, 3]

    def test_non_dict_progress_ignored(self):
        """Non-dict progress values are safely skipped."""
        rows = [_mock_progress(None)]
        result = _extract_completed_day_numbers(rows)
        assert result == []


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

class _MockProgress:
    """Minimal mock for StudentSubjectProgress with .progress attribute."""

    def __init__(self, progress):
        self.progress = progress


def _mock_progress(progress) -> _MockProgress:
    """Create a mock progress row."""
    return _MockProgress(progress)
