from app.models.domain import LearningIntervention
from app.services.adaptive_experimentation import assign_experiment, experiment_observability
from app.services.causal_safety_rules import causal_confidence
from app.services.intervention_analytics import longitudinal_intervention_analytics
from app.services.intervention_tracking_engine import (
    acceptance_summary,
    attach_intervention_outcome,
    record_generated_interventions,
    update_intervention_status,
)
from app.services.recommendation_effectiveness import evaluate_intervention_effectiveness
from app.services.strategy_registry import choose_strategy, list_strategies
from app.tests.test_student_longitudinal_profile import make_db, seed_longitudinal_history


def test_strategy_registry_exposes_safety_metadata():
    strategies = list_strategies()

    assert strategies
    assert all(item["reversible"] for item in strategies)
    assert choose_strategy({"type": "CONFIDENCE_CALIBRATION"})["strategy_id"] == "confidence_recalibration"


def test_causal_safety_never_overclaims_sparse_data():
    result = causal_confidence(evidence_count=1, pre_points=1, post_points=0, reliability=0.2, confounder_count=1)

    assert result["level"] == "LOW"
    assert "too limited" in result["claim_language"]
    assert "Do not state" in result["confounding_warnings"][-1]


def test_experiment_assignment_is_reliability_aware():
    low = assign_experiment(1, "revision_intensity_v1", {"recommendation_confidence": 0.1, "mode": "SOFT"})
    ok = assign_experiment(1, "revision_intensity_v1", {"recommendation_confidence": 0.6, "mode": "GUIDED"})

    assert low["assigned"] is False
    assert ok["assigned"] is True
    assert experiment_observability([low, ok])["assigned_rate"] == 50


def test_intervention_lifecycle_and_acceptance_summary():
    db, engine = make_db()
    try:
        user = seed_longitudinal_history(db)
        interventions = record_generated_interventions(
            db,
            user.id,
            [{"type": "PRACTICE_DRILL", "topic": "Kinematics", "priority": "MEDIUM"}],
            {"trajectory_reliability": {"level": "LOW"}},
        )

        assert interventions[0].status == "GENERATED"
        update_intervention_status(db, interventions[0].recommendation_id, "ACCEPTED", {"source": "test"})
        attach_intervention_outcome(db, interventions[0].recommendation_id, {"post_intervention_accuracy_delta": 5})
        refreshed = db.query(LearningIntervention).first()

        assert refreshed.status == "ACCEPTED"
        assert acceptance_summary([refreshed])["accepted_rate"] == 100
    finally:
        db.close()
        engine.dispose()


def test_effectiveness_and_longitudinal_intervention_analytics_are_causal_safe():
    db, engine = make_db()
    try:
        user = seed_longitudinal_history(db)
        intervention = record_generated_interventions(
            db,
            user.id,
            [{"type": "REVISION", "topic": "Kinematics", "priority": "HIGH"}],
            {"trajectory_reliability": {"level": "LOW"}},
        )[0]
        outcome = evaluate_intervention_effectiveness(db, intervention)
        attach_intervention_outcome(db, intervention.recommendation_id, outcome)
        analytics = longitudinal_intervention_analytics(db)

        assert "Correlation is not causation." in outcome["causal_safety"]["confounding_warnings"]
        assert outcome["safe_summary"]
        assert analytics["intervention_count"] == 1
        assert "revision_reinforcement" in analytics["strategy_results"]
    finally:
        db.close()
        engine.dispose()
