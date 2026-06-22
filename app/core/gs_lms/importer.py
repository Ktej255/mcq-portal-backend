"""No-loss content importer for GS LMS Platform (Task 9.4).

Mirrors the Optional platform ``importer.py`` pattern: takes a JSON artifact
(or in-memory dict) and imports it into the database as GS LMS content.

The importer handles:
  1. Syllabus tree nodes (with parent relationships, node types, weights, ordering)
  2. Content sections per leaf node (4 sections each with blocks)
  3. PYQs (Prelims + Mains with metadata)
  4. MCQ questions (with options, correct answer, type classification)

Idempotency strategy: match existing records by (title + parent_id) for tree
nodes, (syllabus_node_id + section_label) for content sections, and
(syllabus_node_id + question_text) for PYQs/MCQs. On re-run, existing records
are updated rather than duplicated — running twice produces the same DB state
as running once (Design Property 20).

Review gate: all imported content starts as UNREVIEWED by default, satisfying
Property 19 (review-gate filtering). Pass ``review_status="REVIEWED"`` to
bypass the gate for pre-approved content.

Requirements: 10.5, 11.4
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
    GsLmsPyq,
    GsLmsMcqQuestion,
    GsLmsNodeTypeEnum,
    GsLmsExamTypeEnum,
    GsLmsQuestionTypeEnum,
    GsLmsSectionLabelEnum,
)

# Default artifact path (committed, reproducible).
DEFAULT_ARTIFACT_PATH = (
    Path(__file__).resolve().parent / "data" / "gs_geography_syllabus.json"
)

# Actor identifier stamped on audit fields.
_ACTOR = "gs-lms-importer"


# ---------------------------------------------------------------------------
# Artifact Loading
# ---------------------------------------------------------------------------


def load_artifact(artifact_path: Optional[os.PathLike | str] = None) -> dict[str, Any]:
    """Load a GS LMS JSON artifact from disk.

    Returns the parsed dict. Raises FileNotFoundError if the path does not
    exist.
    """
    path = Path(artifact_path) if artifact_path else DEFAULT_ARTIFACT_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"GS LMS content artifact not found at {path}. "
            "Provide a valid artifact path or place the file at the default location."
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Syllabus Tree Import
# ---------------------------------------------------------------------------


def import_syllabus_tree(
    db: Session,
    tree_data: list[dict[str, Any]],
    subject_id: int,
    *,
    review_status: str = "UNREVIEWED",
    parent_id: Optional[int] = None,
) -> dict[str, Any]:
    """Import a syllabus tree structure into the database.

    Each node in ``tree_data`` is a dict with keys:
      - title (str): Node title
      - node_type (str): MEGA_TOPIC, SUB_TOPIC, or LEAF_TOPIC
      - weight (float): Weight for coverage calculation
      - display_order (int): Order within siblings
      - ordering_justification (str | None): Why this ordering
      - day_lesson_id (int | None): Bridge to existing day-lesson system
      - children (list[dict]): Child nodes (recursive)
      - content_sections (list[dict] | None): Sections for leaf nodes
      - pyqs (list[dict] | None): PYQs for this node
      - mcq_questions (list[dict] | None): MCQ questions for this node

    Idempotency: matches existing nodes by (title + parent_id + subject_id).
    If found, updates attributes; otherwise creates a new node.

    Returns a counts dict summarizing what was imported.
    """
    rs_enum = GsReviewStatusEnum(review_status)
    counts = {
        "nodes_created": 0,
        "nodes_updated": 0,
        "sections_created": 0,
        "sections_updated": 0,
        "pyqs_created": 0,
        "pyqs_updated": 0,
        "mcqs_created": 0,
        "mcqs_updated": 0,
    }

    for node_data in tree_data:
        node_counts = _import_node(
            db,
            node_data,
            subject_id=subject_id,
            parent_id=parent_id,
            review_status=rs_enum,
        )
        _merge_counts(counts, node_counts)

    db.flush()
    return counts


def _import_node(
    db: Session,
    node_data: dict[str, Any],
    *,
    subject_id: int,
    parent_id: Optional[int],
    review_status: GsReviewStatusEnum,
) -> dict[str, Any]:
    """Import a single syllabus node and recurse into children.

    Idempotent: matches by (title, parent_id, subject_id).
    """
    counts = {
        "nodes_created": 0,
        "nodes_updated": 0,
        "sections_created": 0,
        "sections_updated": 0,
        "pyqs_created": 0,
        "pyqs_updated": 0,
        "mcqs_created": 0,
        "mcqs_updated": 0,
    }

    title = node_data["title"]
    node_type = GsLmsNodeTypeEnum(node_data["node_type"])

    # Idempotent lookup: match by title + parent + subject.
    existing = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.title == title,
            GsLmsSyllabusNode.parent_id == parent_id,
            GsLmsSyllabusNode.subject_id == subject_id,
        )
        .one_or_none()
    )

    if existing:
        # Update existing node attributes.
        existing.node_type = node_type
        existing.weight = node_data.get("weight", 1.0)
        existing.display_order = node_data.get("display_order", 0)
        existing.ordering_justification = node_data.get("ordering_justification")
        existing.day_lesson_id = node_data.get("day_lesson_id")
        existing.review_status = review_status
        existing.updated_by = _ACTOR
        db.flush()
        node = existing
        counts["nodes_updated"] += 1
    else:
        # Create new node.
        node = GsLmsSyllabusNode(
            subject_id=subject_id,
            parent_id=parent_id,
            title=title,
            node_type=node_type,
            weight=node_data.get("weight", 1.0),
            display_order=node_data.get("display_order", 0),
            ordering_justification=node_data.get("ordering_justification"),
            day_lesson_id=node_data.get("day_lesson_id"),
            review_status=review_status,
            created_by=_ACTOR,
            updated_by=_ACTOR,
        )
        db.add(node)
        db.flush()
        counts["nodes_created"] += 1

    # Import content sections for this node (if provided).
    sections_data = node_data.get("content_sections")
    if sections_data:
        sec_counts = import_content_sections(
            db, sections_data, node.id, review_status=review_status.value
        )
        counts["sections_created"] += sec_counts["created"]
        counts["sections_updated"] += sec_counts["updated"]

    # Import PYQs for this node (if provided).
    pyqs_data = node_data.get("pyqs")
    if pyqs_data:
        pyq_counts = import_pyqs(
            db, pyqs_data, subject_id, node_id=node.id, review_status=review_status.value
        )
        counts["pyqs_created"] += pyq_counts["created"]
        counts["pyqs_updated"] += pyq_counts["updated"]

    # Import MCQ questions for this node (if provided).
    mcqs_data = node_data.get("mcq_questions")
    if mcqs_data:
        mcq_counts = import_mcq_questions(
            db, mcqs_data, node.id, review_status=review_status.value
        )
        counts["mcqs_created"] += mcq_counts["created"]
        counts["mcqs_updated"] += mcq_counts["updated"]

    # Recurse into children.
    children_data = node_data.get("children", [])
    for child_data in children_data:
        child_counts = _import_node(
            db,
            child_data,
            subject_id=subject_id,
            parent_id=node.id,
            review_status=review_status,
        )
        _merge_counts(counts, child_counts)

    return counts


# ---------------------------------------------------------------------------
# Content Sections Import
# ---------------------------------------------------------------------------


def import_content_sections(
    db: Session,
    sections_data: list[dict[str, Any]],
    node_id: int,
    *,
    review_status: str = "UNREVIEWED",
) -> dict[str, int]:
    """Import content sections for a syllabus node.

    Each section dict has keys:
      - section_label (str): BASIC, ADVANCED, NCERT_LEVEL, or EXAMINER_TRAPS
      - title (str): Section title
      - blocks (list[dict]): Content blocks
      - display_order (int): 1-4
      - authored (bool): Whether content is authored

    Idempotency: matches by (syllabus_node_id + section_label).

    Returns counts of created and updated sections.
    """
    rs_enum = GsReviewStatusEnum(review_status)
    created = 0
    updated = 0

    for sec_data in sections_data:
        section_label = GsLmsSectionLabelEnum(sec_data["section_label"])

        existing = (
            db.query(GsLmsContentSection)
            .filter(
                GsLmsContentSection.syllabus_node_id == node_id,
                GsLmsContentSection.section_label == section_label,
            )
            .one_or_none()
        )

        if existing:
            existing.title = sec_data.get("title", existing.title)
            existing.blocks = sec_data.get("blocks", existing.blocks)
            existing.display_order = sec_data.get("display_order", existing.display_order)
            existing.review_status = rs_enum
            existing.authored = sec_data.get("authored", existing.authored)
            existing.updated_by = _ACTOR
            updated += 1
        else:
            section = GsLmsContentSection(
                syllabus_node_id=node_id,
                section_label=section_label,
                title=sec_data.get("title", section_label.value),
                blocks=sec_data.get("blocks"),
                display_order=sec_data.get("display_order", 0),
                review_status=rs_enum,
                authored=sec_data.get("authored", False),
                created_by=_ACTOR,
                updated_by=_ACTOR,
            )
            db.add(section)
            created += 1

    db.flush()
    return {"created": created, "updated": updated}


# ---------------------------------------------------------------------------
# PYQ Import
# ---------------------------------------------------------------------------


def import_pyqs(
    db: Session,
    pyqs_data: list[dict[str, Any]],
    subject_id: int,
    *,
    node_id: int,
    review_status: str = "UNREVIEWED",
) -> dict[str, int]:
    """Import Previous Year Questions for a subject/node.

    Each PYQ dict has keys:
      - exam_type (str): PRELIMS or MAINS
      - year (int): Year of the question
      - question_text (str): The question
      - answer_text (str | None): Correct answer or model answer
      - explanation (str | None): Explanation
      - marks (int | None): Marks (for Mains)
      - question_type (str | None): Question type classification

    Idempotency: matches by (syllabus_node_id + question_text + year).

    Returns counts of created and updated PYQs.
    """
    rs_enum = GsReviewStatusEnum(review_status)
    created = 0
    updated = 0

    for pyq_data in pyqs_data:
        question_text = pyq_data["question_text"]
        year = pyq_data.get("year", 0)

        existing = (
            db.query(GsLmsPyq)
            .filter(
                GsLmsPyq.syllabus_node_id == node_id,
                GsLmsPyq.question_text == question_text,
                GsLmsPyq.year == year,
            )
            .one_or_none()
        )

        exam_type = GsLmsExamTypeEnum(pyq_data["exam_type"])
        question_type = None
        if pyq_data.get("question_type"):
            question_type = GsLmsQuestionTypeEnum(pyq_data["question_type"])

        if existing:
            existing.exam_type = exam_type
            existing.answer_text = pyq_data.get("answer_text")
            existing.explanation = pyq_data.get("explanation")
            existing.marks = pyq_data.get("marks")
            existing.question_type = question_type
            existing.review_status = rs_enum
            existing.updated_by = _ACTOR
            updated += 1
        else:
            pyq = GsLmsPyq(
                subject_id=subject_id,
                syllabus_node_id=node_id,
                exam_type=exam_type,
                year=year,
                question_text=question_text,
                answer_text=pyq_data.get("answer_text"),
                explanation=pyq_data.get("explanation"),
                marks=pyq_data.get("marks"),
                question_type=question_type,
                review_status=rs_enum,
                created_by=_ACTOR,
                updated_by=_ACTOR,
            )
            db.add(pyq)
            created += 1

    db.flush()
    return {"created": created, "updated": updated}


# ---------------------------------------------------------------------------
# MCQ Questions Import
# ---------------------------------------------------------------------------


def import_mcq_questions(
    db: Session,
    questions_data: list[dict[str, Any]],
    node_id: int,
    *,
    review_status: str = "UNREVIEWED",
) -> dict[str, int]:
    """Import MCQ questions for a syllabus node.

    Each question dict has keys:
      - question_text (str): The question text
      - options (list[dict]): [{label: "A", text: "..."}, ...]
      - correct_option (str): "A", "B", "C", or "D"
      - explanation (str | None): Explanation
      - question_type (str): Question type classification
      - display_order (int): Order for sequential presentation

    Idempotency: matches by (syllabus_node_id + question_text).

    Returns counts of created and updated questions.
    """
    rs_enum = GsReviewStatusEnum(review_status)
    created = 0
    updated = 0

    for q_data in questions_data:
        question_text = q_data["question_text"]

        existing = (
            db.query(GsLmsMcqQuestion)
            .filter(
                GsLmsMcqQuestion.syllabus_node_id == node_id,
                GsLmsMcqQuestion.question_text == question_text,
            )
            .one_or_none()
        )

        question_type = GsLmsQuestionTypeEnum(q_data["question_type"])

        if existing:
            existing.options = q_data["options"]
            existing.correct_option = q_data["correct_option"]
            existing.explanation = q_data.get("explanation")
            existing.question_type = question_type
            existing.display_order = q_data.get("display_order", existing.display_order)
            existing.review_status = rs_enum
            existing.updated_by = _ACTOR
            updated += 1
        else:
            mcq = GsLmsMcqQuestion(
                syllabus_node_id=node_id,
                question_text=question_text,
                options=q_data["options"],
                correct_option=q_data["correct_option"],
                explanation=q_data.get("explanation"),
                question_type=question_type,
                display_order=q_data.get("display_order", 0),
                review_status=rs_enum,
                created_by=_ACTOR,
                updated_by=_ACTOR,
            )
            db.add(mcq)
            created += 1

    db.flush()
    return {"created": created, "updated": updated}


# ---------------------------------------------------------------------------
# Top-level Import Entry Point
# ---------------------------------------------------------------------------


def import_gs_geography(
    db: Session,
    artifact_path_or_data: Optional[os.PathLike | str | dict[str, Any]] = None,
    *,
    review_status: str = "UNREVIEWED",
) -> dict[str, Any]:
    """Import GS Geography LMS content from a JSON artifact or in-memory dict.

    This is the main entry point for bulk loading. Accepts either:
      - A file path (str or PathLike) to a JSON artifact
      - A dict already parsed in memory
      - None (uses the default artifact path)

    The expected artifact structure::

        {
            "subject_id": 1,
            "tree": [
                {
                    "title": "Geomorphology",
                    "node_type": "MEGA_TOPIC",
                    "weight": 5.0,
                    "display_order": 1,
                    "ordering_justification": "Foundation of physical geography",
                    "children": [
                        {
                            "title": "Plate Tectonics",
                            "node_type": "SUB_TOPIC",
                            "weight": 2.0,
                            "display_order": 1,
                            "children": [
                                {
                                    "title": "Continental Drift",
                                    "node_type": "LEAF_TOPIC",
                                    "weight": 1.0,
                                    "display_order": 1,
                                    "content_sections": [...],
                                    "pyqs": [...],
                                    "mcq_questions": [...]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

    Idempotent: running twice produces the same DB state (Property 20).
    All imported content starts as UNREVIEWED by default (Property 19).

    Returns a summary report with counts of all entities processed.
    """
    # Resolve the data source.
    if artifact_path_or_data is None:
        data = load_artifact()
    elif isinstance(artifact_path_or_data, dict):
        data = artifact_path_or_data
    else:
        data = load_artifact(artifact_path_or_data)

    subject_id = data["subject_id"]
    tree_data = data.get("tree", [])

    # Import the syllabus tree (recursively handles sections, PYQs, MCQs).
    counts = import_syllabus_tree(
        db,
        tree_data,
        subject_id,
        review_status=review_status,
    )

    db.flush()

    return {
        "subject_id": subject_id,
        "review_status": review_status,
        **counts,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    """Merge source counts into target (in-place addition)."""
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(
        description="Import GS Geography LMS content into the database."
    )
    parser.add_argument(
        "--artifact", default=None, help="Path to the JSON artifact."
    )
    parser.add_argument(
        "--review-status",
        default="UNREVIEWED",
        choices=[e.value for e in GsReviewStatusEnum],
        help="review_status to stamp on imported content (default: UNREVIEWED).",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.artifact:
            result = import_gs_geography(
                session, args.artifact, review_status=args.review_status
            )
        else:
            result = import_gs_geography(session, review_status=args.review_status)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("=== GS LMS Geography import complete ===")
    print("Import results:")
    for k, v in result.items():
        print(f"  {k:<20} {v}")


if __name__ == "__main__":  # pragma: no cover
    main()
