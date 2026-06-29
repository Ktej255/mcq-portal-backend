"""Recall Scoring Engine — pure functions for comparing a speech transcript
against extracted key concepts from a content section.

All functions in this module are pure (no I/O, no database access, no side
effects) to enable property-based testing.

Requirements: 5.3, 5.4, 5.5
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConceptMatch:
    """Result of matching a single concept against the transcript."""
    concept: str
    matched: bool
    matched_fragment: str | None = None


@dataclass(frozen=True)
class RecallResult:
    """Complete result of recall scoring."""
    recall_score: float          # 0.0–1.0 (fraction of concepts matched)
    confidence_score: float      # 0.0–1.0 (weighted clarity/completeness)
    concepts: List[ConceptMatch] = field(default_factory=list)
    total_concepts: int = 0
    matched_count: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum Jaccard similarity to consider a concept matched
MATCH_THRESHOLD = 0.7

# Weights for confidence score computation
BREADTH_WEIGHT = 0.4
DEPTH_WEIGHT = 0.3
ARTICULATION_WEIGHT = 0.3

# Minimum words in a sentence for it to count as articulate
MIN_ARTICULATE_SENTENCE_WORDS = 5


# ---------------------------------------------------------------------------
# Key Concept Extraction
# ---------------------------------------------------------------------------

def extract_key_concepts(section_blocks: list[dict]) -> list[str]:
    """Extract key concepts from content section blocks.

    Parses highlighted keywords (**bold**), diagram titles, and callout box
    content to build the concept checklist.

    Args:
        section_blocks: List of content block dicts from GsLmsContentSection.blocks

    Returns:
        Deduplicated list of concept phrases (lowercased).
    """
    concepts: set[str] = set()

    if not section_blocks:
        return []

    for block in section_blocks:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")
        text = block.get("text", "") or block.get("content", "") or ""

        # Extract bold keywords (**keyword**)
        bold_matches = re.findall(r"\*\*(.+?)\*\*", text)
        for match in bold_matches:
            cleaned = match.strip().lower()
            if cleaned and len(cleaned) > 2:
                concepts.add(cleaned)

        # Extract diagram titles
        if block_type == "diagram":
            title = block.get("title", "")
            if title:
                concepts.add(title.strip().lower())

        # Extract callout box content
        if block_type == "callout":
            callout_text = block.get("content", "") or block.get("text", "")
            # Extract key phrases from callout (words between ** markers)
            callout_bold = re.findall(r"\*\*(.+?)\*\*", callout_text)
            for match in callout_bold:
                cleaned = match.strip().lower()
                if cleaned and len(cleaned) > 2:
                    concepts.add(cleaned)

    return sorted(concepts)


# ---------------------------------------------------------------------------
# Recall Scoring (Pure Function)
# ---------------------------------------------------------------------------

def score_recall(transcript: str, key_concepts: list[str]) -> RecallResult:
    """Score a recall transcript against key concepts.

    Uses fuzzy string matching (Jaccard similarity) to determine concept
    matches. Pure function — no I/O or side effects.

    Args:
        transcript: The student's spoken recall text (transcribed).
        key_concepts: List of key concept strings from the content section.

    Returns:
        RecallResult with recall_score, confidence_score, and per-concept matches.
    """
    if not key_concepts:
        return RecallResult(
            recall_score=0.0,
            confidence_score=0.0,
            concepts=[],
            total_concepts=0,
            matched_count=0,
        )

    if not transcript or not transcript.strip():
        return RecallResult(
            recall_score=0.0,
            confidence_score=0.0,
            concepts=[ConceptMatch(concept=c, matched=False) for c in key_concepts],
            total_concepts=len(key_concepts),
            matched_count=0,
        )

    # Normalize transcript
    transcript_lower = transcript.lower()
    sentences = _split_sentences(transcript_lower)
    transcript_tokens = set(_tokenize(transcript_lower))

    # Match each concept
    concept_matches: list[ConceptMatch] = []
    matched_count = 0

    for concept in key_concepts:
        concept_lower = concept.lower().strip()
        concept_tokens = set(_tokenize(concept_lower))

        matched = False
        matched_fragment = None

        # Strategy 1: Direct substring match
        if concept_lower in transcript_lower:
            matched = True
            matched_fragment = _find_fragment(transcript_lower, concept_lower)
        else:
            # Strategy 2: Jaccard similarity per sentence
            for sentence in sentences:
                sentence_tokens = set(_tokenize(sentence))
                similarity = _jaccard_similarity(concept_tokens, sentence_tokens)
                if similarity >= MATCH_THRESHOLD:
                    matched = True
                    matched_fragment = sentence.strip()
                    break

            # Strategy 3: Token overlap (for multi-word concepts)
            if not matched and len(concept_tokens) > 1:
                overlap = concept_tokens & transcript_tokens
                if len(overlap) / len(concept_tokens) >= MATCH_THRESHOLD:
                    matched = True
                    matched_fragment = " ".join(sorted(overlap))

        if matched:
            matched_count += 1

        concept_matches.append(ConceptMatch(
            concept=concept,
            matched=matched,
            matched_fragment=matched_fragment,
        ))

    # Compute scores
    total_concepts = len(key_concepts)
    recall_score = matched_count / total_concepts if total_concepts > 0 else 0.0
    confidence_score = compute_confidence_score(
        transcript, concept_matches, total_concepts
    )

    return RecallResult(
        recall_score=_clamp(recall_score),
        confidence_score=_clamp(confidence_score),
        concepts=concept_matches,
        total_concepts=total_concepts,
        matched_count=matched_count,
    )


# ---------------------------------------------------------------------------
# Confidence Score Computation
# ---------------------------------------------------------------------------

def compute_confidence_score(
    transcript: str,
    concept_matches: list[ConceptMatch],
    total_concepts: int,
) -> float:
    """Compute speech confidence from coverage depth and articulation.

    Factors (weighted):
    - Coverage breadth (0.4): fraction of concepts mentioned
    - Coverage depth (0.3): average detail per matched concept
    - Articulation (0.3): sentence completeness and coherence

    Returns float 0.0–1.0.
    """
    if total_concepts == 0:
        return 0.0

    matched = [cm for cm in concept_matches if cm.matched]
    matched_count = len(matched)

    # 1. Coverage breadth
    breadth = matched_count / total_concepts

    # 2. Coverage depth: average fragment length relative to concept length
    depth_scores: list[float] = []
    for cm in matched:
        if cm.matched_fragment:
            fragment_words = len(cm.matched_fragment.split())
            concept_words = max(len(cm.concept.split()), 1)
            # More words in fragment = more depth, capped at 1.0
            depth_scores.append(min(1.0, fragment_words / max(concept_words * 3, 1)))
        else:
            depth_scores.append(0.5)  # matched but no specific fragment

    depth = sum(depth_scores) / len(depth_scores) if depth_scores else 0.0

    # 3. Articulation: fraction of sentences with >= 5 words
    sentences = _split_sentences(transcript)
    if sentences:
        articulate_count = sum(
            1 for s in sentences
            if len(s.split()) >= MIN_ARTICULATE_SENTENCE_WORDS
        )
        articulation = articulate_count / len(sentences)
    else:
        articulation = 0.0

    # Weighted combination
    score = (
        BREADTH_WEIGHT * breadth
        + DEPTH_WEIGHT * depth
        + ARTICULATION_WEIGHT * articulation
    )

    return _clamp(score)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Split text into lowercase word tokens, stripping punctuation."""
    return re.findall(r'\b[a-z0-9]+\b', text.lower())


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Split on period, question mark, exclamation, or newline
    sentences = re.split(r'[.!?\n]+', text)
    return [s.strip() for s in sentences if s.strip()]


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _find_fragment(text: str, concept: str) -> str:
    """Find the surrounding context of a concept in text."""
    idx = text.find(concept)
    if idx == -1:
        return concept
    # Return a window around the match
    start = max(0, idx - 30)
    end = min(len(text), idx + len(concept) + 30)
    return text[start:end].strip()


def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp a value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "ConceptMatch",
    "RecallResult",
    "extract_key_concepts",
    "score_recall",
    "compute_confidence_score",
    "MATCH_THRESHOLD",
]
