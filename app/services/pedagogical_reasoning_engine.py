from __future__ import annotations

from typing import Any

from app.services.educational_memory_engine import EDUCATIONAL_MEMORY_VERSION
from app.core.pedagogy.inference_reliability import clamp

PEDAGOGICAL_REASONING_VERSION = "pedagogical-reasoning.v1"


def evidence_linked_claim(
    claim: str,
    evidence_source: str,
    supporting_attempts: list[int],
    conceptual_regions: list[str],
    telemetry_reliability: float,
    narrative_confidence: float,
    contradiction_flags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "claim": claim,
        "evidence_source": evidence_source,
        "supporting_attempts": supporting_attempts,
        "conceptual_regions": conceptual_regions,
        "telemetry_reliability": round(clamp(telemetry_reliability), 4),
        "narrative_confidence": round(clamp(narrative_confidence), 4),
        "contradiction_flags": contradiction_flags or [],
        "safety_boundary": "Educational reasoning only; do not infer personality, intelligence, or diagnosis.",
        "metric_version": PEDAGOGICAL_REASONING_VERSION,
    }


def reason_recovery_failures(memory: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    failed = memory.get("recovery_memory", {}).get("failed_recoveries", [])
    misconceptions = {
        item["topic"]: item
        for item in memory.get("misconception_memory", {}).get("misconceptions", [])
    }
    telemetry = memory.get("profile", {}).get("longitudinal_reliability", {}).get("telemetry_continuity", 0)

    for item in failed:
        topic = item["topic"]
        misconception = misconceptions.get(topic, {})
        prereqs = misconception.get("prerequisite_chain", [])
        if prereqs:
            reason = f"Recovery around {topic} may have failed because prerequisite evidence remains unstable."
        else:
            reason = f"Recovery around {topic} remains unstable; evidence does not isolate a single cause."
        claims.append(evidence_linked_claim(
            claim=reason,
            evidence_source="revision_effectiveness + misconception_memory",
            supporting_attempts=misconception.get("supporting_attempts", []),
            conceptual_regions=[topic, *prereqs],
            telemetry_reliability=telemetry,
            narrative_confidence=misconception.get("probability", 0.35),
            contradiction_flags=[] if prereqs else ["CAUSE_UNRESOLVED"],
        ))
    return claims


def reason_stability_improvements(memory: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    durable = memory.get("recovery_memory", {}).get("durable_recoveries", [])
    interventions = memory.get("recovery_memory", {}).get("successful_interventions", [])
    telemetry = memory.get("profile", {}).get("longitudinal_reliability", {}).get("telemetry_continuity", 0)
    intervention_topics = {item.get("topic") for item in interventions if item.get("topic")}

    for item in durable:
        topic = item["topic"]
        linked = topic in intervention_topics
        claim = (
            f"Stability around {topic} improved after recorded educational support, but causation is not established."
            if linked else
            f"Stability around {topic} improved in recent history; supporting intervention evidence is limited."
        )
        claims.append(evidence_linked_claim(
            claim=claim,
            evidence_source="recovery_memory + intervention_history",
            supporting_attempts=[],
            conceptual_regions=[topic],
            telemetry_reliability=telemetry,
            narrative_confidence=clamp(item.get("retention_score", 0) / 100),
            contradiction_flags=[] if linked else ["INTERVENTION_LINK_WEAK"],
        ))
    return claims


def reason_prerequisite_collapse(memory: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    unstable = memory.get("conceptual_memory", {}).get("unstable_regions", [])
    telemetry = memory.get("profile", {}).get("longitudinal_reliability", {}).get("telemetry_continuity", 0)
    for item in unstable[:8]:
        claims.append(evidence_linked_claim(
            claim=f"The prerequisite chain for {item['topic']} may be contributing to repeated conceptual instability.",
            evidence_source="knowledge_graph + weak_foundation_detection",
            supporting_attempts=[],
            conceptual_regions=[item["topic"], *item.get("prerequisite_chain", [])],
            telemetry_reliability=telemetry,
            narrative_confidence=item.get("inference_confidence", 0.3),
            contradiction_flags=[],
        ))
    return claims


def pedagogical_reasoning_report(memory: dict[str, Any]) -> dict[str, Any]:
    failure_claims = reason_recovery_failures(memory)
    stability_claims = reason_stability_improvements(memory)
    prerequisite_claims = reason_prerequisite_collapse(memory)
    claims = [*failure_claims, *stability_claims, *prerequisite_claims]
    return {
        "user_id": memory.get("user_id"),
        "claims": claims,
        "teacher_support": memory.get("teacher_summary", {}),
        "narrative_timeline": memory.get("narrative_continuity", {}),
        "reasoning_confidence": round(sum(item["narrative_confidence"] for item in claims) / len(claims), 4) if claims else 0,
        "scientific_safety_policy": {
            "no_diagnosis": True,
            "no_permanent_labels": True,
            "no_personality_inference": True,
            "requires_evidence_links": True,
            "metric_version": PEDAGOGICAL_REASONING_VERSION,
        },
        "memory_version": EDUCATIONAL_MEMORY_VERSION,
        "metric_version": PEDAGOGICAL_REASONING_VERSION,
    }
