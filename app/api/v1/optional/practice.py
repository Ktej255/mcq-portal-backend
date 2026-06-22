"""Practice board endpoint for the Optional Subjects Platform (Task 8 — 1D).

Exposes the per-student practice status that powers the frontend
``PracticeBoard``. The route is mounted under ``/api/v1/optional`` and is
auth-gated at the package router level.

Route:

* ``GET /{slug}/practice/status``
    Returns the subject's practice **topics organized under the syllabus tree**
    (papers → sections → topics — R7.1) with, for each topic, the requesting
    student's per-topic practice status (R7.3): how many attempts they have
    made, when they last practiced, and a simple derived status
    (NOT_STARTED / IN_PROGRESS / PRACTICED). The frontend uses this to present a
    clear practice call-to-action per topic (R7.2).

Honesty (design Property 8 / R5.4, R17.3): each topic carries an ``authored``
flag that is True only when the topic has a reviewed+authored ContentUnit — the
same honesty gate the Read layer uses (reused from ``content.py``). The UI only
offers practice for authored topics and shows the shared "not yet authored"
state for the rest; this endpoint never fabricates practiceability.

Ownership (design Property 10 / R15.4): the practice status is derived purely
from the **requesting student's own** ``AnswerAttempt`` rows
(filtered by ``student_id == current_user.id`` AND ``subject_id`` AND
``topic_node_id``). A student with no attempts gets the honest zero-state
(count 0, no last-practiced timestamp, NOT_STARTED) — nothing is invented, and
one student never sees another's practice activity.

Note on the practice action itself: the actual answer-writing/evaluation flow
is the ``AnswerWorkspace`` built in **Task 9**. This endpoint only reports
status and lets the UI expose a clean practice seam; no evaluation happens here.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.optional.models import (
    OptionalSubject,
    SyllabusNode,
)
from app.core.optional.student_models import (
    AnswerAttempt,
    AnswerAttemptStatusEnum,
)
# Reuse the single source of truth for the Read-layer honesty gate so a topic
# is "practiceable" under exactly the same condition it is "readable".
from app.api.v1.optional.content import _is_authored, _node_type_value
from app.api.v1.optional.schemas import (
    PracticeTopicStatusOut,
    PracticeSectionOut,
    PracticePaperOut,
    PracticeBoardOut,
    PRACTICE_STATUS_NOT_STARTED,
    PRACTICE_STATUS_IN_PROGRESS,
    PRACTICE_STATUS_PRACTICED,
)

router = APIRouter()


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


class _TopicStat:
    """Accumulator for one topic's per-student attempt status."""

    __slots__ = ("count", "last_at", "has_evaluated")

    def __init__(self) -> None:
        self.count = 0
        self.last_at = None  # datetime | None
        self.has_evaluated = False

    def add(self, attempt: AnswerAttempt) -> None:
        self.count += 1
        created = getattr(attempt, "created_at", None)
        if created is not None and (self.last_at is None or created > self.last_at):
            self.last_at = created
        if attempt.status == AnswerAttemptStatusEnum.EVALUATED:
            self.has_evaluated = True

    @property
    def status(self) -> str:
        if self.count == 0:
            return PRACTICE_STATUS_NOT_STARTED
        if self.has_evaluated:
            return PRACTICE_STATUS_PRACTICED
        return PRACTICE_STATUS_IN_PROGRESS

    @property
    def last_iso(self) -> Optional[str]:
        return self.last_at.isoformat() if self.last_at is not None else None


def _attempt_stats_by_topic(
    db: Session, *, student_id: int, subject_id: int
) -> dict[int, _TopicStat]:
    """Build a topic_node_id -> _TopicStat map for the requesting student only.

    Ownership gate (design Property 10): filters strictly to the student's own
    non-deleted attempts for this subject. Returns an empty map when the student
    has never practiced — the caller renders the honest zero-state from that.
    """
    q = db.query(AnswerAttempt).filter(
        AnswerAttempt.student_id == student_id,
        AnswerAttempt.subject_id == subject_id,
        AnswerAttempt.topic_node_id.isnot(None),
    )
    if hasattr(AnswerAttempt, "is_deleted"):
        q = q.filter(AnswerAttempt.is_deleted.is_(False))

    stats: dict[int, _TopicStat] = {}
    for attempt in q.all():
        stats.setdefault(attempt.topic_node_id, _TopicStat()).add(attempt)
    return stats


@router.get("/{slug}/practice/status")
def get_practice_status(
    slug: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the subject's practice topics + per-student status (R7.1/R7.3).

    Organizes the subject's top-level practice topics under the syllabus tree
    (papers → sections → topics) and overlays, for each topic, the requesting
    student's own practice status: attempt count, last-practiced timestamp and a
    derived NOT_STARTED / IN_PROGRESS / PRACTICED status. Topics carry an
    honesty ``authored`` flag so the UI only offers practice where reviewed
    content exists. Students with no attempts get the honest zero-state.
    """
    subject = _get_subject_or_404(db, slug)

    stats = _attempt_stats_by_topic(
        db, student_id=current_user.id, subject_id=subject.id
    )

    total_topics = 0
    authored_topics = 0
    practiced_topics = 0

    papers_out: list[PracticePaperOut] = []
    papers = sorted(subject.papers, key=lambda p: (p.display_order, p.id))
    for paper in papers:
        sections_out: list[PracticeSectionOut] = []
        sections = sorted(paper.sections, key=lambda s: (s.display_order, s.id))
        for section in sections:
            # Practice topics are the top-level syllabus nodes hanging off a
            # section (TOPIC), mirroring the syllabus tree / analysis surfaces.
            top_nodes = sorted(
                [n for n in section.syllabus_nodes if n.parent_id is None],
                key=lambda n: (n.display_order, n.id),
            )
            topics_out: list[PracticeTopicStatusOut] = []
            for node in top_nodes:
                authored = _is_authored(node)
                stat = stats.get(node.id) or _TopicStat()
                topic_status = stat.status

                total_topics += 1
                if authored:
                    authored_topics += 1
                if topic_status == PRACTICE_STATUS_PRACTICED:
                    practiced_topics += 1

                topics_out.append(
                    PracticeTopicStatusOut(
                        node_id=node.id,
                        title=node.title,
                        node_type=_node_type_value(node),
                        authored=authored,
                        weight=node.weight,
                        display_order=node.display_order,
                        attempt_count=stat.count,
                        last_practiced_at=stat.last_iso,
                        status=topic_status,
                    )
                )
            sections_out.append(
                PracticeSectionOut(
                    section_id=section.id,
                    label=section.label.value
                    if section.label is not None and hasattr(section.label, "value")
                    else (str(section.label) if section.label is not None else None),
                    name=section.name,
                    display_order=section.display_order,
                    topics=topics_out,
                )
            )
        papers_out.append(
            PracticePaperOut(
                paper_id=paper.id,
                label=paper.label.value
                if hasattr(paper.label, "value")
                else str(paper.label),
                name=paper.name,
                display_order=paper.display_order,
                sections=sections_out,
            )
        )

    data = PracticeBoardOut(
        slug=subject.slug,
        name=subject.name,
        total_topics=total_topics,
        authored_topics=authored_topics,
        practiced_topics=practiced_topics,
        papers=papers_out,
    )
    return StandardResponse(
        success=True,
        message="Practice status retrieved",
        data=data,
    )
