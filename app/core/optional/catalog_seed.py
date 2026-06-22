"""Catalog seeder — ensures all 25 UPSC optional subjects exist in the DB
(Task 17.2 — Phase 2, R1.2 / R19.1 / R19.2).

The frontend catalog (``optionalSubjectsCatalog.ts``) lists all 25 standard
UPSC optionals. Students can select any of them (R1.3), which calls
``PUT /optional/selection`` → requires an ``optional_subjects`` row. Without a
DB row, the subject returns 404 on selection, config, completeness, etc.

This seeder creates a **minimal scaffold row** for every subject not already in
the DB. Geography and Public Administration are imported by their own seeders
(``importer.py`` / ``pubad_seed.py``) — they are skipped if they already exist.

Each scaffold row:
- Has no papers/sections/topics/content (those come from founder content
  uploads via ``POST /import-subject``).
- Carries a default config with the common feature set (``read``, ``pyq``,
  ``practice``, ``answer``, ``gap``).
- Is marked ``is_complete=False`` with completeness_status indicating content
  is pending — so the completeness endpoint honestly reports "Not started".
- Does NOT fabricate or author content of any kind.

Idempotent: re-running is safe — only missing slugs are inserted.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.optional.models import OptionalSubject

SEEDER_ACTOR = "catalog-scaffold-seeder"

# The canonical 25 standard UPSC optional subjects. Slug + display name must
# match the frontend catalog (``optionalSubjectsCatalog.ts``) so that
# ``PUT /selection`` can resolve any subject a student selects from the UI.
CATALOG: list[dict[str, Any]] = [
    {"slug": "agriculture", "name": "Agriculture"},
    {"slug": "animal-husbandry-veterinary-science", "name": "Animal Husbandry & Veterinary Science"},
    {"slug": "anthropology", "name": "Anthropology"},
    {"slug": "botany", "name": "Botany"},
    {"slug": "chemistry", "name": "Chemistry"},
    {"slug": "civil-engineering", "name": "Civil Engineering"},
    {"slug": "commerce-accountancy", "name": "Commerce & Accountancy"},
    {"slug": "economics", "name": "Economics"},
    {"slug": "electrical-engineering", "name": "Electrical Engineering"},
    {"slug": "geography", "name": "Geography"},
    {"slug": "geology", "name": "Geology"},
    {"slug": "history", "name": "History"},
    {"slug": "law", "name": "Law"},
    {"slug": "management", "name": "Management"},
    {"slug": "mathematics", "name": "Mathematics"},
    {"slug": "mechanical-engineering", "name": "Mechanical Engineering"},
    {"slug": "medical-science", "name": "Medical Science"},
    {"slug": "philosophy", "name": "Philosophy"},
    {"slug": "physics", "name": "Physics"},
    {"slug": "political-science-international-relations", "name": "Political Science & International Relations"},
    {"slug": "psychology", "name": "Psychology"},
    {"slug": "public-administration", "name": "Public Administration"},
    {"slug": "sociology", "name": "Sociology"},
    {"slug": "statistics", "name": "Statistics"},
    {"slug": "zoology", "name": "Zoology"},
]

# Default features for a subject with no subject-specific configuration yet.
_DEFAULT_CONFIG: dict[str, Any] = {
    "papers": [
        {"label": "PAPER_I", "sections": ["SECTION_A", "SECTION_B"]},
        {"label": "PAPER_II", "sections": []},
    ],
    "features": ["read", "pyq", "practice", "answer", "gap"],
}


def seed_catalog(
    session: Session,
    *,
    actor: str = SEEDER_ACTOR,
) -> dict[str, int]:
    """Ensure all 25 subjects exist in ``optional_subjects``.

    Only inserts subjects whose slug is not already present. Returns a report
    of how many were created vs already existed.
    """
    existing_slugs: set[str] = {
        row[0]
        for row in session.query(OptionalSubject.slug).all()
    }

    created = 0
    skipped = 0

    for order, entry in enumerate(CATALOG):
        slug = entry["slug"]
        if slug in existing_slugs:
            skipped += 1
            continue

        session.add(
            OptionalSubject(
                slug=slug,
                name=entry["name"],
                description=f"UPSC {entry['name']} optional — scaffold. Content pending authoring + founder review.",
                display_order=order,
                is_complete=False,
                config=_DEFAULT_CONFIG,
                completeness_status={"phase": "phase-2-scaffold", "content": "pending-authoring"},
                created_by=actor,
                updated_by=actor,
            )
        )
        created += 1

    session.flush()
    return {"total_catalog": len(CATALOG), "created": created, "skipped": skipped}


def main() -> None:  # pragma: no cover - CLI entrypoint
    """Seed the catalog (run via ``python -m app.core.optional.catalog_seed``)."""
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        counts = seed_catalog(session)
        session.commit()
        print("=== Optional subjects catalog seeded ===")
        for k, v in counts.items():
            print(f"  {k:<16} {v}")
    finally:
        session.close()


if __name__ == "__main__":
    main()


__all__ = ["seed_catalog", "CATALOG", "SEEDER_ACTOR"]
