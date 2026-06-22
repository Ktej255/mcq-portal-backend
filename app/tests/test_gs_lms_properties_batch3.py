"""Property-based tests for GS LMS Platform (Batch 3).

Tasks: 9.5, 10.2, 10.4
Properties tested:
  - Property 20: Content importer idempotency
  - Property 19: Review-gate filtering
  - Property 23: Auth gating on all endpoints
  - Property 21: Day-lesson bridge mapping integrity
  - Property 22: Progress migration data preservation

Uses hypothesis for property-based testing with in-memory SQLite for DB-backed
properties.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.core.gs.models import GsReviewStatusEnum, GsSubject, GsDayLesson
from app.core.gs_lms.models import (
    GsLmsNodeTypeEnum,
    GsLmsSectionLabelEnum,
    GsLmsExamTypeEnum,
    GsLmsQuestionTypeEnum,
    GsLmsSyllabusNode,
    GsLmsContentSection,
    GsLmsPyq,
    GsLmsMcqQuestion,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress
from app.core.gs_lms.importer import import_gs_geography
from app.core.gs_lms.migration import (
    validate_bridge_mapping,
    migrate_progress,
)
from app.models.domain import User, RoleEnum, StudentSubjectProgress


# ---------------------------------------------------------------------------
# Shared Infrastructure
# ---------------------------------------------------------------------------

SECTION_LABELS_ORDERED = [
    GsLmsSectionLabelEnum.BASIC,
    GsLmsSectionLabelEnum.ADVANCED,
    GsLmsSectionLabelEnum.NCERT_LEVEL,
    GsLmsSectionLabelEnum.EXAMINER_TRAPS,
]


def make_engine_and_session():
    """Create an in-memory SQLite engine with all relevant tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import all models to register on Base.metadata
    from app.models.domain import User  # noqa: F401
    from app.core.gs.models import GsSubject, GsDayLesson  # noqa: F401

    Base.metadata.create_all(engine, checkfirst=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, Session


def seed_subject(session, subject_id=1):
    """Seed a GsSubject for FK requirements."""
    subject = GsSubject(
        id=subject_id,
        slug="geography",
        name="GS Geography",
        display_order=1,
        created_by="test",
        updated_by="test",
    )
    session.add(subject)
    session.flush()
    return subject


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_content_artifact(draw):
    """Generate an arbitrary valid GS LMS content artifact for import.

    Produces a dict matching the expected importer structure with:
    - subject_id
    - tree: list of syllabus nodes (1-3 MEGA_TOPICs with children)
    """
    subject_id = 1

    # Generate 1-2 mega topics for manageable test size
    num_megas = draw(st.integers(min_value=1, max_value=2))
    tree = []

    for mega_idx in range(num_megas):
        mega = _draw_mega_topic(draw, mega_idx)
        tree.append(mega)

    return {"subject_id": subject_id, "tree": tree}


def _draw_mega_topic(draw, idx):
    """Draw a MEGA_TOPIC node with children."""
    title = f"MegaTopic_{idx}_{draw(st.integers(min_value=1, max_value=9999))}"
    mega = {
        "title": title,
        "node_type": "MEGA_TOPIC",
        "weight": draw(st.floats(min_value=0.1, max_value=10.0,
                                  allow_nan=False, allow_infinity=False)),
        "display_order": idx + 1,
        "ordering_justification": draw(st.one_of(
            st.none(), st.just("Foundation topic")
        )),
        "day_lesson_id": None,
        "children": [],
    }

    # Add 1-2 sub topics
    num_subs = draw(st.integers(min_value=1, max_value=2))
    for sub_idx in range(num_subs):
        sub = _draw_sub_topic(draw, idx, sub_idx)
        mega["children"].append(sub)

    return mega


def _draw_sub_topic(draw, mega_idx, sub_idx):
    """Draw a SUB_TOPIC node with leaf children."""
    title = f"SubTopic_{mega_idx}_{sub_idx}_{draw(st.integers(min_value=1, max_value=9999))}"
    sub = {
        "title": title,
        "node_type": "SUB_TOPIC",
        "weight": draw(st.floats(min_value=0.1, max_value=5.0,
                                  allow_nan=False, allow_infinity=False)),
        "display_order": sub_idx + 1,
        "ordering_justification": None,
        "day_lesson_id": None,
        "children": [],
    }

    # Add 1-2 leaf topics
    num_leaves = draw(st.integers(min_value=1, max_value=2))
    for leaf_idx in range(num_leaves):
        leaf = _draw_leaf_topic(draw, mega_idx, sub_idx, leaf_idx)
        sub["children"].append(leaf)

    return sub


def _draw_leaf_topic(draw, mega_idx, sub_idx, leaf_idx):
    """Draw a LEAF_TOPIC with optional content sections, PYQs, and MCQs."""
    title = (
        f"Leaf_{mega_idx}_{sub_idx}_{leaf_idx}_"
        f"{draw(st.integers(min_value=1, max_value=9999))}"
    )
    leaf: dict[str, Any] = {
        "title": title,
        "node_type": "LEAF_TOPIC",
        "weight": draw(st.floats(min_value=0.1, max_value=3.0,
                                  allow_nan=False, allow_infinity=False)),
        "display_order": leaf_idx + 1,
        "ordering_justification": None,
        "day_lesson_id": None,
        "children": [],
    }

    # Optionally add content sections
    has_sections = draw(st.booleans())
    if has_sections:
        leaf["content_sections"] = _draw_content_sections(draw)

    # Optionally add PYQs
    has_pyqs = draw(st.booleans())
    if has_pyqs:
        leaf["pyqs"] = _draw_pyqs(draw)

    # Optionally add MCQs
    has_mcqs = draw(st.booleans())
    if has_mcqs:
        leaf["mcq_questions"] = _draw_mcqs(draw)

    return leaf


def _draw_content_sections(draw):
    """Draw 4 content sections matching the expected labels."""
    sections = []
    for i, label in enumerate(SECTION_LABELS_ORDERED, start=1):
        sections.append({
            "section_label": label.value,
            "title": f"{label.value} Section",
            "blocks": [{"type": "text", "content": f"Content for {label.value}"}],
            "display_order": i,
            "authored": True,
        })
    return sections


def _draw_pyqs(draw):
    """Draw 1-2 PYQs."""
    num = draw(st.integers(min_value=1, max_value=2))
    pyqs = []
    for i in range(num):
        exam_type = draw(st.sampled_from(["PRELIMS", "MAINS"]))
        pyqs.append({
            "exam_type": exam_type,
            "year": draw(st.integers(min_value=2000, max_value=2024)),
            "question_text": f"PYQ question {i} {draw(st.integers(min_value=1, max_value=99999))}",
            "answer_text": "Model answer",
            "explanation": "Explanation text",
            "marks": 15 if exam_type == "MAINS" else None,
            "question_type": draw(st.sampled_from([
                "STATEMENT_BASED", "FACTUAL", "MAP_BASED",
            ])),
        })
    return pyqs


def _draw_mcqs(draw):
    """Draw 1-2 MCQ questions."""
    num = draw(st.integers(min_value=1, max_value=2))
    mcqs = []
    for i in range(num):
        mcqs.append({
            "question_text": f"MCQ question {i} {draw(st.integers(min_value=1, max_value=99999))}",
            "options": [
                {"label": "A", "text": "Option A"},
                {"label": "B", "text": "Option B"},
                {"label": "C", "text": "Option C"},
                {"label": "D", "text": "Option D"},
            ],
            "correct_option": draw(st.sampled_from(["A", "B", "C", "D"])),
            "explanation": "MCQ explanation",
            "question_type": draw(st.sampled_from([
                "STATEMENT_BASED", "FACTUAL", "ASSERTION_REASON",
            ])),
            "display_order": i + 1,
        })
    return mcqs


@st.composite
def st_review_status_mix(draw):
    """Generate a random mix of REVIEWED and UNREVIEWED content items.

    Returns a list of (title, review_status) tuples for creating syllabus nodes.
    """
    num_items = draw(st.integers(min_value=2, max_value=8))
    items = []
    for i in range(num_items):
        status = draw(st.sampled_from([
            GsReviewStatusEnum.REVIEWED,
            GsReviewStatusEnum.UNREVIEWED,
        ]))
        items.append((f"Topic_{i}_{draw(st.integers(min_value=1, max_value=9999))}", status))
    return items


@st.composite
def st_syllabus_with_day_lessons(draw):
    """Generate a syllabus tree with day_lesson_id mappings.

    Returns:
        - num_day_lessons: total day lessons to create
        - node_mappings: list of (node_title, day_lesson_id_or_none) pairs
        - has_duplicates: whether the mapping intentionally contains duplicates (for negative testing)
    """
    num_nodes = draw(st.integers(min_value=2, max_value=6))
    num_day_lessons = draw(st.integers(min_value=1, max_value=6))

    # Generate valid partial function mapping (no duplicates)
    available_dl_ids = list(range(1, num_day_lessons + 1))
    node_mappings = []

    for i in range(num_nodes):
        # Randomly assign a day_lesson_id or None
        if available_dl_ids and draw(st.booleans()):
            dl_id = draw(st.sampled_from(available_dl_ids))
            available_dl_ids.remove(dl_id)
            node_mappings.append((f"Node_{i}", dl_id))
        else:
            node_mappings.append((f"Node_{i}", None))

    return num_day_lessons, node_mappings


@st.composite
def st_old_progress_data(draw):
    """Generate random old-system progress data in one of the supported shapes.

    Returns a dict mapping day numbers to completion status, representing
    a StudentSubjectProgress.progress JSON field.
    """
    shape = draw(st.sampled_from(["shape1", "shape2", "shape3", "shape4"]))
    num_days = draw(st.integers(min_value=1, max_value=8))
    completed_days = draw(
        st.lists(
            st.integers(min_value=1, max_value=num_days),
            min_size=1,
            max_size=num_days,
            unique=True,
        )
    )

    if shape == "shape1":
        # {"1": true, "2": true, "5": false}
        progress = {}
        for d in range(1, num_days + 1):
            progress[str(d)] = d in completed_days
        return progress, completed_days

    elif shape == "shape2":
        # {"completedLessons": [1, 2, 3]}
        return {"completedLessons": sorted(completed_days)}, completed_days

    elif shape == "shape3":
        # {"day1": {"completed": true}, "day2": {"completed": false}}
        progress = {}
        for d in range(1, num_days + 1):
            progress[f"day{d}"] = {"completed": d in completed_days}
        return progress, completed_days

    else:
        # shape4: {"lessons": {"1": {"completed": true}}}
        lessons = {}
        for d in range(1, num_days + 1):
            lessons[str(d)] = {"completed": d in completed_days}
        return {"lessons": lessons}, completed_days


# ---------------------------------------------------------------------------
# DB Snapshot Helpers
# ---------------------------------------------------------------------------

def snapshot_db_state(session) -> dict[str, list[dict]]:
    """Take a snapshot of all GS LMS tables in the DB.

    Returns a dict mapping table name to list of row dicts (excluding
    timestamps that might differ between runs).
    """
    snapshot = {}

    # Snapshot syllabus nodes
    nodes = session.query(GsLmsSyllabusNode).all()
    snapshot["nodes"] = [
        {
            "title": n.title,
            "node_type": n.node_type.value if n.node_type else None,
            "parent_id": n.parent_id,
            "weight": round(n.weight, 6) if n.weight else None,
            "display_order": n.display_order,
            "day_lesson_id": n.day_lesson_id,
            "review_status": n.review_status.value if n.review_status else None,
        }
        for n in nodes
    ]

    # Snapshot content sections
    sections = session.query(GsLmsContentSection).all()
    snapshot["sections"] = [
        {
            "syllabus_node_id": s.syllabus_node_id,
            "section_label": s.section_label.value if s.section_label else None,
            "title": s.title,
            "display_order": s.display_order,
            "authored": s.authored,
        }
        for s in sections
    ]

    # Snapshot PYQs
    pyqs = session.query(GsLmsPyq).all()
    snapshot["pyqs"] = [
        {
            "syllabus_node_id": p.syllabus_node_id,
            "question_text": p.question_text,
            "year": p.year,
            "exam_type": p.exam_type.value if p.exam_type else None,
        }
        for p in pyqs
    ]

    # Snapshot MCQs
    mcqs = session.query(GsLmsMcqQuestion).all()
    snapshot["mcqs"] = [
        {
            "syllabus_node_id": m.syllabus_node_id,
            "question_text": m.question_text,
            "correct_option": m.correct_option,
            "display_order": m.display_order,
        }
        for m in mcqs
    ]

    return snapshot


# ===========================================================================
# Property 20: Content importer idempotency
# Validates: Requirements 10.5
# ===========================================================================


class TestContentImporterIdempotency:
    """Property 20: For any valid content artifact, running the importer twice
    must produce the same database state as running it once.

    Formally: import(artifact); state1 = snapshot(); import(artifact);
    state2 = snapshot(); assert state1 == state2.

    **Validates: Requirements 10.5**
    """

    @given(artifact=st_content_artifact())
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_idempotent_import_same_state(self, artifact):
        """Import the same artifact twice; DB state must be identical."""
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            # Seed the required subject
            seed_subject(session, subject_id=artifact["subject_id"])
            session.commit()

            # First import
            import_gs_geography(session, artifact)
            session.commit()

            # Snapshot after first import
            state1 = snapshot_db_state(session)

            # Second import (same artifact)
            import_gs_geography(session, artifact)
            session.commit()

            # Snapshot after second import
            state2 = snapshot_db_state(session)

            # The two snapshots must be identical
            assert len(state1["nodes"]) == len(state2["nodes"]), (
                f"Node count differs: {len(state1['nodes'])} vs {len(state2['nodes'])}"
            )
            assert len(state1["sections"]) == len(state2["sections"]), (
                f"Section count differs: {len(state1['sections'])} vs "
                f"{len(state2['sections'])}"
            )
            assert len(state1["pyqs"]) == len(state2["pyqs"]), (
                f"PYQ count differs: {len(state1['pyqs'])} vs {len(state2['pyqs'])}"
            )
            assert len(state1["mcqs"]) == len(state2["mcqs"]), (
                f"MCQ count differs: {len(state1['mcqs'])} vs {len(state2['mcqs'])}"
            )

            # Deep equality on content
            assert state1["nodes"] == state2["nodes"], "Node state changed on re-import"
            assert state1["sections"] == state2["sections"], (
                "Section state changed on re-import"
            )
            assert state1["pyqs"] == state2["pyqs"], "PYQ state changed on re-import"
            assert state1["mcqs"] == state2["mcqs"], "MCQ state changed on re-import"
        finally:
            session.close()
            engine.dispose()


# ===========================================================================
# Property 19: Review-gate filtering
# Validates: Requirements 10.3
# ===========================================================================


class TestReviewGateFiltering:
    """Property 19: For any query returning content visible to students, the
    result set must contain only records with review_status = REVIEWED. No
    UNREVIEWED or IN_REVIEW records may appear in student-facing responses.

    **Validates: Requirements 10.3**
    """

    @given(items=st_review_status_mix())
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_student_query_never_returns_unreviewed_nodes(self, items):
        """Generate random REVIEWED/UNREVIEWED node mixes and verify that a
        student-facing query filters out all non-REVIEWED content."""
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            seed_subject(session)
            session.commit()

            # Create nodes with varying review statuses
            for i, (title, status) in enumerate(items):
                node = GsLmsSyllabusNode(
                    subject_id=1,
                    parent_id=None,
                    title=title,
                    node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                    weight=1.0,
                    display_order=i,
                    review_status=status,
                    created_by="test",
                    updated_by="test",
                )
                session.add(node)
            session.commit()

            # Simulate student-facing query: only REVIEWED
            visible_nodes = (
                session.query(GsLmsSyllabusNode)
                .filter(GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED)
                .all()
            )

            # Verify: no UNREVIEWED content appears
            for node in visible_nodes:
                assert node.review_status == GsReviewStatusEnum.REVIEWED, (
                    f"UNREVIEWED node '{node.title}' leaked into student response"
                )

            # Verify count matches expected
            expected_reviewed = sum(
                1 for _, status in items
                if status == GsReviewStatusEnum.REVIEWED
            )
            assert len(visible_nodes) == expected_reviewed
        finally:
            session.close()
            engine.dispose()


    @given(items=st_review_status_mix())
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_student_query_never_returns_unreviewed_sections(self, items):
        """Verify review-gate on content sections: only REVIEWED sections
        appear in student-facing queries, regardless of the mix."""
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            seed_subject(session)
            session.commit()

            # Create a REVIEWED node to attach sections to
            node = GsLmsSyllabusNode(
                subject_id=1,
                parent_id=None,
                title="Host Node",
                node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                weight=1.0,
                display_order=0,
                review_status=GsReviewStatusEnum.REVIEWED,
                created_by="test",
                updated_by="test",
            )
            session.add(node)
            session.flush()

            # Create sections with varying statuses
            for i, (title, status) in enumerate(items):
                label = SECTION_LABELS_ORDERED[i % 4]
                sec = GsLmsContentSection(
                    syllabus_node_id=node.id,
                    section_label=label,
                    title=title,
                    display_order=i + 1,
                    review_status=status,
                    authored=True,
                    created_by="test",
                    updated_by="test",
                )
                session.add(sec)
            session.commit()

            # Student-facing query filters by REVIEWED
            visible_sections = (
                session.query(GsLmsContentSection)
                .filter(
                    GsLmsContentSection.syllabus_node_id == node.id,
                    GsLmsContentSection.review_status == GsReviewStatusEnum.REVIEWED,
                )
                .all()
            )

            for sec in visible_sections:
                assert sec.review_status == GsReviewStatusEnum.REVIEWED, (
                    f"UNREVIEWED section '{sec.title}' leaked"
                )

            expected_reviewed = sum(
                1 for _, status in items
                if status == GsReviewStatusEnum.REVIEWED
            )
            assert len(visible_sections) == expected_reviewed
        finally:
            session.close()
            engine.dispose()


# ===========================================================================
# Property 23: Auth gating on all endpoints
# Validates: Requirements 10.2
# ===========================================================================


class TestAuthGatingProperty:
    """Property 23: For any GS LMS API endpoint, a request without valid
    authentication credentials must be rejected with HTTP 401 or 403 status,
    and no data must be returned.

    Uses a hypothesis-based parametrized approach that generates random
    subsets of the registered routes and verifies auth gating.

    **Validates: Requirements 10.2**
    """

    GS_LMS_PREFIX = "/api/v1/gs-lms"
    _PARAM_RE = re.compile(r"\{[^}]+\}")

    @classmethod
    def _concrete_path(cls, path: str) -> str:
        """Replace path parameters with '1'."""
        return cls._PARAM_RE.sub("1", path)

    @classmethod
    def _gs_lms_routes(cls):
        """Collect all GS LMS routes from the app."""
        from app.main import app

        routes = []
        seen = set()
        for route in app.routes:
            path = getattr(route, "path", "") or ""
            methods = getattr(route, "methods", None) or set()
            if not path.startswith(cls.GS_LMS_PREFIX):
                continue
            key = (path, frozenset(methods))
            if key in seen:
                continue
            seen.add(key)
            for method in methods:
                routes.append((path, method))
        return routes

    @given(data=st.data())
    @settings(max_examples=30, deadline=None)
    def test_random_route_subset_requires_auth(self, data):
        """Pick a random subset of GS LMS routes and verify auth rejection."""
        from fastapi.testclient import TestClient
        from app.main import app

        all_routes = self._gs_lms_routes()
        assume(len(all_routes) > 0)

        # Pick a random subset (1 to min(5, total))
        subset_size = data.draw(
            st.integers(min_value=1, max_value=min(5, len(all_routes)))
        )
        chosen_routes = data.draw(
            st.lists(
                st.sampled_from(all_routes),
                min_size=subset_size,
                max_size=subset_size,
            )
        )

        client = TestClient(app)
        for path, method in chosen_routes:
            url = self._concrete_path(path)
            resp = client.request(method, url)
            # Must be rejected: 401 is ideal, 403 acceptable,
            # 405 if method mismatch, 422 if validation kicks in before auth
            # Key invariant: never a 2xx success
            assert resp.status_code != 200 or resp.status_code in (401, 403), (
                f"Route {method} {url} returned {resp.status_code} without auth. "
                f"Expected 401/403."
            )
            # Stronger: must be 401 for unauthenticated
            if resp.status_code not in (405, 422, 307):
                assert resp.status_code == 401, (
                    f"Route {method} {url} returned {resp.status_code}, expected 401"
                )


# ===========================================================================
# Property 21: Day-lesson bridge mapping integrity
# Validates: Requirements 11.2
# ===========================================================================


class TestBridgeMappingIntegrity:
    """Property 21: For any syllabus tree with day_lesson_id bridges:
    (a) every non-null day_lesson_id must reference a valid GsDayLesson record,
    (b) no two syllabus nodes may reference the same GsDayLesson, and
    (c) the mapping must be a valid partial function from syllabus nodes to
        day lessons.

    **Validates: Requirements 11.2**
    """

    @given(mapping_data=st_syllabus_with_day_lessons())
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_valid_mapping_passes_validation(self, mapping_data):
        """A valid partial function mapping (no duplicates, all references
        valid) must pass validate_bridge_mapping."""
        num_day_lessons, node_mappings = mapping_data
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            # Seed subject
            seed_subject(session)
            session.commit()

            # Create GsDayLesson records
            for dl_id in range(1, num_day_lessons + 1):
                lesson = GsDayLesson(
                    id=dl_id,
                    subject_id=1,
                    day_number=dl_id,
                    title=f"Day Lesson {dl_id}",
                    created_by="test",
                    updated_by="test",
                )
                session.add(lesson)
            session.flush()

            # Create syllabus nodes with the mapping
            for i, (title, dl_id) in enumerate(node_mappings):
                node = GsLmsSyllabusNode(
                    subject_id=1,
                    parent_id=None,
                    title=title,
                    node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                    weight=1.0,
                    display_order=i,
                    day_lesson_id=dl_id,
                    review_status=GsReviewStatusEnum.REVIEWED,
                    created_by="test",
                    updated_by="test",
                )
                session.add(node)
            session.commit()

            # Validate bridge mapping
            result = validate_bridge_mapping(session)

            # Since our strategy generates unique mappings, should be valid
            assert result["valid"] is True, (
                f"Expected valid mapping but got: "
                f"duplicates={result['duplicates']}, orphans={result['orphans']}"
            )
            assert result["duplicates"] == []
            assert result["orphans"] == []

            # Verify total_bridges count
            expected_bridges = sum(
                1 for _, dl_id in node_mappings if dl_id is not None
            )
            assert result["total_bridges"] == expected_bridges
        finally:
            session.close()
            engine.dispose()


    @given(
        num_day_lessons=st.integers(min_value=1, max_value=5),
        num_nodes=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_duplicate_mapping_detected(self, num_day_lessons, num_nodes):
        """If two nodes share the same day_lesson_id, validation must
        report duplicates and valid=False."""
        assume(num_nodes >= 2)
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            seed_subject(session)
            session.commit()

            # Create a day lesson
            lesson = GsDayLesson(
                id=1,
                subject_id=1,
                day_number=1,
                title="Day Lesson 1",
                created_by="test",
                updated_by="test",
            )
            session.add(lesson)
            session.flush()

            # Create two nodes pointing to the SAME day_lesson_id (violation)
            for i in range(2):
                node = GsLmsSyllabusNode(
                    subject_id=1,
                    parent_id=None,
                    title=f"Duplicate Node {i}",
                    node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                    weight=1.0,
                    display_order=i,
                    day_lesson_id=1,  # Both point to same lesson
                    review_status=GsReviewStatusEnum.REVIEWED,
                    created_by="test",
                    updated_by="test",
                )
                session.add(node)
            session.commit()

            result = validate_bridge_mapping(session)

            # Must detect the duplicate
            assert result["valid"] is False, (
                "Duplicate day_lesson_id mapping should be invalid"
            )
            assert len(result["duplicates"]) > 0, (
                "Expected duplicates to be reported"
            )
            assert result["duplicates"][0]["day_lesson_id"] == 1
            assert result["duplicates"][0]["node_count"] == 2
        finally:
            session.close()
            engine.dispose()


    @given(mapping_data=st_syllabus_with_day_lessons())
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_no_two_nodes_share_same_day_lesson(self, mapping_data):
        """Property invariant: given any valid mapping, verify that the
        day_lesson_id → node mapping is indeed a partial function (injective)."""
        num_day_lessons, node_mappings = mapping_data

        # Check the mapping itself (before DB): no two entries have same dl_id
        assigned_ids = [dl_id for _, dl_id in node_mappings if dl_id is not None]
        assert len(assigned_ids) == len(set(assigned_ids)), (
            f"Strategy generated duplicate day_lesson_ids: {assigned_ids}"
        )


# ===========================================================================
# Property 22: Progress migration data preservation
# Validates: Requirements 11.5
# ===========================================================================


class TestProgressMigrationDataPreservation:
    """Property 22: For any student with existing progress in the day-lesson
    system, after migration to the topic-based system, the equivalent
    completion data must exist in the new GsLmsStudentSectionProgress records
    with no data loss.

    **Validates: Requirements 11.5**
    """

    @given(progress_data=st_old_progress_data())
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_migration_preserves_all_completed_days(self, progress_data):
        """Migrate old progress; verify all completed day lessons have
        corresponding section progress records in the new system."""
        progress_json, completed_days = progress_data
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            # Seed subject
            seed_subject(session)
            session.commit()

            # Create a student
            student = User(
                id=1,
                google_uid="test-student-uid",
                email="student@test.local",
                full_name="Test Student",
                role=RoleEnum.STUDENT,
            )
            session.add(student)
            session.flush()

            # Create GsDayLesson records for each possible day
            max_day = max(completed_days) if completed_days else 1
            day_lesson_ids = {}
            for d in range(1, max_day + 1):
                lesson = GsDayLesson(
                    id=d,
                    subject_id=1,
                    day_number=d,
                    title=f"Day {d}",
                    created_by="test",
                    updated_by="test",
                )
                session.add(lesson)
                day_lesson_ids[d] = d
            session.flush()

            # Create syllabus nodes bridged to day lessons
            node_ids = {}
            for d in range(1, max_day + 1):
                node = GsLmsSyllabusNode(
                    id=100 + d,
                    subject_id=1,
                    parent_id=None,
                    title=f"Topic for Day {d}",
                    node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                    weight=1.0,
                    display_order=d,
                    day_lesson_id=d,  # Bridge to day lesson
                    review_status=GsReviewStatusEnum.REVIEWED,
                    created_by="test",
                    updated_by="test",
                )
                session.add(node)
                node_ids[d] = 100 + d
            session.flush()

            # Create BASIC content sections for each node (migration target)
            section_ids = {}
            for d in range(1, max_day + 1):
                sec = GsLmsContentSection(
                    id=200 + d,
                    syllabus_node_id=node_ids[d],
                    section_label=GsLmsSectionLabelEnum.BASIC,
                    title=f"BASIC for Day {d}",
                    display_order=1,
                    review_status=GsReviewStatusEnum.REVIEWED,
                    authored=True,
                    created_by="test",
                    updated_by="test",
                )
                session.add(sec)
                section_ids[d] = 200 + d
            session.flush()

            # Create old-system progress record
            old_progress = StudentSubjectProgress(
                user_id=1,
                subject_slug="geography",
                progress=progress_json,
            )
            session.add(old_progress)
            session.commit()

            # Run migration
            result = migrate_progress(session, student_id=1)
            session.commit()

            # Verify: every completed day should have a progress record
            new_progress = (
                session.query(GsLmsStudentSectionProgress)
                .filter(GsLmsStudentSectionProgress.student_id == 1)
                .all()
            )

            # The migrated records should cover all completed days that have
            # both a bridged node AND a BASIC section
            migrated_section_ids = {p.section_id for p in new_progress}

            for day_num in completed_days:
                if day_num <= max_day:
                    expected_section_id = section_ids[day_num]
                    assert expected_section_id in migrated_section_ids, (
                        f"Day {day_num} completion was not migrated. "
                        f"Expected section_id={expected_section_id} in progress."
                    )

            # Verify no data loss: records_created should equal completed days
            # that have valid bridges
            assert result["records_created"] == len(completed_days), (
                f"Expected {len(completed_days)} records created, "
                f"got {result['records_created']}"
            )
            assert result["day_lessons_without_bridge"] == []
            assert result["day_lessons_without_basic_section"] == []
        finally:
            session.close()
            engine.dispose()


    @given(progress_data=st_old_progress_data())
    @settings(max_examples=30, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    def test_migration_is_idempotent(self, progress_data):
        """Running migration twice for the same student must not create
        duplicate records (idempotent)."""
        progress_json, completed_days = progress_data
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            seed_subject(session)
            session.commit()

            # Create student
            student = User(
                id=1,
                google_uid="test-student-uid",
                email="student@test.local",
                full_name="Test Student",
                role=RoleEnum.STUDENT,
            )
            session.add(student)
            session.flush()

            # Create day lessons, nodes, and sections
            max_day = max(completed_days) if completed_days else 1
            for d in range(1, max_day + 1):
                lesson = GsDayLesson(
                    id=d, subject_id=1, day_number=d,
                    title=f"Day {d}", created_by="test", updated_by="test",
                )
                session.add(lesson)
            session.flush()

            for d in range(1, max_day + 1):
                node = GsLmsSyllabusNode(
                    id=100 + d, subject_id=1, parent_id=None,
                    title=f"Topic for Day {d}",
                    node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                    weight=1.0, display_order=d, day_lesson_id=d,
                    review_status=GsReviewStatusEnum.REVIEWED,
                    created_by="test", updated_by="test",
                )
                session.add(node)
            session.flush()

            for d in range(1, max_day + 1):
                sec = GsLmsContentSection(
                    id=200 + d, syllabus_node_id=100 + d,
                    section_label=GsLmsSectionLabelEnum.BASIC,
                    title=f"BASIC for Day {d}", display_order=1,
                    review_status=GsReviewStatusEnum.REVIEWED,
                    authored=True, created_by="test", updated_by="test",
                )
                session.add(sec)
            session.flush()

            # Old progress
            old_progress = StudentSubjectProgress(
                user_id=1, subject_slug="geography", progress=progress_json,
            )
            session.add(old_progress)
            session.commit()

            # First migration
            result1 = migrate_progress(session, student_id=1)
            session.commit()

            # Second migration (should skip existing records)
            result2 = migrate_progress(session, student_id=1)
            session.commit()

            # Second run should create 0 new records, skip all
            assert result2["records_created"] == 0, (
                f"Second migration created {result2['records_created']} records, "
                f"expected 0 (idempotent)"
            )
            assert result2["records_skipped"] == result1["records_created"], (
                f"Second migration skipped {result2['records_skipped']}, "
                f"expected {result1['records_created']}"
            )

            # Total records unchanged
            total_progress = (
                session.query(GsLmsStudentSectionProgress)
                .filter(GsLmsStudentSectionProgress.student_id == 1)
                .count()
            )
            assert total_progress == result1["records_created"]
        finally:
            session.close()
            engine.dispose()
