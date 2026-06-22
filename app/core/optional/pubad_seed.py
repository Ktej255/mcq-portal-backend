"""Public Administration subject + current-affairs draft seeder
(Task 17.1 — Phase 2, R11.4 / R19.1 / R19.2).

Creates the **Public Administration** optional subject with a config that
enables the standard feature modules PLUS the subject-specific
``currentAffairs`` feature, and seeds a small **DRAFT / UNREVIEWED** current-
affairs feed.

IMPORTANT — content honesty (vision §0 + carry-over rule): this is a *scaffold
for founder review*, NOT a finished Public Administration subject. The subject
ships with **no reviewed content** (so its completeness surface honestly shows
"Not started") and the seeded current-affairs items are stamped ``UNREVIEWED``
so they are gated from students (design Property 8). A content author/founder
authors the real syllabus/notes/PYQs and reviews the current-affairs items
(flipping them to ``REVIEWED`` via the review workflow) before students see any
of it. The seeded item summaries are generic, clearly-draft placeholders, never
presented as authoritative.

Idempotent: re-running updates the subject's config and replaces this seeder's
prior current-affairs rows.

Requirements: 11.4, 17.2, 17.3, 19.1, 19.2
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core.optional.models import OptionalSubject, OptionalReviewStatusEnum
from app.core.optional.current_affairs_models import CurrentAffairsItem

SEEDER_ACTOR = "pubad-draft-seeder"
PUBAD_SLUG = "public-administration"

_PUBAD_CONFIG: dict[str, Any] = {
    "papers": [
        {"label": "PAPER_I", "sections": ["SECTION_A", "SECTION_B"]},
        {"label": "PAPER_II", "sections": []},
    ],
    # Standard feature modules + the subject-specific current-affairs feature.
    "features": [
        "read",
        "pyq",
        "practice",
        "answer",
        "gap",
        "recall",
        "currentAffairs",
    ],
}

# Generic, clearly-draft current-affairs prompts — placeholders for the real
# author-curated feed. All seeded UNREVIEWED (gated).
_DRAFT_CURRENT_AFFAIRS: list[dict[str, Any]] = [
    {"title": "[DRAFT] Governance reform in focus", "topic": "Governance", "summary": "[DRAFT — pending review] Placeholder note for an authored governance current-affairs item.", "year": 2026, "month": 6},
    {"title": "[DRAFT] Civil services accountability debate", "topic": "Accountability", "summary": "[DRAFT — pending review] Placeholder note for an authored accountability item.", "year": 2026, "month": 5},
    {"title": "[DRAFT] Recent administrative reforms committee update", "topic": "Reforms", "summary": "[DRAFT — pending review] Placeholder note for an authored reforms item.", "year": 2026, "month": 4},
]


def _ensure_subject(session: Session) -> OptionalSubject:
    subject = (
        session.query(OptionalSubject)
        .filter(OptionalSubject.slug == PUBAD_SLUG)
        .one_or_none()
    )
    if subject is None:
        subject = OptionalSubject(
            slug=PUBAD_SLUG,
            name="Public Administration",
            description=(
                "UPSC Public Administration optional — scaffolded with the "
                "subject-specific current-affairs feature (Phase 2). Content "
                "pending authoring + founder review."
            ),
            display_order=1,
            is_complete=False,
            config=_PUBAD_CONFIG,
            completeness_status={"phase": "phase-2-scaffold", "content": "pending-review"},
            created_by=SEEDER_ACTOR,
            updated_by=SEEDER_ACTOR,
        )
        session.add(subject)
        session.flush()
    else:
        subject.config = _PUBAD_CONFIG
        subject.updated_by = SEEDER_ACTOR
        session.flush()
    return subject


def seed_public_administration(
    session: Session,
    *,
    review_status: str = "UNREVIEWED",
    actor: str = SEEDER_ACTOR,
) -> dict[str, int]:
    """Create/refresh the PA subject + seed its gated DRAFT current-affairs feed.

    Defaults to ``review_status="UNREVIEWED"`` so the feed is gated until
    reviewed. Returns a counts report.
    """
    rs_enum = OptionalReviewStatusEnum(review_status)
    subject = _ensure_subject(session)

    # Replace this seeder's prior current-affairs rows (idempotency).
    session.query(CurrentAffairsItem).filter(
        CurrentAffairsItem.subject_id == subject.id,
        CurrentAffairsItem.created_by == actor,
    ).delete(synchronize_session=False)
    session.flush()

    counts = {"subjects": 1, "current_affairs": 0}
    for order, item in enumerate(_DRAFT_CURRENT_AFFAIRS):
        session.add(
            CurrentAffairsItem(
                subject_id=subject.id,
                title=item["title"],
                topic=item.get("topic"),
                summary=item.get("summary"),
                source_url=None,
                published_on=date(item["year"], item["month"], 1),
                display_order=order,
                review_status=rs_enum,
                created_by=actor,
                updated_by=actor,
            )
        )
        counts["current_affairs"] += 1

    session.flush()
    return counts


__all__ = ["seed_public_administration", "SEEDER_ACTOR", "PUBAD_SLUG"]
