"""Tests for the Geography Optional PYQ seeder (spec task 7.1).

Validates the seeding pipeline + draft dataset against Requirements
R4.1 (26-year PYQ corpus), R4.2 (map each segment to questions),
R4.3 (hidden topics for themes beyond the printed syllabus) and
R17.1 (authoritative source provenance) — and the founder honesty gate:
every seeded PYQ is UNREVIEWED so it stays out of the student view.

Hermetic + deterministic: builds an in-memory SQLite DB from the optional
models' own metadata (same pattern as ``test_optional_content_no_loss``),
runs the importer (task 4.1) to lay down the real syllabus tree, then runs the
PYQ seeder on top. Never touches the dev DB.
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
    SyllabusNode,
    SourceRef,
    Pyq,
    HiddenTopic,
    OptionalReviewStatusEnum,
    PaperLabelEnum,
    SectionLabelEnum,
)
from app.core.optional.importer import import_geography_optional
from app.core.optional.pyq_seed import (
    seed_geography_pyqs,
    SEEDER_ACTOR,
    SUBJECT_SLUG,
)


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
        # Lay down the real Geography syllabus tree first (task 4.1).
        import_geography_optional(db, review_status="REVIEWED")
        db.flush()
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def seeded(session):
    counts = seed_geography_pyqs(session)
    session.flush()
    return session, counts


def _seeder_pyqs(session):
    return session.query(Pyq).filter(Pyq.created_by == SEEDER_ACTOR).all()


# ---------------------------------------------------------------------------
# Pipeline requires the importer to have run
# ---------------------------------------------------------------------------

def test_seeder_requires_subject():
    """Seeding without the subject present raises a clear error."""
    engine = create_engine("sqlite:///:memory:", future=True)
    optional_tables = [
        t for n, t in Base.metadata.tables.items() if n.startswith("optional_")
    ]
    Base.metadata.create_all(engine, tables=optional_tables)
    db = sessionmaker(bind=engine)()
    try:
        with pytest.raises(RuntimeError):
            seed_geography_pyqs(db)
    finally:
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# R4.1 / R4.2 — PYQs created and mapped to real syllabus nodes
# ---------------------------------------------------------------------------

def test_pyqs_created(seeded):
    session, counts = seeded
    pyqs = _seeder_pyqs(session)
    assert len(pyqs) == counts["pyqs"] > 0


def test_every_pyq_maps_to_a_real_syllabus_node(seeded):
    session, _ = seeded
    node_ids = {nid for (nid,) in session.query(SyllabusNode.id).all()}
    for pyq in _seeder_pyqs(session):
        assert pyq.topic_node_id is not None, f"PYQ {pyq.id} has no topic node"
        assert pyq.topic_node_id in node_ids, (
            f"PYQ {pyq.id} maps to a non-existent node {pyq.topic_node_id}"
        )


def test_spread_covers_both_papers_and_sections(seeded):
    """Representative spread across Paper I A/B and Paper II (R4.1)."""
    session, counts = seeded
    assert counts["pyqs_paper_i_a"] > 0
    assert counts["pyqs_paper_i_b"] > 0
    assert counts["pyqs_paper_ii"] > 0

    pyqs = _seeder_pyqs(session)
    paper_labels = {p.paper_label for p in pyqs}
    assert PaperLabelEnum.PAPER_I in paper_labels
    assert PaperLabelEnum.PAPER_II in paper_labels
    section_labels = {p.section_label for p in pyqs}
    assert SectionLabelEnum.SECTION_A in section_labels
    assert SectionLabelEnum.SECTION_B in section_labels

    # Spread across many years (a credible multi-year starter).
    years = {p.year for p in pyqs}
    assert len(years) >= 10, f"expected a wide year spread, got {sorted(years)}"


def test_paper_i_section_a_maps_to_existing_importer_nodes(seeded):
    """Section A PYQs hang off the importer's real Physical-Geography nodes."""
    session, _ = seeded
    importer_node_ids = {
        nid
        for (nid,) in session.query(SyllabusNode.id)
        .filter(SyllabusNode.created_by == "geo-optional-importer")
        .all()
    }
    sec_a = [
        p for p in _seeder_pyqs(session)
        if p.section_label == SectionLabelEnum.SECTION_A
    ]
    assert sec_a
    for p in sec_a:
        assert p.topic_node_id in importer_node_ids


# ---------------------------------------------------------------------------
# R4.3 — hidden topics filed under nodes with rationale + beyond_syllabus flags
# ---------------------------------------------------------------------------

def test_hidden_topics_filed(seeded):
    session, counts = seeded
    hts = session.query(HiddenTopic).filter(
        HiddenTopic.created_by == SEEDER_ACTOR
    ).all()
    assert len(hts) == counts["hidden_topics"] > 0
    node_ids = {nid for (nid,) in session.query(SyllabusNode.id).all()}
    for ht in hts:
        assert ht.syllabus_node_id in node_ids
        assert ht.rationale, "hidden topic missing rationale"


def test_beyond_syllabus_flagged(seeded):
    session, counts = seeded
    beyond = [p for p in _seeder_pyqs(session) if p.beyond_syllabus]
    assert len(beyond) == counts["pyqs_beyond_syllabus"] > 0


# ---------------------------------------------------------------------------
# R17.1 — authoritative source attached to every PYQ and hidden topic
# ---------------------------------------------------------------------------

def test_sources_attached(seeded):
    session, _ = seeded
    src_ids = {
        sid for (sid,) in session.query(SourceRef.id).filter(
            SourceRef.created_by == SEEDER_ACTOR
        ).all()
    }
    assert src_ids
    for pyq in _seeder_pyqs(session):
        assert pyq.source_ref_id in src_ids, f"PYQ {pyq.id} has no source"
    for ht in session.query(HiddenTopic).filter(
        HiddenTopic.created_by == SEEDER_ACTOR
    ).all():
        assert ht.source_ref_id in src_ids, "hidden topic has no source"


# ---------------------------------------------------------------------------
# Honesty gate — every seeded PYQ is UNREVIEWED (gated from students)
# ---------------------------------------------------------------------------

def test_all_seeded_pyqs_are_unreviewed(seeded):
    session, _ = seeded
    for pyq in _seeder_pyqs(session):
        assert pyq.review_status == OptionalReviewStatusEnum.UNREVIEWED, (
            f"PYQ {pyq.id} is not gated (review_status={pyq.review_status})"
        )


def test_scaffold_nodes_are_gated_unreviewed(seeded):
    """Section B / Paper II scaffold nodes are UNREVIEWED so they stay hidden."""
    session, counts = seeded
    scaffold = session.query(SyllabusNode).filter(
        SyllabusNode.created_by == SEEDER_ACTOR
    ).all()
    assert len(scaffold) == counts["scaffold_nodes"] > 0
    for node in scaffold:
        assert node.review_status == OptionalReviewStatusEnum.UNREVIEWED


def test_mark_reviewed_flag_marks_reviewed(session):
    """Explicit founder validation path stamps REVIEWED."""
    counts = seed_geography_pyqs(session, mark_reviewed=True)
    session.flush()
    assert counts["review_status"] == "REVIEWED"
    for pyq in _seeder_pyqs(session):
        assert pyq.review_status == OptionalReviewStatusEnum.REVIEWED


# ---------------------------------------------------------------------------
# Idempotency — re-running replaces the seed set, no duplicates
# ---------------------------------------------------------------------------

def test_seeder_is_idempotent(session):
    first = seed_geography_pyqs(session)
    session.flush()
    second = seed_geography_pyqs(session)
    session.flush()
    assert first == second, f"seeder not idempotent: {first} != {second}"
    # Exactly one seeded set present.
    assert session.query(Pyq).filter(Pyq.created_by == SEEDER_ACTOR).count() == first["pyqs"]
    assert (
        session.query(HiddenTopic).filter(HiddenTopic.created_by == SEEDER_ACTOR).count()
        == first["hidden_topics"]
    )
    # Still exactly one subject (importer tree untouched).
    assert session.query(OptionalSubject).filter(
        OptionalSubject.slug == SUBJECT_SLUG
    ).count() == 1


def test_seeder_does_not_disturb_importer_pyqs(seeded):
    """Importer-owned PYQs coexist; seeder only manages its own rows."""
    session, counts = seeded
    importer_pyqs = session.query(Pyq).filter(
        Pyq.created_by == "geo-optional-importer"
    ).count()
    # Importer seeds Section A PYQs from the TS content; they must survive.
    assert importer_pyqs > 0
    # Re-run the seeder; importer PYQ count is unchanged.
    seed_geography_pyqs(session)
    session.flush()
    assert session.query(Pyq).filter(
        Pyq.created_by == "geo-optional-importer"
    ).count() == importer_pyqs
