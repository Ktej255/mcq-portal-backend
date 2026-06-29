"""Content-addressed evaluation report cache (R18.1).

Re-evaluating an identical answer for the same question and rubric should not
cost another inference call. The cache key is a content hash of
(answer + question + rubric + required-sections), so a repeat submission returns
the stored report and issues no model call (design Property 21).

Pure logic + an in-memory default. Subject-neutral.
"""
from __future__ import annotations

import hashlib
from typing import Dict, Optional, Protocol, Sequence

from app.core.evaluation.schema import EvaluationReport


def content_hash(
    *,
    answer_text: str,
    question: Optional[str],
    rubric: str,
    required_sections: Sequence[str],
) -> str:
    """Stable hash of the evaluation inputs that determine the report."""
    hasher = hashlib.sha256()
    hasher.update((answer_text or "").encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((question or "").encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update((rubric or "").encode("utf-8"))
    hasher.update(b"\x00")
    hasher.update("|".join(required_sections).encode("utf-8"))
    return hasher.hexdigest()


class ReportCache(Protocol):
    """A keyed store of completed evaluation reports."""

    def get(self, key: str) -> Optional[EvaluationReport]: ...
    def put(self, key: str, report: EvaluationReport) -> None: ...


class InMemoryReportCache:
    """Process-local report cache (default; swappable for Redis in prod)."""

    def __init__(self) -> None:
        self._store: Dict[str, EvaluationReport] = {}

    def get(self, key: str) -> Optional[EvaluationReport]:
        return self._store.get(key)

    def put(self, key: str, report: EvaluationReport) -> None:
        self._store[key] = report


__all__ = ["content_hash", "ReportCache", "InMemoryReportCache"]
