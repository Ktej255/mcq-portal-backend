"""Recall scoring engine for the Optional platform Recall-LMS
(Task 12.3 — Phase 1H, R14.1 / R14.3 / R14.5 / R14.6 / R14.7).

Pure, deterministic scoring math turning per-concept classifications
(``recalled`` / ``partial`` / ``missed``) into a recall score over a segment's
weighted concept checklist (design "Recall-LMS loop" scoring algorithm):

    recall_score = Σ(weight × match_factor) / Σ(weight)
    match_factor = {recalled: 1.0, partial: 0.5, missed: 0.0}

This module holds the invariants the Property tests pin:

* **Property 3 (bounds + monotonicity, R14.1/R14.3):** ``0 ≤ score ≤ 1``; and
  because the cumulative score takes the *best* factor seen per concept across
  turns (:func:`accumulate_factors`), responding to hints can only raise or hold
  the score, never lower it; re-saying an already-credited concept does not
  raise it.
* **Property 4 (determinism, R14.6):** the math is a pure function of the
  classifications + checklist, so the same inputs always yield the same score
  (the matching itself is low-temperature / deterministic-mock upstream).
* **Property 5 (anti-gaming, R14.7):** verbatim echoes are forced to ``missed``
  upstream (``ConceptClassification`` validator) and contribute factor 0 here,
  so echoing the segment script never raises the score.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Per-classification contribution to the recall score (design scoring step 3).
RECALL_MATCH_FACTOR: Dict[str, float] = {
    "recalled": 1.0,
    "partial": 0.5,
    "missed": 0.0,
}


@dataclass
class RecallOutcome:
    """The scored result over a checklist for a set of classifications.

    ``matched`` lists the credited concepts (factor > 0) with their best status
    and own-words evidence; ``missed`` lists the not-yet-credited concept texts.
    Together they are the explainability payload (R14.5). ``best_factor`` maps
    each checklist concept to its best match factor (the cumulative state).
    """

    score: float
    matched: List[dict] = field(default_factory=list)
    missed: List[str] = field(default_factory=list)
    best_factor: Dict[str, float] = field(default_factory=dict)

    @property
    def percent(self) -> float:
        return round(self.score * 100.0, 4)

    @property
    def is_complete(self) -> bool:
        """All checklist concepts fully recalled (every factor == 1.0)."""
        return bool(self.best_factor) and all(
            f >= 1.0 for f in self.best_factor.values()
        )


def _normalize_concept(text: str) -> str:
    return " ".join(str(text).split()).strip().lower()


def _classification_fields(cl: Any) -> Tuple[str, str, str]:
    """Read (concept, classification, evidence) from an object or a dict.

    Accepts ``ConceptClassification`` instances, plain dicts (``classification``
    or ``status`` key), so the engine works for both fresh model output and
    classifications reconstructed from persisted turn rows.
    """
    if isinstance(cl, Mapping):
        concept = str(cl.get("concept", ""))
        classification = str(cl.get("classification") or cl.get("status") or "missed")
        evidence = str(cl.get("evidence", "") or "")
        return concept, classification, evidence
    concept = str(getattr(cl, "concept", ""))
    classification = str(getattr(cl, "classification", "missed"))
    evidence = str(getattr(cl, "evidence", "") or "")
    return concept, classification, evidence


def _checklist_weights(
    concept_checklist: Sequence[Mapping[str, Any]],
) -> Tuple[List[str], Dict[str, float], Dict[str, float]]:
    """Return (ordered display concepts, norm→weight, norm→display) for a checklist.

    Weights default to equal (1.0 each) when none are authored, so the score is
    always well-defined and bounded (mirrors the coverage equal-weight fallback).
    """
    display_order: List[str] = []
    norm_weight: Dict[str, float] = {}
    norm_display: Dict[str, float] = {}
    for item in concept_checklist:
        raw = str(item.get("concept", "")).strip()
        if not raw:
            continue
        key = _normalize_concept(raw)
        if key not in norm_weight:
            display_order.append(raw)
            norm_display[key] = raw
        weight = item.get("weight")
        try:
            norm_weight[key] = float(weight) if weight is not None else 0.0
        except (TypeError, ValueError):
            norm_weight[key] = 0.0

    total = sum(norm_weight.values())
    if total <= 0 and norm_weight:
        # Equal weighting fallback (no authored weights).
        norm_weight = {k: 1.0 for k in norm_weight}
    return display_order, norm_weight, norm_display


def accumulate_factors(
    concept_checklist: Sequence[Mapping[str, Any]],
    classifications: Iterable[Any],
) -> Dict[str, float]:
    """Best (max) match factor per checklist concept over all classifications.

    Taking the max guarantees monotonicity (Property 3): adding more
    classifications — e.g. from a later hint-response turn — can only raise or
    hold each concept's factor, never lower it.
    """
    _, norm_weight, _ = _checklist_weights(concept_checklist)
    best: Dict[str, float] = {k: 0.0 for k in norm_weight}
    for cl in classifications:
        concept, classification, _ = _classification_fields(cl)
        key = _normalize_concept(concept)
        if key not in best:
            continue
        factor = RECALL_MATCH_FACTOR.get(classification, 0.0)
        if factor > best[key]:
            best[key] = factor
    return best


def score_classifications(
    concept_checklist: Sequence[Mapping[str, Any]],
    classifications: Iterable[Any],
) -> RecallOutcome:
    """Score a checklist against classifications (design scoring algorithm).

    ``classifications`` may be the union of every turn's classifications — the
    best-factor accumulation makes the result the cumulative session score.
    Pure and deterministic (Property 4): same inputs → same output.
    """
    display_order, norm_weight, norm_display = _checklist_weights(concept_checklist)
    materialized = list(classifications)
    best = accumulate_factors(concept_checklist, materialized)

    # Capture best status + evidence per concept for the explainability payload.
    status_by: Dict[str, str] = {k: "missed" for k in norm_weight}
    evidence_by: Dict[str, str] = {k: "" for k in norm_weight}
    for cl in materialized:
        concept, classification, evidence = _classification_fields(cl)
        key = _normalize_concept(concept)
        if key not in norm_weight:
            continue
        factor = RECALL_MATCH_FACTOR.get(classification, 0.0)
        if factor > 0 and factor >= best[key] and factor >= RECALL_MATCH_FACTOR.get(
            status_by[key], 0.0
        ):
            status_by[key] = classification
            evidence_by[key] = evidence

    total_w = sum(norm_weight.values())
    if total_w <= 0:
        score = 0.0
    else:
        score = sum(norm_weight[k] * best[k] for k in norm_weight) / total_w
    score = max(0.0, min(1.0, round(score, 6)))

    matched: List[dict] = []
    missed: List[str] = []
    for raw in display_order:
        key = _normalize_concept(raw)
        if best.get(key, 0.0) > 0:
            matched.append(
                {"concept": raw, "status": status_by[key], "evidence": evidence_by[key]}
            )
        else:
            missed.append(raw)

    return RecallOutcome(score=score, matched=matched, missed=missed, best_factor=best)


def missed_concepts(
    concept_checklist: Sequence[Mapping[str, Any]],
    classifications: Iterable[Any],
) -> List[str]:
    """Checklist concepts not yet fully recalled (factor < 1.0).

    Used to target adaptive Socratic hints at concepts still owed (R14.2).
    """
    display_order, _, _ = _checklist_weights(concept_checklist)
    best = accumulate_factors(concept_checklist, classifications)
    return [c for c in display_order if best.get(_normalize_concept(c), 0.0) < 1.0]


__all__ = [
    "RECALL_MATCH_FACTOR",
    "RecallOutcome",
    "accumulate_factors",
    "score_classifications",
    "missed_concepts",
]
