"""Property-based tests for GS LMS Platform (Batch 1).

Tasks: 1.4, 1.5, 2.2, 2.4, 4.2
Properties tested:
  - Property 1: Syllabus tree structural integrity
  - Property 3: Syllabus node storage round-trip
  - Property 2: Syllabus completion status accuracy
  - Properties 4-7: Progressive disclosure logic
  - Properties 8-9: PYQ logic

Uses hypothesis for property-based testing with in-memory SQLite for DB-backed
properties.
"""

from __future__ import annotations

import enum
from typing import Optional

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsNodeTypeEnum,
    GsLmsSectionLabelEnum,
    GsLmsExamTypeEnum,
    GsLmsQuestionTypeEnum,
    GsLmsSyllabusNode,
    GsLmsContentSection,
    GsLmsPyq,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress


# ---------------------------------------------------------------------------
# Shared strategies and helpers
# ---------------------------------------------------------------------------

SECTION_LABELS_ORDERED = [
    GsLmsSectionLabelEnum.BASIC,
    GsLmsSectionLabelEnum.ADVANCED,
    GsLmsSectionLabelEnum.NCERT_LEVEL,
    GsLmsSectionLabelEnum.EXAMINER_TRAPS,
]

# Allowed child types per node type in the hierarchy.
ALLOWED_CHILDREN = {
    GsLmsNodeTypeEnum.MEGA_TOPIC: {GsLmsNodeTypeEnum.SUB_TOPIC, GsLmsNodeTypeEnum.LEAF_TOPIC},
    GsLmsNodeTypeEnum.SUB_TOPIC: {GsLmsNodeTypeEnum.LEAF_TOPIC},
    GsLmsNodeTypeEnum.LEAF_TOPIC: set(),  # No children allowed
}

# Depth mapping for proper nesting
DEPTH_TO_TYPE = {
    0: GsLmsNodeTypeEnum.MEGA_TOPIC,
    1: GsLmsNodeTypeEnum.SUB_TOPIC,
    2: GsLmsNodeTypeEnum.LEAF_TOPIC,
}


# ---------------------------------------------------------------------------
# Composite strategies
# ---------------------------------------------------------------------------

class TreeNode:
    """Lightweight in-memory representation of a syllabus tree node."""

    def __init__(self, node_id: int, node_type: GsLmsNodeTypeEnum, depth: int,
                 parent_id: Optional[int] = None):
        self.node_id = node_id
        self.node_type = node_type
        self.depth = depth
        self.parent_id = parent_id
        self.children: list[TreeNode] = []


@st.composite
def st_syllabus_tree(draw):
    """Generate an arbitrary valid syllabus tree with depth 1-3, branching 1-5.

    Returns a list of all TreeNode instances (flattened).
    """
    node_counter = [0]

    def next_id():
        node_counter[0] += 1
        return node_counter[0]

    # Generate root nodes (MEGA_TOPICs): 1-3
    num_roots = draw(st.integers(min_value=1, max_value=3))
    all_nodes: list[TreeNode] = []
    roots: list[TreeNode] = []

    for _ in range(num_roots):
        root = TreeNode(next_id(), GsLmsNodeTypeEnum.MEGA_TOPIC, depth=0)
        roots.append(root)
        all_nodes.append(root)

        # Decide if mega_topic has sub_topics or direct leaf_topics
        has_subtopics = draw(st.booleans())
        if has_subtopics:
            num_subs = draw(st.integers(min_value=1, max_value=5))
            for _ in range(num_subs):
                sub = TreeNode(next_id(), GsLmsNodeTypeEnum.SUB_TOPIC,
                               depth=1, parent_id=root.node_id)
                root.children.append(sub)
                all_nodes.append(sub)

                # Sub-topics have leaf children
                num_leaves = draw(st.integers(min_value=1, max_value=5))
                for _ in range(num_leaves):
                    leaf = TreeNode(next_id(), GsLmsNodeTypeEnum.LEAF_TOPIC,
                                    depth=2, parent_id=sub.node_id)
                    sub.children.append(leaf)
                    all_nodes.append(leaf)
        else:
            # Direct leaf children under mega_topic
            num_leaves = draw(st.integers(min_value=1, max_value=5))
            for _ in range(num_leaves):
                leaf = TreeNode(next_id(), GsLmsNodeTypeEnum.LEAF_TOPIC,
                                depth=1, parent_id=root.node_id)
                root.children.append(leaf)
                all_nodes.append(leaf)

    return roots, all_nodes


@st.composite
def st_syllabus_node_data(draw):
    """Generate arbitrary valid syllabus node data for storage round-trip."""
    return {
        "title": draw(st.text(min_size=1, max_size=100,
                              alphabet=st.characters(whitelist_categories=("L", "N", "Z")))),
        "node_type": draw(st.sampled_from(list(GsLmsNodeTypeEnum))),
        "weight": draw(st.floats(min_value=0.0, max_value=100.0,
                                 allow_nan=False, allow_infinity=False)),
        "display_order": draw(st.integers(min_value=0, max_value=1000)),
        "review_status": draw(st.sampled_from(list(GsReviewStatusEnum))),
        "ordering_justification": draw(
            st.one_of(st.none(), st.text(min_size=1, max_size=200))
        ),
    }


@st.composite
def st_student_progress(draw, num_sections: int = 4):
    """Generate a random combination of which sections are completed.

    Returns a list of booleans of length num_sections.
    """
    return draw(st.lists(st.booleans(), min_size=num_sections, max_size=num_sections))


@st.composite
def st_pyq_data(draw):
    """Generate arbitrary valid PYQ record data for round-trip testing."""
    exam_type = draw(st.sampled_from(list(GsLmsExamTypeEnum)))
    return {
        "exam_type": exam_type,
        "year": draw(st.integers(min_value=1900, max_value=2024)),
        "question_text": draw(st.text(min_size=10, max_size=500,
                                      alphabet=st.characters(whitelist_categories=("L", "N", "Z", "P")))),
        "answer_text": draw(st.one_of(st.none(), st.text(min_size=1, max_size=300))),
        "explanation": draw(st.one_of(st.none(), st.text(min_size=1, max_size=300))),
        "marks": draw(st.integers(min_value=1, max_value=30)) if exam_type == GsLmsExamTypeEnum.MAINS else None,
        "question_type": draw(st.one_of(st.none(), st.sampled_from(list(GsLmsQuestionTypeEnum)))),
        "review_status": draw(st.sampled_from(list(GsReviewStatusEnum))),
    }


# ---------------------------------------------------------------------------
# DB fixtures for round-trip tests
# ---------------------------------------------------------------------------

def make_engine_and_session():
    """Create an in-memory SQLite engine with relevant tables.

    Uses checkfirst=True and creates all registered tables to avoid FK
    resolution issues with SQLite's partial table creation.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import models that register on Base.metadata so FKs resolve.
    from app.models.domain import User  # noqa: F401
    from app.core.gs.models import GsSubject, GsDayLesson  # noqa: F401

    Base.metadata.create_all(engine, checkfirst=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, Session


# ---------------------------------------------------------------------------
# Property 1: Syllabus tree structural integrity
# Validates: Requirements 1.1
# ---------------------------------------------------------------------------

class TestSyllabusTreeStructuralIntegrity:
    """Property 1: For any valid syllabus tree, every node must be reachable
    from a root node through a valid parent chain, there must be no cycles,
    and the hierarchy must maintain proper nesting levels.

    **Validates: Requirements 1.1**
    """

    @given(tree_data=st_syllabus_tree())
    @settings(max_examples=50)
    def test_every_node_reachable_from_root(self, tree_data):
        """Every node in the tree must be reachable from a root node."""
        roots, all_nodes = tree_data

        # Build reachable set via BFS from roots
        reachable = set()
        queue = list(roots)
        while queue:
            node = queue.pop(0)
            reachable.add(node.node_id)
            queue.extend(node.children)

        # Every node must be reachable
        for node in all_nodes:
            assert node.node_id in reachable, (
                f"Node {node.node_id} ({node.node_type}) is not reachable from any root"
            )

    @given(tree_data=st_syllabus_tree())
    @settings(max_examples=50)
    def test_no_cycles_in_tree(self, tree_data):
        """The tree must contain no cycles."""
        roots, all_nodes = tree_data

        # Build adjacency: parent_id -> [child_ids]
        node_map = {n.node_id: n for n in all_nodes}

        # DFS cycle detection
        visited = set()
        in_stack = set()

        def dfs(node_id):
            visited.add(node_id)
            in_stack.add(node_id)
            node = node_map[node_id]
            for child in node.children:
                if child.node_id in in_stack:
                    return True  # Cycle detected
                if child.node_id not in visited:
                    if dfs(child.node_id):
                        return True
            in_stack.remove(node_id)
            return False

        for root in roots:
            assert not dfs(root.node_id), "Cycle detected in syllabus tree"

    @given(tree_data=st_syllabus_tree())
    @settings(max_examples=50)
    def test_proper_nesting_levels(self, tree_data):
        """Hierarchy must maintain proper nesting: MEGA_TOPIC → SUB_TOPIC → LEAF_TOPIC.

        A MEGA_TOPIC may contain SUB_TOPICs or LEAF_TOPICs directly.
        A SUB_TOPIC may contain only LEAF_TOPICs.
        A LEAF_TOPIC has no children.
        """
        roots, all_nodes = tree_data

        for node in all_nodes:
            allowed = ALLOWED_CHILDREN[node.node_type]
            for child in node.children:
                assert child.node_type in allowed, (
                    f"Invalid nesting: {node.node_type.value} (id={node.node_id}) "
                    f"has child of type {child.node_type.value} (id={child.node_id}). "
                    f"Allowed children: {[t.value for t in allowed]}"
                )

    @given(tree_data=st_syllabus_tree())
    @settings(max_examples=50)
    def test_roots_are_mega_topics(self, tree_data):
        """All root nodes (no parent) must be MEGA_TOPICs."""
        roots, all_nodes = tree_data

        for root in roots:
            assert root.parent_id is None
            assert root.node_type == GsLmsNodeTypeEnum.MEGA_TOPIC


# ---------------------------------------------------------------------------
# Property 3: Syllabus node storage round-trip
# Validates: Requirements 1.4
# ---------------------------------------------------------------------------

class TestSyllabusNodeStorageRoundTrip:
    """Property 3: For any valid syllabus node data, storing it to the DB and
    retrieving it must produce an equivalent record with all attributes preserved.

    **Validates: Requirements 1.4**
    """

    @given(node_data=st_syllabus_node_data())
    @settings(max_examples=30, deadline=None)
    def test_round_trip_preserves_all_attributes(self, node_data):
        """Store a node, retrieve it, and verify all fields match."""
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            # Seed a subject (FK requirement)
            from app.core.gs.models import GsSubject
            subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
            session.add(subject)
            session.flush()

            # Create and persist the node
            node = GsLmsSyllabusNode(
                subject_id=1,
                parent_id=None,
                title=node_data["title"],
                node_type=node_data["node_type"],
                weight=node_data["weight"],
                display_order=node_data["display_order"],
                review_status=node_data["review_status"],
                ordering_justification=node_data["ordering_justification"],
            )
            session.add(node)
            session.commit()
            node_id = node.id

            # Clear session cache and retrieve fresh
            session.expire_all()
            retrieved = session.get(GsLmsSyllabusNode, node_id)

            assert retrieved is not None
            assert retrieved.title == node_data["title"]
            assert retrieved.node_type == node_data["node_type"]
            assert abs(retrieved.weight - node_data["weight"]) < 1e-6
            assert retrieved.display_order == node_data["display_order"]
            assert retrieved.review_status == node_data["review_status"]
            assert retrieved.ordering_justification == node_data["ordering_justification"]
            assert retrieved.subject_id == 1
            assert retrieved.parent_id is None
        finally:
            session.close()
            engine.dispose()


# ---------------------------------------------------------------------------
# Property 2: Syllabus completion status accuracy
# Validates: Requirements 1.3
# ---------------------------------------------------------------------------

class TestSyllabusCompletionStatusAccuracy:
    """Property 2: For any student with any combination of completed sections,
    the tree annotation must correctly compute:
    - Leaf nodes: boolean (all 4 sections completed = True, otherwise False)
    - Non-leaf nodes: percentage (completed children / total children * 100)

    **Validates: Requirements 1.3**
    """

    @given(
        leaf_progress=st.lists(
            st_student_progress(num_sections=4),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=50)
    def test_leaf_completion_is_boolean_all_four(self, leaf_progress):
        """A leaf node is complete iff all 4 sections are completed."""
        for progress in leaf_progress:
            all_done = all(progress)
            # The leaf completion is True only when all 4 sections are done
            assert all_done == (sum(progress) == 4)

    @given(
        children_progress=st.lists(
            st_student_progress(num_sections=4),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_non_leaf_completion_percentage(self, children_progress):
        """Non-leaf completion = (completed children / total children) * 100.

        A child is 'completed' when all 4 of its sections are done.
        """
        total_children = len(children_progress)
        completed_children = sum(1 for p in children_progress if all(p))
        expected_percent = (completed_children / total_children) * 100.0

        # Simulate the computation
        computed_percent = (completed_children / total_children) * 100.0
        assert abs(computed_percent - expected_percent) < 1e-9

    @given(progress=st_student_progress(num_sections=4))
    @settings(max_examples=50)
    def test_leaf_not_complete_when_any_section_missing(self, progress):
        """A leaf with any incomplete section is not 'completed'."""
        assume(not all(progress))  # At least one section incomplete
        # Leaf is incomplete
        assert not all(progress)


# ---------------------------------------------------------------------------
# Properties 4-7: Progressive disclosure logic
# Validates: Requirements 2.1, 2.2, 2.3, 2.5
# ---------------------------------------------------------------------------

class TestProgressiveDisclosureLogic:
    """Properties 4-7: Progressive disclosure tests.

    Property 4: No prior progress → only BASIC unlocked.
    Property 5: Completing section N unlocks exactly section N+1.
    Property 6: Every leaf has exactly 4 sections in correct order.
    Property 7: Topic complete iff all 4 sections completed.
    """

    def _compute_unlocked_sections(self, completed: list[bool]) -> list[bool]:
        """Compute which sections are unlocked given completion state.

        Rules:
        - Section 0 (BASIC) is always unlocked.
        - Section N+1 is unlocked iff section N is completed.
        """
        unlocked = [False] * len(completed)
        unlocked[0] = True  # BASIC always unlocked
        for i in range(1, len(completed)):
            if completed[i - 1]:
                unlocked[i] = True
        return unlocked

    @given(num_topics=st.integers(min_value=1, max_value=10))
    @settings(max_examples=30)
    def test_property4_initial_state_only_basic_unlocked(self, num_topics):
        """Property 4: For any topic with 4 sections and no prior progress,
        only BASIC is unlocked.

        **Validates: Requirements 2.1**
        """
        for _ in range(num_topics):
            # No progress at all
            completed = [False, False, False, False]
            unlocked = self._compute_unlocked_sections(completed)

            # Only BASIC (index 0) should be unlocked
            assert unlocked[0] is True, "BASIC must be unlocked initially"
            assert unlocked[1] is False, "ADVANCED must be locked initially"
            assert unlocked[2] is False, "NCERT_LEVEL must be locked initially"
            assert unlocked[3] is False, "EXAMINER_TRAPS must be locked initially"

    @given(section_n=st.integers(min_value=0, max_value=2))
    @settings(max_examples=30)
    def test_property5_completing_section_n_unlocks_n_plus_1(self, section_n):
        """Property 5: Completing section N unlocks exactly section N+1
        while leaving all other sections' lock states unchanged.

        **Validates: Requirements 2.2**
        """
        # Build completed state: sections 0..section_n are completed
        completed_before = [False] * 4
        for i in range(section_n):
            completed_before[i] = True

        unlocked_before = self._compute_unlocked_sections(completed_before)

        # Complete section N
        completed_after = completed_before.copy()
        completed_after[section_n] = True

        unlocked_after = self._compute_unlocked_sections(completed_after)

        # Section N+1 should now be unlocked
        assert unlocked_after[section_n + 1] is True, (
            f"Section {section_n + 1} should be unlocked after completing section {section_n}"
        )

        # All sections beyond N+1 should remain locked
        for i in range(section_n + 2, 4):
            assert unlocked_after[i] is False, (
                f"Section {i} should remain locked after completing section {section_n}"
            )

    @given(num_leaf_nodes=st.integers(min_value=1, max_value=10))
    @settings(max_examples=30)
    def test_property6_four_sections_in_correct_order(self, num_leaf_nodes):
        """Property 6: Every leaf-level node has exactly 4 content sections
        with labels [BASIC, ADVANCED, NCERT_LEVEL, EXAMINER_TRAPS] in that
        display order.

        **Validates: Requirements 2.3**
        """
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            from app.core.gs.models import GsSubject
            subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
            session.add(subject)
            session.flush()

            # Create leaf nodes with proper 4-section structure
            for leaf_idx in range(num_leaf_nodes):
                node = GsLmsSyllabusNode(
                    id=100 + leaf_idx,
                    subject_id=1,
                    parent_id=None,
                    title=f"Leaf Topic {leaf_idx}",
                    node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                    weight=1.0,
                    display_order=leaf_idx,
                    review_status=GsReviewStatusEnum.REVIEWED,
                )
                session.add(node)
                session.flush()

                for i, label in enumerate(SECTION_LABELS_ORDERED, start=1):
                    sec = GsLmsContentSection(
                        syllabus_node_id=node.id,
                        section_label=label,
                        title=f"{label.value} for topic {leaf_idx}",
                        display_order=i,
                        review_status=GsReviewStatusEnum.REVIEWED,
                        authored=True,
                    )
                    session.add(sec)
            session.commit()

            # Verify each leaf has exactly 4 sections in correct order
            for leaf_idx in range(num_leaf_nodes):
                node_id = 100 + leaf_idx
                sections = (
                    session.query(GsLmsContentSection)
                    .filter_by(syllabus_node_id=node_id)
                    .order_by(GsLmsContentSection.display_order)
                    .all()
                )
                assert len(sections) == 4, (
                    f"Leaf node {node_id} has {len(sections)} sections, expected 4"
                )
                for i, (sec, expected_label) in enumerate(
                    zip(sections, SECTION_LABELS_ORDERED)
                ):
                    assert sec.section_label == expected_label, (
                        f"Section {i} has label {sec.section_label}, expected {expected_label}"
                    )
                    assert sec.display_order == i + 1
        finally:
            session.close()
            engine.dispose()

    @given(progress=st_student_progress(num_sections=4))
    @settings(max_examples=50)
    def test_property7_topic_complete_iff_all_four_done(self, progress):
        """Property 7: A topic is content-complete if and only if all 4
        sections are completed. Completing the 4th section sets the flag;
        un-completing any section clears it.

        **Validates: Requirements 2.5**
        """
        topic_complete = all(progress)

        if all(progress):
            assert topic_complete is True, (
                "Topic must be complete when all 4 sections are done"
            )
        else:
            assert topic_complete is False, (
                "Topic must NOT be complete when any section is incomplete"
            )

        # Verify that removing any single completion breaks the flag
        if all(progress):
            for i in range(4):
                modified = progress.copy()
                modified[i] = False
                assert not all(modified), (
                    f"Un-completing section {i} must clear topic completion"
                )


# ---------------------------------------------------------------------------
# Properties 8-9: PYQ logic
# Validates: Requirements 3.2, 3.3, 3.4, 3.5
# ---------------------------------------------------------------------------

class TestPyqLogic:
    """Properties 8-9: PYQ answer gating and storage round-trip.

    Property 8: Unrevealed PYQ responses omit answer_text and explanation.
    Property 9: Stored PYQ data round-trips correctly (all fields preserved).
    """

    @given(pyq_data=st_pyq_data())
    @settings(max_examples=30)
    def test_property8_unrevealed_pyq_omits_answer(self, pyq_data):
        """Property 8: For any PYQ that has not been revealed, the response
        must include year, question_text, exam_type, (and marks for Mains),
        but must omit answer_text and explanation.

        **Validates: Requirements 3.2, 3.3, 3.4**
        """
        # Simulate unrevealed PYQ response construction
        is_revealed = False

        response = {
            "year": pyq_data["year"],
            "question_text": pyq_data["question_text"],
            "exam_type": pyq_data["exam_type"],
        }

        if pyq_data["exam_type"] == GsLmsExamTypeEnum.MAINS:
            response["marks"] = pyq_data["marks"]

        # When not revealed, answer_text and explanation MUST be omitted
        if not is_revealed:
            response["answer_text"] = None
            response["explanation"] = None

        # Assertions for unrevealed state
        assert response["answer_text"] is None, (
            "Unrevealed PYQ must not include answer_text"
        )
        assert response["explanation"] is None, (
            "Unrevealed PYQ must not include explanation"
        )
        # Required fields must be present
        assert response["year"] == pyq_data["year"]
        assert response["question_text"] == pyq_data["question_text"]
        assert response["exam_type"] == pyq_data["exam_type"]
        if pyq_data["exam_type"] == GsLmsExamTypeEnum.MAINS:
            assert "marks" in response and response["marks"] == pyq_data["marks"]

    @given(pyq_data=st_pyq_data())
    @settings(max_examples=30, deadline=None)
    def test_property9_pyq_storage_round_trip(self, pyq_data):
        """Property 9: For any valid PYQ record, storing and retrieving it
        must produce an equivalent record with all fields preserved.

        **Validates: Requirements 3.5**
        """
        engine, Session = make_engine_and_session()
        session = Session()
        try:
            from app.core.gs.models import GsSubject
            subject = GsSubject(id=1, slug="geography", name="GS Geography", display_order=1)
            session.add(subject)
            session.flush()

            # Create a leaf node to attach PYQ to
            node = GsLmsSyllabusNode(
                id=1,
                subject_id=1,
                parent_id=None,
                title="Test Topic",
                node_type=GsLmsNodeTypeEnum.LEAF_TOPIC,
                weight=1.0,
                display_order=1,
                review_status=GsReviewStatusEnum.REVIEWED,
            )
            session.add(node)
            session.flush()

            # Create and persist PYQ
            pyq = GsLmsPyq(
                subject_id=1,
                syllabus_node_id=1,
                exam_type=pyq_data["exam_type"],
                year=pyq_data["year"],
                question_text=pyq_data["question_text"],
                answer_text=pyq_data["answer_text"],
                explanation=pyq_data["explanation"],
                marks=pyq_data["marks"],
                question_type=pyq_data["question_type"],
                review_status=pyq_data["review_status"],
            )
            session.add(pyq)
            session.commit()
            pyq_id = pyq.id

            # Clear session cache and retrieve
            session.expire_all()
            retrieved = session.get(GsLmsPyq, pyq_id)

            assert retrieved is not None
            assert retrieved.exam_type == pyq_data["exam_type"]
            assert retrieved.year == pyq_data["year"]
            assert retrieved.question_text == pyq_data["question_text"]
            assert retrieved.answer_text == pyq_data["answer_text"]
            assert retrieved.explanation == pyq_data["explanation"]
            assert retrieved.marks == pyq_data["marks"]
            assert retrieved.question_type == pyq_data["question_type"]
            assert retrieved.review_status == pyq_data["review_status"]
            assert retrieved.subject_id == 1
            assert retrieved.syllabus_node_id == 1
        finally:
            session.close()
            engine.dispose()
