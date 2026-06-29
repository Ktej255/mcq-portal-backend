"""GS-paper-aware rubric strategy for the shared evaluation core (R7, R8).

Adapts GS Mains grading onto the core :class:`RubricStrategy`:

* **GS-paper awareness** (R8.1) — the rubric reflects the conventions of the
  paper (GS1–GS4) the question belongs to.
* **Word/length discipline** (R8.2) — ``word_limit`` is 150 words for short
  (≤12-mark) answers and 250 for longer ones.
* **Reference grounding** (R7.3/R7.4) — when a model answer is supplied the
  rubric derives the expected content from it + the marking scheme; when absent
  it assesses coverage against the rubric only and fabricates no expected points.

Imports ONLY the shared core — never the Optional domain (Requirement 2).
"""
from __future__ import annotations

from typing import Optional, Sequence

from app.core.evaluation.schema import REQUIRED_EVALUATION_SECTIONS, MarkingScheme


# Per-paper grading conventions (concise; injected into the rubric).
_PAPER_CONVENTIONS = {
    "GS1": (
        "GS Paper I (Indian Heritage & Culture, History, Geography, Society). "
        "Reward analytical treatment of society/geography/history, relevant maps "
        "and diagrams, and balanced, multi-dimensional argument."
    ),
    "GS2": (
        "GS Paper II (Governance, Constitution, Polity, Social Justice, "
        "International Relations). Reward constitutional/institutional accuracy, "
        "current governance examples, and balanced evaluation."
    ),
    "GS3": (
        "GS Paper III (Economy, Environment, Science & Tech, Security, Disaster "
        "Management). Reward data/examples, scheme/policy references, diagrams, "
        "and solution-oriented conclusions."
    ),
    "GS4": (
        "GS Paper IV (Ethics, Integrity & Aptitude). Reward clear ethical "
        "reasoning, definitions, thinkers/quotes where apt, and — for case "
        "studies — stakeholder analysis with a defensible course of action."
    ),
}


class GsPaperRubricStrategy:
    """Rubric strategy for GS Mains descriptive answers."""

    def __init__(self, gs_paper: Optional[str] = None) -> None:
        self.gs_paper = (gs_paper or "").strip().upper() or None

    def required_sections(self) -> Sequence[str]:
        return REQUIRED_EVALUATION_SECTIONS

    def word_limit(self, marking_scheme: MarkingScheme) -> Optional[int]:
        """150 words for ≤12-mark answers, else 250 (R8.2).

        Returns ``None`` for a free-form practice question with no mark
        allotment (length is not normalized when there is no marks context).
        """
        if marking_scheme.max_marks is None:
            return None
        return 150 if marking_scheme.max_marks <= 12 else 250

    def build_rubric(
        self,
        *,
        question: Optional[str],
        reference_answer: Optional[str],
        marking_scheme: MarkingScheme,
    ) -> str:
        parts = [
            "Evaluate this UPSC GS Mains answer as a senior examiner would. "
            "Assess: whether the introduction frames the demand; depth, relevance "
            "and substantiation of the body; a balanced, forward-looking "
            "conclusion; coverage of the expected content; examiner/technical "
            "keywords; exam-appropriate answer language; structure and "
            "presentation; and value addition (diagrams, maps, data, examples). "
            "Give concrete, actionable feedback and an overall assessment."
        ]

        if self.gs_paper and self.gs_paper in _PAPER_CONVENTIONS:
            parts.append(f"PAPER CONVENTIONS — {_PAPER_CONVENTIONS[self.gs_paper]}")

        if marking_scheme.max_marks is not None:
            wl = self.word_limit(marking_scheme)
            parts.append(
                f"MARKS: this answer is out of {marking_scheme.max_marks} marks; "
                f"expected length is about {wl} words. Do not reward padding "
                "beyond the expected length."
            )

        if reference_answer and reference_answer.strip():
            parts.append(
                "MODEL ANSWER (derive the expected content points from this "
                "reference together with the marking scheme; assess the "
                "student's coverage against these points):\n"
                f"{reference_answer.strip()}"
            )
        else:
            parts.append(
                "No model answer is available. Assess coverage against this "
                "rubric only; do NOT fabricate expected points."
            )

        if marking_scheme.expected_dimensions:
            dims = ", ".join(marking_scheme.expected_dimensions)
            parts.append(f"EXPECTED DIMENSIONS TO CHECK: {dims}")

        return "\n\n".join(parts)


__all__ = ["GsPaperRubricStrategy"]
