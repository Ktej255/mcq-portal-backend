from datetime import datetime, timezone

from app.db.session import Base
from app.models.domain import LearningIntervention
from app.services.educational_memory_engine import (
    build_educational_memory,
    educational_memory_observability,
    persist_educational_memory,
)
from app.services.pedagogical_reasoning_engine import pedagogical_reasoning_report
from app.tests.test_knowledge_graph_engine import seed_concept_graph
from app.tests.test_student_longitudinal_profile import make_db


def add_followed_intervention(db, user_id: int):
    intervention = LearningIntervention(
        user_id=user_id,
        recommendation_id="memory-rec-1",
        strategy_id="foundation_repair_v1",
        recommendation_payload={
            "recommendation": {
                "type": "REVISION",
                "topic": "Vectors",
                "reason": "Foundational repair",
            }
        },
        status="FOLLOWED",
        outcome_metadata={
            "outcome": {
                "post_intervention_accuracy_delta": 8,
                "pacing_stabilization": 12,
            }
        },
        reliability_snapshot={"level": "LOW"},
        metric_version="intervention-tracking.v1",
        generated_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(intervention)
    db.commit()


def test_builds_probabilistic_educational_memory():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        add_followed_intervention(db, user.id)
        memory = build_educational_memory(db, user.id)

        misconceptions = memory["misconception_memory"]["misconceptions"]
        assert misconceptions
        assert misconceptions[0]["safety_note"]
        assert "Vectors" in {item["topic"] for item in misconceptions}
        assert memory["recovery_memory"]["successful_interventions"]
        assert memory["teacher_summary"]["summary_type"] == "EDUCATIONAL_SUPPORT"
        assert memory["memory_aging"]["decay_ready"] is True
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_persists_memory_into_user_behavioral_profile_and_observability():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        memory = persist_educational_memory(db, user.id)
        observed = educational_memory_observability(db)

        assert memory["metric_version"] == "educational-memory.v1"
        assert observed["memory_profile_count"] == 1
        assert observed["misconception_persistence_rate"] >= 1
        assert observed["narrative_stability"] >= 0
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_pedagogical_reasoning_is_evidence_linked_and_safe():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        add_followed_intervention(db, user.id)
        memory = build_educational_memory(db, user.id)
        report = pedagogical_reasoning_report(memory)

        assert report["claims"]
        first = report["claims"][0]
        assert first["evidence_source"]
        assert "supporting_attempts" in first
        assert first["safety_boundary"]
        assert report["scientific_safety_policy"]["no_diagnosis"] is True
        assert report["teacher_support"]["safety_note"]
    finally:
        db.close()
        Base.metadata.drop_all(engine)
