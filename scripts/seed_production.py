#!/usr/bin/env python3
"""Idempotent production seed for the GS Geography LMS.

Consolidates every step needed to bring a database (SQLite local OR RDS
PostgreSQL) to the current content state:

  1. Ensure all GS LMS tables exist (create_all — additive, never drops).
  2. Ensure the additive ``gs_paper`` column on ``gs_lms_pyqs`` (SQLite only;
     PostgreSQL is handled by Alembic).
  3. Ensure the ``geography`` row exists in ``gs_subjects`` (subject_id=1).
  4. Clear subject-1 content (sections/PYQs/MCQs) and re-import the merged
     ``gs_geography_syllabus.json`` as REVIEWED (idempotent importer).
  5. Delete orphaned LEAF_TOPIC nodes that have no content sections (left over
     from earlier "Lecture N" titles that were renamed/restructured).

Usage:
    # Local SQLite (uses DATABASE_URL from .env)
    python scripts/seed_production.py

    # Production (PowerShell):
    #   $env:DATABASE_URL="postgresql://USER:PASS@HOST:5432/DB"
    #   python scripts/seed_production.py

Safe to run repeatedly — produces the same DB state every time.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.db.session import Base, SessionLocal, engine

# Register the full model graph on Base.metadata.
import app.models.domain  # noqa: F401
import app.core.gs.models  # noqa: F401
import app.core.gs_lms.models  # noqa: F401
import app.core.gs_lms.student_models  # noqa: F401

from app.core.gs.models import GsSubject
from app.core.gs_lms.importer import import_gs_geography

SUBJECT_ID = 1
SUBJECT_SLUG = "geography"


def _ensure_gs_paper_column() -> None:
    """Add the nullable gs_paper column to gs_lms_pyqs if missing (SQLite only)."""
    if engine.dialect.name == "postgresql":
        print("  [skip] PostgreSQL — gs_paper handled by Alembic")
        return
    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info('gs_lms_pyqs')"))]
        if cols and "gs_paper" not in cols:
            conn.execute(text("ALTER TABLE gs_lms_pyqs ADD COLUMN gs_paper VARCHAR"))
            print("  [added] gs_lms_pyqs.gs_paper")
        else:
            print("  [ok] gs_lms_pyqs.gs_paper present")


def _ensure_subject(session) -> None:
    """Ensure the geography subject row exists (resolve_subject depends on it)."""
    subject = (
        session.query(GsSubject)
        .filter(GsSubject.slug == SUBJECT_SLUG)
        .one_or_none()
    )
    if subject is None:
        now = datetime.now(timezone.utc)
        subject = GsSubject(
            id=SUBJECT_ID,
            slug=SUBJECT_SLUG,
            name="Geography",
            description="GS Paper 1 - Geography (Physical, Human, Indian)",
            display_order=1,
            is_complete=False,
            created_at=now,
            updated_at=now,
        )
        session.add(subject)
        session.flush()
        print(f"  [created] gs_subjects '{SUBJECT_SLUG}' (id={SUBJECT_ID})")
    else:
        print(f"  [ok] gs_subjects '{SUBJECT_SLUG}' exists (id={subject.id})")


def _clear_subject_content(session) -> None:
    """Delete subject-1 sections/PYQs/MCQs so the import is a clean replace."""
    session.execute(text(
        "DELETE FROM gs_lms_mcq_questions WHERE syllabus_node_id IN "
        "(SELECT id FROM gs_lms_syllabus_nodes WHERE subject_id = :sid)"
    ), {"sid": SUBJECT_ID})
    session.execute(text("DELETE FROM gs_lms_pyqs WHERE subject_id = :sid"), {"sid": SUBJECT_ID})
    session.execute(text(
        "DELETE FROM gs_lms_content_sections WHERE syllabus_node_id IN "
        "(SELECT id FROM gs_lms_syllabus_nodes WHERE subject_id = :sid)"
    ), {"sid": SUBJECT_ID})
    session.flush()


def _delete_orphan_nodes(session) -> int:
    """Delete subject-1 LEAF_TOPIC nodes that have no content sections.

    After renaming/restructuring, the importer creates new nodes (matched by
    title+parent) and leaves the old ones orphaned with no sections.
    """
    orphan_ids = [r[0] for r in session.execute(text(
        "SELECT n.id FROM gs_lms_syllabus_nodes n "
        "WHERE n.subject_id = :sid AND n.node_type = 'LEAF_TOPIC' "
        "AND NOT EXISTS (SELECT 1 FROM gs_lms_content_sections s "
        "WHERE s.syllabus_node_id = n.id)"
    ), {"sid": SUBJECT_ID})]
    if not orphan_ids:
        return 0
    # Clean dependent student/progress rows first (best-effort).
    dep = [
        ("gs_lms_funnel_progress", "syllabus_node_id"),
        ("gs_lms_video_watches", "syllabus_node_id"),
        ("gs_lms_revisit_schedule", "syllabus_node_id"),
        ("gs_lms_reading_times", "syllabus_node_id"),
        ("gs_lms_recall_attempts", "syllabus_node_id"),
        ("gs_lms_student_section_progress", "syllabus_node_id"),
    ]
    for tbl, col in dep:
        try:
            session.execute(
                text(f"DELETE FROM {tbl} WHERE {col} = ANY(:ids)")
                if engine.dialect.name == "postgresql"
                else text(f"DELETE FROM {tbl} WHERE {col} IN ({','.join(str(i) for i in orphan_ids)})"),
                {"ids": orphan_ids} if engine.dialect.name == "postgresql" else {},
            )
        except Exception:
            pass
    if engine.dialect.name == "postgresql":
        session.execute(
            text("DELETE FROM gs_lms_syllabus_nodes WHERE id = ANY(:ids)"),
            {"ids": orphan_ids},
        )
    else:
        session.execute(text(
            f"DELETE FROM gs_lms_syllabus_nodes WHERE id IN ({','.join(str(i) for i in orphan_ids)})"
        ))
    session.flush()
    return len(orphan_ids)


def main() -> None:
    print(f"DB: {engine.url}")
    print("Step 1: ensure tables")
    Base.metadata.create_all(engine)
    print("Step 2: ensure gs_paper column")
    _ensure_gs_paper_column()

    session = SessionLocal()
    try:
        print("Step 3: ensure geography subject")
        _ensure_subject(session)

        print("Step 4: clear + re-import subject content (REVIEWED)")
        _clear_subject_content(session)
        result = import_gs_geography(session, review_status="REVIEWED")

        print("Step 5: delete orphan nodes")
        removed = _delete_orphan_nodes(session)
        print(f"  [removed] {removed} orphan leaf nodes")

        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        session.close()

    print("\n=== Seed complete (REVIEWED) ===")
    for k, v in result.items():
        print(f"  {k:<22} {v}")


if __name__ == "__main__":
    main()
