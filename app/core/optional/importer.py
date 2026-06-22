"""Geography Optional content importer (Task 4.1) — no-loss migration, step 2.

This is the BACKEND half of the two-step, no-loss content migration pipeline.

Step 1 (frontend): ``frontend/scripts/extract-geo-optional-content.mjs`` reads
the authored TypeScript modules (``geomorphology.ts`` / ``climatology.ts`` +
the ``DiagramId`` union + the diagram registry), mechanically transpiles and
serializes them, and writes a faithful JSON artifact to
``backend/app/core/optional/data/geo_optional_content.json``. There is no hand
transcription — the artifact is exactly the live TS objects.

Step 2 (this module): reads that artifact and upserts the canonical rows for
the Geography optional subject following the design "Content migration (no
loss)" 1:1 mapping::

    OptionalSubject "geography"
      Paper I
        Section A
          SyllabusNode (TOPIC)  per topic (Geomorphology, Climatology)
            official_phrasing = the official printed syllabus lines
            ContentUnit (topic overview: summary / trends / official / meta)
            HiddenTopic rows  (one per syllabus.hiddenTopics entry)
            SyllabusNode (SUBTOPIC) per subtopic
              ContentUnit (blocks + examKeywords + answerLanguage)
                Diagram rows   (one per `diagram` block — all 11 ids)
                SourceRef      (authoritative source)
              Pyq rows         (one per pyq)

Idempotency: a run first removes the existing ``geography`` subject tree
wholesale (in FK-safe order) and then recreates it, so re-running yields the
same counts and never duplicates.

Requirements: 5.3, 5.5, 18.2 (and R17.1/R17.4 via SourceRef + review_status).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.optional.models import (
    OptionalSubject,
    Paper,
    Section,
    SyllabusNode,
    ContentUnit,
    Diagram,
    SourceRef,
    Pyq,
    HiddenTopic,
    PaperLabelEnum,
    SectionLabelEnum,
    SyllabusNodeTypeEnum,
    OptionalReviewStatusEnum,
)

# Default artifact path (committed, reproducible): produced by the extractor.
DEFAULT_ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "geo_optional_content.json"

# Authoritative source attached to every imported content unit (R17.1, R17.4).
_AUTHORITATIVE_SOURCE = {
    "title": "Official UPSC Geography (Optional) Syllabus — Paper I, Section A (Physical Geography)",
    "citation": (
        "Union Public Service Commission, Civil Services (Main) Examination — "
        "Geography optional syllabus; content grounded in the official printed "
        "syllabus and 25+ years of question patterns."
    ),
    "source_type": "OFFICIAL_SYLLABUS",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_artifact(artifact_path: Optional[os.PathLike | str] = None) -> dict[str, Any]:
    """Load the extractor's JSON artifact."""
    path = Path(artifact_path) if artifact_path else DEFAULT_ARTIFACT_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Content artifact not found at {path}. Run the frontend extractor first: "
            f"`node scripts/extract-geo-optional-content.mjs` (from frontend/)."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _delete_existing_subject(session: Session, slug: str) -> None:
    """Remove an existing subject tree in FK-safe order (idempotency)."""
    subject = session.query(OptionalSubject).filter(OptionalSubject.slug == slug).one_or_none()
    if subject is None:
        return

    subject_id = subject.id
    # Collect node + content-unit ids belonging to this subject.
    node_ids = [
        nid
        for (nid,) in session.query(SyllabusNode.id)
        .join(Section, SyllabusNode.section_id == Section.id)
        .join(Paper, Section.paper_id == Paper.id)
        .filter(Paper.subject_id == subject_id)
        .all()
    ]
    # Include descendant nodes (subtopics whose section_id may be null but whose
    # ancestry leads back to the subject). Walk down by parent.
    frontier = list(node_ids)
    seen = set(node_ids)
    while frontier:
        children = (
            session.query(SyllabusNode.id)
            .filter(SyllabusNode.parent_id.in_(frontier))
            .all()
        )
        frontier = [cid for (cid,) in children if cid not in seen]
        seen.update(frontier)
    node_ids = list(seen)

    cu_ids = []
    if node_ids:
        cu_ids = [
            cid
            for (cid,) in session.query(ContentUnit.id)
            .filter(ContentUnit.syllabus_node_id.in_(node_ids))
            .all()
        ]

    if cu_ids:
        session.query(Diagram).filter(Diagram.content_unit_id.in_(cu_ids)).delete(
            synchronize_session=False
        )
        session.query(SourceRef).filter(SourceRef.content_unit_id.in_(cu_ids)).delete(
            synchronize_session=False
        )
    session.query(Pyq).filter(Pyq.subject_id == subject_id).delete(synchronize_session=False)
    if node_ids:
        session.query(HiddenTopic).filter(
            HiddenTopic.syllabus_node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        session.query(ContentUnit).filter(
            ContentUnit.syllabus_node_id.in_(node_ids)
        ).delete(synchronize_session=False)
        # Delete deepest nodes first to respect the self-referential FK.
        for nid in sorted(node_ids, reverse=True):
            session.query(SyllabusNode).filter(SyllabusNode.id == nid).delete(
                synchronize_session=False
            )
    # Sections + papers, then the subject.
    paper_ids = [pid for (pid,) in session.query(Paper.id).filter(Paper.subject_id == subject_id).all()]
    if paper_ids:
        session.query(Section).filter(Section.paper_id.in_(paper_ids)).delete(
            synchronize_session=False
        )
    session.query(Paper).filter(Paper.subject_id == subject_id).delete(synchronize_session=False)
    session.query(OptionalSubject).filter(OptionalSubject.id == subject_id).delete(
        synchronize_session=False
    )
    session.flush()


def import_geography_optional(
    session: Session,
    *,
    artifact_path: Optional[os.PathLike | str] = None,
    review_status: str = "REVIEWED",
    actor: str = "geo-optional-importer",
) -> dict[str, Any]:
    """Import the Geography optional deep notes + diagrams into the DB.

    The migrated Geomorphology/Climatology notes are established, authored deep
    notes (already shipping in the frontend), so ``authored=True`` and the
    default ``review_status="REVIEWED"`` with an attached authoritative source
    keeps the Read layer (R5.3) functional while satisfying R17.1/R17.4. Pass
    ``review_status="IN_REVIEW"`` to gate them behind the review workflow.

    Idempotent: replaces the geography subject tree on each run.

    Returns a counts report (imported vs source).
    """
    artifact = load_artifact(artifact_path)
    slug = artifact["subjectSlug"]
    rs_enum = OptionalReviewStatusEnum(review_status)
    reviewed_at = _now() if rs_enum == OptionalReviewStatusEnum.REVIEWED else None

    _delete_existing_subject(session, slug)

    counts = {
        "subjects": 0,
        "papers": 0,
        "sections": 0,
        "topic_nodes": 0,
        "subtopic_nodes": 0,
        "content_units": 0,
        "diagrams": 0,
        "source_refs": 0,
        "pyqs": 0,
        "hidden_topics": 0,
        "exam_keywords": 0,
        "answer_language_lines": 0,
        "official_lines": 0,
        "trends": 0,
    }

    # --- Subject -----------------------------------------------------------
    subject = OptionalSubject(
        slug=slug,
        name=artifact["subjectName"],
        description=(
            "UPSC Geography optional — deep notes folded into the LMS spine "
            "(Phase 1 stabilization target)."
        ),
        display_order=0,
        is_complete=False,
        config={
            "papers": [
                {"label": "PAPER_I", "sections": ["SECTION_A", "SECTION_B"]},
                {"label": "PAPER_II", "sections": []},
            ],
            "features": [
                "read",
                "pyq",
                "practice",
                "answer",
                "mapping",
                "diagrams",
                "gap",
                "recall",
            ],
            "diagram_ids": artifact["diagramIds"],
        },
        completeness_status={
            "phase": "phase-1-in-progress",
            "imported_topics": [t["slug"] for t in artifact["topics"]],
        },
        created_by=actor,
        updated_by=actor,
    )
    session.add(subject)
    session.flush()
    counts["subjects"] += 1

    # --- Paper I -----------------------------------------------------------
    paper_i = Paper(
        subject_id=subject.id,
        label=PaperLabelEnum.PAPER_I,
        name="Paper I",
        display_order=0,
        created_by=actor,
        updated_by=actor,
    )
    session.add(paper_i)
    session.flush()
    counts["papers"] += 1

    # --- Section A ---------------------------------------------------------
    section_label = artifact["topics"][0].get("section", "Section A")
    section_a = Section(
        paper_id=paper_i.id,
        label=SectionLabelEnum.SECTION_A,
        name=section_label,
        display_order=0,
        created_by=actor,
        updated_by=actor,
    )
    session.add(section_a)
    session.flush()
    counts["sections"] += 1

    # --- Topics ------------------------------------------------------------
    for t_index, topic in enumerate(artifact["topics"]):
        syllabus = topic["syllabus"]
        subtopics = topic["subtopics"]

        topic_node = SyllabusNode(
            section_id=section_a.id,
            parent_id=None,
            title=topic["title"],
            official_phrasing="\n".join(syllabus["official"]),
            node_type=SyllabusNodeTypeEnum.TOPIC,
            weight=float(len(subtopics)),  # bottom-up: sum of subtopic weights (1.0 each)
            display_order=t_index,
            review_status=rs_enum,
            created_by=actor,
            updated_by=actor,
        )
        session.add(topic_node)
        session.flush()
        counts["topic_nodes"] += 1
        counts["official_lines"] += len(syllabus["official"])
        counts["trends"] += len(syllabus["trendSays"])

        # Topic-level overview content unit (preserves meta + trend layer).
        overview_unit = ContentUnit(
            syllabus_node_id=topic_node.id,
            title=f"{topic['title']} — Overview",
            blocks={
                "kind": "topic-overview",
                "slug": topic["slug"],
                "paper": topic["paper"],
                "section": topic["section"],
                "order": topic["order"],
                "status": topic["status"],
                "summary": topic["summary"],
                "readMinutes": topic["readMinutes"],
                "syllabus": {
                    "official": syllabus["official"],
                    "trendSays": syllabus["trendSays"],
                    "hiddenTopics": syllabus["hiddenTopics"],
                },
            },
            exam_keywords=None,
            answer_language=None,
            hidden_topics=syllabus["hiddenTopics"],
            authored=True,
            review_status=rs_enum,
            reviewed_at=reviewed_at,
            display_order=0,
            created_by=actor,
            updated_by=actor,
        )
        session.add(overview_unit)
        session.flush()
        counts["content_units"] += 1

        overview_source = SourceRef(
            content_unit_id=overview_unit.id,
            created_by=actor,
            updated_by=actor,
            **_AUTHORITATIVE_SOURCE,
        )
        session.add(overview_source)
        counts["source_refs"] += 1

        # Hidden topics (filed under the topic node) — R4.3.
        for ht in syllabus["hiddenTopics"]:
            session.add(
                HiddenTopic(
                    syllabus_node_id=topic_node.id,
                    title=ht["topic"],
                    rationale=ht["why"],
                    created_by=actor,
                    updated_by=actor,
                )
            )
            counts["hidden_topics"] += 1

        # Subtopics.
        for s_index, st in enumerate(subtopics):
            subtopic_node = SyllabusNode(
                section_id=section_a.id,
                parent_id=topic_node.id,
                title=st["title"],
                official_phrasing=st.get("syllabusTag"),
                node_type=SyllabusNodeTypeEnum.SUBTOPIC,
                weight=1.0,
                display_order=s_index,
                review_status=rs_enum,
                created_by=actor,
                updated_by=actor,
            )
            session.add(subtopic_node)
            session.flush()
            counts["subtopic_nodes"] += 1

            content_unit = ContentUnit(
                syllabus_node_id=subtopic_node.id,
                title=st["title"],
                blocks={
                    "kind": "subtopic",
                    "subtopicId": st["id"],
                    "hook": st["hook"],
                    "syllabusTag": st["syllabusTag"],
                    "blocks": st["blocks"],
                },
                exam_keywords=st["examKeywords"],
                answer_language=st["answerLanguage"],
                hidden_topics=None,
                authored=True,
                review_status=rs_enum,
                reviewed_at=reviewed_at,
                display_order=0,
                created_by=actor,
                updated_by=actor,
            )
            session.add(content_unit)
            session.flush()
            counts["content_units"] += 1
            counts["exam_keywords"] += len(st["examKeywords"])
            counts["answer_language_lines"] += len(st["answerLanguage"])

            session.add(
                SourceRef(
                    content_unit_id=content_unit.id,
                    created_by=actor,
                    updated_by=actor,
                    **_AUTHORITATIVE_SOURCE,
                )
            )
            counts["source_refs"] += 1

            # Diagram rows — one per `diagram` block (covers all 11 ids).
            d_order = 0
            for block in st["blocks"]:
                if block.get("type") == "diagram":
                    session.add(
                        Diagram(
                            content_unit_id=content_unit.id,
                            diagram_id=block["id"],
                            title=block["id"],
                            caption=block.get("caption"),
                            display_order=d_order,
                            created_by=actor,
                            updated_by=actor,
                        )
                    )
                    d_order += 1
                    counts["diagrams"] += 1

            # PYQ rows — one per pyq, mapped to the subtopic node.
            for pyq in st["pyq"]:
                year_raw = pyq.get("year")
                try:
                    year = int(year_raw) if year_raw not in (None, "") else 0
                except (TypeError, ValueError):
                    year = 0
                session.add(
                    Pyq(
                        subject_id=subject.id,
                        paper_id=paper_i.id,
                        section_id=section_a.id,
                        topic_node_id=subtopic_node.id,
                        year=year,
                        paper_label=PaperLabelEnum.PAPER_I,
                        section_label=SectionLabelEnum.SECTION_A,
                        question_text=pyq["q"],
                        beyond_syllabus=False,
                        # Importer PYQs belong to the already-REVIEWED authored
                        # deep-notes content, so they are student-visible. Stamp
                        # the same review_status as the content units (default
                        # REVIEWED) so the PYQ read API (task 7.2) surfaces them
                        # without weakening the honesty gate (design Property 8).
                        review_status=rs_enum,
                        created_by=actor,
                        updated_by=actor,
                    )
                )
                counts["pyqs"] += 1

    session.flush()
    return counts


def backfill_pyq_review_status(
    session: Session,
    *,
    actor: str = "geo-optional-importer",
    review_status: str = "REVIEWED",
) -> int:
    """Idempotently stamp legacy importer-owned PYQs that have no review_status.

    The ``Pyq.review_status`` column was added after the importer first ran
    (spec task 7.1), so importer PYQ rows created before that migration carry a
    NULL ``review_status``. Those rows belong to the already-REVIEWED authored
    deep-notes content, so for the PYQ read API (task 7.2) they must be treated
    as student-visible. This helper backfills exactly those rows — importer-
    owned (``created_by == actor``) AND ``review_status IS NULL`` — to REVIEWED.

    It is safe to run repeatedly: only NULL rows are touched, so a second run
    updates nothing. It never touches the task-7.1 DRAFT seed (a different
    actor, and those rows are deliberately stamped UNREVIEWED). Returns the
    number of rows updated.
    """
    rs_enum = OptionalReviewStatusEnum(review_status)
    updated = (
        session.query(Pyq)
        .filter(Pyq.created_by == actor, Pyq.review_status.is_(None))
        .update({Pyq.review_status: rs_enum}, synchronize_session=False)
    )
    session.flush()
    return int(updated or 0)


def _build_source_report(artifact: dict[str, Any]) -> dict[str, int]:
    """Independent source-side counts derived from the artifact (for parity)."""
    topics = artifact["topics"]
    return {
        "topic_nodes": len(topics),
        "subtopic_nodes": sum(len(t["subtopics"]) for t in topics),
        "diagrams": len(artifact["diagramIds"]),
        "pyqs": sum(len(s["pyq"]) for t in topics for s in t["subtopics"]),
        "hidden_topics": sum(len(t["syllabus"]["hiddenTopics"]) for t in topics),
        "exam_keywords": sum(
            len(s["examKeywords"]) for t in topics for s in t["subtopics"]
        ),
        "answer_language_lines": sum(
            len(s["answerLanguage"]) for t in topics for s in t["subtopics"]
        ),
        "official_lines": sum(len(t["syllabus"]["official"]) for t in topics),
        "trends": sum(len(t["syllabus"]["trendSays"]) for t in topics),
    }


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description="Import Geography Optional content into the DB.")
    parser.add_argument("--artifact", default=None, help="Path to the JSON artifact.")
    parser.add_argument(
        "--review-status",
        default="REVIEWED",
        choices=[e.value for e in OptionalReviewStatusEnum],
        help="review_status to stamp on imported content units/nodes.",
    )
    args = parser.parse_args()

    artifact = load_artifact(args.artifact)
    source_report = _build_source_report(artifact)

    session = SessionLocal()
    try:
        counts = import_geography_optional(
            session, artifact_path=args.artifact, review_status=args.review_status
        )
        # Idempotent safety net for any legacy importer PYQ rows that predate
        # the review_status column (NULL) in a pre-existing database.
        backfilled = backfill_pyq_review_status(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("=== Geography Optional import complete ===")
    print(f"Backfilled legacy NULL PYQ review_status rows: {backfilled}")
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
