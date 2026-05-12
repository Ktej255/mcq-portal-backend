from app.db.session import Base
from app.services.educational_orchestrator import orchestrate_education, orchestration_observability
from app.services.educational_policy_engine import arbitrate_educational_action, safety_governance
from app.services.educational_state_manager import build_unified_educational_state
from app.services.educational_memory_engine import persist_educational_memory
from app.tests.test_educational_memory_engine import add_followed_intervention
from app.tests.test_knowledge_graph_engine import seed_concept_graph
from app.tests.test_student_longitudinal_profile import make_db


def test_unified_state_combines_engine_reliability_and_contradictions():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        state = build_unified_educational_state(db, user.id)

        assert state["reliability"]["components"]["longitudinal_reliability"] >= 0
        assert state["reliability"]["components"]["conceptual_reliability"] >= 0
        assert "adaptive_plan" in state
        assert "educational_memory" in state
        assert "pedagogical_reasoning" in state
        assert state["metric_version"] == "educational-state.v1"
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_policy_arbitrates_toward_stability_and_blocks_unsafe_actions():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        state = build_unified_educational_state(db, user.id)
        decision = arbitrate_educational_action(state)
        governance = safety_governance(state)

        assert decision["action_type"] in {"FOUNDATION_FIRST_REMEDIATION", "LOAD_REDUCTION", "ADAPTIVE_PRACTICE", "SOFT_GUIDANCE"}
        assert decision["governance"]["reversibility_required"] is True
        assert governance["runaway_adaptation_guard"] is True
        assert any(item["action"] in {"ASSERTIVE_ADAPTATION", "SKIP_FOUNDATION_REPAIR", "HIGH_INTENSITY_WORKLOAD"} for item in governance["blocked_actions"])
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_orchestrator_returns_explainable_memory_aware_decision():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        add_followed_intervention(db, user.id)
        result = orchestrate_education(db, user.id)

        assert result["decision"]["action_type"] in {"FOUNDATION_FIRST_REMEDIATION", "SOFT_GUIDANCE"}
        assert result["cross_engine_reasoning"]["contributing_engines"]["pedagogical_memory"]["weight"] > 0
        assert result["explanation"]["why_generated"]
        assert "blocked_alternatives" in result["explanation"]
        assert result["memory_aware_context"]["misconceptions"]
        assert result["scientific_safety"]["evidence_linked"] is True
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_orchestration_observability_counts_persisted_memory_profiles():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        persist_educational_memory(db, user.id)
        metrics = orchestration_observability(db)

        assert metrics["orchestrated_user_count"] == 1
        assert metrics["low_confidence_orchestration_rate"] >= 0
        assert metrics["metric_version"] == "educational-orchestrator.v1"
    finally:
        db.close()
        Base.metadata.drop_all(engine)
