"""No-content-loss migration assertion test — design Correctness Property 1.

This is the safety gate that MUST pass before Task 6.4 deletes the legacy
bespoke Geography optional files. It implements design **Property 1 (No content
loss on migration)**:

    For every subtopic, examiner keyword, answer-language line, PYQ, hidden
    topic, and diagram id present in the source ``geomorphology.ts`` /
    ``climatology.ts`` (faithfully serialized into the JSON artifact by the
    frontend extractor), a corresponding DB record exists after import.

**Validates: Requirements 5.5, 18.2**

Strategy / DB session:
- Hermetic, deterministic, CI-safe: the test imports into an **in-memory
  SQLite** database created from the optional models' own metadata
  (``create_all``). It NEVER touches the dev ``production.db`` or any real
  Postgres — no network, no fixtures, no migrations required.
- The expected ("source") side is recomputed directly from the artifact inside
  the test (independent of the importer's own counting), then cross-checked
  against the importer's ``_build_source_report`` for an extra guard.
- Coverage is asserted by BOTH count parity AND content membership (every
  individual keyword / answer-language line / PYQ text / hidden-topic title /
  diagram id is found in the DB), so the test fails loudly on any missing item.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base

# Importing the models registers every ``optional_*`` table on ``Base.metadata``.
from app.core.optional import models as optional_models
from app.core.optional.models import (
    OptionalSubject,
    SyllabusNode,
    ContentUnit,
    Diagram,
    Pyq,
    HiddenTopic,
    SyllabusNodeTypeEnum,
)
from app.core.optional.importer import (
    load_artifact,
    import_geography_optional,
    _build_source_report,
)

# The 11 canonical diagram ids (design R5.3 / R18.2). Asserted explicitly so the
# test is a hard guard even if the artifact's list were ever altered.
CANONICAL_DIAGRAM_IDS = {
    "endo-exo-balance",
    "plate-boundaries",
    "isostasy-airy-pratt",
    "davis-penck-cycle",
    "channel-patterns",
    "slope-elements",
    "heat-budget",
    "tricellular-circulation",
    "air-mass-fronts",
    "koppen-climate",
    "urban-heat-island",
}


# ---------------------------------------------------------------------------
# Fixtures: hermetic in-memory DB + a freshly-imported geography subject tree
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def artifact():
    """The faithful serialization of the source TS content."""
    return load_artifact()


@pytest.fixture()
def session():
    """An isolated in-memory SQLite session built from the optional metadata.

    Only the ``optional_*`` tables are created, keeping the test hermetic and
    fast and avoiding any dependency on the wider app schema / real database.
    """
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


@pytest.fixture()
def imported(session, artifact):
    """Run the importer once and return ``(session, counts)``."""
    counts = import_geography_optional(session, review_status="REVIEWED")
    session.flush()
    return session, counts


# ---------------------------------------------------------------------------
# Expected ("source") sets recomputed directly from the artifact
# ---------------------------------------------------------------------------

def _source_sets(artifact):
    """Recompute the source-side membership sets straight from the artifact.

    Independent of the importer so a bug in the importer's own counting cannot
    mask content loss.
    """
    subtopic_titles: set[str] = set()
    exam_keywords: set[str] = set()
    answer_language: set[str] = set()
    pyq_texts: set[str] = set()
    hidden_topics: set[str] = set()
    diagram_ids: set[str] = set()

    for topic in artifact["topics"]:
        for ht in topic["syllabus"]["hiddenTopics"]:
            hidden_topics.add(ht["topic"])
        for st in topic["subtopics"]:
            subtopic_titles.add(st["title"])
            exam_keywords.update(st["examKeywords"])
            answer_language.update(st["answerLanguage"])
            for pyq in st["pyq"]:
                pyq_texts.add(pyq["q"])
            for block in st["blocks"]:
                if block.get("type") == "diagram":
                    diagram_ids.add(block["id"])

    return {
        "subtopic_titles": subtopic_titles,
        "exam_keywords": exam_keywords,
        "answer_language": answer_language,
        "pyq_texts": pyq_texts,
        "hidden_topics": hidden_topics,
        "diagram_ids": diagram_ids,
    }


# ---------------------------------------------------------------------------
# Sanity: the importer ran and produced the subject tree
# ---------------------------------------------------------------------------

def test_import_creates_geography_subject(imported, artifact):
    session, counts = imported
    subject = (
        session.query(OptionalSubject)
        .filter(OptionalSubject.slug == artifact["subjectSlug"])
        .one_or_none()
    )
    assert subject is not None, "Geography optional subject was not imported"
    assert counts["subjects"] == 1


# ---------------------------------------------------------------------------
# Property 1 — count parity per category (source vs DB)
# ---------------------------------------------------------------------------

def test_no_loss_counts_match_source(imported, artifact):
    """Every Property-1 category count in the DB equals the source artifact."""
    session, counts = imported
    src = _source_sets(artifact)
    report = _build_source_report(artifact)

    # Subtopics -> SUBTOPIC SyllabusNodes
    db_subtopic_nodes = (
        session.query(SyllabusNode)
        .filter(SyllabusNode.node_type == SyllabusNodeTypeEnum.SUBTOPIC)
        .count()
    )
    assert db_subtopic_nodes == len(src["subtopic_titles"]) == report["subtopic_nodes"], (
        f"subtopic node count mismatch: db={db_subtopic_nodes} "
        f"source={len(src['subtopic_titles'])}"
    )

    # Each subtopic also has a documenting ContentUnit (topic overview units +
    # one per subtopic). At minimum every subtopic must be documented.
    db_content_units = session.query(ContentUnit).count()
    assert db_content_units >= db_subtopic_nodes, (
        f"content units ({db_content_units}) fewer than subtopics "
        f"({db_subtopic_nodes}) — subtopic content lost"
    )

    # Diagrams: distinct ids
    db_diagram_ids = {d for (d,) in session.query(Diagram.diagram_id).distinct().all()}
    assert len(db_diagram_ids) == len(src["diagram_ids"]) == report["diagrams"], (
        f"diagram id count mismatch: db={len(db_diagram_ids)} "
        f"source={len(src['diagram_ids'])}"
    )

    # PYQs
    db_pyqs = session.query(Pyq).count()
    assert db_pyqs == report["pyqs"] >= len(src["pyq_texts"]), (
        f"PYQ count mismatch: db={db_pyqs} report={report['pyqs']} "
        f"distinct_source={len(src['pyq_texts'])}"
    )

    # Hidden topics
    db_hidden = session.query(HiddenTopic).count()
    assert db_hidden == len(src["hidden_topics"]) == report["hidden_topics"], (
        f"hidden topic count mismatch: db={db_hidden} "
        f"source={len(src['hidden_topics'])}"
    )


# ---------------------------------------------------------------------------
# Property 1 — content membership (every individual item is present in the DB)
# ---------------------------------------------------------------------------

def test_every_subtopic_present(imported, artifact):
    session, _ = imported
    src = _source_sets(artifact)
    db_titles = {
        t
        for (t,) in session.query(SyllabusNode.title)
        .filter(SyllabusNode.node_type == SyllabusNodeTypeEnum.SUBTOPIC)
        .all()
    }
    missing = src["subtopic_titles"] - db_titles
    assert not missing, f"Subtopics missing from DB: {sorted(missing)}"


def test_every_exam_keyword_present(imported, artifact):
    session, _ = imported
    src = _source_sets(artifact)
    db_keywords: set[str] = set()
    for (kw_list,) in session.query(ContentUnit.exam_keywords).all():
        if kw_list:
            db_keywords.update(kw_list)
    missing = src["exam_keywords"] - db_keywords
    assert not missing, f"Examiner keywords missing from DB: {sorted(missing)}"


def test_every_answer_language_line_present(imported, artifact):
    session, _ = imported
    src = _source_sets(artifact)
    db_lines: set[str] = set()
    for (al_list,) in session.query(ContentUnit.answer_language).all():
        if al_list:
            db_lines.update(al_list)
    missing = src["answer_language"] - db_lines
    assert not missing, f"Answer-language lines missing from DB: {sorted(missing)}"


def test_every_pyq_present(imported, artifact):
    session, _ = imported
    src = _source_sets(artifact)
    db_pyq_texts = {q for (q,) in session.query(Pyq.question_text).all()}
    missing = src["pyq_texts"] - db_pyq_texts
    assert not missing, f"PYQs missing from DB: {sorted(missing)}"


def test_every_hidden_topic_present(imported, artifact):
    session, _ = imported
    src = _source_sets(artifact)
    db_hidden = {t for (t,) in session.query(HiddenTopic.title).all()}
    missing = src["hidden_topics"] - db_hidden
    assert not missing, f"Hidden topics missing from DB: {sorted(missing)}"


def test_all_eleven_canonical_diagrams_present(imported, artifact):
    """The 11 canonical diagram ids are all represented as DB rows."""
    session, _ = imported
    db_diagram_ids = {d for (d,) in session.query(Diagram.diagram_id).distinct().all()}

    # The artifact's declared ids match the canonical 11.
    assert set(artifact["diagramIds"]) == CANONICAL_DIAGRAM_IDS
    assert len(CANONICAL_DIAGRAM_IDS) == 11

    missing = CANONICAL_DIAGRAM_IDS - db_diagram_ids
    assert not missing, f"Canonical diagram ids missing from DB: {sorted(missing)}"
    # No stray ids beyond the canonical set either.
    extra = db_diagram_ids - CANONICAL_DIAGRAM_IDS
    assert not extra, f"Unexpected diagram ids in DB: {sorted(extra)}"


def test_import_is_idempotent(session, artifact):
    """Re-running the importer yields identical counts (no duplication)."""
    first = import_geography_optional(session, review_status="REVIEWED")
    session.flush()
    second = import_geography_optional(session, review_status="REVIEWED")
    session.flush()
    assert first == second, f"Importer not idempotent: {first} != {second}"
    # And the DB reflects a single subject tree, not two.
    assert session.query(OptionalSubject).count() == 1
