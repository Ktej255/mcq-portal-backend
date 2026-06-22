"""GS Geography content importer (Master Plan A3/B3) — no-loss migration, step 2.

BACKEND half of the two-step, no-loss content migration that moves GS Geography
content onto FastAPI/Postgres (GATE-1 = standardize the live loop on the
backend), mirroring ``app.core.optional.importer``.

Step 1 (frontend): ``frontend/scripts/extract-gs-geography-content.mjs`` reads
the authored TS modules (``plan.ts`` ``geographySessions`` + the 30
``geographyDay<N>PortalLesson.ts`` Watch modules), transpiles + serializes them,
and writes a faithful JSON artifact to
``backend/app/core/gs/data/gs_geography_content.json``. No hand transcription.

Step 2 (this module): reads that artifact and upserts the canonical
``GsSubject "geography"`` + 30 ``GsDayLesson`` rows. Each day stores the full
authored payload in ``content`` (``{"session": ..., "lesson": {...all module
exports...}}``) so the migration loses nothing; ``scenes`` and ``subtopics`` are
promoted columns for a future read API.

Faithful join: lesson module ``N`` is paired with the curriculum session whose
``day == N`` when one exists (Geography days 1..20). Authored scene-only lessons
without a session (e.g. lessons 21..30) are stored with ``has_session=False`` —
no session metadata is fabricated.

Idempotency: a run removes the existing ``geography`` GS subject tree wholesale
first, then recreates it, so re-running yields the same counts and never
duplicates.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.gs.models import GsSubject, GsDayLesson, GsReviewStatusEnum

DEFAULT_ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "gs_geography_content.json"


def load_artifact(artifact_path: Optional[os.PathLike | str] = None) -> dict[str, Any]:
    """Load the extractor's JSON artifact."""
    path = Path(artifact_path) if artifact_path else DEFAULT_ARTIFACT_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"GS Geography content artifact not found at {path}. Run the frontend "
            f"extractor first: `node scripts/extract-gs-geography-content.mjs` (from frontend/)."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _delete_existing_subject(session: Session, slug: str) -> None:
    """Remove an existing GS subject tree in FK-safe order (idempotency)."""
    subject = session.query(GsSubject).filter(GsSubject.slug == slug).one_or_none()
    if subject is None:
        return
    session.query(GsDayLesson).filter(GsDayLesson.subject_id == subject.id).delete(
        synchronize_session=False
    )
    session.query(GsSubject).filter(GsSubject.id == subject.id).delete(
        synchronize_session=False
    )
    session.flush()


def import_gs_geography(
    session: Session,
    *,
    artifact_path: Optional[os.PathLike | str] = None,
    review_status: str = "REVIEWED",
    actor: str = "gs-geography-importer",
) -> dict[str, Any]:
    """Import the GS Geography curriculum + Watch lessons into the DB.

    The migrated content is the already-shipping authored GS Geography study
    loop, so the default ``review_status="REVIEWED"`` keeps it student-visible;
    pass a different status to gate it behind a review workflow.

    Idempotent: replaces the ``geography`` GS subject tree on each run. Returns a
    counts report.
    """
    artifact = load_artifact(artifact_path)
    slug = artifact["subjectSlug"]
    rs_enum = GsReviewStatusEnum(review_status)

    _delete_existing_subject(session, slug)

    sessions_by_day: dict[int, dict[str, Any]] = {}
    for s in artifact.get("sessions", []):
        try:
            sessions_by_day[int(s["day"])] = s
        except (KeyError, TypeError, ValueError):
            continue

    weeks = sorted({s.get("week") for s in artifact.get("sessions", []) if s.get("week") is not None})

    subject = GsSubject(
        slug=slug,
        name=artifact["subjectName"],
        description=(
            "GS Geography — 30-day guided-study curriculum (Watch/Talk/MCQ/Track/"
            "Revisit loop) migrated onto the backend as the source of truth."
        ),
        display_order=0,
        is_complete=False,
        config={
            "session_days": sorted(sessions_by_day.keys()),
            "lesson_count": int(artifact.get("lessonCount", 0) or 0),
            "weeks": weeks,
        },
        completeness_status={
            "phase": "b3-geography-backend-migration",
            "session_count": int(artifact.get("sessionCount", 0) or 0),
            "lesson_count": int(artifact.get("lessonCount", 0) or 0),
        },
        created_by=actor,
        updated_by=actor,
    )
    session.add(subject)
    session.flush()

    counts = {
        "subjects": 1,
        "day_lessons": 0,
        "lessons_with_session": 0,
        "lessons_scene_only": 0,
        "scenes": 0,
    }

    for lesson in artifact.get("lessons", []):
        n = int(lesson["lessonNumber"])
        sess = sessions_by_day.get(n)
        scenes = lesson.get("scenes") or []

        row = GsDayLesson(
            subject_id=subject.id,
            day_number=n,
            week=(int(sess["week"]) if sess and sess.get("week") is not None else None),
            title=lesson.get("title") or (sess.get("title") if sess else None) or f"Day {n}",
            session_title=(sess.get("title") if sess else None),
            has_session=sess is not None,
            scenes=scenes,
            subtopics=(sess.get("subtopics") if sess else None),
            # Full faithful payload — no content loss.
            content={"session": sess, "lesson": lesson.get("exports", {})},
            review_status=rs_enum,
            display_order=n,
            created_by=actor,
            updated_by=actor,
        )
        session.add(row)
        counts["day_lessons"] += 1
        counts["scenes"] += len(scenes)
        if sess is not None:
            counts["lessons_with_session"] += 1
        else:
            counts["lessons_scene_only"] += 1

    session.flush()
    return counts


def _build_source_report(artifact: dict[str, Any]) -> dict[str, int]:
    """Independent source-side counts derived from the artifact (for parity)."""
    lessons = artifact.get("lessons", [])
    session_days = {int(s["day"]) for s in artifact.get("sessions", []) if s.get("day") is not None}
    lesson_numbers = {int(l["lessonNumber"]) for l in lessons}
    return {
        "day_lessons": len(lessons),
        "lessons_with_session": len(lesson_numbers & session_days),
        "lessons_scene_only": len(lesson_numbers - session_days),
        "scenes": sum(len(l.get("scenes") or []) for l in lessons),
    }


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description="Import GS Geography content into the DB.")
    parser.add_argument("--artifact", default=None, help="Path to the JSON artifact.")
    parser.add_argument(
        "--review-status",
        default="REVIEWED",
        choices=[e.value for e in GsReviewStatusEnum],
        help="review_status to stamp on imported day lessons.",
    )
    args = parser.parse_args()

    artifact = load_artifact(args.artifact)
    source_report = _build_source_report(artifact)

    session = SessionLocal()
    try:
        counts = import_gs_geography(
            session, artifact_path=args.artifact, review_status=args.review_status
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("=== GS Geography import complete ===")
    print("Imported counts:")
    for k, v in counts.items():
        print(f"  {k:<22} {v}")
    print("\nSource (artifact) counts for parity:")
    for k, v in source_report.items():
        imported = counts.get(k)
        match = "OK" if imported == v else "MISMATCH"
        print(f"  {k:<22} source={v} imported={imported} [{match}]")


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["load_artifact", "import_gs_geography"]
