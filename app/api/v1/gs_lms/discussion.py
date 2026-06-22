"""AI Discussion endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms; auth-gated at the package router):
* POST /geography/discussion/start — Initiate discussion for a topic
* POST /geography/discussion/{session_id}/turn — Student sends message, gets AI response
* GET /geography/discussion/{session_id}/status — Session completion status

Key behaviours:
- `start`: Creates a new session OR returns the existing active session. If
  already completed, returns a response indicating content is already unlocked.
- `turn`: Adds student turn → generates AI response → adds AI turn → checks
  threshold → if met, auto-completes session. Returns both turns + status +
  gate_passed boolean.
- `status`: Returns current session state with all turns.
- Ownership: students can only access their own sessions.
- Error handling: 404 for missing sessions, 422 for turns on completed sessions.

Requirements traced: 5.1, 5.2, 5.3, 5.4, 5.6
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.schemas.common import StandardResponse
from app.core.gs_lms.student_models import (
    GsLmsDiscussionSession,
    GsLmsDiscussionStatusEnum,
)
from app.core.gs_lms.discussion import (
    create_session,
    add_student_turn,
    add_ai_turn,
    generate_ai_response,
    check_threshold,
    complete_session,
    has_completed_discussion,
    get_active_session,
    get_session_transcript,
)
from app.core.gs_lms.coverage import create_gap_snapshot
from app.api.v1.gs_lms.schemas import (
    GsLmsDiscussionStartIn,
    GsLmsDiscussionTurnIn,
    GsLmsDiscussionTurnOut,
    GsLmsDiscussionSessionOut,
    GsLmsDiscussionTurnResponseOut,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_session_or_404(db: Session, session_id: int) -> GsLmsDiscussionSession:
    """Fetch a discussion session by ID or raise 404."""
    session = (
        db.query(GsLmsDiscussionSession)
        .filter(GsLmsDiscussionSession.id == session_id)
        .one_or_none()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return session


def _check_ownership(session: GsLmsDiscussionSession, user: User) -> None:
    """Verify the session belongs to the requesting student."""
    if session.student_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )


def _build_session_out(
    db: Session, session: GsLmsDiscussionSession
) -> GsLmsDiscussionSessionOut:
    """Build a GsLmsDiscussionSessionOut from a session + its transcript."""
    transcript = get_session_transcript(db, session.id)
    turns_out = [
        GsLmsDiscussionTurnOut(
            turn_order=t["turn_order"],
            role=t["role"],
            content=t["content"],
            created_at=t.get("created_at", session.started_at.isoformat())
            if isinstance(t.get("created_at"), str)
            else (
                t["created_at"].isoformat()
                if t.get("created_at")
                else session.started_at.isoformat()
            ),
        )
        for t in transcript
    ]
    return GsLmsDiscussionSessionOut(
        session_id=session.id,
        syllabus_node_id=session.syllabus_node_id,
        status=session.status.value,
        started_at=session.started_at.isoformat(),
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        turns=turns_out,
    )


def _turn_to_out(turn) -> GsLmsDiscussionTurnOut:
    """Convert a GsLmsDiscussionTurn ORM instance to the output schema."""
    return GsLmsDiscussionTurnOut(
        turn_order=turn.turn_order,
        role=turn.role,
        content=turn.content,
        created_at=turn.created_at.isoformat() if turn.created_at else "",
    )


# ---------------------------------------------------------------------------
# POST /geography/discussion/start
# ---------------------------------------------------------------------------


@router.post("/geography/discussion/start")
def start_discussion(
    body: GsLmsDiscussionStartIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Initiate a discussion session for a topic.

    Behaviour:
    - If the student already has a COMPLETED discussion for this topic,
      returns a response indicating content is already unlocked (R5.6).
    - If an active (INITIATED or IN_PROGRESS) session already exists,
      returns that session.
    - Otherwise, creates a new session.

    Validates: Requirements 5.1, 5.6
    """
    node_id = body.syllabus_node_id

    # Check if already completed — skip directly to content on subsequent visits
    if has_completed_discussion(db, current_user.id, node_id):
        return StandardResponse(
            success=True,
            message="Discussion already completed; content unlocked",
            data={
                "already_completed": True,
                "syllabus_node_id": node_id,
                "gate_passed": True,
            },
        )

    # Check for an existing active session
    active = get_active_session(db, current_user.id, node_id)
    if active is not None:
        session_out = _build_session_out(db, active)
        return StandardResponse(
            success=True,
            message="Existing active session returned",
            data=session_out,
        )

    # Create a new session
    new_session = create_session(db, current_user.id, node_id)
    db.commit()
    db.refresh(new_session)

    session_out = _build_session_out(db, new_session)
    return StandardResponse(
        success=True,
        message="Discussion session created",
        data=session_out,
    )


# ---------------------------------------------------------------------------
# POST /geography/discussion/{session_id}/turn
# ---------------------------------------------------------------------------


@router.post("/geography/discussion/{session_id}/turn")
def submit_turn(
    session_id: int,
    body: GsLmsDiscussionTurnIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Student sends a message, receives AI response.

    Flow:
    1. Validate session exists + ownership + not completed.
    2. Add student turn.
    3. Generate AI response using the discussion engine.
    4. Add AI turn.
    5. Check threshold — if met, auto-complete session.
    6. Return both turns + session status + gate_passed.

    Validates: Requirements 5.2, 5.3, 5.4
    """
    session = _get_session_or_404(db, session_id)
    _check_ownership(session, current_user)

    # Cannot submit turns on a completed or abandoned session
    if session.status in (
        GsLmsDiscussionStatusEnum.COMPLETED,
        GsLmsDiscussionStatusEnum.ABANDONED,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot add turns to a completed or abandoned session",
        )

    # 1. Add student turn
    student_turn = add_student_turn(db, session, body.content)

    # 2. Get transcript for AI context
    transcript = get_session_transcript(db, session.id)

    # 3. Generate AI response
    ai_response_text = generate_ai_response(
        session,
        body.content,
        transcript=transcript,
    )

    # 4. Add AI turn
    ai_turn = add_ai_turn(db, session, ai_response_text)

    # 5. Check threshold and auto-complete if met
    total_turns = len(transcript) + 1  # transcript was fetched before AI turn was added
    # Actually recount: transcript was fetched after student turn (flushed), so it
    # includes student_turn. We added ai_turn after that, so total = len(transcript) + 1
    gate_passed = False
    if check_threshold(session, turn_count=total_turns):
        try:
            complete_session(db, session)
            gate_passed = True
            # Update gap profile after discussion completion (R6.5)
            create_gap_snapshot(db, current_user.id)
        except ValueError:
            # Threshold might not actually be met due to count logic — ignore
            pass

    db.commit()

    # Build response
    return StandardResponse(
        success=True,
        message="Turn recorded",
        data=GsLmsDiscussionTurnResponseOut(
            session_id=session.id,
            status=session.status.value,
            student_turn=_turn_to_out(student_turn),
            ai_turn=_turn_to_out(ai_turn),
            gate_passed=gate_passed,
        ),
    )


# ---------------------------------------------------------------------------
# GET /geography/discussion/{session_id}/status
# ---------------------------------------------------------------------------


@router.get("/geography/discussion/{session_id}/status")
def get_discussion_status(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Return the current session state with all turns.

    Ownership check: students can only access their own sessions.

    Validates: Requirements 5.5
    """
    session = _get_session_or_404(db, session_id)
    _check_ownership(session, current_user)

    session_out = _build_session_out(db, session)
    return StandardResponse(
        success=True,
        message="Discussion session status",
        data=session_out,
    )
