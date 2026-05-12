from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from sqlalchemy.orm import Session

from app.models.domain import Question, Subject, Topic
from app.services.inference_reliability import clamp

GRAPH_VERSION = "knowledge-graph.v1"


def build_knowledge_graph(db: Session) -> dict[str, Any]:
    subjects = db.query(Subject).all()
    topics = db.query(Topic).all()
    nodes = {}
    edges = []
    adjacency: dict[int, list[int]] = defaultdict(list)
    reverse_adjacency: dict[int, list[int]] = defaultdict(list)

    for topic in topics:
        q_count = db.query(Question).filter(Question.topic_id == topic.id).count()
        nodes[topic.id] = {
            "id": topic.id,
            "name": topic.name,
            "subject_id": topic.subject_id,
            "subject": topic.subject.name if topic.subject else None,
            "type": "TOPIC_CONCEPT",
            "question_count": q_count,
            "prerequisites": topic.prerequisites or [],
            "metric_version": GRAPH_VERSION,
        }
        for prereq_id in topic.prerequisites or []:
            if prereq_id in nodes or db.query(Topic).filter(Topic.id == prereq_id).first():
                edge = {
                    "from": prereq_id,
                    "to": topic.id,
                    "type": "PREREQUISITE",
                    "dependency_strength": 0.8,
                    "dependency_confidence": 0.9,
                    "metric_version": GRAPH_VERSION,
                }
                edges.append(edge)
                adjacency[prereq_id].append(topic.id)
                reverse_adjacency[topic.id].append(prereq_id)

    return {
        "nodes": nodes,
        "edges": edges,
        "adjacency": dict(adjacency),
        "reverse_adjacency": dict(reverse_adjacency),
        "subject_count": len(subjects),
        "topic_count": len(topics),
        "metric_version": GRAPH_VERSION,
    }


def dependency_paths(graph: dict[str, Any], start_topic_id: int, max_depth: int = 4) -> list[list[int]]:
    paths = []
    queue = deque([(start_topic_id, [start_topic_id])])
    while queue:
        current, path = queue.popleft()
        if len(path) > max_depth:
            continue
        children = graph.get("adjacency", {}).get(current, [])
        if not children and len(path) > 1:
            paths.append(path)
        for child in children:
            if child not in path:
                queue.append((child, [*path, child]))
    return paths


def prerequisite_chain(graph: dict[str, Any], topic_id: int) -> list[int]:
    seen = set()
    chain = []
    queue = deque(graph.get("reverse_adjacency", {}).get(topic_id, []))
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        chain.append(current)
        queue.extend(graph.get("reverse_adjacency", {}).get(current, []))
    return chain


def topology_analysis(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", {})
    adjacency = graph.get("adjacency", {})
    reverse = graph.get("reverse_adjacency", {})
    centrality = []
    bottlenecks = []
    bridges = []
    for topic_id, node in nodes.items():
        outgoing = len(adjacency.get(topic_id, []))
        incoming = len(reverse.get(topic_id, []))
        score = outgoing * 2 + incoming
        item = {
            "topic_id": topic_id,
            "topic": node["name"],
            "centrality_score": score,
            "dependency_density": outgoing + incoming,
        }
        centrality.append(item)
        if outgoing >= 2:
            bottlenecks.append(item)
        if incoming >= 1 and outgoing >= 1:
            bridges.append(item)

    return {
        "centrality": sorted(centrality, key=lambda item: item["centrality_score"], reverse=True),
        "bottleneck_concepts": sorted(bottlenecks, key=lambda item: item["centrality_score"], reverse=True),
        "bridge_concepts": sorted(bridges, key=lambda item: item["centrality_score"], reverse=True),
        "graph_coverage": graph_coverage(graph),
        "metric_version": GRAPH_VERSION,
    }


def graph_coverage(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", {})
    edge_count = len(graph.get("edges", []))
    topics_with_questions = len([node for node in nodes.values() if node.get("question_count", 0) > 0])
    topics_with_edges = len(set([edge["from"] for edge in graph.get("edges", [])] + [edge["to"] for edge in graph.get("edges", [])]))
    total = len(nodes) or 1
    return {
        "topic_question_coverage": round(topics_with_questions / total, 4),
        "dependency_coverage": round(topics_with_edges / total, 4),
        "edge_count": edge_count,
        "metric_version": GRAPH_VERSION,
    }


def mastery_by_topic_name(profile: dict[str, Any]) -> dict[str, float]:
    points = profile.get("trajectory_points", [])
    if not points:
        return {}
    mastery = {}
    for point in points:
        for topic, score in point.get("topic_scores", {}).items():
            mastery[topic] = score
    return mastery


def topic_name_to_id(graph: dict[str, Any]) -> dict[str, int]:
    return {node["name"]: topic_id for topic_id, node in graph.get("nodes", {}).items()}


def topic_id_to_name(graph: dict[str, Any]) -> dict[int, str]:
    return {topic_id: node["name"] for topic_id, node in graph.get("nodes", {}).items()}


def propagate_mastery(graph: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    name_to_id = topic_name_to_id(graph)
    id_to_name = topic_id_to_name(graph)
    raw_mastery = mastery_by_topic_name(profile)
    propagated = {}
    risks = []
    reliability = profile.get("longitudinal_reliability", {}).get("overall_reliability", 0)

    for topic_name, score in raw_mastery.items():
        topic_id = name_to_id.get(topic_name)
        if topic_id is None:
            continue
        prereqs = prerequisite_chain(graph, topic_id)
        prereq_scores = [raw_mastery.get(id_to_name.get(pid, ""), 50) for pid in prereqs]
        prereq_penalty = max(0, 60 - min(prereq_scores, default=score)) * 0.35
        inferred_score = clamp((score - prereq_penalty) / 100) * 100
        confidence = clamp(reliability * 0.65 + (len(prereq_scores) / 5) * 0.20 + 0.15)
        propagated[topic_name] = {
            "observed_mastery": round(score, 4),
            "dependency_adjusted_mastery": round(inferred_score, 4),
            "dependency_confidence": round(confidence, 4),
            "prerequisite_chain": [id_to_name.get(pid, str(pid)) for pid in prereqs],
            "reliability_downgrade": round(max(0, score - inferred_score), 4),
            "metric_version": GRAPH_VERSION,
        }
        if inferred_score < score - 5:
            risks.append({
                "topic": topic_name,
                "risk_type": "PREREQUISITE_PROPAGATION",
                "observed_mastery": round(score, 4),
                "adjusted_mastery": round(inferred_score, 4),
            })

    return {
        "mastery": propagated,
        "conceptual_risks": risks,
        "metric_version": GRAPH_VERSION,
    }


def weak_foundation_detection(graph: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    propagated = propagate_mastery(graph, profile)
    mastery = propagated["mastery"]
    confidence = profile.get("confidence_evolution", {})
    stability = profile.get("behavioral_stability", {})
    findings = []
    for topic, data in mastery.items():
        observed = data["observed_mastery"]
        adjusted = data["dependency_adjusted_mastery"]
        prereqs = data["prerequisite_chain"]
        if prereqs and adjusted < observed - 5:
            cause = "prerequisite weakness"
        elif stability.get("consistency_score", 1) < 0.45:
            cause = "unstable understanding"
        elif confidence.get("calibration_slope", 0) < 0 and observed < 65:
            cause = "confidence illusion"
        elif stability.get("pacing_volatility", 0) > 60:
            cause = "fatigue-related collapse"
        else:
            cause = "memorization or local recall failure"
        findings.append({
            "topic": topic,
            "likely_cause": cause,
            "observed_mastery": observed,
            "dependency_adjusted_mastery": adjusted,
            "prerequisite_chain": prereqs,
            "inference_confidence": data["dependency_confidence"],
            "metric_version": GRAPH_VERSION,
        })
    return sorted(findings, key=lambda item: item["dependency_adjusted_mastery"])


def conceptual_recovery_sequence(graph: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    findings = weak_foundation_detection(graph, profile)
    sequence = []
    seen = set()
    for finding in findings:
        for prereq in finding["prerequisite_chain"]:
            if prereq not in seen:
                sequence.append({
                    "topic": prereq,
                    "reason": f"Prerequisite for {finding['topic']}",
                    "priority": "FOUNDATION_FIRST",
                    "metric_version": GRAPH_VERSION,
                })
                seen.add(prereq)
        if finding["topic"] not in seen:
            sequence.append({
                "topic": finding["topic"],
                "reason": finding["likely_cause"],
                "priority": "TARGETED_REPAIR",
                "metric_version": GRAPH_VERSION,
            })
            seen.add(finding["topic"])
    return sequence


def cross_topic_reasoning(graph: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    id_to_name = topic_id_to_name(graph)
    reverse_dependents = graph.get("adjacency", {})
    shared_failures = []
    mastery = propagate_mastery(graph, profile)["mastery"]
    weak_topics = {topic for topic, data in mastery.items() if data["dependency_adjusted_mastery"] < 60}
    for topic_id, dependents in reverse_dependents.items():
        prereq_name = id_to_name.get(topic_id)
        dependent_names = [id_to_name.get(dep) for dep in dependents if id_to_name.get(dep) in weak_topics]
        if prereq_name and len(dependent_names) >= 2:
            shared_failures.append({
                "shared_dependency": prereq_name,
                "affected_topics": dependent_names,
                "reason": "linked conceptual failures",
                "metric_version": GRAPH_VERSION,
            })
    return {
        "shared_dependency_failures": shared_failures,
        "transfer_weaknesses": shared_failures,
        "metric_version": GRAPH_VERSION,
    }


def graph_observability(graph: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    topology = topology_analysis(graph)
    unresolved = []
    for topic_id, node in graph.get("nodes", {}).items():
        missing = [pid for pid in node.get("prerequisites", []) if pid not in graph.get("nodes", {})]
        if missing:
            unresolved.append({"topic": node["name"], "missing_prerequisites": missing})
    unstable = []
    if profile:
        unstable = [
            item for item in weak_foundation_detection(graph, profile)
            if item["dependency_adjusted_mastery"] < 60
        ]
    return {
        "coverage": topology["graph_coverage"],
        "unresolved_prerequisite_chains": unresolved,
        "bottleneck_count": len(topology["bottleneck_concepts"]),
        "bridge_count": len(topology["bridge_concepts"]),
        "unstable_dependency_regions": unstable[:10],
        "metric_version": GRAPH_VERSION,
    }
