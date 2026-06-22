"""Generic subject content ingestion (Task 17.2 enabler — R19.1 / R19.2).

Lets a content author/founder **upload a subject's syllabus structure + PYQs**
from a single structured payload (JSON), creating the canonical DB rows so the
subject becomes navigable. Deep Read notes are authored later; this seeds the
skeleton (papers → sections → topics/subtopics) and the PYQ corpus.

Content honesty (vision §0 + design Property 8): everything is ingested as
**gated draft** by default (``review_status="UNREVIEWED"``), so it is hidden
from students until the founder reviews it and publishes it via the review
workflow (`POST /optional/review/{kind}/{id}`). This module fabricates no
content — it only stores what the founder provides.

Idempotent per subject: re-importing a slug replaces that subject's tree
(reusing the Geography importer's FK-safe delete).

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.

Payload shape (see ``DOCS/CONTENT_UPLOAD_TEMPLATE.md``)::

    {
      "slug": "history",
      "name": "History",
      "description": "...",                      # optional
      "features": ["read","pyq","practice", ...], # optional
      "papers": [
        {"label": "PAPER_I", "name": "Paper I", "sections": [
          {"label": "SECTION_A", "name": "Section A", "topics": [
            {"title": "...", "official_phrasing": "...",
             "subtopics": [{"title": "...", "official_phrasing": "..."}]}
          ]}
        ]},
        {"label": "PAPER_II", "name": "Paper II", "sections": [
          {"label": null, "name": "Paper II", "topics": [...]}
        ]}
      ],
      "pyqs": [
        {"year": 2020, "paper": "PAPER_I", "section": "SECTION_A",
         "topic_title": "...", "question": "...", "marks": 15,
         "beyond_syllabus": false}
      ]
    }
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.optional.models import (
    OptionalSubject,
    Paper,
    Section,
    SyllabusNode,
    Pyq,
    PaperLabelEnum,
    SectionLabelEnum,
    SyllabusNodeTypeEnum,
    OptionalReviewStatusEnum,
)
from app.core.optional.importer import _delete_existing_subject

DEFAULT_FEATURES = ["read", "pyq", "practice", "answer", "gap"]


def _paper_label(value: Any) -> PaperLabelEnum:
    return PaperLabelEnum(str(value).strip().upper())


def _section_label(value: Any) -> Optional[SectionLabelEnum]:
    if value in (None, "", "null"):
        return None
    return SectionLabelEnum(str(value).strip().upper())


def import_subject_from_payload(
    session: Session,
    payload: dict[str, Any],
    *,
    review_status: str = "UNREVIEWED",
    actor: str = "subject-content-upload",
) -> dict[str, int]:
    """Ingest a subject's syllabus + PYQs from ``payload`` (gated draft by default).

    Returns a counts report. Raises ``ValueError`` for a missing slug/name or an
    unknown paper/section label.
    """
    slug = str(payload.get("slug", "")).strip()
    name = str(payload.get("name", "")).strip()
    if not slug or not name:
        raise ValueError("payload must include a non-empty 'slug' and 'name'")

    rs_enum = OptionalReviewStatusEnum(review_status)

    # Idempotent: drop any existing tree for this slug first.
    _delete_existing_subject(session, slug)

    features = payload.get("features") or DEFAULT_FEATURES
    subject = OptionalSubject(
        slug=slug,
        name=name,
        description=payload.get("description"),
        display_order=int(payload.get("display_order", 0) or 0),
        is_complete=False,
        config={
            "papers": [
                {
                    "label": str(p.get("label", "")).strip().upper(),
                    "sections": [
                        (str(s.get("label")).strip().upper() if s.get("label") else None)
                        for s in (p.get("sections") or [])
                    ],
                }
                for p in (payload.get("papers") or [])
            ],
            "features": [str(f) for f in features],
        },
        completeness_status={"phase": "phase-2-upload", "content": "pending-review"},
        created_by=actor,
        updated_by=actor,
    )
    session.add(subject)
    session.flush()

    counts = {
        "subjects": 1,
        "papers": 0,
        "sections": 0,
        "topic_nodes": 0,
        "subtopic_nodes": 0,
        "pyqs": 0,
    }

    # Index for mapping PYQs to topic nodes by (paper_label, section_label, title).
    topic_index: dict[tuple, SyllabusNode] = {}
    paper_by_label: dict[str, Paper] = {}
    section_by_key: dict[tuple, Section] = {}

    for p_order, p in enumerate(payload.get("papers") or []):
        plabel = _paper_label(p.get("label"))
        paper = Paper(
            subject_id=subject.id,
            label=plabel,
            name=str(p.get("name") or plabel.value),
            display_order=p_order,
            created_by=actor,
            updated_by=actor,
        )
        session.add(paper)
        session.flush()
        counts["papers"] += 1
        paper_by_label[plabel.value] = paper

        for s_order, s in enumerate(p.get("sections") or []):
            slabel = _section_label(s.get("label"))
            section = Section(
                paper_id=paper.id,
                label=slabel,
                name=str(s.get("name") or (slabel.value if slabel else paper.name)),
                display_order=s_order,
                created_by=actor,
                updated_by=actor,
            )
            session.add(section)
            session.flush()
            counts["sections"] += 1
            section_by_key[(plabel.value, slabel.value if slabel else None)] = section

            for t_order, t in enumerate(s.get("topics") or []):
                title = str(t.get("title", "")).strip()
                if not title:
                    continue
                topic = SyllabusNode(
                    section_id=section.id,
                    parent_id=None,
                    title=title,
                    official_phrasing=t.get("official_phrasing"),
                    node_type=SyllabusNodeTypeEnum.TOPIC,
                    weight=float(len(t.get("subtopics") or []) or 1),
                    display_order=t_order,
                    review_status=rs_enum,
                    created_by=actor,
                    updated_by=actor,
                )
                session.add(topic)
                session.flush()
                counts["topic_nodes"] += 1
                topic_index[(plabel.value, slabel.value if slabel else None, title.lower())] = topic

                for st_order, st in enumerate(t.get("subtopics") or []):
                    st_title = str(st.get("title", "")).strip()
                    if not st_title:
                        continue
                    session.add(
                        SyllabusNode(
                            section_id=section.id,
                            parent_id=topic.id,
                            title=st_title,
                            official_phrasing=st.get("official_phrasing"),
                            node_type=SyllabusNodeTypeEnum.SUBTOPIC,
                            weight=1.0,
                            display_order=st_order,
                            review_status=rs_enum,
                            created_by=actor,
                            updated_by=actor,
                        )
                    )
                    counts["subtopic_nodes"] += 1

    session.flush()

    # PYQs — mapped to a topic node when (paper, section, topic_title) matches.
    for q in payload.get("pyqs") or []:
        question = str(q.get("question", "")).strip()
        if not question:
            continue
        try:
            year = int(q.get("year")) if q.get("year") not in (None, "") else 0
        except (TypeError, ValueError):
            year = 0
        plabel = _paper_label(q["paper"]) if q.get("paper") else None
        slabel = _section_label(q.get("section"))
        topic = None
        if plabel and q.get("topic_title"):
            topic = topic_index.get(
                (plabel.value, slabel.value if slabel else None, str(q["topic_title"]).strip().lower())
            )
        paper = paper_by_label.get(plabel.value) if plabel else None
        section = section_by_key.get((plabel.value, slabel.value if slabel else None)) if plabel else None

        session.add(
            Pyq(
                subject_id=subject.id,
                paper_id=paper.id if paper else None,
                section_id=section.id if section else None,
                topic_node_id=topic.id if topic else None,
                year=year,
                paper_label=plabel,
                section_label=slabel,
                question_text=question,
                marks=q.get("marks"),
                beyond_syllabus=bool(q.get("beyond_syllabus", False)),
                review_status=rs_enum,
                created_by=actor,
                updated_by=actor,
            )
        )
        counts["pyqs"] += 1

    session.flush()
    return counts


__all__ = ["import_subject_from_payload", "DEFAULT_FEATURES"]
