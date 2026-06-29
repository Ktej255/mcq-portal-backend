"""AI Discussion Engine for the GS LMS Platform.

Manages the pre-content recall conversation that gates topic access. A session
transitions through INITIATED → IN_PROGRESS → COMPLETED. Completion sets the
gate flag (session status = COMPLETED) that unlocks Topic_Page content.

The engine manages session state and delegates AI response generation to a
pluggable provider. A default mock provider is included for testing and
development.

Key responsibilities:
- Session lifecycle management (INITIATED → IN_PROGRESS → COMPLETED)
- Concept-level scoring against topic concept checklists (primary gate mechanism)
- Minimum exchange threshold enforcement (5 turns minimum) as fallback
- Gate flag setting on completion to unlock Topic_Page content
- Transcript persistence for gap analysis

Requirements traced: 2.1, 2.3, 2.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
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

# Minimum turns required when using concept-based gating (less than turn-based
# fallback, since concept coverage is the primary signal).
CONCEPT_GATE_MINIMUM_TURNS = 3

# Concept match percentage required to pass the gate (80%).
CONCEPT_GATE_THRESHOLD = 80.0


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
        concepts_missed: list[str] | None = None,
        match_percentage: float | None = None,
    ) -> str:
        """Generate an AI response given the conversation context.

        Args:
            topic_title: The title of the topic being discussed.
            transcript: List of prior turns as dicts with 'role' and 'content'.
            student_message: The latest student message to respond to.
            concepts_missed: Optional list of concepts not yet covered by the student.
                When provided, the AI should generate Socratic questions targeting these gaps.
            match_percentage: Optional current concept match percentage (0.0-1.0).

        Returns:
            The AI response text.
        """
        ...


class MockAIResponseProvider:
    """Mock AI response provider for testing and development.

    Generates counter-questions that probe depth based on turn position
    in the conversation. Accepts but ignores concepts_missed and match_percentage
    parameters (graceful handling per task 4.4).
    """

    def generate_response(
        self,
        topic_title: str,
        transcript: list[dict],
        student_message: str,
        concepts_missed: list[str] | None = None,
        match_percentage: float | None = None,
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
# Concept Extraction & Matching (Local, deterministic — no LLM calls)
# ---------------------------------------------------------------------------

def extract_matched_concepts(
    student_messages: list[str],
    concept_checklist: list[str],
) -> tuple[list[str], list[str]]:
    """Match student messages against a topic's concept checklist.

    Uses case-insensitive substring matching. A concept is considered
    "matched" if any student message contains the concept string (or a
    close variant — trailing 's' is stripped for fuzzy plural matching).

    This is a LOCAL implementation — does NOT call Gemini. Keeps matching
    fast and deterministic for gate evaluation.

    Args:
        student_messages: All student messages in the session so far.
        concept_checklist: The topic's list of key concepts to check.

    Returns:
        Tuple of (matched_concepts, missed_concepts).

    Requirements traced: 2.1, 2.3
    """
    if not concept_checklist:
        return [], []

    # Combine all student text into one lowercased corpus for efficient matching
    combined_text = " ".join(msg.lower() for msg in student_messages)

    matched: list[str] = []
    missed: list[str] = []

    for concept in concept_checklist:
        concept_lower = concept.lower().strip()
        if not concept_lower:
            continue

        # Check exact substring match
        if concept_lower in combined_text:
            matched.append(concept)
            continue

        # Fuzzy variant: strip trailing 's' for plural matching
        # e.g. "plate tectonics" matches "plate tectonic" and vice versa
        concept_stripped = concept_lower.rstrip("s")
        # Also check if student used the plural when concept is singular
        concept_plural = concept_lower + "s"

        if concept_stripped in combined_text or concept_plural in combined_text:
            matched.append(concept)
        else:
            missed.append(concept)

    return matched, missed


def compute_concept_match_percentage(
    matched: list[str],
    total_checklist: list[str],
) -> float:
    """Compute the percentage of concepts matched from the checklist.

    Args:
        matched: List of matched concept strings.
        total_checklist: The full concept checklist for the topic.

    Returns:
        Match percentage (0.0–100.0). Returns 0.0 if checklist is empty.

    Requirements traced: 2.1, 2.3
    """
    if not total_checklist:
        return 0.0
    return len(matched) / len(total_checklist) * 100.0


def check_concept_gate(
    student_messages: list[str],
    concept_checklist: list[str],
    turn_count: int,
) -> tuple[bool, list[str], list[str], float]:
    """Check if the concept-based gate should open.

    The gate passes when:
    - match_percentage >= CONCEPT_GATE_THRESHOLD (80%)
    - AND at least CONCEPT_GATE_MINIMUM_TURNS (3) turns have occurred

    Args:
        student_messages: All student messages in the session so far.
        concept_checklist: The topic's concept checklist.
        turn_count: Total number of turns in the session.

    Returns:
        Tuple of (gate_passed, matched_concepts, missed_concepts, match_percentage).

    Requirements traced: 2.1, 2.3, 2.4
    """
    matched, missed = extract_matched_concepts(student_messages, concept_checklist)
    percentage = compute_concept_match_percentage(matched, concept_checklist)

    gate_passed = (
        percentage >= CONCEPT_GATE_THRESHOLD
        and turn_count >= CONCEPT_GATE_MINIMUM_TURNS
    )

    return gate_passed, matched, missed, percentage


def update_session_concepts(
    session: "GsLmsDiscussionSession",
    matched: list[str],
    missed: list[str],
    match_percentage: float,
) -> None:
    """Update the session's concept tracking columns.

    Args:
        session: The discussion session to update.
        matched: List of matched concept strings.
        missed: List of missed concept strings.
        match_percentage: The computed match percentage.

    Requirements traced: 2.5
    """
    session.concepts_matched = matched
    session.concepts_missed = missed
    session.match_percentage = match_percentage


def get_student_messages_from_transcript(transcript: list[dict]) -> list[str]:
    """Extract all student message contents from a transcript.

    Args:
        transcript: List of turn dicts with 'role' and 'content' keys.

    Returns:
        List of student message content strings.
    """
    return [
        t["content"]
        for t in transcript
        if t.get("role") == "student"
    ]


def get_topic_concept_checklist(session: "GsLmsDiscussionSession") -> list[str] | None:
    """Get the concept checklist from the session's syllabus node.

    Returns None if:
    - The syllabus_node relationship is not loaded
    - The node has no concept_checklist
    - The concept_checklist is empty

    Args:
        session: The discussion session.

    Returns:
        The concept checklist list, or None if unavailable/empty.
    """
    try:
        if (
            session.syllabus_node
            and hasattr(session.syllabus_node, "concept_checklist")
            and session.syllabus_node.concept_checklist
        ):
            checklist = session.syllabus_node.concept_checklist
            if isinstance(checklist, list) and len(checklist) > 0:
                return checklist
    except Exception:
        pass
    return None


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
    concepts_missed: list[str] | None = None,
    match_percentage: float | None = None,
) -> str:
    """Generate an AI response for the given student message.

    Delegates to the configured AI response provider. Does NOT persist
    the response — use add_ai_turn() to persist after generation.

    When concepts_missed is provided, the AI provider will generate Socratic
    follow-up questions specifically targeting those missed concepts (R2.6).

    Args:
        session: The current discussion session.
        student_content: The student's latest message.
        transcript: Optional list of prior turns as dicts. If None, an empty
            list is used (caller should provide full transcript for context).
        provider: Optional AI provider override. Falls back to default.
        concepts_missed: Optional list of concepts the student hasn't covered yet.
            When provided, the AI targets these gaps with Socratic questions.
        match_percentage: Optional current concept match percentage (0.0-1.0).

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
        concepts_missed=concepts_missed,
        match_percentage=match_percentage,
    )


def check_threshold(session: GsLmsDiscussionSession, turn_count: int | None = None) -> bool:
    """Check if the discussion gate should open.

    Two modes of operation:
    1. **Concept-based gate** (when topic has a concept_checklist):
       Gate passes when match_percentage >= 80% AND at least 3 turns occurred.
       This is evaluated externally via check_concept_gate() and stored on
       the session. This function checks the stored match_percentage.
    2. **Turn-count fallback** (when no concept_checklist):
       Gate passes after MINIMUM_TURN_THRESHOLD (5) turns.

    Args:
        session: The discussion session to check.
        turn_count: Optional pre-computed turn count. If None, uses the
            session's turns relationship (requires it to be loaded).

    Returns:
        True if the gate condition is met.

    Requirements traced: 2.3, 2.4
    """
    # Determine effective turn count
    effective_turn_count: int
    if turn_count is not None:
        effective_turn_count = turn_count
    elif hasattr(session, "turns") and session.turns is not None:
        effective_turn_count = len(session.turns)
    else:
        effective_turn_count = 0

    # Check if concept-based gating is active (match_percentage has been computed)
    match_pct = getattr(session, "match_percentage", None)
    if match_pct is not None:
        return (
            match_pct >= CONCEPT_GATE_THRESHOLD
            and effective_turn_count >= CONCEPT_GATE_MINIMUM_TURNS
        )

    # Fallback: turn-count-based threshold
    return effective_turn_count >= MINIMUM_TURN_THRESHOLD


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
        if session.match_percentage is not None:
            raise ValueError(
                f"Cannot complete session: concept match {session.match_percentage:.1f}% "
                f"< {CONCEPT_GATE_THRESHOLD}% required (or fewer than "
                f"{CONCEPT_GATE_MINIMUM_TURNS} turns)."
            )
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
# Turn Processing with Concept Matching
# ---------------------------------------------------------------------------

def process_turn_concepts(
    db: Session,
    session: GsLmsDiscussionSession,
    transcript: list[dict],
) -> tuple[bool, list[str] | None, float | None]:
    """Process concept matching after a student turn.

    After each student turn, this function:
    1. Checks if the topic has a concept_checklist
    2. If yes, extracts all student messages and runs concept matching
    3. Updates session concept tracking columns (concepts_matched, concepts_missed, match_percentage)
    4. Returns whether concept gating is active, missed concepts, and match percentage

    If no concept_checklist exists, returns (False, None, None) indicating the
    caller should use the turn-count fallback logic.

    Args:
        db: SQLAlchemy database session.
        session: The discussion session.
        transcript: The full transcript including the latest student turn.

    Returns:
        Tuple of (concept_gate_active, missed_concepts, match_percentage):
        - concept_gate_active: True if concept gate was evaluated (checklist exists)
        - missed_concepts: List of missed concepts (for AI targeting), or None
          if no checklist exists
        - match_percentage: Current match percentage, or None if no checklist

    Requirements traced: 2.1, 2.3, 2.4, 2.5
    """
    concept_checklist = get_topic_concept_checklist(session)

    if concept_checklist is None:
        # No concept checklist — caller uses turn-count fallback
        return False, None, None

    # Extract student messages from transcript
    student_messages = get_student_messages_from_transcript(transcript)

    # Compute concept matching
    turn_count = len(transcript)
    _gate_passed, matched, missed, percentage = check_concept_gate(
        student_messages, concept_checklist, turn_count
    )

    # Update session columns
    update_session_concepts(session, matched, missed, percentage)
    db.flush()

    return True, missed, percentage


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
    "CONCEPT_GATE_MINIMUM_TURNS",
    "CONCEPT_GATE_THRESHOLD",
    # Provider protocol + mock
    "AIResponseProvider",
    "MockAIResponseProvider",
    "get_default_provider",
    "set_default_provider",
    # Concept extraction & matching
    "extract_matched_concepts",
    "compute_concept_match_percentage",
    "check_concept_gate",
    "update_session_concepts",
    "get_student_messages_from_transcript",
    "get_topic_concept_checklist",
    "process_turn_concepts",
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
