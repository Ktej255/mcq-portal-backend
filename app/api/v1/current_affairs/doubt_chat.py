"""CA Doubt Chat endpoints — AI-powered freeform Q&A per item.

Students can ask doubts about any CA item's content and get
context-aware AI responses.

Requirements: Enhancement 4 (AI Q&A Doubt Clearing)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.current_affairs.ca_models import CAItem, CADoubtChat

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatMessageIn(BaseModel):
    message: str = Field(..., min_length=5, max_length=2000)


class ChatMessageOut(BaseModel):
    role: str  # "student" or "ai"
    content: str
    timestamp: str


class ChatSessionOut(BaseModel):
    item_id: int
    item_title: str
    messages: List[ChatMessageOut]
    total_messages: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/items/{item_id}/doubt-chat", response_model=ChatSessionOut)
def get_doubt_chat(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the doubt chat session for a CA item (creates if not exists)."""
    item = db.query(CAItem).filter(
        CAItem.id == item_id,
        CAItem.review_status == "PUBLISHED",
        CAItem.is_deleted == False,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    chat = db.query(CADoubtChat).filter(
        CADoubtChat.student_id == current_user.id,
        CADoubtChat.ca_item_id == item_id,
    ).first()

    messages = chat.messages if chat else []

    return ChatSessionOut(
        item_id=item_id,
        item_title=item.title,
        messages=[
            ChatMessageOut(role=m["role"], content=m["content"], timestamp=m.get("timestamp", ""))
            for m in messages
        ],
        total_messages=len(messages),
    )


@router.post("/items/{item_id}/doubt-chat", response_model=ChatSessionOut)
def send_doubt_message(
    item_id: int,
    body: ChatMessageIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a doubt question and get AI response.

    The AI is context-aware — it knows the article content and responds
    with UPSC-relevant explanations.
    """
    item = db.query(CAItem).filter(
        CAItem.id == item_id,
        CAItem.review_status == "PUBLISHED",
        CAItem.is_deleted == False,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    now = datetime.now(timezone.utc)

    # Get or create chat session
    chat = db.query(CADoubtChat).filter(
        CADoubtChat.student_id == current_user.id,
        CADoubtChat.ca_item_id == item_id,
    ).first()

    if not chat:
        chat = CADoubtChat(
            student_id=current_user.id,
            ca_item_id=item_id,
            messages=[],
            total_messages=0,
        )
        db.add(chat)
        db.flush()

    # Add student message
    messages = list(chat.messages or [])
    messages.append({
        "role": "student",
        "content": body.message,
        "timestamp": now.isoformat(),
    })

    # Generate AI response (context-aware based on item content)
    ai_response = _generate_doubt_response(item, body.message, messages)
    messages.append({
        "role": "ai",
        "content": ai_response,
        "timestamp": now.isoformat(),
    })

    # Update chat
    chat.messages = messages
    chat.total_messages = len(messages)
    chat.last_message_at = now
    db.commit()

    return ChatSessionOut(
        item_id=item_id,
        item_title=item.title,
        messages=[
            ChatMessageOut(role=m["role"], content=m["content"], timestamp=m.get("timestamp", ""))
            for m in messages
        ],
        total_messages=len(messages),
    )


# ---------------------------------------------------------------------------
# AI Response Generation (Mock — production would use LLM)
# ---------------------------------------------------------------------------

def _generate_doubt_response(item: CAItem, question: str, history: list) -> str:
    """Generate a context-aware AI response for the student's doubt.

    In production, this would call the LLM with:
    - System prompt: "You are a UPSC preparation AI. Answer doubts about this news item."
    - Context: item.title, item.content_blocks, item.so_what_analysis
    - Conversation history
    - Student's question

    For now, returns a structured mock response.
    """
    # Extract context from item
    subject = item.subject or "current affairs"
    gs_paper = item.gs_paper or "GS"
    title = item.title or "this topic"

    # Mock contextual response
    response_parts = [
        f"Regarding your question about '{title}':",
        "",
        f"This topic is relevant for {gs_paper} and connects to the {subject} domain.",
    ]

    # Add UPSC-specific context if available
    if item.so_what_analysis:
        analysis = item.so_what_analysis
        if isinstance(analysis, dict):
            if analysis.get("upsc_angle"):
                response_parts.append(f"\nUPSC Angle: {analysis['upsc_angle']}")
            if analysis.get("connected_static_topic"):
                response_parts.append(f"\nConnected to: {analysis['connected_static_topic']}")

    response_parts.extend([
        "",
        "For the exam, focus on:",
        "1. The factual accuracy of key terms and entities",
        "2. How this connects to the broader syllabus topic",
        "3. Potential question framing in Prelims (statement-based) and Mains (analytical)",
        "",
        "Would you like me to elaborate on any specific aspect?"
    ])

    return "\n".join(response_parts)
