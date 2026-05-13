from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from app.services.inference_reliability import clamp
from app.services.knowledge_graph_engine import (
    prerequisite_chain,
    topology_analysis,
    topic_id_to_name,
    topic_name_to_id,
)

CONTENT_INTELLIGENCE_VERSION = "content-intelligence.v1"

FORMULA_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*\s*=\s*[-+*/^(). A-Za-z0-9_]+")
DEFINITION_PATTERN = re.compile(r"\b(is defined as|refers to|means|is called|is known as)\b", re.IGNORECASE)
REASONING_MARKERS = {"because", "therefore", "hence", "so", "implies", "leads to", "as a result", "if", "then"}
VISUAL_MARKERS = {"diagram", "graph", "figure", "chart", "table", "image", "axis", "curve"}
BILINGUAL_MARKERS = {"hindi", "english", "bilingual", "translation", "अनुवाद", "हिंदी"}


def _normalize(text: str) -> str:
    if not text:
        return ""
    # Preserve newlines but collapse horizontal whitespace
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(lines).strip()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_+-]*", text.lower())


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[.!?\n]+", text) if item.strip()]


def extract_content_concepts(text: str, graph: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize(text)
    tokens = _tokens(normalized)
    token_counts = Counter(tokens)
    topic_matches = []
    concept_terms = []

    for topic_id, node in graph.get("nodes", {}).items():
        name = node.get("name", "")
        name_tokens = _tokens(name)
        position = normalized.lower().find(name.lower()) if name else -1
        if position >= 0:
            confidence = 0.95
        else:
            hits = sum(token_counts[token] for token in name_tokens)
            confidence = clamp(hits / max(1, len(name_tokens) * 2))
            position = len(normalized) + topic_id
        if confidence >= 0.25:
            topic_matches.append({
                "topic_id": topic_id,
                "topic": name,
                "match_confidence": round(confidence, 4),
                "evidence_position": position,
                "metric_version": CONTENT_INTELLIGENCE_VERSION,
            })
            concept_terms.extend(name_tokens)

    formulas = [match.group(0).strip() for match in FORMULA_PATTERN.finditer(normalized)]
    definitions = [
        sentence for sentence in _sentences(normalized)
        if DEFINITION_PATTERN.search(sentence)
    ]
    reasoning_chains = [
        sentence for sentence in _sentences(normalized)
        if any(marker in sentence.lower() for marker in REASONING_MARKERS)
    ]
    repeated_terms = [
        {"term": term, "count": count}
        for term, count in token_counts.most_common(20)
        if count >= 2 and len(term) > 3 and term not in {"this", "that", "with", "from"}
    ]

    return {
        "concepts": sorted(topic_matches, key=lambda item: (-item["match_confidence"], item["evidence_position"])),
        "key_terms": repeated_terms[:10],
        "formulas": formulas[:20],
        "definitions": definitions[:20],
        "reasoning_chains": reasoning_chains[:20],
        "conceptual_density": conceptual_density(normalized, len(topic_matches), len(formulas), len(definitions)),
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def conceptual_density(text: str, concept_count: int, formula_count: int, definition_count: int) -> dict[str, Any]:
    words = max(1, len(_tokens(text)))
    signal_units = concept_count + formula_count + definition_count
    density = signal_units / words * 100
    if density > 9:
        band = "HIGH_OVERLOAD_RISK"
    elif density >= 4:
        band = "MODERATE"
    else:
        band = "LOW"
    return {
        "score": round(min(density, 100), 4),
        "band": band,
        "word_count": words,
        "signal_units": signal_units,
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def modality_profile(resource: dict[str, Any]) -> dict[str, Any]:
    text = _normalize(resource.get("text", ""))
    declared = set(resource.get("modalities", []) or [])
    lower = text.lower()
    inferred = set()
    if text:
        inferred.add("TEXT")
    if any(marker in lower for marker in VISUAL_MARKERS):
        inferred.add("VISUAL_REFERENCE")
    if FORMULA_PATTERN.search(text):
        inferred.add("FORMULA")
    if "|" in text or "\t" in text or "table" in lower:
        inferred.add("TABLE")
    if any(marker in lower for marker in BILINGUAL_MARKERS):
        inferred.add("BILINGUAL")
    return {
        "modalities": sorted(declared | inferred),
        "formula_ready": "FORMULA" in inferred or "FORMULA" in declared,
        "visual_linkage_ready": "VISUAL_REFERENCE" in inferred or "IMAGE" in declared,
        "bilingual_mapping_ready": "BILINGUAL" in inferred or "BILINGUAL" in declared,
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def map_resource_to_graph(resource: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    extraction = extract_content_concepts(resource.get("text", ""), graph)
    name_by_id = topic_id_to_name(graph)
    mapped_topics = extraction["concepts"]
    prerequisite_regions = []
    for concept in mapped_topics:
        chain = prerequisite_chain(graph, concept["topic_id"])
        prerequisite_regions.append({
            "topic": concept["topic"],
            "prerequisite_chain": [name_by_id.get(topic_id, str(topic_id)) for topic_id in chain],
            "match_confidence": concept["match_confidence"],
        })

    avg_confidence = (
        sum(item["match_confidence"] for item in mapped_topics) / len(mapped_topics)
        if mapped_topics else 0
    )
    density = extraction["conceptual_density"]
    difficulty = (
        "ADVANCED" if density["band"] == "HIGH_OVERLOAD_RISK" or len(extraction["formulas"]) >= 3
        else "INTERMEDIATE" if len(mapped_topics) >= 2 or extraction["reasoning_chains"]
        else "BEGINNER"
    )
    remediation_relevance = clamp(avg_confidence * 0.55 + (1 if prerequisite_regions else 0) * 0.25 + min(len(extraction["definitions"]), 3) / 3 * 0.20)

    return {
        "resource_id": resource.get("id"),
        "resource_type": resource.get("type", "UNKNOWN"),
        "mapped_topics": mapped_topics,
        "prerequisite_regions": prerequisite_regions,
        "difficulty_band": difficulty,
        "remediation_relevance": round(remediation_relevance, 4),
        "extraction": extraction,
        "modality_profile": modality_profile(resource),
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def conceptual_overlap(resources: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any]:
    resource_topics: dict[str, set[str]] = {}
    for resource in resources:
        mapped = map_resource_to_graph(resource, graph)
        resource_topics[str(resource.get("id"))] = {item["topic"] for item in mapped["mapped_topics"]}

    overlaps = []
    ids = list(resource_topics)
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            shared = sorted(resource_topics[left] & resource_topics[right])
            union = resource_topics[left] | resource_topics[right]
            if shared:
                overlaps.append({
                    "resource_a": left,
                    "resource_b": right,
                    "shared_topics": shared,
                    "overlap_score": round(len(shared) / max(1, len(union)), 4),
                })

    return {
        "overlaps": sorted(overlaps, key=lambda item: item["overlap_score"], reverse=True),
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def semantic_search(query: str, resources: list[dict[str, Any]], graph: dict[str, Any], limit: int = 5) -> dict[str, Any]:
    query_map = map_resource_to_graph({"id": "__query__", "text": query, "type": "QUERY"}, graph)
    query_topics = {item["topic"] for item in query_map["mapped_topics"]}
    query_terms = {item["term"] for item in query_map["extraction"]["key_terms"]} | set(_tokens(query))
    results = []

    for resource in resources:
        mapped = map_resource_to_graph(resource, graph)
        topics = {item["topic"] for item in mapped["mapped_topics"]}
        terms = {item["term"] for item in mapped["extraction"]["key_terms"]} | set(_tokens(resource.get("text", "")))
        topic_score = len(query_topics & topics) / max(1, len(query_topics | topics))
        term_score = len(query_terms & terms) / max(1, len(query_terms | terms))
        score = topic_score * 0.7 + term_score * 0.3
        if score > 0:
            results.append({
                "resource_id": resource.get("id"),
                "resource_type": resource.get("type", "UNKNOWN"),
                "score": round(score, 4),
                "matched_topics": sorted(query_topics & topics),
                "difficulty_band": mapped["difficulty_band"],
                "remediation_relevance": mapped["remediation_relevance"],
            })

    return {
        "query_topics": sorted(query_topics),
        "results": sorted(results, key=lambda item: item["score"], reverse=True)[:limit],
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def remediation_library(resources: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any]:
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource in resources:
        mapped = map_resource_to_graph(resource, graph)
        for topic in mapped["mapped_topics"]:
            if mapped["remediation_relevance"] >= 0.35:
                by_topic[topic["topic"]].append({
                    "resource_id": resource.get("id"),
                    "resource_type": resource.get("type", "UNKNOWN"),
                    "difficulty_band": mapped["difficulty_band"],
                    "remediation_relevance": mapped["remediation_relevance"],
                    "modality_profile": mapped["modality_profile"]["modalities"],
                })

    return {
        "topics": {
            topic: sorted(items, key=lambda item: item["remediation_relevance"], reverse=True)
            for topic, items in by_topic.items()
        },
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def material_effectiveness(resources: list[dict[str, Any]], outcome_records: list[dict[str, Any]]) -> dict[str, Any]:
    by_resource: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcome_records:
        if outcome.get("resource_id"):
            by_resource[str(outcome["resource_id"])].append(outcome)

    results = {}
    resource_ids = {str(resource.get("id")) for resource in resources}
    for resource_id in resource_ids:
        outcomes = by_resource.get(resource_id, [])
        improvements = [item.get("post_score", 0) - item.get("pre_score", 0) for item in outcomes]
        overloads = [item for item in outcomes if item.get("overload_flag")]
        evidence_count = len(outcomes)
        avg_improvement = sum(improvements) / evidence_count if evidence_count else 0
        results[resource_id] = {
            "evidence_count": evidence_count,
            "post_exposure_improvement": round(avg_improvement, 4),
            "overload_rate": round(len(overloads) / evidence_count * 100, 4) if evidence_count else 0,
            "evidence_confidence": "MEDIUM" if evidence_count >= 10 else "LOW" if evidence_count else "INSUFFICIENT",
            "causal_warning": "Post-resource outcomes are associative evidence only; do not infer causation.",
            "metric_version": CONTENT_INTELLIGENCE_VERSION,
        }

    return {
        "resources": results,
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }


def content_observability(resources: list[dict[str, Any]], graph: dict[str, Any]) -> dict[str, Any]:
    mappings = [map_resource_to_graph(resource, graph) for resource in resources]
    topic_counts = Counter(
        topic["topic"]
        for mapping in mappings
        for topic in mapping["mapped_topics"]
    )
    all_topics = {node["name"] for node in graph.get("nodes", {}).values()}
    covered = set(topic_counts)
    overloaded = [
        mapping for mapping in mappings
        if mapping["extraction"]["conceptual_density"]["band"] == "HIGH_OVERLOAD_RISK"
    ]
    low_quality_candidates = [
        mapping for mapping in mappings
        if not mapping["extraction"]["definitions"] and mapping["extraction"]["conceptual_density"]["score"] > 6
    ]
    topology = topology_analysis(graph)

    return {
        "resource_count": len(resources),
        "concept_coverage_rate": round(len(covered) / max(1, len(all_topics)), 4),
        "sparse_concept_regions": sorted(all_topics - covered),
        "overloaded_content_count": len(overloaded),
        "low_quality_explanation_cluster_count": len(low_quality_candidates),
        "bottleneck_resource_gaps": [
            item["topic"] for item in topology["bottleneck_concepts"]
            if item["topic"] not in covered
        ],
        "metric_version": CONTENT_INTELLIGENCE_VERSION,
    }
