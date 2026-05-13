from __future__ import annotations

from typing import Any

from app.core.pedagogy.inference_reliability import clamp

CAUSAL_SAFETY_VERSION = "causal-safety.v1"


def causal_confidence(evidence_count: int, pre_points: int, post_points: int, reliability: float, confounder_count: int = 0) -> dict[str, Any]:
    sample = clamp(min(pre_points, post_points) / 5)
    evidence = clamp(evidence_count / 10)
    confidence = clamp(reliability * 0.4 + sample * 0.35 + evidence * 0.25 - min(0.4, confounder_count * 0.1))
    level = "LOW" if confidence < 0.45 else "MODERATE" if confidence < 0.75 else "CAUTIOUS_HIGH"
    return {
        "causal_confidence": round(confidence, 4),
        "level": level,
        "claim_language": safe_claim_language(level),
        "confounding_warnings": confounding_warnings(pre_points, post_points, confounder_count),
        "metric_version": CAUSAL_SAFETY_VERSION,
    }


def safe_claim_language(level: str) -> str:
    if level == "CAUTIOUS_HIGH":
        return "Outcomes improved after this intervention; causal attribution remains provisional."
    if level == "MODERATE":
        return "Outcomes are consistent with possible intervention benefit, with meaningful uncertainty."
    return "Performance changed after this recommendation, but evidence is too limited for causal claims."


def confounding_warnings(pre_points: int, post_points: int, confounder_count: int) -> list[str]:
    warnings = ["Correlation is not causation."]
    if pre_points < 3 or post_points < 3:
        warnings.append("Sparse pre/post data limits causal interpretation.")
    if confounder_count:
        warnings.append("Other changes occurred near the intervention window.")
    warnings.append("Do not state that the recommendation caused improvement.")
    return warnings
