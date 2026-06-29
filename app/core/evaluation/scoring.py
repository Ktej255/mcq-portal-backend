"""Marks- and length-normalized scoring helpers (R7.1/R7.2, R8.3/R8.4).

UPSC Mains answers are graded out of a real mark allotment (e.g. 10 or 15), not
a free 0–100, and over-long answers should not score higher merely for padding.
These pure helpers convert a model's 0–100 ``overall_score`` into a
marks-normalized score bounded by the question's maximum marks, and apply a
length adjustment that never *increases* the score once the answer exceeds its
word limit.

Pure functions, no I/O. Subject-neutral.
"""
from __future__ import annotations

from typing import Optional


def count_words(text: Optional[str]) -> int:
    """Whitespace word count of ``text`` (0 for empty/None)."""
    if not text:
        return 0
    return len(text.split())


def length_adjustment_factor(word_count: int, word_limit: Optional[int]) -> float:
    """Return a length factor in (0, 1] that is non-increasing beyond the limit.

    At or under the word limit the factor is 1.0 (no penalty). Beyond the limit
    the factor decreases monotonically with additional words (capped at a 20%
    reduction), so appending words past the limit can never raise the score
    (length-bias control — R8.3, design Property 12).
    """
    if word_limit is None or word_limit <= 0 or word_count <= word_limit:
        return 1.0
    overflow = word_count - word_limit
    penalty = min(0.2, (overflow / word_limit) * 0.2)
    return 1.0 - penalty


def normalize_marks(
    overall_score: Optional[float],
    max_marks: Optional[int],
    *,
    length_factor: float = 1.0,
) -> Optional[float]:
    """Convert a 0–100 ``overall_score`` into marks within ``[0, max_marks]``.

    Returns ``None`` when no ``max_marks`` is known (free-form practice). The
    result is always clamped to ``[0, max_marks]`` regardless of an out-of-range
    raw score (R7.1/R7.2, design Property 8). ``length_factor`` (from
    :func:`length_adjustment_factor`) applies length-bias control without ever
    pushing the score above the bound.
    """
    if max_marks is None or max_marks <= 0:
        return None
    if overall_score is None:
        return None
    raw = (overall_score / 100.0) * float(max_marks) * max(0.0, min(1.0, length_factor))
    return round(max(0.0, min(float(max_marks), raw)), 2)


__all__ = ["count_words", "length_adjustment_factor", "normalize_marks"]
