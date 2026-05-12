from app.models.domain import Question
from app.services.adaptive_learning_engine import (
    adaptive_reliability,
    cognitive_load_balance,
    personalized_difficulty,
    personalized_study_plan,
    topic_priority,
)
from app.services.dynamic_test_generator import assemble_dynamic_test
from app.services.learning_state_machine import probabilistic_learning_states, state_adaptation_guidance
from app.tests.test_student_longitudinal_profile import make_db, seed_longitudinal_history


def sample_profile():
    return {
        "attempt_count": 4,
        "learning_velocity": {"accuracy_slope": 4},
        "confidence_evolution": {"calibration_slope": 3},
        "behavioral_stability": {
            "consistency_score": 0.42,
            "accuracy_volatility": 28,
            "pacing_volatility": 55,
        },
        "revision_effectiveness": {
            "topics": {
                "Kinematics": {"status": "UNSTABLE", "retention_score": 55, "decay": 20},
                "Thermodynamics": {"status": "STABLE", "retention_score": 82, "decay": 4},
            }
        },
        "adaptive_recommendation_context": {
            "weak_topics": [{"topic": "Kinematics"}],
        },
        "longitudinal_reliability": {
            "overall_reliability": 0.38,
            "level": "LOW",
        },
    }


def test_probabilistic_learning_states_are_not_deterministic_labels():
    state = probabilistic_learning_states(sample_profile())

    assert state["primary_state"] in state["state_probabilities"]
    assert abs(sum(state["state_probabilities"].values()) - 1) < 0.01
    assert "not psychological labels" in state["safety_note"]
    assert state_adaptation_guidance(state)["adaptation_bias"]


def test_personalized_difficulty_adjusts_to_mastery_and_reliability():
    question = Question(id=1, difficulty="HARD")
    low_mastery = personalized_difficulty(question, topic_mastery=20, reliability=0.8)
    high_mastery = personalized_difficulty(question, topic_mastery=90, reliability=0.8)

    assert low_mastery["relative_difficulty"] > high_mastery["relative_difficulty"]
    assert low_mastery["challenge_band"] in {"FRUSTRATION_RISK", "PRODUCTIVE_CHALLENGE"}


def test_topic_priority_uses_decay_and_weakness():
    priorities = topic_priority(sample_profile())

    assert priorities[0]["topic"] == "Kinematics"
    assert priorities[0]["priority_score"] > priorities[1]["priority_score"]


def test_cognitive_load_and_study_plan_are_cautious_for_low_reliability():
    profile = sample_profile()
    load = cognitive_load_balance(profile)
    plan = personalized_study_plan(profile)
    reliability = adaptive_reliability(profile, evidence_count=profile["attempt_count"])

    assert load["recommended_session_intensity"] in {"LIGHT", "MODERATE", "STANDARD"}
    assert plan["adaptive_reliability"]["mode"] == "SOFT"
    assert reliability["evidence_quality"] == "LOW"
    assert plan["workload"]["question_count"] <= 20


def test_dynamic_test_generation_assembles_candidates():
    db, engine = make_db()
    try:
        user = seed_longitudinal_history(db)
        result = assemble_dynamic_test(db, user.id, target_count=2)

        assert result["question_count"] >= 1
        assert result["questions"][0]["difficulty"]["relative_difficulty"] >= 0
        assert result["adaptive_reliability"]["mode"] in {"SOFT", "GUIDED", "ASSERTIVE_BUT_REVERSIBLE"}
    finally:
        db.close()
        engine.dispose()
