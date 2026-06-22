"""AI Discussion Engine for the GS LMS Platform.

Manages the pre-content recall conversation that gates topic access. A session
transitions through INITIATED → IN_PROGRESS → COMPLETED. Completion sets the
gate flag (session status = COMPLETED) that unlocks Topic_Page content.

The engine manages session state and delegates AI response generation to a
pluggable provider. A default mock provider is included for testing and
development.

Key responsibilities:
- Session lifecycle management (INITIATED → IN_PROGRESS → COMPLETED)
- Minimum exchange threshold enforcement (5 turns minimum)
- Gate flag setting on completion to unlock Topic_Page content
- Transcript persistence for gap analysis

Requirements traced: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.gs_lms.student_models import (
    GsLmsDiscussionSession,
    GsLmsDiscussionStatusEnum,
    GsLmsDiscussionTurn,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum number of turns before a session can be completed.
# Pattern: student explanation (1) + AI counter-question (2) + student response (3)
#          + AI counter-question (4) + student response (5) = 5 turns minimum
MINIMUM_TURN_THRESHOLD = 5


# ---------------------------------------------------------------------------
# AI Response Provider Protocol
# ---------------------------------------------------------------------------

class AIResponseProvider(Protocol):
    """Protocol for AI response generation.

    Implementations can range from a simple mock to a full LLM integration.
    The engine delegates response text generation to this provider.
    """

    def generate_response(
        self,
        topic_title: str,
        transcript: list[dict],
        student_message: str,
    ) -> str:
        """Generate an AI response given the conversation context.

        Args:
            topic_title: The title of the topic being discussed.
            transcript: List of prior turns as dicts with 'role' and 'content'.
            student_message: The latest student message to respond to.

        Returns:
            The AI response text.
        """
        ...


class MockAIResponseProvider:
    """Mock AI response provider for testing and development.

    Generates counter-questions that probe depth based on turn position
    in the conversation.
    """

    def generate_response(
        self,
        topic_title: str,
        transcript: list[dict],
        student_message: str,
    ) -> str:
        """Generate a mock counter-question based on conversation position."""
        # Count existing AI turns to determine which counter-question this is
        ai_turn_count = sum(1 for t in transcript if t["role"] == "ai")

        if ai_turn_count == 0:
            return (
                f"Interesting perspective on {topic_title}. "
                "Can you elaborate on the underlying mechanisms or causes "
                "behind what you described?"
            )
        elif ai_turn_count == 1:
            return (
                "Good. Now, can you think of any real-world examples or "
                "applications that illustrate this concept? How would you "
                "explain the practical significance?"
            )
        else:
            return (
                "Thank you for that explanation. You've demonstrated a solid "
                f"foundational understanding of {topic_title}. "
                "Let's proceed to the content."
            )


# ---------------------------------------------------------------------------
# Default provider instance (module-level for easy override/injection)
# ---------------------------------------------------------------------------

_default_provider: AIResponseProvider = MockAIResponseProvider()


def get_default_provider() -> AIResponseProvider:
    """Return the default AI response provider."""
    return _default_provider


def set_default_provider(provider: AIResponseProvider) -> None:
    """Override the default AI response provider (useful for testing)."""
    global _default_provider
    _default_provider = provider


# ---------------------------------------------------------------------------
# Session Lifecycle Functions
# ---------------------------------------------------------------------------

def create_session(
    db: Session,
    student_id: int,
    node_id: int,
) -> GsLmsDiscussionSession:
    """Create a new discussion session for a student on a topic.

    The session starts in INITIATED status and transitions to IN_PROGRESS
    when the first student turn is added.

    Args:
        db: SQLAlchemy database session.
        student_id: The student's user ID.
        node_id: The syllabus node (topic) ID.

    Returns:
        The newly created GsLmsDiscussionSession.
    """
    session = GsLmsDiscussionSession(
        student_id=student_id,
        syllabus_node_id=node_id,
        status=GsLmsDiscussionStatusEnum.INITIATED,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.flush()
    return session


def add_student_turn(
    db: Session,
    session: GsLmsDiscussionSession,
    content: str,
) -> GsLmsDiscussionTurn:
    """Add a student turn to the discussion session.

    If the session is in INITIATED status, it transitions to IN_PROGRESS.

    Args:
        db: SQLAlchemy database session.
        session: The discussion session to add the turn to.
        content: The student's message content.

    Returns:
        The newly created GsLmsDiscussionTurn.

    Raises:
        ValueError: If the session is already COMPLETED or ABANDONED.
    """
    if session.status in (
        GsLmsDiscussionStatusEnum.COMPLETED,
        GsLmsDiscussionStatusEnum.ABANDONED,
    ):
        raise ValueError(
            f"Cannot add turns to a session in {session.status.value} status."
        )

    # Transition INITIATED → IN_PROGRESS on first student message
    if session.status == GsLmsDiscussionStatusEnum.INITIATED:
        session.status = GsLmsDiscussionStatusEnum.IN_PROGRESS

    # Determine turn order (next in sequence)
    turn_order = _get_next_turn_order(db, session.id)

    turn = GsLmsDiscussionTurn(
        session_id=session.id,
        turn_order=turn_order,
        role="student",
        content=content,
        created_at=datetime.now(timezone.utc),
    )
    db.add(turn)
    db.flush()
    return turn


def add_ai_turn(
    db: Session,
    session: GsLmsDiscussionSession,
    content: str,
) -> GsLmsDiscussionTurn:
    """Add an AI turn to the discussion session.

    Args:
        db: SQLAlchemy database session.
        session: The discussion session to add the turn to.
        content: The AI's response content.

    Returns:
        The newly created GsLmsDiscussionTurn.

    Raises:
        ValueError: If the session is already COMPLETED or ABANDONED.
    """
    if session.status in (
        GsLmsDiscussionStatusEnum.COMPLETED,
        GsLmsDiscussionStatusEnum.ABANDONED,
    ):
        raise ValueError(
            f"Cannot add turns to a session in {session.status.value} status."
        )

    turn_order = _get_next_turn_order(db, session.id)

    turn = GsLmsDiscussionTurn(
        session_id=session.id,
        turn_order=turn_order,
        role="ai",
        content=content,
        created_at=datetime.now(timezone.utc),
    )
    db.add(turn)
    db.flush()
    return turn


def generate_ai_response(
    session: GsLmsDiscussionSession,
    student_content: str,
    transcript: list[dict] | None = None,
    provider: AIResponseProvider | None = None,
) -> str:
    """Generate an AI response for the given student message.

    Delegates to the configured AI response provider. Does NOT persist
    the response — use add_ai_turn() to persist after generation.

    Args:
        session: The current discussion session.
        student_content: The student's latest message.
        transcript: Optional list of prior turns as dicts. If None, an empty
            list is used (caller should provide full transcript for context).
        provider: Optional AI provider override. Falls back to default.

    Returns:
        The generated AI response text.
    """
    if provider is None:
        provider = get_default_provider()

    if transcript is None:
        transcript = []

    # Get topic title from the session's syllabus node relationship
    topic_title = _get_topic_title(session)

    return provider.generate_response(
        topic_title=topic_title,
        transcript=transcript,
        student_message=student_content,
    )


def check_threshold(session: GsLmsDiscussionSession, turn_count: int | None = None) -> bool:
    """Check if the minimum exchange threshold has been met.

    The threshold requires at least MINIMUM_TURN_THRESHOLD turns total:
    - Turn 1: student explanation (role="student")
    - Turn 2: AI counter-question 1 (role="ai")
    - Turn 3: student response 1 (role="student")
    - Turn 4: AI counter-question 2 (role="ai")
    - Turn 5: student response 2 (role="student")

    Args:
        session: The discussion session to check.
        turn_count: Optional pre-computed turn count. If None, uses the
            session's turns relationship (requires it to be loaded).

    Returns:
        True if the minimum turn threshold is met.
    """
    if turn_count is not None:
        return turn_count >= MINIMUM_TURN_THRESHOLD

    # Use the session's turns relationship if available
    if hasattr(session, "turns") and session.turns is not None:
        return len(session.turns) >= MINIMUM_TURN_THRESHOLD

    return False


def complete_session(
    db: Session,
    session: GsLmsDiscussionSession,
) -> GsLmsDiscussionSession:
    """Transition session to COMPLETED status (sets the gate flag).

    This is the gate-setting action: once a session is COMPLETED, the
    student can access the Topic_Page content for the associated topic.

    Args:
        db: SQLAlchemy database session.
        session: The session to complete.

    Returns:
        The updated session.

    Raises:
        ValueError: If the session is not in IN_PROGRESS status.
        ValueError: If the minimum threshold has not been met.
    """
    if session.status != GsLmsDiscussionStatusEnum.IN_PROGRESS:
        raise ValueError(
            f"Can only complete a session in IN_PROGRESS status, "
            f"got {session.status.value}."
        )

    # Verify threshold is met by counting turns in the DB
    turn_count = _count_turns(db, session.id)
    if not check_threshold(session, turn_count=turn_count):
        raise ValueError(
            f"Cannot complete session: minimum {MINIMUM_TURN_THRESHOLD} turns "
            f"required, only {turn_count} present."
        )

    session.status = GsLmsDiscussionStatusEnum.COMPLETED
    session.completed_at = datetime.now(timezone.utc)
    db.flush()
    return session


def has_completed_discussion(
    db: Session,
    student_id: int,
    node_id: int,
) -> bool:
    """Check if a student has a COMPLETED discussion session for a topic.

    This is the gate check: returns True if the student can access Topic_Page
    content, False if the AI Discussion is still required.

    Args:
        db: SQLAlchemy database session.
        student_id: The student's user ID.
        node_id: The syllabus node (topic) ID.

    Returns:
        True if a COMPLETED session exists for this student+topic pair.
    """
    exists = (
        db.query(GsLmsDiscussionSession.id)
        .filter(
            GsLmsDiscussionSession.student_id == student_id,
            GsLmsDiscussionSession.syllabus_node_id == node_id,
            GsLmsDiscussionSession.status == GsLmsDiscussionStatusEnum.COMPLETED,
        )
        .first()
    )
    return exists is not None


def get_session_transcript(
    db: Session,
    session_id: int,
) -> list[dict]:
    """Retrieve the full transcript of a discussion session.

    Returns turns ordered by turn_order, formatted as dicts for easy
    consumption by the AI provider or gap analysis engine.

    Args:
        db: SQLAlchemy database session.
        session_id: The discussion session ID.

    Returns:
        List of dicts with 'role', 'content', and 'turn_order' keys.
    """
    turns = (
        db.query(GsLmsDiscussionTurn)
        .filter(GsLmsDiscussionTurn.session_id == session_id)
        .order_by(GsLmsDiscussionTurn.turn_order.asc())
        .all()
    )
    return [
        {
            "role": turn.role,
            "content": turn.content,
            "turn_order": turn.turn_order,
        }
        for turn in turns
    ]


def get_active_session(
    db: Session,
    student_id: int,
    node_id: int,
) -> GsLmsDiscussionSession | None:
    """Get the active (non-completed, non-abandoned) session for a student+topic.

    Returns the most recent INITIATED or IN_PROGRESS session, or None if
    no active session exists.

    Args:
        db: SQLAlchemy database session.
        student_id: The student's user ID.
        node_id: The syllabus node (topic) ID.

    Returns:
        The active session, or None.
    """
    return (
        db.query(GsLmsDiscussionSession)
        .filter(
            GsLmsDiscussionSession.student_id == student_id,
            GsLmsDiscussionSession.syllabus_node_id == node_id,
            GsLmsDiscussionSession.status.in_([
                GsLmsDiscussionStatusEnum.INITIATED,
                GsLmsDiscussionStatusEnum.IN_PROGRESS,
            ]),
        )
        .order_by(GsLmsDiscussionSession.started_at.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_next_turn_order(db: Session, session_id: int) -> int:
    """Get the next turn order number for a session."""
    from sqlalchemy import func

    max_order = (
        db.query(func.max(GsLmsDiscussionTurn.turn_order))
        .filter(GsLmsDiscussionTurn.session_id == session_id)
        .scalar()
    )
    return (max_order or 0) + 1


def _count_turns(db: Session, session_id: int) -> int:
    """Count the total number of turns in a session."""
    from sqlalchemy import func

    return (
        db.query(func.count(GsLmsDiscussionTurn.id))
        .filter(GsLmsDiscussionTurn.session_id == session_id)
        .scalar()
    ) or 0


def _get_topic_title(session: GsLmsDiscussionSession) -> str:
    """Extract topic title from session, with fallback."""
    try:
        if session.syllabus_node and hasattr(session.syllabus_node, "title"):
            return session.syllabus_node.title
    except Exception:
        pass
    return f"Topic {session.syllabus_node_id}"


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    # Constants
    "MINIMUM_TURN_THRESHOLD",
    # Provider protocol + mock
    "AIResponseProvider",
    "MockAIResponseProvider",
    "get_default_provider",
    "set_default_provider",
    # Session lifecycle
    "create_session",
    "add_student_turn",
    "add_ai_turn",
    "generate_ai_response",
    "check_threshold",
    "complete_session",
    # Gate check
    "has_completed_discussion",
    # Transcript + active session
    "get_session_transcript",
    "get_active_session",
]
