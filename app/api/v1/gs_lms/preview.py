"""Preview endpoint for generated Universe topic JSON files.

No auth required — intended for internal/dev use only.
Serves content from backend/scripts/generated_lectures/topic_1_subtopic_*.json

Routes:
  GET /api/v1/gs-lms/preview/universe-topics — List all Universe topic files
  GET /api/v1/gs-lms/preview/universe-topics/{topic_id} — Get a single topic
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/preview")

LECTURES_DIR = Path(__file__).resolve().parents[4] / "scripts" / "generated_lectures"


@router.get("/universe-topics")
def list_universe_topics() -> dict[str, Any]:
    """Return metadata for all Universe topic files (topic_1_subtopic_*)."""
    topics = []
    for f in sorted(LECTURES_DIR.glob("topic_1_subtopic_*.json")):
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        topics.append({
            "topic_id": data.get("topic_id"),
            "title": data.get("title"),
            "parent_topic": data.get("parent_topic"),
            "display_order": data.get("display_order"),
            "prelims_relevance": data.get("prelims_relevance"),
            "mains_relevance": data.get("mains_relevance"),
            "filename": f.name,
        })
    return {"success": True, "data": topics}


@router.get("/universe-topics/{topic_id}")
def get_universe_topic(topic_id: str) -> dict[str, Any]:
    """Return the full content of a single Universe topic by topic_id (e.g. '1.2')."""
    for f in LECTURES_DIR.glob("topic_1_subtopic_*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("topic_id") == topic_id:
            return {"success": True, "data": data}
    raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
