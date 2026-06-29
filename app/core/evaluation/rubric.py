"""Rubric-strategy interface for the shared evaluation core (R1.4).

The two domains (Optional, GS) differ ONLY in how they build a rubric and what
report sections / word limits apply. The :class:`RubricStrategy` Protocol lets
the subject-neutral :class:`~app.core.evaluation.engine.EvaluationEngine` accept
that variation by injection — the engine never imports a domain to decide
behavior (design "Strategy injection, not internal branching" — R1.4).

Subject-neutral: imports only the core schema.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

from app.core.evaluation.schema import REQUIRED_EVALUATION_SECTIONS, MarkingScheme


@runtime_checkable
class RubricStrategy(Protocol):
    """Strategy a domain supplies to shape evaluation (R1.4).

    Implementations are pure: given the question/reference/marking-scheme they
    return the rubric text, the required report sections, and the applicable
    word limit (or ``None`` when length is not normalized).
    """

    def required_sections(self) -> Sequence[str]:
        """The required report sections for this domain."""
        ...

    def build_rubric(
        self,
        *,
        question: Optional[str],
        reference_answer: Optional[str],
        marking_scheme: MarkingScheme,
    ) -> str:
        """Build the rubric text the evaluator grades against."""
        ...

    def word_limit(self, marking_scheme: MarkingScheme) -> Optional[int]:
        """Applicable word limit, or ``None`` when length is not normalized."""
        ...


class PrebuiltRubricStrategy:
    """A trivial strategy that returns a precomputed rubric string.

    Used to preserve existing Optional behavior, where the rubric is assembled
    from DB-authored topic content in the API layer and simply handed to the
    engine. ``word_limit`` is ``None`` (Optional is not length-normalized),
    preserving current behavior (R1.2, R19.4).
    """

    def __init__(
        self,
        rubric: str,
        *,
        sections: Sequence[str] = REQUIRED_EVALUATION_SECTIONS,
    ) -> None:
        self._rubric = rubric
        self._sections = tuple(sections)

    def required_sections(self) -> Sequence[str]:
        return self._sections

    def build_rubric(
        self,
        *,
        question: Optional[str],
        reference_answer: Optional[str],
        marking_scheme: MarkingScheme,
    ) -> str:
        return self._rubric

    def word_limit(self, marking_scheme: MarkingScheme) -> Optional[int]:
        return None


__all__ = ["RubricStrategy", "PrebuiltRubricStrategy"]
