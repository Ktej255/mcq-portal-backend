"""Tests for GS LMS content importer (Task 9.4).

Validates:
  - Property 20: Importer idempotency (import twice → same state as once)
  - Property 19: All imported content starts as UNREVIEWED (review-gate)
  - No-loss import of syllabus tree + content sections + PYQs + MCQs
  - Bulk loading from in-memory JSON artifact structure

Requirements traced: 10.5, 11.4
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.core.gs.models import GsSubject, GsReviewStatusEnum
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
from app.core.gs_lms.importer import (
    import_gs_geography,
    import_syllabus_tree,
    import_content_sections,
    import_pyqs,
    import_mcq_questions,
)

# Ensure all models are registered on Base.metadata.
from app.models.domain import User, RoleEnum  # noqa: F401
from app.core.gs_lms import models as _gs_lms_models  # noqa: F401
from app.core.gs_lms import student_models as _gs_lms_student  # noqa: F401


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def db_session():
    """Create an in-memory SQLite DB with required tables and return a session."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    relevant_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name in (
            "users",
            "gs_subjects",
            "gs_day_lessons",
            "gs_lms_syllabus_nodes",
            "gs_lms_content_sections",
            "gs_lms_pyqs",
            "gs_lms_mcq_questions",
        )
    ]
    Base.metadata.create_all(engine, tables=relevant_tables)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()

    # Seed the required subject (FK target for syllabus nodes).
    subject = GsSubject(id=1, name="Geography", slug="geography")
    session.add(subject)
    session.commit()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture()
def sample_artifact():
    """A minimal but complete in-memory artifact for testing."""
    return {
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
                                "content_sections": [
                                    {
                                        "section_label": "BASIC",
                                        "title": "Basic Concepts",
                                        "blocks": [{"type": "text", "content": "Intro to drift"}],
                                        "display_order": 1,
                                        "authored": True,
                                    },
                                    {
                                        "section_label": "ADVANCED",
                                        "title": "Advanced Theory",
                                        "blocks": [{"type": "text", "content": "Wegener's evidence"}],
                                        "display_order": 2,
                                        "authored": True,
                                    },
                                    {
                                        "section_label": "NCERT_LEVEL",
                                        "title": "NCERT Coverage",
                                        "blocks": [{"type": "text", "content": "NCERT Ch 3"}],
                                        "display_order": 3,
                                        "authored": True,
                                    },
                                    {
                                        "section_label": "EXAMINER_TRAPS",
                                        "title": "Traps & Pitfalls",
                                        "blocks": [{"type": "text", "content": "Common mistakes"}],
                                        "display_order": 4,
                                        "authored": True,
                                    },
                                ],
                                "pyqs": [
                                    {
                                        "exam_type": "PRELIMS",
                                        "year": 2019,
                                        "question_text": "Continental drift was proposed by?",
                                        "answer_text": "Alfred Wegener",
                                        "explanation": "Wegener proposed it in 1912.",
                                        "marks": None,
                                        "question_type": "FACTUAL",
                                    },
                                    {
                                        "exam_type": "MAINS",
                                        "year": 2020,
                                        "question_text": "Discuss evidence for continental drift.",
                                        "answer_text": "Model answer about jigsaw fit...",
                                        "explanation": None,
                                        "marks": 15,
                                        "question_type": None,
                                    },
                                ],
                                "mcq_questions": [
                                    {
                                        "question_text": "Who proposed continental drift?",
                                        "options": [
                                            {"label": "A", "text": "Wegener"},
                                            {"label": "B", "text": "Holmes"},
                                            {"label": "C", "text": "Hess"},
                                            {"label": "D", "text": "Wilson"},
                                        ],
                                        "correct_option": "A",
                                        "explanation": "Wegener in 1912.",
                                        "question_type": "FACTUAL",
                                        "display_order": 1,
                                    },
                                    {
                                        "question_text": "Pangaea broke apart during?",
                                        "options": [
                                            {"label": "A", "text": "Jurassic"},
                                            {"label": "B", "text": "Cretaceous"},
                                            {"label": "C", "text": "Triassic"},
                                            {"label": "D", "text": "Permian"},
                                        ],
                                        "correct_option": "A",
                                        "explanation": "Around 200 Ma in the Jurassic.",
                                        "question_type": "FACTUAL",
                                        "display_order": 2,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "title": "Climatology",
                "node_type": "MEGA_TOPIC",
                "weight": 4.0,
                "display_order": 2,
                "ordering_justification": "Builds on geomorphology concepts",
                "children": [],
            },
        ],
    }


# ===========================================================================
# Test: import_gs_geography (top-level entry point)
# ===========================================================================

class TestImportGsGeography:
    """Tests for the main import_gs_geography function."""

    def test_imports_full_artifact(self, db_session, sample_artifact):
        """Import creates all expected entities from artifact."""
        result = import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        # Verify counts.
        assert result["subject_id"] == 1
        # 4 nodes: Geomorphology, Plate Tectonics, Continental Drift, Climatology
        assert result["nodes_created"] == 4
        assert result["nodes_updated"] == 0
        # 4 content sections on Continental Drift.
        assert result["sections_created"] == 4
        assert result["sections_updated"] == 0
        # 2 PYQs.
        assert result["pyqs_created"] == 2
        assert result["pyqs_updated"] == 0
        # 2 MCQs.
        assert result["mcqs_created"] == 2
        assert result["mcqs_updated"] == 0

    def test_all_content_starts_unreviewed(self, db_session, sample_artifact):
        """Property 19: all imported content starts as UNREVIEWED."""
        import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        nodes = db_session.query(GsLmsSyllabusNode).all()
        for node in nodes:
            assert node.review_status == GsReviewStatusEnum.UNREVIEWED

        sections = db_session.query(GsLmsContentSection).all()
        for sec in sections:
            assert sec.review_status == GsReviewStatusEnum.UNREVIEWED

        pyqs = db_session.query(GsLmsPyq).all()
        for pyq in pyqs:
            assert pyq.review_status == GsReviewStatusEnum.UNREVIEWED

        mcqs = db_session.query(GsLmsMcqQuestion).all()
        for mcq in mcqs:
            assert mcq.review_status == GsReviewStatusEnum.UNREVIEWED

    def test_custom_review_status(self, db_session, sample_artifact):
        """Can override review_status for pre-approved content."""
        import_gs_geography(
            db_session, sample_artifact, review_status="REVIEWED"
        )
        db_session.commit()

        nodes = db_session.query(GsLmsSyllabusNode).all()
        for node in nodes:
            assert node.review_status == GsReviewStatusEnum.REVIEWED

    def test_idempotency_same_state_after_two_runs(self, db_session, sample_artifact):
        """Property 20: import(artifact); import(artifact) → same DB state."""
        # First run.
        import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        # Snapshot state after first run.
        nodes_r1 = db_session.query(GsLmsSyllabusNode).count()
        sections_r1 = db_session.query(GsLmsContentSection).count()
        pyqs_r1 = db_session.query(GsLmsPyq).count()
        mcqs_r1 = db_session.query(GsLmsMcqQuestion).count()

        # Second run (same artifact).
        result = import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        # Snapshot state after second run.
        nodes_r2 = db_session.query(GsLmsSyllabusNode).count()
        sections_r2 = db_session.query(GsLmsContentSection).count()
        pyqs_r2 = db_session.query(GsLmsPyq).count()
        mcqs_r2 = db_session.query(GsLmsMcqQuestion).count()

        # State must be identical.
        assert nodes_r1 == nodes_r2
        assert sections_r1 == sections_r2
        assert pyqs_r1 == pyqs_r2
        assert mcqs_r1 == mcqs_r2

        # Second run should report updates, not creates.
        assert result["nodes_created"] == 0
        assert result["nodes_updated"] == 4
        assert result["sections_created"] == 0
        assert result["sections_updated"] == 4
        assert result["pyqs_created"] == 0
        assert result["pyqs_updated"] == 2
        assert result["mcqs_created"] == 0
        assert result["mcqs_updated"] == 2

    def test_tree_hierarchy_preserved(self, db_session, sample_artifact):
        """Parent-child relationships are correctly established."""
        import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        geo = (
            db_session.query(GsLmsSyllabusNode)
            .filter(GsLmsSyllabusNode.title == "Geomorphology")
            .one()
        )
        assert geo.parent_id is None
        assert geo.node_type == GsLmsNodeTypeEnum.MEGA_TOPIC

        plate = (
            db_session.query(GsLmsSyllabusNode)
            .filter(GsLmsSyllabusNode.title == "Plate Tectonics")
            .one()
        )
        assert plate.parent_id == geo.id
        assert plate.node_type == GsLmsNodeTypeEnum.SUB_TOPIC

        drift = (
            db_session.query(GsLmsSyllabusNode)
            .filter(GsLmsSyllabusNode.title == "Continental Drift")
            .one()
        )
        assert drift.parent_id == plate.id
        assert drift.node_type == GsLmsNodeTypeEnum.LEAF_TOPIC

    def test_content_sections_linked_to_leaf(self, db_session, sample_artifact):
        """Content sections are attached to the correct leaf node."""
        import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        drift = (
            db_session.query(GsLmsSyllabusNode)
            .filter(GsLmsSyllabusNode.title == "Continental Drift")
            .one()
        )
        sections = (
            db_session.query(GsLmsContentSection)
            .filter(GsLmsContentSection.syllabus_node_id == drift.id)
            .order_by(GsLmsContentSection.display_order)
            .all()
        )
        assert len(sections) == 4
        labels = [s.section_label for s in sections]
        assert labels == [
            GsLmsSectionLabelEnum.BASIC,
            GsLmsSectionLabelEnum.ADVANCED,
            GsLmsSectionLabelEnum.NCERT_LEVEL,
            GsLmsSectionLabelEnum.EXAMINER_TRAPS,
        ]
        # Verify blocks are preserved (no data loss).
        assert sections[0].blocks == [{"type": "text", "content": "Intro to drift"}]
        assert sections[0].authored is True

    def test_pyqs_imported_with_metadata(self, db_session, sample_artifact):
        """PYQs have correct exam_type, year, marks, and content."""
        import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        pyqs = db_session.query(GsLmsPyq).order_by(GsLmsPyq.year).all()
        assert len(pyqs) == 2

        prelims = pyqs[0]
        assert prelims.exam_type == GsLmsExamTypeEnum.PRELIMS
        assert prelims.year == 2019
        assert prelims.question_text == "Continental drift was proposed by?"
        assert prelims.answer_text == "Alfred Wegener"
        assert prelims.marks is None
        assert prelims.question_type == GsLmsQuestionTypeEnum.FACTUAL

        mains = pyqs[1]
        assert mains.exam_type == GsLmsExamTypeEnum.MAINS
        assert mains.year == 2020
        assert mains.marks == 15
        assert mains.question_type is None  # Not classified

    def test_mcqs_imported_with_options(self, db_session, sample_artifact):
        """MCQ questions have options, correct answer, and type."""
        import_gs_geography(db_session, sample_artifact)
        db_session.commit()

        mcqs = (
            db_session.query(GsLmsMcqQuestion)
            .order_by(GsLmsMcqQuestion.display_order)
            .all()
        )
        assert len(mcqs) == 2

        q1 = mcqs[0]
        assert q1.question_text == "Who proposed continental drift?"
        assert len(q1.options) == 4
        assert q1.correct_option == "A"
        assert q1.question_type == GsLmsQuestionTypeEnum.FACTUAL
        assert q1.explanation == "Wegener in 1912."

    def test_empty_tree_imports_nothing(self, db_session):
        """Empty tree in artifact produces zero entities."""
        data = {"subject_id": 1, "tree": []}
        result = import_gs_geography(db_session, data)
        db_session.commit()

        assert result["nodes_created"] == 0
        assert db_session.query(GsLmsSyllabusNode).count() == 0


# ===========================================================================
# Test: import_syllabus_tree (standalone)
# ===========================================================================

class TestImportSyllabusTree:
    """Tests for import_syllabus_tree function."""

    def test_flat_tree_no_children(self, db_session):
        """Import a flat list of mega topics without children."""
        tree = [
            {
                "title": "Oceanography",
                "node_type": "MEGA_TOPIC",
                "weight": 3.0,
                "display_order": 1,
                "ordering_justification": "Water bodies",
            },
            {
                "title": "Human Geography",
                "node_type": "MEGA_TOPIC",
                "weight": 2.0,
                "display_order": 2,
                "ordering_justification": None,
            },
        ]
        counts = import_syllabus_tree(db_session, tree, subject_id=1)
        db_session.commit()

        assert counts["nodes_created"] == 2
        nodes = db_session.query(GsLmsSyllabusNode).all()
        assert len(nodes) == 2
        assert nodes[0].weight == 3.0
        assert nodes[1].weight == 2.0

    def test_node_weight_and_order_preserved(self, db_session):
        """Weight, display_order, and justification are stored faithfully."""
        tree = [
            {
                "title": "Resource Geography",
                "node_type": "MEGA_TOPIC",
                "weight": 7.5,
                "display_order": 5,
                "ordering_justification": "After human geography",
            },
        ]
        import_syllabus_tree(db_session, tree, subject_id=1)
        db_session.commit()

        node = db_session.query(GsLmsSyllabusNode).one()
        assert node.weight == 7.5
        assert node.display_order == 5
        assert node.ordering_justification == "After human geography"


# ===========================================================================
# Test: import_content_sections (standalone)
# ===========================================================================

class TestImportContentSections:
    """Tests for import_content_sections function."""

    def _create_leaf_node(self, db_session) -> int:
        """Helper: create a leaf node and return its id."""
        node = GsLmsSyllabusNode(
            subject_id=1,
            title="Test Leaf",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.UNREVIEWED,
            created_by="test",
            updated_by="test",
        )
        db_session.add(node)
        db_session.flush()
        return node.id

    def test_creates_four_sections(self, db_session):
        """Standard 4-section import for a leaf node."""
        node_id = self._create_leaf_node(db_session)
        sections = [
            {"section_label": "BASIC", "title": "Basic", "blocks": [], "display_order": 1, "authored": True},
            {"section_label": "ADVANCED", "title": "Advanced", "blocks": [], "display_order": 2, "authored": True},
            {"section_label": "NCERT_LEVEL", "title": "NCERT", "blocks": [], "display_order": 3, "authored": True},
            {"section_label": "EXAMINER_TRAPS", "title": "Traps", "blocks": [], "display_order": 4, "authored": True},
        ]
        result = import_content_sections(db_session, sections, node_id)
        db_session.commit()

        assert result["created"] == 4
        assert result["updated"] == 0
        assert db_session.query(GsLmsContentSection).filter_by(syllabus_node_id=node_id).count() == 4

    def test_idempotent_update(self, db_session):
        """Second import updates existing sections."""
        node_id = self._create_leaf_node(db_session)
        sections = [
            {"section_label": "BASIC", "title": "Basic v1", "blocks": [{"x": 1}], "display_order": 1, "authored": False},
        ]
        import_content_sections(db_session, sections, node_id)
        db_session.commit()

        # Update with new content.
        sections_v2 = [
            {"section_label": "BASIC", "title": "Basic v2", "blocks": [{"x": 2}], "display_order": 1, "authored": True},
        ]
        result = import_content_sections(db_session, sections_v2, node_id)
        db_session.commit()

        assert result["created"] == 0
        assert result["updated"] == 1
        sec = db_session.query(GsLmsContentSection).filter_by(syllabus_node_id=node_id).one()
        assert sec.title == "Basic v2"
        assert sec.blocks == [{"x": 2}]
        assert sec.authored is True


# ===========================================================================
# Test: import_pyqs (standalone)
# ===========================================================================

class TestImportPyqs:
    """Tests for import_pyqs function."""

    def _create_leaf_node(self, db_session) -> int:
        node = GsLmsSyllabusNode(
            subject_id=1,
            title="PYQ Leaf",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.UNREVIEWED,
            created_by="test",
            updated_by="test",
        )
        db_session.add(node)
        db_session.flush()
        return node.id

    def test_imports_prelims_and_mains(self, db_session):
        node_id = self._create_leaf_node(db_session)
        pyqs = [
            {
                "exam_type": "PRELIMS",
                "year": 2018,
                "question_text": "Q1 prelims?",
                "answer_text": "Answer A",
                "explanation": "Because...",
                "marks": None,
                "question_type": "STATEMENT_BASED",
            },
            {
                "exam_type": "MAINS",
                "year": 2021,
                "question_text": "Q2 mains discuss",
                "answer_text": "Model answer...",
                "explanation": None,
                "marks": 10,
                "question_type": None,
            },
        ]
        result = import_pyqs(db_session, pyqs, subject_id=1, node_id=node_id)
        db_session.commit()

        assert result["created"] == 2
        assert result["updated"] == 0

        all_pyqs = db_session.query(GsLmsPyq).all()
        assert len(all_pyqs) == 2

    def test_idempotent_no_duplicates(self, db_session):
        """Same PYQs imported twice → no duplicates."""
        node_id = self._create_leaf_node(db_session)
        pyqs = [
            {
                "exam_type": "PRELIMS",
                "year": 2017,
                "question_text": "Unique question?",
                "answer_text": "Answer",
                "explanation": None,
                "marks": None,
                "question_type": None,
            },
        ]
        import_pyqs(db_session, pyqs, subject_id=1, node_id=node_id)
        db_session.commit()

        result = import_pyqs(db_session, pyqs, subject_id=1, node_id=node_id)
        db_session.commit()

        assert result["created"] == 0
        assert result["updated"] == 1
        assert db_session.query(GsLmsPyq).count() == 1


# ===========================================================================
# Test: import_mcq_questions (standalone)
# ===========================================================================

class TestImportMcqQuestions:
    """Tests for import_mcq_questions function."""

    def _create_leaf_node(self, db_session) -> int:
        node = GsLmsSyllabusNode(
            subject_id=1,
            title="MCQ Leaf",
            node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
            weight=1.0,
            display_order=1,
            review_status=GsReviewStatusEnum.UNREVIEWED,
            created_by="test",
            updated_by="test",
        )
        db_session.add(node)
        db_session.flush()
        return node.id

    def test_imports_questions_with_all_fields(self, db_session):
        node_id = self._create_leaf_node(db_session)
        questions = [
            {
                "question_text": "What is erosion?",
                "options": [
                    {"label": "A", "text": "Wearing away"},
                    {"label": "B", "text": "Building up"},
                    {"label": "C", "text": "Melting"},
                    {"label": "D", "text": "Freezing"},
                ],
                "correct_option": "A",
                "explanation": "Erosion removes material.",
                "question_type": "FACTUAL",
                "display_order": 1,
            },
        ]
        result = import_mcq_questions(db_session, questions, node_id)
        db_session.commit()

        assert result["created"] == 1
        mcq = db_session.query(GsLmsMcqQuestion).one()
        assert mcq.question_text == "What is erosion?"
        assert mcq.correct_option == "A"
        assert mcq.question_type == GsLmsQuestionTypeEnum.FACTUAL
        assert len(mcq.options) == 4

    def test_idempotent_no_duplicates(self, db_session):
        """Same MCQs imported twice → no duplicates, second run updates."""
        node_id = self._create_leaf_node(db_session)
        questions = [
            {
                "question_text": "What causes earthquakes?",
                "options": [
                    {"label": "A", "text": "Plate movement"},
                    {"label": "B", "text": "Wind"},
                    {"label": "C", "text": "Rain"},
                    {"label": "D", "text": "Sun"},
                ],
                "correct_option": "A",
                "explanation": "Tectonic plates.",
                "question_type": "STATEMENT_BASED",
                "display_order": 1,
            },
        ]
        import_mcq_questions(db_session, questions, node_id)
        db_session.commit()

        # Import again.
        result = import_mcq_questions(db_session, questions, node_id)
        db_session.commit()

        assert result["created"] == 0
        assert result["updated"] == 1
        assert db_session.query(GsLmsMcqQuestion).count() == 1

    def test_multiple_question_types(self, db_session):
        """Import questions of different types."""
        node_id = self._create_leaf_node(db_session)
        questions = [
            {
                "question_text": "Statement Q",
                "options": [{"label": "A", "text": "X"}, {"label": "B", "text": "Y"},
                            {"label": "C", "text": "Z"}, {"label": "D", "text": "W"}],
                "correct_option": "B",
                "explanation": None,
                "question_type": "STATEMENT_BASED",
                "display_order": 1,
            },
            {
                "question_text": "Map Q",
                "options": [{"label": "A", "text": "X"}, {"label": "B", "text": "Y"},
                            {"label": "C", "text": "Z"}, {"label": "D", "text": "W"}],
                "correct_option": "C",
                "explanation": None,
                "question_type": "MAP_BASED",
                "display_order": 2,
            },
        ]
        result = import_mcq_questions(db_session, questions, node_id)
        db_session.commit()

        assert result["created"] == 2
        mcqs = db_session.query(GsLmsMcqQuestion).order_by(GsLmsMcqQuestion.display_order).all()
        assert mcqs[0].question_type == GsLmsQuestionTypeEnum.STATEMENT_BASED
        assert mcqs[1].question_type == GsLmsQuestionTypeEnum.MAP_BASED


# ===========================================================================
# Test: load_artifact
# ===========================================================================

class TestLoadArtifact:
    """Tests for load_artifact file-loading logic."""

    def test_file_not_found_raises(self, tmp_path):
        """Missing artifact raises FileNotFoundError."""
        from app.core.gs_lms.importer import load_artifact

        with pytest.raises(FileNotFoundError):
            load_artifact(tmp_path / "nonexistent.json")

    def test_loads_valid_json(self, tmp_path):
        """Loads and parses a valid JSON artifact file."""
        from app.core.gs_lms.importer import load_artifact
        import json

        artifact = {"subject_id": 1, "tree": []}
        path = tmp_path / "test_artifact.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")

        result = load_artifact(path)
        assert result == artifact
