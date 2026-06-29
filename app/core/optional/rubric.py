"""Optional-platform rubric strategy (R1.2, R19.4).

Adapts the Optional platform onto the shared evaluation core's
:class:`~app.core.evaluation.rubric.RubricStrategy`. The Optional rubric is
assembled from DB-authored topic content in the API layer (the existing
``_build_rubric`` helper) and handed to this strategy as a precomputed string, so
behavior is preserved exactly. ``word_limit`` is ``None`` — Optional answers are
not length-normalized (R1.2).

Imports ONLY the shared core — never GS modules (Requirement 2 / Property 9).
"""
from __future__ import annotations

from typing import Optional, Sequence

from app.core.evaluation.rubric import PrebuiltRubricStrategy
from app.core.evaluation.schema import REQUIRED_EVALUATION_SECTIONS, MarkingScheme


class OptionalRubricStrategy(PrebuiltRubricStrategy):
    """Optional subject rubric strategy (precomputed, not length-normalized)."""

    def __init__(self, rubric: str) -> None:
        super().__init__(rubric, sections=REQUIRED_EVALUATION_SECTIONS)

    def word_limit(self, marking_scheme: MarkingScheme) -> Optional[int]:
        # Optional answers are not length-normalized (preserves current behavior).
        return None


__all__ = ["OptionalRubricStrategy"]
