"""PYQ explorer read endpoint for the Optional Subjects Platform (Task 7.2).

Exposes the student-facing previous-year-question (PYQ) listing that powers the
frontend ``PyqExplorer``. The route is mounted under ``/api/v1/optional`` and is
auth-gated at the package router level.

Route:

* ``GET /{slug}/pyqs``
    Optional query params ``year`` (int), ``paper`` (PAPER_I|PAPER_II),
    ``section`` (SECTION_A|SECTION_B) and ``topic_node_id`` (int — filter to a
    syllabus topic, R6.4), plus ``sort`` (``year_desc`` default | ``year_asc``).
    Returns the subject's **student-visible** PYQs filtered by the provided
    params and year-sorted (R6.1/R6.2/R6.3/R6.5), together with the available
    filter facets (distinct years, papers, sections with data) so the UI can
    build stable controls.

* ``GET /{slug}/pyqs/by-topic``
    Returns the subject's **student-visible** PYQs grouped topic-wise under the
    syllabus tree (R6.4): each group is a syllabus topic node (id + title +
    node's paper/section) with the list of its PYQs. Powers the PyqExplorer
    "By topic" solving view.

Honesty / review gate (design Property 8 / R17.2, R17.3):
A PYQ is student-visible **only** when ``review_status == REVIEWED``. Draft /
UNREVIEWED PYQs (e.g. the task-7.1 seed corpus) and any never-reviewed rows are
gated OUT of this listing exactly like unreviewed content.

Note on importer-owned PYQs: the task-4.1 importer's Section-A PYQs belong to
already-REVIEWED authored deep-notes content. The importer now stamps them
``REVIEWED`` on creation, and ``importer.backfill_pyq_review_status`` repairs any
legacy rows whose ``review_status`` is NULL (pre-dating the column) to REVIEWED,
so they are correctly student-visible here.

Deferred: surfacing official phrasing + trend + hidden topics per syllabus
segment is Task 7.4 and is not implemented here. Answer-solving / evaluation
(the full AnswerWorkspace) is Task 9 — this module only groups PYQs topic-wise
so the UI can offer a "Solve" affordance; no evaluation happens here.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import (
    OptionalSubject,
    Paper,
    Section,
    SyllabusNode,
    Pyq,
    PaperLabelEnum,
    SectionLabelEnum,
    OptionalReviewStatusEnum,
)
from app.api.v1.optional.schemas import (
    PyqOut,
    PyqFacetsOut,
    PyqFiltersEcho,
    PyqListOut,
    PyqTopicGroupOut,
    PyqByTopicOut,
)

router = APIRouter()

# Sort modes for the year-wise listing (R6.1). Newest-first by default.
_SORT_YEAR_DESC = "year_desc"
_SORT_YEAR_ASC = "year_asc"
_VALID_SORTS = {_SORT_YEAR_DESC, _SORT_YEAR_ASC}


def _get_subject_or_404(db: Session, slug: str) -> OptionalSubject:
    subject = (
        db.query(OptionalSubject)
        .filter(OptionalSubject.slug == slug)
        .one_or_none()
    )
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optional subject '{slug}' not found",
        )
    return subject


def _enum_value(v: Any) -> Optional[str]:
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


def _student_visible_base(db: Session, subject_id: int):
    """Base query for the subject's student-visible (REVIEWED) PYQs.

    The single source of truth for the PYQ honesty gate: only ``REVIEWED`` rows
    are ever considered, and soft-deleted rows are excluded.
    """
    q = db.query(Pyq).filter(
        Pyq.subject_id == subject_id,
        Pyq.review_status == OptionalReviewStatusEnum.REVIEWED,
    )
    # Exclude soft-deleted rows when the mixin column is present.
    if hasattr(Pyq, "is_deleted"):
        q = q.filter(Pyq.is_deleted.is_(False))
    return q


def _pyq_out(pyq: Pyq) -> PyqOut:
    return PyqOut(
        id=pyq.id,
        year=pyq.year,
        paper_label=_enum_value(pyq.paper_label),
        section_label=_enum_value(pyq.section_label),
        question_text=pyq.question_text,
        marks=pyq.marks,
        beyond_syllabus=bool(pyq.beyond_syllabus),
        topic_node_id=pyq.topic_node_id,
        review_status=_enum_value(pyq.review_status) or "",
    )


def _facets(db: Session, subject_id: int) -> PyqFacetsOut:
    """Distinct years / papers / sections present in the REVIEWED corpus.

    Independent of the currently applied filters so the UI's controls stay
    stable and only ever offer values that actually return data.
    """
    rows = _student_visible_base(db, subject_id).all()
    years = sorted({r.year for r in rows}, reverse=True)
    papers = sorted({_enum_value(r.paper_label) for r in rows if r.paper_label is not None})
    sections = sorted(
        {_enum_value(r.section_label) for r in rows if r.section_label is not None}
    )
    return PyqFacetsOut(years=years, papers=papers, sections=sections)


@router.get("/{slug}/pyqs")
def list_pyqs(
    slug: str,
    year: Optional[int] = Query(None, description="Filter by exam year (R6.1)."),
    paper: Optional[PaperLabelEnum] = Query(
        None, description="Filter by paper: PAPER_I | PAPER_II (R6.2)."
    ),
    section: Optional[SectionLabelEnum] = Query(
        None, description="Filter by section: SECTION_A | SECTION_B (R6.3)."
    ),
    topic_node_id: Optional[int] = Query(
        None,
        description="Filter by syllabus topic node id (R6.4); restricts the "
        "listing to PYQs filed under that topic.",
    ),
    sort: str = Query(
        _SORT_YEAR_DESC,
        description="Year-wise sort order: year_desc (default) | year_asc (R6.1).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's student-visible PYQs, filtered + year-sorted.

    Applies the review gate (only REVIEWED PYQs), the requested year/paper/
    section filters (R6.2/R6.3/R6.5), and year-wise ordering (R6.1). Includes
    the available filter facets for the UI.
    """
    subject = _get_subject_or_404(db, slug)

    if sort not in _VALID_SORTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort '{sort}'. Expected one of {sorted(_VALID_SORTS)}.",
        )

    q = _student_visible_base(db, subject.id)

    conditions = []
    if year is not None:
        conditions.append(Pyq.year == year)
    if paper is not None:
        conditions.append(Pyq.paper_label == paper)
    if section is not None:
        conditions.append(Pyq.section_label == section)
    if topic_node_id is not None:
        conditions.append(Pyq.topic_node_id == topic_node_id)
    if conditions:
        q = q.filter(and_(*conditions))

    if sort == _SORT_YEAR_ASC:
        q = q.order_by(Pyq.year.asc(), Pyq.id.asc())
    else:
        q = q.order_by(Pyq.year.desc(), Pyq.id.asc())

    rows = q.all()

    data = PyqListOut(
        slug=subject.slug,
        name=subject.name,
        total=len(rows),
        filters=PyqFiltersEcho(
            year=year,
            paper=_enum_value(paper),
            section=_enum_value(section),
            sort=sort,
        ),
        facets=_facets(db, subject.id),
        pyqs=[_pyq_out(p) for p in rows],
    )
    return StandardResponse(
        success=True,
        message="PYQs retrieved",
        data=data,
    )


# ---------------------------------------------------------------------------
# Topic-wise grouping (Task 7.3 — R6.4)
# ---------------------------------------------------------------------------

def _resolve_owning_section(db: Session, node: SyllabusNode) -> Optional[Section]:
    """Walk up parents until a section-attached node is found, return its Section.

    Topic/subtopic nodes hang off a Section; subtopics inherit their section via
    their own ``section_id`` (the importer sets it directly) or via an ancestor.
    Returns ``None`` if no owning section can be resolved.
    """
    current = node
    guard = 0
    while current is not None and current.section_id is None and current.parent_id is not None and guard < 100:
        current = (
            db.query(SyllabusNode)
            .filter(SyllabusNode.id == current.parent_id)
            .one_or_none()
        )
        guard += 1
    if current is None or current.section_id is None:
        return None
    return db.query(Section).filter(Section.id == current.section_id).one_or_none()


@router.get("/{slug}/pyqs/by-topic")
def list_pyqs_by_topic(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's student-visible PYQs grouped topic-wise (R6.4).

    Groups the REVIEWED PYQ corpus under its syllabus topic node so the UI can
    present a topic-wise solving view (pick a topic in the syllabus tree, see
    that topic's PYQs). Each group carries the node id + title + the node's
    paper/section + the list of its PYQs.

    Honesty gate (design Property 8 / R17.3): only ``REVIEWED`` PYQs are ever
    grouped; unreviewed/draft questions never appear. PYQs not mapped to a
    syllabus node are omitted from the grouped view (there is no topic to file
    them under) — they remain visible in the flat ``/pyqs`` listing.
    """
    subject = _get_subject_or_404(db, slug)

    rows = (
        _student_visible_base(db, subject.id)
        .filter(Pyq.topic_node_id.isnot(None))
        .order_by(Pyq.year.desc(), Pyq.id.asc())
        .all()
    )

    # Group PYQs by their topic node, preserving year-desc order within a group.
    grouped: dict[int, list[Pyq]] = {}
    for pyq in rows:
        grouped.setdefault(pyq.topic_node_id, []).append(pyq)

    # Resolve each node's metadata + owning paper/section once.
    node_cache: dict[int, Optional[SyllabusNode]] = {}
    section_cache: dict[int, Optional[Section]] = {}
    paper_cache: dict[int, Optional[Paper]] = {}

    def _node(node_id: int) -> Optional[SyllabusNode]:
        if node_id not in node_cache:
            node_cache[node_id] = (
                db.query(SyllabusNode).filter(SyllabusNode.id == node_id).one_or_none()
            )
        return node_cache[node_id]

    def _section_for(node: SyllabusNode) -> Optional[Section]:
        sec = _resolve_owning_section(db, node)
        if sec is not None:
            section_cache[sec.id] = sec
        return sec

    def _paper_for(section: Section) -> Optional[Paper]:
        if section.paper_id not in paper_cache:
            paper_cache[section.paper_id] = (
                db.query(Paper).filter(Paper.id == section.paper_id).one_or_none()
            )
        return paper_cache[section.paper_id]

    groups: list[PyqTopicGroupOut] = []
    # Sort key carriers so groups appear in syllabus order (paper → section → node).
    sortable: list[tuple[tuple[int, int, int, str], PyqTopicGroupOut]] = []

    for node_id, pyqs in grouped.items():
        node = _node(node_id)
        if node is None:
            # Defensive: a PYQ referencing a missing node — skip (can't file it).
            continue
        # Confirm the node belongs to this subject (isolation + safety).
        section = _section_for(node)
        paper = _paper_for(section) if section is not None else None
        if section is None or paper is None or paper.subject_id != subject.id:
            continue

        group = PyqTopicGroupOut(
            node_id=node.id,
            title=node.title,
            node_type=_enum_value(node.node_type) or "",
            official_phrasing=node.official_phrasing,
            paper_label=_enum_value(paper.label),
            paper_name=paper.name,
            section_label=_enum_value(section.label),
            section_name=section.name,
            pyq_count=len(pyqs),
            pyqs=[_pyq_out(p) for p in pyqs],
        )
        sort_key = (
            paper.display_order,
            section.display_order,
            node.display_order,
            node.title.lower(),
        )
        sortable.append((sort_key, group))

    sortable.sort(key=lambda item: item[0])
    groups = [g for _, g in sortable]

    data = PyqByTopicOut(
        slug=subject.slug,
        name=subject.name,
        total=sum(g.pyq_count for g in groups),
        group_count=len(groups),
        groups=groups,
    )
    return StandardResponse(
        success=True,
        message="PYQs grouped by topic",
        data=data,
    )
