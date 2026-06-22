"""Geography Optional PYQ corpus seeder (Task 7.1) — DRAFT / UNREVIEWED.

================================ HONESTY NOTICE ================================
THIS IS A DRAFT, UNREVIEWED SEED DATASET — **NOT** the verified, complete
26-year UPSC Geography optional PYQ corpus.

Every PYQ row produced by this seeder is stamped ``review_status=UNREVIEWED``
(unless the operator explicitly passes ``mark_reviewed=True``). The read layer
(spec task 7.2) gates UNREVIEWED PYQs out of the student view exactly like
unreviewed content (design Property 8 / R17.2, R17.3). The corpus therefore
stays invisible to students until the founder validates each question against
the official UPSC question papers.

The deliverable here is twofold (founder decision):
  1. A robust, idempotent SEEDING PIPELINE that loads a Geography PYQ corpus
     into the existing canonical models (``Pyq`` / ``HiddenTopic`` / ``SourceRef``
     mapped onto ``SyllabusNode``).
  2. A credible STARTER draft dataset (below) — a representative spread across
     years and across Paper I Section A, Paper I Section B and Paper II — that
     is explicitly labelled unverified. Full, fully-accurate 26-year population
     is a later content-review pass, not this task.

Do NOT present this content to students or claim it is verified. The question
texts are honest, examiner-style drafts authored for pipeline/shape validation;
their exact wording and year attribution MUST be checked against the official
UPSC Civil Services (Main) Geography optional question papers before review.
==============================================================================

Pipeline behaviour
------------------
``seed_geography_pyqs(session, *, mark_reviewed=False)``:

* Requires the Geography optional subject + syllabus tree to already exist
  (seeded by ``importer.import_geography_optional`` — spec task 4.1). It maps
  each draft PYQ to a real ``SyllabusNode`` **by title**.
* Paper I Section A questions map onto the existing Physical-Geography topic /
  subtopic nodes created by the importer.
* Paper I Section B (Human Geography) and Paper II (Geography of India) are not
  yet modelled as syllabus nodes by the importer (it only imported Section A),
  so the seeder lazily creates the minimal **gated** (UNREVIEWED) topic-node
  scaffold for those segments — owned by the seeder actor and torn down on
  re-run — so the draft corpus can span the whole subject honestly.
* Attaches authoritative ``SourceRef`` provenance (official UPSC question
  papers) to every PYQ and hidden topic (R17.1).
* Files "themes asked beyond the printed syllabus" as ``HiddenTopic`` rows under
  the right node, with a rationale (R4.3); their PYQs carry
  ``beyond_syllabus=True``.

Idempotency: a run first removes every row this seeder previously created for
the Geography subject (scoped by the seeder actor, in FK-safe order) and then
recreates them — so re-running yields identical counts and never duplicates,
and it never disturbs the importer-owned content tree.

Requirements: 4.1, 4.2, 4.3, 17.1
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.optional.models import (
    OptionalSubject,
    Paper,
    Section,
    SyllabusNode,
    SourceRef,
    Pyq,
    HiddenTopic,
    PaperLabelEnum,
    SectionLabelEnum,
    SyllabusNodeTypeEnum,
    OptionalReviewStatusEnum,
)

# Subject this seeder is responsible for.
SUBJECT_SLUG = "geography"

# Actor tag stamped on every row this seeder owns. Idempotent cleanup is scoped
# to this tag so the seeder never touches importer-owned content.
SEEDER_ACTOR = "geo-pyq-seeder"

# ---------------------------------------------------------------------------
# Authoritative sources (provenance) — R17.1.
# A source is what backs accuracy; the review_status column is the gate.
# ---------------------------------------------------------------------------
_DRAFT_NOTE = (
    "DRAFT — UNREVIEWED. Question texts and year attribution are examiner-style "
    "drafts pending verification against the official UPSC papers; not yet "
    "shown to students."
)

_SOURCE_PYQ = {
    "title": (
        "UPSC Civil Services (Main) Examination — Geography (Optional) "
        "Previous-Year Question Papers"
    ),
    "citation": (
        "Union Public Service Commission, Civil Services (Main) Examination — "
        "Geography optional question papers (Paper I & Paper II). "
        + _DRAFT_NOTE
    ),
    "url": None,
    "source_type": "OFFICIAL_PYQ",
}

_SOURCE_HIDDEN = {
    "title": (
        "UPSC Geography (Optional) — 25+ year question-pattern / trend analysis"
    ),
    "citation": (
        "Themes recurrently asked beyond the printed syllabus, derived from a "
        "scan of past Geography optional papers. " + _DRAFT_NOTE
    ),
    "url": None,
    "source_type": "TREND_ANALYSIS",
}


# ---------------------------------------------------------------------------
# DRAFT seed dataset
# ---------------------------------------------------------------------------
# Shape of each PYQ record:
#   year:            int        exam year (DRAFT attribution)
#   paper:           "PAPER_I" | "PAPER_II"
#   section:         "SECTION_A" | "SECTION_B" | None   (None for Paper II)
#   topic_title:     str        syllabus node title to map onto (by title)
#   question_text:   str        examiner-style draft question
#   marks:           int | None
#   beyond_syllabus: bool       theme appeared beyond the printed syllabus
#
# Paper I Section A topic_titles MATCH the importer's real subtopic nodes.
# Paper I Section B and Paper II topic_titles are official-syllabus headings the
# seeder scaffolds as gated topic nodes.

# --- Paper I, Section A — Physical Geography (maps to existing importer nodes)
_PYQS_PAPER_I_SEC_A: list[dict[str, Any]] = [
    {"year": 2023, "topic_title": "Plate tectonics, continental drift & recent views on mountain building",
     "question_text": "Examine the role of plate tectonics in explaining the global distribution of fold mountains, with special reference to the Himalaya.", "marks": 20},
    {"year": 2019, "topic_title": "Plate tectonics, continental drift & recent views on mountain building",
     "question_text": "Bring out the contribution of the continental drift hypothesis to the development of the theory of plate tectonics.", "marks": 15},
    {"year": 2008, "topic_title": "Plate tectonics, continental drift & recent views on mountain building",
     "question_text": "Discuss the recent views on mountain building in the light of plate-tectonic theory.", "marks": 20},
    {"year": 2021, "topic_title": "Isostasy — Airy vs Pratt and the modern view",
     "question_text": "Compare and contrast the views of Airy and Pratt on isostasy.", "marks": 15},
    {"year": 2004, "topic_title": "Isostasy — Airy vs Pratt and the modern view",
     "question_text": "Explain the concept of isostasy and discuss its relevance to the present-day understanding of crustal equilibrium.", "marks": 20},
    {"year": 2022, "topic_title": "Geomorphic cycles, landscape development & slope theories",
     "question_text": "Critically evaluate the Davisian concept of the geographical cycle of erosion and contrast it with Penck's model.", "marks": 20},
    {"year": 2015, "topic_title": "Geomorphic cycles, landscape development & slope theories",
     "question_text": "Discuss the slope-development theories and their significance in understanding landscape evolution.", "marks": 15},
    {"year": 2017, "topic_title": "Channel morphology & denudation chronology",
     "question_text": "Explain the concept of the graded profile of a river and the factors responsible for rejuvenation.", "marks": 15},
    {"year": 2011, "topic_title": "Factors controlling landform development — endogenetic & exogenetic forces",
     "question_text": "Distinguish between endogenetic and exogenetic forces and assess their role in shaping landforms.", "marks": 15},
    {"year": 2020, "topic_title": "Applied Geomorphology — geohydrology, economic geology & environment",
     "question_text": "Discuss the relevance of applied geomorphology in watershed management and natural-hazard mitigation.", "marks": 15,
     "beyond_syllabus": True},
    {"year": 2024, "topic_title": "Monsoons & jet streams",
     "question_text": "Examine the jet-stream theory of the Indian monsoon and contrast it with the classical thermal concept.", "marks": 20},
    {"year": 2018, "topic_title": "Monsoons & jet streams",
     "question_text": "Assess the influence of ENSO and the Indian Ocean Dipole on the inter-annual variability of the Indian monsoon.", "marks": 15,
     "beyond_syllabus": True},
    {"year": 2016, "topic_title": "Air masses, fronts & cyclones",
     "question_text": "Compare and contrast the origin and structure of temperate and tropical cyclones with suitable diagrams.", "marks": 20},
    {"year": 2013, "topic_title": "Precipitation & climate classification",
     "question_text": "Critically evaluate Köppen's scheme of climatic classification and compare it with that of Thornthwaite.", "marks": 20},
    {"year": 2022, "topic_title": "Climate change & applied / urban climatology",
     "question_text": "Explain the formation of the urban heat island and suggest measures to mitigate it.", "marks": 15,
     "beyond_syllabus": True},
    {"year": 2010, "topic_title": "Heat budget & temperature / pressure belts",
     "question_text": "Describe the heat budget of the earth and account for the latitudinal imbalance of net radiation.", "marks": 20},
    {"year": 2014, "topic_title": "Atmospheric circulation, winds & stability",
     "question_text": "Explain the tri-cellular model of atmospheric circulation and its control over global wind and rainfall belts.", "marks": 15},
]

# --- Paper I, Section B — Human Geography (scaffolded gated topic nodes)
_PYQS_PAPER_I_SEC_B: list[dict[str, Any]] = [
    {"year": 2023, "topic_title": "Perspectives in Human Geography",
     "question_text": "Examine the relevance of the areal-differentiation and spatial-organisation perspectives in contemporary human geography.", "marks": 20},
    {"year": 2012, "topic_title": "Perspectives in Human Geography",
     "question_text": "Bring out the significance of the welfare and humanistic approaches in human geography.", "marks": 15},
    {"year": 2020, "topic_title": "Economic Geography",
     "question_text": "Critically examine Weber's theory of industrial location in the context of modern manufacturing.", "marks": 20},
    {"year": 2018, "topic_title": "Population and Settlement Geography",
     "question_text": "Discuss the demographic transition model and assess its applicability to developing countries.", "marks": 15},
    {"year": 2016, "topic_title": "Models, Theories and Laws in Human Geography",
     "question_text": "Explain the central-place theory of Christaller and discuss its limitations.", "marks": 20},
    {"year": 2009, "topic_title": "Regional Planning",
     "question_text": "Discuss the concept of growth poles and growth centres in regional planning.", "marks": 15},
]

# --- Paper II — Geography of India (scaffolded gated topic nodes)
_PYQS_PAPER_II: list[dict[str, Any]] = [
    {"year": 2024, "topic_title": "Physical Setting",
     "question_text": "Account for the physiographic diversity of India and its influence on the drainage system.", "marks": 20},
    {"year": 2019, "topic_title": "Agriculture",
     "question_text": "Examine the regional disparities in the success of the Green Revolution in India.", "marks": 15},
    {"year": 2021, "topic_title": "Resources",
     "question_text": "Assess the prospects of non-conventional energy resources in meeting India's growing energy demand.", "marks": 15,
     "beyond_syllabus": True},
    {"year": 2017, "topic_title": "Industry",
     "question_text": "Discuss the factors responsible for the recent dispersal of the cotton-textile industry in India.", "marks": 15},
    {"year": 2022, "topic_title": "Settlements",
     "question_text": "Examine the problems of metropolitan growth in India and the emergence of census towns.", "marks": 20,
     "beyond_syllabus": True},
    {"year": 2015, "topic_title": "Regional Development and Planning",
     "question_text": "Critically evaluate the role of multi-level planning in reducing regional imbalances in India.", "marks": 15},
    {"year": 2013, "topic_title": "Political Aspects",
     "question_text": "Discuss the geopolitical significance of India's land and maritime boundaries.", "marks": 15},
    {"year": 2023, "topic_title": "Contemporary Issues",
     "question_text": "Examine the geographical dimensions of environmental hazards and disaster management in India.", "marks": 20,
     "beyond_syllabus": True},
]


# Hidden topics — themes asked beyond the printed syllabus, filed under a node.
# Shape: paper / section / topic_title (target node) / title / rationale.
_HIDDEN_TOPICS: list[dict[str, Any]] = [
    {"paper": "PAPER_I", "section": "SECTION_A",
     "topic_title": "Applied Geomorphology — geohydrology, economic geology & environment",
     "title": "Watershed management & landslide hazard zonation",
     "rationale": "Recurrently asked as an applied extension of geomorphology though the printed head only says 'applied geomorphology'; questions increasingly demand disaster-management linkage (GS-III crossover)."},
    {"paper": "PAPER_I", "section": "SECTION_A",
     "topic_title": "Monsoons & jet streams",
     "title": "ENSO, IOD and monsoon teleconnections",
     "rationale": "The printed syllabus lists 'monsoons and jet streams' but recent papers expect ocean–atmosphere teleconnections (El Niño/La Niña, Indian Ocean Dipole) not named in the syllabus."},
    {"paper": "PAPER_I", "section": "SECTION_A",
     "topic_title": "Climate change & applied / urban climatology",
     "title": "Urban heat island & bioclimatic city design",
     "rationale": "Urban/applied climatology is asked well beyond the one-line syllabus mention, often demanding planning and mitigation measures."},
    {"paper": "PAPER_I", "section": "SECTION_B",
     "topic_title": "Economic Geography",
     "title": "Global value chains & footloose industries",
     "rationale": "Classical location theories are extended in recent papers to contemporary themes (GVCs, footloose industry) that the printed syllabus does not enumerate."},
    {"paper": "PAPER_II", "section": None,
     "topic_title": "Contemporary Issues",
     "title": "Climate-induced migration & coastal vulnerability",
     "rationale": "Filed as a hidden theme: contemporary-issues questions increasingly probe climate migration and delta/coastal-city vulnerability beyond the listed heads."},
]


# Official-syllabus headings used when scaffolding gated topic nodes for the
# segments the importer has not yet modelled (Paper I Section B, Paper II).
# display_order preserves the official sequence.
_SCAFFOLD_ORDER: dict[tuple[str, Optional[str]], list[str]] = {
    ("PAPER_I", "SECTION_B"): [
        "Perspectives in Human Geography",
        "Economic Geography",
        "Population and Settlement Geography",
        "Regional Planning",
        "Models, Theories and Laws in Human Geography",
    ],
    ("PAPER_II", None): [
        "Physical Setting",
        "Resources",
        "Agriculture",
        "Industry",
        "Transport, Communication and Trade",
        "Cultural Setting",
        "Settlements",
        "Regional Development and Planning",
        "Political Aspects",
        "Contemporary Issues",
    ],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_subject(session: Session, slug: str) -> OptionalSubject:
    subject = (
        session.query(OptionalSubject)
        .filter(OptionalSubject.slug == slug)
        .one_or_none()
    )
    if subject is None:
        raise RuntimeError(
            f"Optional subject '{slug}' not found. Run the content importer "
            f"(app.core.optional.importer) before seeding PYQs."
        )
    return subject


def _delete_existing_seed(session: Session, subject_id: int) -> None:
    """Remove every row this seeder previously created for the subject.

    Scoped to ``SEEDER_ACTOR`` and ordered FK-safe so importer-owned content is
    never touched (idempotency).
    """
    # PYQs owned by the seeder.
    session.query(Pyq).filter(
        Pyq.subject_id == subject_id, Pyq.created_by == SEEDER_ACTOR
    ).delete(synchronize_session=False)

    # Hidden topics owned by the seeder.
    session.query(HiddenTopic).filter(
        HiddenTopic.created_by == SEEDER_ACTOR
    ).delete(synchronize_session=False)

    # Source refs owned by the seeder (now unreferenced).
    session.query(SourceRef).filter(
        SourceRef.created_by == SEEDER_ACTOR
    ).delete(synchronize_session=False)

    # Scaffold syllabus nodes owned by the seeder (gated topic nodes).
    seeder_node_ids = [
        nid
        for (nid,) in session.query(SyllabusNode.id)
        .join(Section, SyllabusNode.section_id == Section.id)
        .join(Paper, Section.paper_id == Paper.id)
        .filter(Paper.subject_id == subject_id, SyllabusNode.created_by == SEEDER_ACTOR)
        .all()
    ]
    if seeder_node_ids:
        session.query(SyllabusNode).filter(
            SyllabusNode.id.in_(seeder_node_ids)
        ).delete(synchronize_session=False)

    # Seeder-created sections, then seeder-created papers.
    paper_ids = [
        pid for (pid,) in session.query(Paper.id).filter(Paper.subject_id == subject_id).all()
    ]
    if paper_ids:
        session.query(Section).filter(
            Section.paper_id.in_(paper_ids), Section.created_by == SEEDER_ACTOR
        ).delete(synchronize_session=False)
    session.query(Paper).filter(
        Paper.subject_id == subject_id, Paper.created_by == SEEDER_ACTOR
    ).delete(synchronize_session=False)
    session.flush()


def _get_or_create_paper(session: Session, subject_id: int, label: PaperLabelEnum) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.subject_id == subject_id, Paper.label == label)
        .first()
    )
    if paper is not None:
        return paper
    paper = Paper(
        subject_id=subject_id,
        label=label,
        name="Paper I" if label == PaperLabelEnum.PAPER_I else "Paper II",
        display_order=0 if label == PaperLabelEnum.PAPER_I else 1,
        created_by=SEEDER_ACTOR,
        updated_by=SEEDER_ACTOR,
    )
    session.add(paper)
    session.flush()
    return paper


def _get_or_create_section(
    session: Session,
    paper: Paper,
    section_label: Optional[SectionLabelEnum],
) -> Section:
    q = session.query(Section).filter(Section.paper_id == paper.id)
    if section_label is None:
        q = q.filter(Section.label.is_(None))
        name = paper.name
        order = 0
    else:
        q = q.filter(Section.label == section_label)
        name = "Section A" if section_label == SectionLabelEnum.SECTION_A else "Section B"
        order = 0 if section_label == SectionLabelEnum.SECTION_A else 1
    section = q.first()
    if section is not None:
        return section
    section = Section(
        paper_id=paper.id,
        label=section_label,
        name=name,
        display_order=order,
        created_by=SEEDER_ACTOR,
        updated_by=SEEDER_ACTOR,
    )
    session.add(section)
    session.flush()
    return section


def _find_node_by_title(session: Session, subject_id: int, title: str) -> Optional[SyllabusNode]:
    """Find an existing syllabus node (any depth) of the subject by exact title."""
    return (
        session.query(SyllabusNode)
        .join(Section, SyllabusNode.section_id == Section.id)
        .join(Paper, Section.paper_id == Paper.id)
        .filter(Paper.subject_id == subject_id, SyllabusNode.title == title)
        .first()
    )


def seed_geography_pyqs(
    session: Session,
    *,
    mark_reviewed: bool = False,
) -> dict[str, Any]:
    """Seed the DRAFT Geography optional PYQ corpus.

    Maps each draft PYQ onto a real ``SyllabusNode`` (creating gated scaffold
    nodes for the not-yet-modelled Section B / Paper II segments), attaches
    authoritative source provenance, and files hidden topics.

    Every PYQ is stamped UNREVIEWED unless ``mark_reviewed=True`` (which should
    only be used after founder validation). Idempotent: re-running replaces the
    seeder's own rows without duplicating and without touching importer content.

    Returns a counts report.
    """
    rs = (
        OptionalReviewStatusEnum.REVIEWED
        if mark_reviewed
        else OptionalReviewStatusEnum.UNREVIEWED
    )

    subject = _get_subject(session, SUBJECT_SLUG)
    _delete_existing_seed(session, subject.id)

    counts = {
        "pyqs": 0,
        "pyqs_paper_i_a": 0,
        "pyqs_paper_i_b": 0,
        "pyqs_paper_ii": 0,
        "pyqs_beyond_syllabus": 0,
        "hidden_topics": 0,
        "source_refs": 0,
        "scaffold_nodes": 0,
        "review_status": rs.value,
        "years": set(),
    }

    # --- Authoritative sources (provenance) -------------------------------
    src_pyq = SourceRef(
        content_unit_id=None,
        created_by=SEEDER_ACTOR,
        updated_by=SEEDER_ACTOR,
        **_SOURCE_PYQ,
    )
    src_hidden = SourceRef(
        content_unit_id=None,
        created_by=SEEDER_ACTOR,
        updated_by=SEEDER_ACTOR,
        **_SOURCE_HIDDEN,
    )
    session.add_all([src_pyq, src_hidden])
    session.flush()
    counts["source_refs"] = 2

    # Cache of resolved/created nodes by (paper_label, section_label, title).
    node_cache: dict[tuple[str, Optional[str], str], SyllabusNode] = {}

    def resolve_node(
        paper_label: PaperLabelEnum,
        section_label: Optional[SectionLabelEnum],
        title: str,
    ) -> SyllabusNode:
        sec_key = section_label.value if section_label else None
        key = (paper_label.value, sec_key, title)
        if key in node_cache:
            return node_cache[key]

        # Prefer an existing (importer-owned) node with this title.
        existing = _find_node_by_title(session, subject.id, title)
        if existing is not None:
            node_cache[key] = existing
            return existing

        # Otherwise scaffold a gated topic node under the proper section.
        paper = _get_or_create_paper(session, subject.id, paper_label)
        section = _get_or_create_section(session, paper, section_label)
        order_list = _SCAFFOLD_ORDER.get((paper_label.value, sec_key), [])
        order = order_list.index(title) if title in order_list else 0
        node = SyllabusNode(
            section_id=section.id,
            parent_id=None,
            title=title,
            official_phrasing=title,
            node_type=SyllabusNodeTypeEnum.TOPIC,
            weight=1.0,
            display_order=order,
            review_status=OptionalReviewStatusEnum.UNREVIEWED,  # gated scaffold
            created_by=SEEDER_ACTOR,
            updated_by=SEEDER_ACTOR,
        )
        session.add(node)
        session.flush()
        counts["scaffold_nodes"] += 1
        node_cache[key] = node
        return node

    def add_pyq_batch(
        records: list[dict[str, Any]],
        paper_label: PaperLabelEnum,
        section_label: Optional[SectionLabelEnum],
        counter_key: str,
    ) -> None:
        for rec in records:
            node = resolve_node(paper_label, section_label, rec["topic_title"])
            section = session.get(Section, node.section_id)
            beyond = bool(rec.get("beyond_syllabus", False))
            session.add(
                Pyq(
                    subject_id=subject.id,
                    paper_id=section.paper_id if section else None,
                    section_id=node.section_id,
                    topic_node_id=node.id,
                    source_ref_id=src_pyq.id,
                    year=int(rec["year"]),
                    paper_label=paper_label,
                    section_label=section_label,
                    question_text=rec["question_text"],
                    marks=rec.get("marks"),
                    beyond_syllabus=beyond,
                    review_status=rs,
                    created_by=SEEDER_ACTOR,
                    updated_by=SEEDER_ACTOR,
                )
            )
            counts["pyqs"] += 1
            counts[counter_key] += 1
            counts["years"].add(int(rec["year"]))
            if beyond:
                counts["pyqs_beyond_syllabus"] += 1

    add_pyq_batch(_PYQS_PAPER_I_SEC_A, PaperLabelEnum.PAPER_I, SectionLabelEnum.SECTION_A, "pyqs_paper_i_a")
    add_pyq_batch(_PYQS_PAPER_I_SEC_B, PaperLabelEnum.PAPER_I, SectionLabelEnum.SECTION_B, "pyqs_paper_i_b")
    add_pyq_batch(_PYQS_PAPER_II, PaperLabelEnum.PAPER_II, None, "pyqs_paper_ii")

    # --- Hidden topics (beyond-syllabus themes filed under a node) --------
    for ht in _HIDDEN_TOPICS:
        paper_label = PaperLabelEnum(ht["paper"])
        sec = ht.get("section")
        section_label = SectionLabelEnum(sec) if sec else None
        node = resolve_node(paper_label, section_label, ht["topic_title"])
        session.add(
            HiddenTopic(
                syllabus_node_id=node.id,
                source_ref_id=src_hidden.id,
                title=ht["title"],
                rationale=ht["rationale"],
                created_by=SEEDER_ACTOR,
                updated_by=SEEDER_ACTOR,
            )
        )
        counts["hidden_topics"] += 1

    session.flush()
    counts["years"] = sorted(counts["years"])
    return counts


def main() -> None:  # pragma: no cover - CLI entrypoint
    import argparse

    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(
        description="Seed the DRAFT Geography optional PYQ corpus (UNREVIEWED by default)."
    )
    parser.add_argument(
        "--mark-reviewed",
        action="store_true",
        help=(
            "Stamp seeded PYQs as REVIEWED (only after founder validation). "
            "Default leaves them UNREVIEWED so they stay gated from students."
        ),
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        counts = seed_geography_pyqs(session, mark_reviewed=args.mark_reviewed)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("=== Geography Optional PYQ seed complete (DRAFT / UNREVIEWED) ===")
    for k, v in counts.items():
        print(f"  {k:<22} {v}")
    if not args.mark_reviewed:
        print(
            "\nNOTE: every seeded PYQ is UNREVIEWED and is gated OUT of the "
            "student view until validated by the founder. This is a DRAFT "
            "starter corpus, not the verified 26-year set."
        )


if __name__ == "__main__":  # pragma: no cover
    main()
