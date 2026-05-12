from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.domain import (
    Attempt,
    AttemptAnswer,
    AttemptStatusEnum,
    ConfidenceEnum,
    ExamEvent,
    Report,
    RoleEnum,
    Subject,
    Test,
    Topic,
    User,
    Question,
)
from app.services.student_longitudinal_profile import (
    LONGITUDINAL_VERSION,
    behavioral_stability,
    build_student_longitudinal_profile,
    confidence_evolution,
    create_cognitive_snapshot,
    learning_velocity,
    revision_effectiveness,
)


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def seed_longitudinal_history(db):
    user = User(google_uid="long-uid", email="long@example.com", role=RoleEnum.STUDENT)
    subject = Subject(name="Physics")
    db.add_all([user, subject])
    db.commit()
    topic = Topic(name="Kinematics", subject_id=subject.id)
    db.add(topic)
    db.commit()
    test = Test(title="Trajectory Test", subject_id=subject.id, correct_marks=4, negative_marking_value=1)
    db.add(test)
    db.commit()
    question = Question(test_id=test.id, topic_id=topic.id, text_en="Q", options_en={"A": "A", "B": "B"}, correct_option="A")
    db.add(question)
    db.commit()

    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    accuracies = [40, 55, 70, 78]
    scores = [2, 4, 6, 7]
    times = [95, 80, 62, 58]
    confidence_levels = [
        ConfidenceEnum.BLIND_GUESS,
        ConfidenceEnum.EDUCATED_GUESS,
        ConfidenceEnum.FAIRLY_SURE,
        ConfidenceEnum.HUNDRED_PERCENT,
    ]

    for idx, accuracy in enumerate(accuracies):
        attempt = Attempt(
            user_id=user.id,
            test_id=test.id,
            status=AttemptStatusEnum.SUBMITTED,
            start_time=base + timedelta(days=idx),
            end_time=base + timedelta(days=idx, minutes=30),
        )
        db.add(attempt)
        db.commit()
        db.add(AttemptAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            selected_option="A",
            is_correct=True,
            time_taken_seconds=times[idx],
            confidence_level=confidence_levels[idx],
        ))
        db.add(ExamEvent(attempt_id=attempt.id, event_type="HEARTBEAT", timestamp=attempt.start_time))
        db.add(ExamEvent(attempt_id=attempt.id, event_type="QUESTION_VIEWED", question_id=question.id, timestamp=attempt.start_time + timedelta(seconds=1)))
        db.add(ExamEvent(attempt_id=attempt.id, event_type="ANSWER_CHANGED", question_id=question.id, payload={"option_id": "A"}, timestamp=attempt.start_time + timedelta(seconds=times[idx])))
        db.add(Report(
            attempt_id=attempt.id,
            total_score=scores[idx],
            accuracy=accuracy,
            correct_count=1,
            incorrect_count=0,
            unattempted_count=0,
            topic_wise_analysis={"Kinematics": {"correct": accuracy, "incorrect": 100 - accuracy, "unattempted": 0, "total": 100}},
            subject_wise_performance={"Physics": {"correct": accuracy, "incorrect": 100 - accuracy, "unattempted": 0, "total": 100}},
            confidence_analysis={confidence_levels[idx].value: {"correct": 1, "incorrect": 0, "total": 1}},
            average_time_per_question=times[idx],
            processing_status="COMPLETED",
            generated_at=attempt.end_time,
        ))
        db.commit()

    return user


def test_learning_velocity_detects_improvement():
    points = [
        {"accuracy": 40, "score": 2},
        {"accuracy": 55, "score": 4},
        {"accuracy": 70, "score": 6},
        {"accuracy": 80, "score": 7},
    ]
    result = learning_velocity(points)

    assert result["accuracy_slope"] > 0
    assert result["score_slope"] > 0
    assert result["metric_version"] == LONGITUDINAL_VERSION


def test_confidence_evolution_tracks_reduction_and_calibration():
    points = [
        {"confidence": {"blind_guess_rate": 60, "overconfidence_rate": 30, "calibration_accuracy": 20}},
        {"confidence": {"blind_guess_rate": 20, "overconfidence_rate": 10, "calibration_accuracy": 70}},
    ]
    result = confidence_evolution(points)

    assert result["blind_guess_reduction"] == 40
    assert result["overconfidence_reduction"] == 20
    assert result["calibration_slope"] > 0


def test_revision_effectiveness_detects_retention_decay():
    points = [
        {"topic_scores": {"Polity": 40}},
        {"topic_scores": {"Polity": 80}},
        {"topic_scores": {"Polity": 60}},
    ]
    result = revision_effectiveness(points)

    assert result["topics"]["Polity"]["decay"] == 20
    assert result["topics"]["Polity"]["status"] == "UNSTABLE"


def test_behavioral_stability_scores_consistency():
    stable = [
        {"accuracy": 70, "average_time_per_question": 60, "telemetry_quality": {"temporal_coherence": 0.9}},
        {"accuracy": 72, "average_time_per_question": 62, "telemetry_quality": {"temporal_coherence": 0.9}},
    ]
    volatile = [
        {"accuracy": 30, "average_time_per_question": 20, "telemetry_quality": {"temporal_coherence": 0.5}},
        {"accuracy": 90, "average_time_per_question": 180, "telemetry_quality": {"temporal_coherence": 0.5}},
    ]

    assert behavioral_stability(stable)["consistency_score"] > behavioral_stability(volatile)["consistency_score"]


def test_build_profile_and_create_snapshot():
    db, engine = make_db()
    try:
        user = seed_longitudinal_history(db)
        profile = build_student_longitudinal_profile(db, user.id)

        assert profile["attempt_count"] == 4
        assert profile["learning_velocity"]["accuracy_slope"] > 0
        assert profile["confidence_evolution"]["blind_guess_reduction"] >= 0
        assert profile["longitudinal_reliability"]["level"] == "LOW"

        latest_attempt_id = profile["trajectory_points"][-1]["attempt_id"]
        snapshot = create_cognitive_snapshot(db, user.id, latest_attempt_id, {"inference_reliability": {"ok": True}})
        assert snapshot is not None
        assert snapshot.metric_version == LONGITUDINAL_VERSION
        assert snapshot.telemetry_snapshot["event_count"] == 3
    finally:
        db.close()
        Base.metadata.drop_all(engine)
