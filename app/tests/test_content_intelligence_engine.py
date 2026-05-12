from app.db.session import Base
from app.services.content_intelligence_engine import (
    conceptual_overlap,
    content_observability,
    extract_content_concepts,
    map_resource_to_graph,
    material_effectiveness,
    remediation_library,
    semantic_search,
)
from app.services.explanation_quality_engine import explanation_quality, rank_explanations
from app.services.knowledge_graph_engine import build_knowledge_graph
from app.tests.test_knowledge_graph_engine import seed_concept_graph
from app.tests.test_student_longitudinal_profile import make_db


def sample_resources():
    return [
        {
            "id": "vectors-foundation",
            "type": "NOTE",
            "modalities": ["TEXT"],
            "text": (
                "Vectors are defined as quantities with magnitude and direction. "
                "A diagram can show components on an axis. Because Kinematics uses displacement, "
                "Vectors are a prerequisite bridge concept."
            ),
        },
        {
            "id": "kinematics-formula",
            "type": "EXPLANATION",
            "modalities": ["TEXT", "FORMULA"],
            "text": (
                "Kinematics means describing motion. v = u + a t and s = u t + 0.5 a t^2. "
                "Therefore weak Vectors can make displacement reasoning unstable."
            ),
        },
        {
            "id": "energy-advanced",
            "type": "PDF_EXTRACT",
            "modalities": ["TEXT"],
            "text": (
                "Energy transfer, Dynamics, Kinematics, Vectors, force, work, graph, table, "
                "therefore conservation reasoning depends on prior motion concepts."
            ),
        },
    ]


def test_extracts_concepts_formulas_definitions_and_modalities():
    db, engine = make_db()
    try:
        seed_concept_graph(db)
        graph = build_knowledge_graph(db)
        resource = sample_resources()[1]
        extraction = extract_content_concepts(resource["text"], graph)
        mapped = map_resource_to_graph(resource, graph)

        assert extraction["concepts"][0]["topic"] == "Kinematics"
        assert extraction["formulas"]
        assert extraction["reasoning_chains"]
        assert mapped["difficulty_band"] in {"INTERMEDIATE", "ADVANCED"}
        assert mapped["modality_profile"]["formula_ready"] is True
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_explanation_quality_is_conservative_and_rankable():
    db, engine = make_db()
    try:
        seed_concept_graph(db)
        graph = build_knowledge_graph(db)
        quality = explanation_quality(sample_resources()[0], graph)
        ranked = rank_explanations(sample_resources(), graph, target_topic="Vectors")

        assert quality["quality_band"] in {"STRONG", "USABLE", "NEEDS_REVIEW"}
        assert quality["scientific_safety_note"]
        assert ranked["ranked"]
        assert "Vectors" in ranked["ranked"][0]["topics"]
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_semantic_retrieval_remediation_and_content_observability():
    db, engine = make_db()
    try:
        seed_concept_graph(db)
        graph = build_knowledge_graph(db)
        resources = sample_resources()
        search = semantic_search("I need prerequisite help for displacement and vectors", resources, graph)
        library = remediation_library(resources, graph)
        overlap = conceptual_overlap(resources, graph)
        observability = content_observability(resources, graph)

        assert search["results"][0]["resource_id"] in {"vectors-foundation", "kinematics-formula"}
        assert "Vectors" in library["topics"]
        assert overlap["overlaps"]
        assert observability["concept_coverage_rate"] > 0
        assert "metric_version" in observability
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_material_effectiveness_exposes_associative_not_causal_evidence():
    resources = sample_resources()
    result = material_effectiveness(resources, [
        {"resource_id": "vectors-foundation", "pre_score": 40, "post_score": 55, "overload_flag": False},
        {"resource_id": "vectors-foundation", "pre_score": 50, "post_score": 48, "overload_flag": True},
    ])

    evidence = result["resources"]["vectors-foundation"]
    assert evidence["evidence_count"] == 2
    assert evidence["post_exposure_improvement"] == 6.5
    assert "do not infer causation" in evidence["causal_warning"]
