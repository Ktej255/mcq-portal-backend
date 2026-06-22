"""Day-lesson bridge and progress migration utility module.

Provides functions to:
1. Validate bridge mapping integrity (no two syllabus nodes share the same
   day_lesson_id — Property 21).
2. Migrate student progress from the old ``student_subject_progress`` table
   to the new ``GsLmsStudentSectionProgress`` records.
3. Roll back a failed migration atomically (Requirement 11.5).

The migration logic: if a GsDayLesson is marked completed for a student in
the old system AND that day_lesson is mapped (via day_lesson_id FK) to a
syllabus node, create section progress records for that node's BASIC section
as the minimum carryover.

Requirements traced: 11.1, 11.2, 11.4, 11.5
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.gs.models import GsDayLesson
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
    GsLmsSectionLabelEnum,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress
from app.models.domain import StudentSubjectProgress


# ---------------------------------------------------------------------------
# Bridge Mapping Validation (Property 21)
# ---------------------------------------------------------------------------

class BridgeMappingError(Exception):
    """Raised when bridge mapping integrity is violated."""

    def __init__(self, duplicates: list[dict[str, Any]]) -> None:
        self.duplicates = duplicates
        super().__init__(
            f"Bridge mapping integrity violated: {len(duplicates)} day_lesson_id(s) "
            f"referenced by multiple syllabus nodes."
        )


def validate_bridge_mapping(db: Session) -> dict[str, Any]:
    """Check that no two syllabus nodes reference the same GsDayLesson.

    Property 21: (a) every non-null day_lesson_id references a valid
    GsDayLesson record, (b) no two syllabus nodes reference the same
    GsDayLesson, and (c) the mapping is a valid partial function from
    syllabus nodes to day lessons.

    Returns:
        A dict with:
        - valid (bool): True if mapping is clean
        - total_bridges (int): count of non-null day_lesson_id entries
        - duplicates (list): any day_lesson_ids shared by multiple nodes
        - orphans (list): any day_lesson_ids pointing to nonexistent GsDayLesson

    Raises:
        BridgeMappingError: If duplicates are found (optional — caller can
        also just inspect the return dict).
    """
    # Find all syllabus nodes with non-null day_lesson_id.
    bridged_nodes = (
        db.query(GsLmsSyllabusNode)
        .filter(GsLmsSyllabusNode.day_lesson_id.isnot(None))
        .all()
    )

    total_bridges = len(bridged_nodes)

    # (b) Check for duplicates: group by day_lesson_id, find any with count > 1.
    duplicate_query = (
        db.query(
            GsLmsSyllabusNode.day_lesson_id,
            func.count(GsLmsSyllabusNode.id).label("node_count"),
        )
        .filter(GsLmsSyllabusNode.day_lesson_id.isnot(None))
        .group_by(GsLmsSyllabusNode.day_lesson_id)
        .having(func.count(GsLmsSyllabusNode.id) > 1)
        .all()
    )

    duplicates = [
        {"day_lesson_id": row[0], "node_count": row[1]}
        for row in duplicate_query
    ]

    # (a) Check for orphans: day_lesson_ids that don't reference valid records.
    orphans: list[dict[str, Any]] = []
    if bridged_nodes:
        day_lesson_ids = [n.day_lesson_id for n in bridged_nodes]
        existing_lessons = (
            db.query(GsDayLesson.id)
            .filter(GsDayLesson.id.in_(day_lesson_ids))
            .all()
        )
        existing_ids = {row[0] for row in existing_lessons}
        orphan_ids = set(day_lesson_ids) - existing_ids
        orphans = [{"day_lesson_id": dl_id} for dl_id in orphan_ids]

    valid = len(duplicates) == 0 and len(orphans) == 0

    return {
        "valid": valid,
        "total_bridges": total_bridges,
        "duplicates": duplicates,
        "orphans": orphans,
    }


# ---------------------------------------------------------------------------
# Progress Migration
# ---------------------------------------------------------------------------

class MigrationError(Exception):
    """Raised when progress migration fails."""
    pass


def migrate_progress(db: Session, student_id: int) -> dict[str, Any]:
    """Migrate a student's day-lesson completion data to GsLmsStudentSectionProgress.

    Logic:
    - Read the student's ``StudentSubjectProgress`` record (JSON progress field).
    - For each day_lesson marked completed in the old system:
      - Find the GsLmsSyllabusNode bridged to that day_lesson via day_lesson_id.
      - Find the BASIC content section of that syllabus node.
      - Create a GsLmsStudentSectionProgress record marking that section completed.
    - The migration is atomic: if any step fails, roll back completely (R11.5).

    Args:
        db: SQLAlchemy session.
        student_id: The user ID of the student to migrate.

    Returns:
        A dict with:
        - student_id (int)
        - records_created (int): new section progress records created
        - records_skipped (int): already-existing progress records (idempotent)
        - day_lessons_without_bridge (list): day_lesson_ids with no syllabus node mapping
        - day_lessons_without_basic_section (list): node_ids missing BASIC section

    Raises:
        MigrationError: If the migration cannot proceed (e.g., no progress record found).
    """
    # Use a savepoint for atomic rollback within the session.
    savepoint = db.begin_nested()

    try:
        # 1. Find the student's existing progress records.
        progress_rows = (
            db.query(StudentSubjectProgress)
            .filter(StudentSubjectProgress.user_id == student_id)
            .all()
        )

        if not progress_rows:
            savepoint.commit()
            return {
                "student_id": student_id,
                "records_created": 0,
                "records_skipped": 0,
                "day_lessons_without_bridge": [],
                "day_lessons_without_basic_section": [],
            }

        # 2. Extract completed day_lesson identifiers from the progress JSON.
        #    The progress JSON structure stores completed lessons as keys with
        #    truthy values, e.g. {"1": true, "2": true} or
        #    {"completedLessons": [1, 2, 3]} or {"dayN": {"completed": true}}.
        completed_day_numbers = _extract_completed_day_numbers(progress_rows)

        if not completed_day_numbers:
            savepoint.commit()
            return {
                "student_id": student_id,
                "records_created": 0,
                "records_skipped": 0,
                "day_lessons_without_bridge": [],
                "day_lessons_without_basic_section": [],
            }

        # 3. Find GsDayLesson records for completed days.
        completed_lessons = (
            db.query(GsDayLesson)
            .filter(GsDayLesson.day_number.in_(completed_day_numbers))
            .all()
        )
        completed_lesson_ids = {lesson.id for lesson in completed_lessons}

        # 4. Find syllabus nodes bridged to those day_lessons.
        bridged_nodes = (
            db.query(GsLmsSyllabusNode)
            .filter(GsLmsSyllabusNode.day_lesson_id.in_(completed_lesson_ids))
            .all()
        )
        bridged_map = {node.day_lesson_id: node for node in bridged_nodes}

        # Track lessons without a bridge.
        day_lessons_without_bridge = [
            dl_id for dl_id in completed_lesson_ids
            if dl_id not in bridged_map
        ]

        # 5. For each bridged node, find the BASIC section and create progress.
        records_created = 0
        records_skipped = 0
        day_lessons_without_basic_section: list[int] = []

        for dl_id, node in bridged_map.items():
            # Find the BASIC section for this node.
            basic_section = (
                db.query(GsLmsContentSection)
                .filter(
                    GsLmsContentSection.syllabus_node_id == node.id,
                    GsLmsContentSection.section_label == GsLmsSectionLabelEnum.BASIC,
                )
                .first()
            )

            if basic_section is None:
                day_lessons_without_basic_section.append(node.id)
                continue

            # Check if progress already exists (idempotent).
            existing = (
                db.query(GsLmsStudentSectionProgress)
                .filter(
                    GsLmsStudentSectionProgress.student_id == student_id,
                    GsLmsStudentSectionProgress.section_id == basic_section.id,
                )
                .first()
            )

            if existing:
                records_skipped += 1
                continue

            # Create new progress record.
            progress_record = GsLmsStudentSectionProgress(
                student_id=student_id,
                section_id=basic_section.id,
                syllabus_node_id=node.id,
                completed=True,
                completed_at=datetime.now(timezone.utc),
                created_by="migration",
                updated_by="migration",
            )
            db.add(progress_record)
            records_created += 1

        savepoint.commit()

        return {
            "student_id": student_id,
            "records_created": records_created,
            "records_skipped": records_skipped,
            "day_lessons_without_bridge": sorted(day_lessons_without_bridge),
            "day_lessons_without_basic_section": sorted(day_lessons_without_basic_section),
        }

    except Exception as exc:
        savepoint.rollback()
        raise MigrationError(
            f"Migration failed for student {student_id}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Rollback Migration
# ---------------------------------------------------------------------------

def rollback_migration(db: Session, student_id: int) -> dict[str, Any]:
    """Reverse a progress migration for a student.

    Removes all GsLmsStudentSectionProgress records created by the migration
    utility (identified by created_by='migration') for the given student.
    This implements the atomic rollback guarantee of R11.5.

    Args:
        db: SQLAlchemy session.
        student_id: The user ID of the student whose migration to roll back.

    Returns:
        A dict with:
        - student_id (int)
        - records_deleted (int): number of progress records removed
    """
    savepoint = db.begin_nested()

    try:
        # Find all migration-created progress records for this student.
        migration_records = (
            db.query(GsLmsStudentSectionProgress)
            .filter(
                GsLmsStudentSectionProgress.student_id == student_id,
                GsLmsStudentSectionProgress.created_by == "migration",
            )
            .all()
        )

        records_deleted = len(migration_records)
        for record in migration_records:
            db.delete(record)

        savepoint.commit()

        return {
            "student_id": student_id,
            "records_deleted": records_deleted,
        }

    except Exception as exc:
        savepoint.rollback()
        raise MigrationError(
            f"Rollback failed for student {student_id}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _extract_completed_day_numbers(
    progress_rows: list[StudentSubjectProgress],
) -> list[int]:
    """Extract completed day numbers from progress JSON.

    The progress JSON can have multiple shapes:
    1. {"1": true, "2": true, ...} — day number as key, truthy = completed
    2. {"completedLessons": [1, 2, 3]} — explicit list
    3. {"day1": {"completed": true}, "day2": {"completed": false}} — nested
    4. {"lessons": {"1": {"completed": true}}} — nested with lessons wrapper

    We handle all known shapes and extract integer day numbers.
    """
    completed: set[int] = set()

    for row in progress_rows:
        progress = row.progress
        if not isinstance(progress, dict):
            continue

        # Shape 2: {"completedLessons": [1, 2, 3]}
        if "completedLessons" in progress:
            lessons = progress["completedLessons"]
            if isinstance(lessons, list):
                for item in lessons:
                    try:
                        completed.add(int(item))
                    except (ValueError, TypeError):
                        continue
            continue

        # Shape 4: {"lessons": {"1": {"completed": true}}}
        if "lessons" in progress and isinstance(progress["lessons"], dict):
            for key, val in progress["lessons"].items():
                try:
                    day_num = int(key)
                except (ValueError, TypeError):
                    continue
                if isinstance(val, dict) and val.get("completed"):
                    completed.add(day_num)
            continue

        # Shape 1 & 3: iterate top-level keys.
        for key, val in progress.items():
            # Shape 3: {"day1": {"completed": true}}
            if isinstance(val, dict):
                if val.get("completed"):
                    # Extract number from "dayN" pattern.
                    day_str = key.replace("day", "").strip()
                    try:
                        completed.add(int(day_str))
                    except (ValueError, TypeError):
                        continue
            else:
                # Shape 1: {"1": true, "2": true}
                if val:
                    try:
                        completed.add(int(key))
                    except (ValueError, TypeError):
                        continue

    return sorted(completed)


__all__ = [
    "BridgeMappingError",
    "MigrationError",
    "validate_bridge_mapping",
    "migrate_progress",
    "rollback_migration",
]
