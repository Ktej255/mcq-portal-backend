from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.domain import Subject, Topic, Test, Question, User, RoleEnum, AttemptAnswer, ExamEvent
from app.schemas.test_engine import SaveAnswerRequest, ExamEventRequest, EventBatchRequest
from app.services.domain_contracts import normalize_option_id, normalize_confidence, detect_analytics_anomalies
from app.services.report_service import generate_report
from app.services.test_engine_service import start_attempt, save_answer
from app.schemas.test_engine import StartAttemptRequest


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def seed_exam(db):
    user = User(google_uid="uid-1", email="student@example.com", role=RoleEnum.STUDENT)
    subject = Subject(name="Physics")
    db.add_all([user, subject])
    db.commit()

    topic = Topic(name="Kinematics", subject_id=subject.id)
    db.add(topic)
    db.commit()

    test = Test(title="Contract Test", subject_id=subject.id, correct_marks=4, negative_marking_value=1, duration_minutes=30)
    db.add(test)
    db.commit()

    q1 = Question(test_id=test.id, topic_id=topic.id, text_en="Q1", options_en={"A": "One", "B": "Two"}, correct_option="B")
    q2 = Question(test_id=test.id, topic_id=topic.id, text_en="Q2", options_en={"A": "One", "C": "Three"}, correct_option="C")
    db.add_all([q1, q2])
    db.commit()
    return user, test, q1, q2


def test_option_identity_normalizes_ui_ids():
    assert normalize_option_id("1_opt_B") == "B"
    assert normalize_option_id("b") == "B"
    assert normalize_option_id(None) is None
    with pytest.raises(ValueError):
        normalize_option_id("not-an-option")


def test_confidence_identity_normalizes_legacy_aliases():
    assert normalize_confidence("50_50") == "FIFTY_FIFTY"
    assert normalize_confidence("100_SURE") == "HUNDRED_PERCENT"
    assert normalize_confidence("FAIRLY_SURE") == "FAIRLY_SURE"


def test_score_correctness_uses_canonical_option_keys(db):
    user, test, q1, q2 = seed_exam(db)
    attempt = start_attempt(db, user.id, StartAttemptRequest(test_id=test.id))

    save_answer(db, attempt.id, user.id, SaveAnswerRequest(
        question_id=q1.id,
        selected_option=f"{q1.id}_opt_B",
        time_taken_seconds=12,
        confidence_level="FAIRLY_SURE",
    ))
    save_answer(db, attempt.id, user.id, SaveAnswerRequest(
        question_id=q2.id,
        selected_option=f"{q2.id}_opt_A",
        time_taken_seconds=8,
        confidence_level="EDUCATED_GUESS",
    ))

    report = generate_report(db, attempt.id, user.id)
    assert report.total_score == 3
    assert report.correct_count == 1
    assert report.incorrect_count == 1
    assert report.accuracy == 50
    assert report.subject_wise_performance["Physics"]["total"] == 2


def test_autosave_timing_is_absolute_not_additive(db):
    user, test, q1, _ = seed_exam(db)
    attempt = start_attempt(db, user.id, StartAttemptRequest(test_id=test.id))
    payload = SaveAnswerRequest(question_id=q1.id, selected_option="B", time_taken_seconds=10)
    save_answer(db, attempt.id, user.id, payload)
    save_answer(db, attempt.id, user.id, SaveAnswerRequest(question_id=q1.id, selected_option="B", time_taken_seconds=10))

    answer = db.query(AttemptAnswer).filter_by(attempt_id=attempt.id, question_id=q1.id).one()
    assert answer.time_taken_seconds == 10


def test_event_contract_rejects_missing_required_payload():
    with pytest.raises(ValueError):
        ExamEventRequest(event_type="ANSWER_CHANGED", question_id=1, payload={}, timestamp=datetime.now(timezone.utc))


def test_event_contract_normalizes_payload():
    event = ExamEventRequest(
        event_type="ANSWER_CHANGED",
        question_id=1,
        payload={"option_id": "1_opt_C", "old_id": "1_opt_A"},
        timestamp=datetime.now(timezone.utc),
    )
    assert event.payload == {"option_id": "C", "old_id": "A"}


def test_event_contract_rejects_future_timestamp():
    with pytest.raises(ValueError):
        ExamEventRequest(
            event_type="QUESTION_VIEWED",
            question_id=1,
            timestamp=datetime.now(timezone.utc) + timedelta(hours=1),
        )


def test_event_batch_cannot_be_empty():
    with pytest.raises(ValueError):
        EventBatchRequest(events=[])


def test_analytics_anomaly_detection_flags_contradictions():
    anomalies = detect_analytics_anomalies({
        "total_questions": 2,
        "correct_count": 1,
        "incorrect_count": 1,
        "unattempted_count": 1,
        "accuracy": 120,
        "average_time_per_question": -1,
        "total_score": 3,
    })
    assert {item["type"] for item in anomalies} >= {"COUNT_CONTRADICTION", "ACCURACY_RANGE", "IMPOSSIBLE_TIMING"}
