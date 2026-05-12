from __future__ import annotations

from typing import Any

from app.services.content_intelligence_engine import CONTENT_INTELLIGENCE_VERSION, extract_content_concepts, map_resource_to_graph
from app.services.inference_reliability import clamp

QUALITY_VERSION = "explanation-quality.v1"


def explanation_quality(resource: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    text = resource.get("text", "")
    mapped = map_resource_to_graph(resource, graph)
    extraction = mapped["extraction"]
    density = extraction["conceptual_density"]
    concept_count = len(extraction["concepts"])
    definition_count = len(extraction["definitions"])
    reasoning_count = len(extraction["reasoning_chains"])
    prereq_chains = mapped["prerequisite_regions"]
    prereq_covered = len([item for item in prereq_chains if item["prerequisite_chain"]])

    clarity = clamp((definition_count * 0.22 + reasoning_count * 0.18 + min(len(text), 1200) / 1200 * 0.20 + 0.25) - (0.25 if density["band"] == "HIGH_OVERLOAD_RISK" else 0))
    dependency_coverage = clamp(prereq_covered / max(1, concept_count))
    overload = clamp(density["score"] / 12)
    remediation = clamp(clarity * 0.45 + dependency_coverage * 0.30 + (1 - overload) * 0.25)

    level = "ADVANCED" if overload > 0.7 or len(extraction["formulas"]) >= 3 else "INTERMEDIATE" if concept_count >= 2 or reasoning_count else "BEGINNER"

    return {
        "resource_id": resource.get("id"),
        "conceptual_clarity": round(clarity, 4),
        "dependency_coverage": round(dependency_coverage, 4),
        "cognitive_overload_risk": round(overload, 4),
        "explanation_density": density,
        "remediation_suitability": round(remediation, 4),
        "learner_level": level,
        "quality_band": "STRONG" if remediation >= 0.7 else "USABLE" if remediation >= 0.45 else "NEEDS_REVIEW",
        "scientific_safety_note": "Explanation quality is a content signal only; learning impact requires outcome evidence.",
        "metric_version": QUALITY_VERSION,
    }


def rank_explanations(resources: list[dict[str, Any]], graph: dict[str, Any], target_topic: str | None = None) -> dict[str, Any]:
    ranked = []
    for resource in resources:
        quality = explanation_quality(resource, graph)
        mapped = map_resource_to_graph(resource, graph)
        topics = [item["topic"] for item in mapped["mapped_topics"]]
        if target_topic and target_topic not in topics:
            continue
        ranked.append({
            **quality,
            "topics": topics,
            "modalities": mapped["modality_profile"]["modalities"],
        })
    return {
        "target_topic": target_topic,
        "ranked": sorted(ranked, key=lambda item: item["remediation_suitability"], reverse=True),
        "metric_version": QUALITY_VERSION,
        "content_engine_version": CONTENT_INTELLIGENCE_VERSION,
    }
