from datetime import datetime, timezone, timedelta

from app.db.session import Base
from app.models.domain import (
    Attempt,
    AttemptAnswer,
    AttemptStatusEnum,
    ConfidenceEnum,
    ExamEvent,
    Question,
    Report,
    RoleEnum,
    Subject,
    Test as ExamTest,
    Topic,
    User,
)
from app.services.adaptive_learning_engine import build_adaptive_learning_plan
from app.services.dynamic_test_generator import assemble_dynamic_test
from app.services.knowledge_graph_engine import (
    build_knowledge_graph,
    conceptual_recovery_sequence,
    cross_topic_reasoning,
    graph_observability,
    propagate_mastery,
    topology_analysis,
    weak_foundation_detection,
)
from app.tests.test_student_longitudinal_profile import make_db


def seed_concept_graph(db):
    user = User(google_uid="graph-uid", email="graph@example.com", role=RoleEnum.STUDENT)
    subject = Subject(name="Physics")
    db.add_all([user, subject])
    db.commit()

    vectors = Topic(name="Vectors", subject_id=subject.id)
    kinematics = Topic(name="Kinematics", subject_id=subject.id)
    dynamics = Topic(name="Dynamics", subject_id=subject.id)
    energy = Topic(name="Energy", subject_id=subject.id)
    db.add_all([vectors, kinematics, dynamics, energy])
    db.commit()

    kinematics.prerequisites = [vectors.id]
    dynamics.prerequisites = [vectors.id, kinematics.id]
    energy.prerequisites = [vectors.id, dynamics.id]
    db.commit()

    test = ExamTest(title="Graph Test", subject_id=subject.id, correct_marks=4, negative_marking_value=1)
    db.add(test)
    db.commit()

    for topic in [vectors, kinematics, dynamics, energy]:
        for difficulty in ["EASY", "MEDIUM"]:
            db.add(Question(
                test_id=test.id,
                topic_id=topic.id,
                text_en=f"{topic.name} {difficulty}",
                options_en={"A": "A", "B": "B"},
                correct_option="A",
                difficulty=difficulty,
            ))
    db.commit()

    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    topic_scores = [
        {"Vectors": 42, "Kinematics": 74, "Dynamics": 55, "Energy": 52},
        {"Vectors": 40, "Kinematics": 76, "Dynamics": 58, "Energy": 54},
        {"Vectors": 38, "Kinematics": 78, "Dynamics": 60, "Energy": 56},
    ]
    for idx, scores in enumerate(topic_scores):
        attempt = Attempt(
            user_id=user.id,
            test_id=test.id,
            status=AttemptStatusEnum.SUBMITTED,
            start_time=base + timedelta(days=idx),
            end_time=base + timedelta(days=idx, minutes=30),
        )
        db.add(attempt)
        db.commit()
        first_question = db.query(Question).filter(Question.topic_id == vectors.id).first()
        db.add(AttemptAnswer(
            attempt_id=attempt.id,
            question_id=first_question.id,
            selected_option="A",
            is_correct=True,
            time_taken_seconds=70,
            confidence_level=ConfidenceEnum.FAIRLY_SURE,
        ))
        db.add(ExamEvent(attempt_id=attempt.id, event_type="HEARTBEAT", timestamp=attempt.start_time))
        db.add(Report(
            attempt_id=attempt.id,
            total_score=idx + 1,
            accuracy=sum(scores.values()) / len(scores),
            correct_count=1,
            incorrect_count=0,
            unattempted_count=0,
            topic_wise_analysis={
                topic: {"correct": score, "incorrect": 100 - score, "unattempted": 0, "total": 100}
                for topic, score in scores.items()
            },
            subject_wise_performance={"Physics": {"correct": 1, "incorrect": 0, "unattempted": 0, "total": 1}},
            confidence_analysis={ConfidenceEnum.FAIRLY_SURE.value: {"correct": 1, "incorrect": 0, "total": 1}},
            average_time_per_question=70,
            processing_status="COMPLETED",
            generated_at=attempt.end_time,
        ))
        db.commit()

    return user


def profile_with_weak_foundation():
    return {
        "trajectory_points": [
            {"topic_scores": {"Vectors": 38, "Kinematics": 78, "Dynamics": 60, "Energy": 56}},
        ],
        "longitudinal_reliability": {"overall_reliability": 0.62},
        "confidence_evolution": {"calibration_slope": -4},
        "behavioral_stability": {"consistency_score": 0.68, "pacing_volatility": 20},
    }


def test_graph_models_dependencies_and_topology():
    db, engine = make_db()
    try:
        seed_concept_graph(db)
        graph = build_knowledge_graph(db)
        topology = topology_analysis(graph)

        assert graph["topic_count"] == 4
        assert len(graph["edges"]) == 5
        assert topology["graph_coverage"]["dependency_coverage"] == 1
        assert topology["bottleneck_concepts"][0]["topic"] == "Vectors"
        assert any(item["topic"] == "Dynamics" for item in topology["bridge_concepts"])
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_mastery_propagates_weak_foundation_risk():
    db, engine = make_db()
    try:
        seed_concept_graph(db)
        graph = build_knowledge_graph(db)
        profile = profile_with_weak_foundation()
        propagated = propagate_mastery(graph, profile)
        findings = weak_foundation_detection(graph, profile)
        recovery = conceptual_recovery_sequence(graph, profile)
        cross_topic = cross_topic_reasoning(graph, profile)
        observability = graph_observability(graph, profile)

        assert propagated["mastery"]["Kinematics"]["dependency_adjusted_mastery"] < 78
        assert any(item["topic"] == "Kinematics" and item["likely_cause"] == "prerequisite weakness" for item in findings)
        assert recovery[0]["topic"] == "Vectors"
        assert cross_topic["shared_dependency_failures"][0]["shared_dependency"] == "Vectors"
        assert observability["unstable_dependency_regions"]
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def test_adaptive_and_dynamic_generation_are_graph_aware():
    db, engine = make_db()
    try:
        user = seed_concept_graph(db)
        plan = build_adaptive_learning_plan(db, user.id)
        generated = assemble_dynamic_test(db, user.id, target_count=3)

        assert plan["conceptual_recovery_sequence"]
        assert plan["conceptual_recovery_sequence"][0]["topic"] == "Vectors"
        assert plan["graph_observability"]["coverage"]["edge_count"] == 5
        assert generated["graph_aware"] is True
        assert "Vectors" in generated["conceptual_recovery_topics"]
        assert generated["questions"][0]["reason"] == "graph_prerequisite_recovery"
    finally:
        db.close()
        Base.metadata.drop_all(engine)
