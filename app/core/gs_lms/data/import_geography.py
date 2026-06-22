"""Seed the GS Geography LMS content from the JSON artifact.

Usage: python -m app.core.gs_lms.data.import_geography

Idempotent: re-running produces identical database state — existing records
are matched by natural keys and updated rather than duplicated.
"""

from __future__ import annotations

import sys

from app.core.gs_lms.importer import import_gs_geography
from app.db.session import SessionLocal


def main() -> None:
    """Run the GS Geography content import with REVIEWED status."""
    session = SessionLocal()
    try:
        print("Starting GS Geography LMS import (review_status=REVIEWED)...")
        result = import_gs_geography(session, review_status="REVIEWED")
        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"ERROR: Import failed — {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        session.close()

    print("\n=== GS Geography LMS import complete ===")
    print("Summary:")
    for key, value in result.items():
        print(f"  {key:<22} {value}")
    print("\nAll content imported as REVIEWED (immediately visible to students).")


if __name__ == "__main__":
    main()
