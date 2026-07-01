"""Tests for the Sociology Optional seeder (spec sociology-optional-content).

Covers:
  * Task 1.3 — authored structure: Paper I has Section A + Section B; the named
    Paper I/II topics exist; the "Sociological Thinkers" topic has exactly the
    six thinker subtopics (none missing, none added). (R1.2, R1.3, R1.4, R1.5)
  * Task 1.4 — seeder idempotency: re-running yields identical counts and no
    duplicate trees. (R1.7, R6.6)
  * Property 1 — every ingested node is gated UNREVIEWED by default. (R1.8, 5.1)

Hermetic + deterministic: builds an in-memory SQLite DB from the optional
models' own metadata (same pattern as ``test_optional_pyq_seed``) and runs the
Sociology seeder, which delegates to the existing ``import_subject_from_payload``.
Never touches the dev DB.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base

# Importing the models registers every ``optional_*`` table on ``Base.metadata``.
from app.core.optional import models as optional_models  # noqa: F401
from app.core.optional.models import (
    OptionalSubject,
    Paper,
    Section,
    SyllabusNode,
    OptionalReviewStatusEnum,
    PaperLabelEnum,
    SectionLabelEnum,
    SyllabusNodeTypeEnum,
)
from app.core.optional.sociology_seed import (
    seed_sociology,
    SUBJECT_SLUG,
    SEEDER_ACTOR,
    SOCIOLOGY_FEATURES,
)

THINKERS = [
    "Karl Marx",
    "Emile Durkheim",
    "Max Weber",
    "Talcott Parsons",
    "Robert K. Merton",
    "George Herbert Mead",
]

PAPER_I_TOPICS = [
    "Sociology - The Discipline",
    "Sociology as Science",
    "Research Methods and Analysis",
    "Sociological Thinkers",
    "Stratification and Mobility",
    "Works and Economic Life",
    "Politics and Society",
    "Religion and Society",
    "Systems of Kinship",
    "Social Change in Modern Society",
]

PAPER_II_TOPICS = [
    "Introducing Indian Society",
    "Social Structure",
    "Social Changes in India",
]


@pytest.fixture()
def session():
    """Isolated in-memory SQLite session built from the optional metadata."""
    engine = create_engine("sqlite:///:memory:", future=True)
    optional_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name.startswith("optional_")
    ]
    Base.metadata.create_all(engine, tables=optional_tables)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _subject(session) -> OptionalSubject:
    return (
        session.query(OptionalSubject)
        .filter(OptionalSubject.slug == SUBJECT_SLUG)
        .one()
    )


def _topic_titles(session, subject_id: int) -> list[str]:
    return [
        n.title
        for n in session.query(SyllabusNode)
        .join(Section, SyllabusNode.section_id == Section.id)
        .join(Paper, Section.paper_id == Paper.id)
        .filter(
            Paper.subject_id == subject_id,
            SyllabusNode.node_type == SyllabusNodeTypeEnum.TOPIC,
        )
        .all()
    ]


# ---------------------------------------------------------------------------
# Task 1.3 — authored structure
# ---------------------------------------------------------------------------

def test_seed_creates_sociology_subject(session):
    seed_sociology(session)
    session.flush()
    subject = _subject(session)
    assert subject.name == "Sociology"


def test_paper_one_has_exactly_section_a_and_b(session):
    seed_sociology(session)
    session.flush()
    subject = _subject(session)
    paper_one = (
        session.query(Paper)
        .filter(Paper.subject_id == subject.id, Paper.label == PaperLabelEnum.PAPER_I)
        .one()
    )
    sections = (
        session.query(Section)
        .filter(Section.paper_id == paper_one.id)
        .order_by(Section.display_order)
        .all()
    )
    labels = [s.label for s in sections]
    assert labels == [SectionLabelEnum.SECTION_A, SectionLabelEnum.SECTION_B]


def test_paper_two_exists(session):
    seed_sociology(session)
    session.flush()
    subject = _subject(session)
    paper_two = (
        session.query(Paper)
        .filter(Paper.subject_id == subject.id, Paper.label == PaperLabelEnum.PAPER_II)
        .one_or_none()
    )
    assert paper_two is not None
    assert paper_two.name == "Indian Society: Structure and Change"


def test_all_named_topics_present(session):
    seed_sociology(session)
    session.flush()
    subject = _subject(session)
    titles = set(_topic_titles(session, subject.id))
    for expected in PAPER_I_TOPICS + PAPER_II_TOPICS:
        assert expected in titles, f"missing topic: {expected}"


def test_sociological_thinkers_has_exactly_six_subtopics(session):
    seed_sociology(session)
    session.flush()
    subject = _subject(session)
    thinkers_topic = (
        session.query(SyllabusNode)
        .filter(SyllabusNode.title == "Sociological Thinkers")
        .one()
    )
    children = (
        session.query(SyllabusNode)
        .filter(SyllabusNode.parent_id == thinkers_topic.id)
        .order_by(SyllabusNode.display_order)
        .all()
    )
    assert [c.title for c in children] == THINKERS


def test_config_features_include_thinkers(session):
    seed_sociology(session)
    session.flush()
    subject = _subject(session)
    features = subject.config.get("features", [])
    assert "thinkers" in features
    # The standard modules are still present (content + config, not a reduction).
    for f in ("read", "pyq", "practice", "answer", "gap"):
        assert f in features


# ---------------------------------------------------------------------------
# Property 1 — ingested content is gated UNREVIEWED (R1.8 / 5.1)
# ---------------------------------------------------------------------------

def test_all_nodes_unreviewed_by_default(session):
    """Feature: sociology-optional-content, Property 1: ingested content is gated UNREVIEWED."""
    seed_sociology(session)
    session.flush()
    subject = _subject(session)
    nodes = (
        session.query(SyllabusNode)
        .join(Section, SyllabusNode.section_id == Section.id)
        .join(Paper, Section.paper_id == Paper.id)
        .filter(Paper.subject_id == subject.id)
        .all()
    )
    assert nodes, "expected the seeder to create syllabus nodes"
    assert all(n.review_status == OptionalReviewStatusEnum.UNREVIEWED for n in nodes)


# ---------------------------------------------------------------------------
# Task 1.4 — idempotency
# ---------------------------------------------------------------------------

def test_seed_is_idempotent(session):
    counts_first = seed_sociology(session)
    session.flush()
    counts_second = seed_sociology(session)
    session.flush()

    # Identical counts on re-run.
    assert counts_first == counts_second

    # Exactly one subject, no duplicate trees.
    subjects = (
        session.query(OptionalSubject)
        .filter(OptionalSubject.slug == SUBJECT_SLUG)
        .all()
    )
    assert len(subjects) == 1

    subject = subjects[0]
    titles = _topic_titles(session, subject.id)
    # No duplicated topic titles after re-seeding.
    assert len(titles) == len(set(titles))
