#!/usr/bin/env python3
"""Local-dev seed: load the (merged) GS Geography content into the running
app's SQLite DB so the upgraded topics show up immediately.

Avoids Alembic (the local sqlite was built via create_all, not migrations).
It (1) creates any missing tables, (2) ensures the additive ``gs_paper`` column
exists on ``gs_lms_pyqs``, then (3) runs the idempotent importer with
review_status=REVIEWED.

Usage (from backend/, with the local sqlite DATABASE_URL in .env):
    python scripts/local_seed_upgraded.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.db.session import Base, SessionLocal, engine

# Register the full model graph on Base.metadata.
import app.models.domain  # noqa: F401
import app.core.gs.models  # noqa: F401
import app.core.gs_lms.models  # noqa: F401
import app.core.gs_lms.student_models  # noqa: F401

from app.core.gs_lms.importer import import_gs_geography


def _ensure_gs_paper_column() -> None:
    """Add the nullable gs_paper column to gs_lms_pyqs if missing (sqlite)."""
    if engine.dialect.name == "postgresql":
        print("Dialect is PostgreSQL, skipping SQLite-specific column check")
        return
    with engine.begin() as conn:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info('gs_lms_pyqs')"))]
        if not cols:
            return  # table will be created by create_all below
        if "gs_paper" not in cols:
            conn.execute(text("ALTER TABLE gs_lms_pyqs ADD COLUMN gs_paper VARCHAR"))
            print("Added column gs_lms_pyqs.gs_paper")
        else:
            print("Column gs_lms_pyqs.gs_paper already present")


def main() -> None:
    print(f"DB: {engine.url}")
    # 1. Create any missing tables (new answer-eval tables, etc.). Existing
    #    tables are left untouched.
    Base.metadata.create_all(engine)
    # 2. Ensure the additive column exists on the existing PYQ table.
    _ensure_gs_paper_column()

    # 3. Clear + re-import subject_id=1 content as REVIEWED.
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM gs_lms_mcq_questions WHERE syllabus_node_id IN (SELECT id FROM gs_lms_syllabus_nodes WHERE subject_id = 1)"))
        session.execute(text("DELETE FROM gs_lms_pyqs WHERE subject_id = 1"))
        session.execute(text("DELETE FROM gs_lms_content_sections WHERE syllabus_node_id IN (SELECT id FROM gs_lms_syllabus_nodes WHERE subject_id = 1)"))
        session.flush()
        result = import_gs_geography(session, review_status="REVIEWED")
        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        session.close()

    print("\n=== Import complete (REVIEWED) ===")
    for k, v in result.items():
        print(f"  {k:<22} {v}")


if __name__ == "__main__":
    main()
