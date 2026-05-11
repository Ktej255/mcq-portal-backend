from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
import enum
from app.db.session import Base

class RoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    STUDENT = "STUDENT"

class ConfidenceEnum(str, enum.Enum):
    BLIND_GUESS = "BLIND_GUESS"
    FIFTY_FIFTY = "50_50"
    EDUCATED_GUESS = "EDUCATED_GUESS"
    FAIRLY_SURE = "FAIRLY_SURE"
    HUNDRED_PERCENT = "100_SURE"

class AttemptStatusEnum(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    google_uid = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    profile_picture = Column(String, nullable=True)
    role = Column(Enum(RoleEnum), default=RoleEnum.STUDENT, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    attempts = relationship("Attempt", back_populates="user")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    
    topics = relationship("Topic", back_populates="subject")
    tests = relationship("Test", back_populates="subject")

class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)

    subject = relationship("Subject", back_populates="topics")
    questions = relationship("Question", back_populates="topic")

class Test(Base):
    __tablename__ = "tests"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    duration_minutes = Column(Integer, default=60, nullable=False)
    correct_marks = Column(Float, default=1.0, nullable=False)
    negative_marking_value = Column(Float, default=0.33, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    subject = relationship("Subject", back_populates="tests")
    questions = relationship("Question", back_populates="test")
    attempts = relationship("Attempt", back_populates="test")

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    text_en = Column(String, nullable=False)
    text_hi = Column(String, nullable=True)
    options_en = Column(JSON, nullable=False) 
    options_hi = Column(JSON, nullable=True)
    correct_option = Column(String, nullable=False)
    difficulty = Column(String, default="MEDIUM")

    test = relationship("Test", back_populates="questions")
    topic = relationship("Topic", back_populates="questions")
    attempt_answers = relationship("AttemptAnswer", back_populates="question")

class Attempt(Base):
    __tablename__ = "attempts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False)
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    end_time = Column(DateTime, nullable=True)
    status = Column(Enum(AttemptStatusEnum), default=AttemptStatusEnum.IN_PROGRESS, nullable=False)

    user = relationship("User", back_populates="attempts")
    test = relationship("Test", back_populates="attempts")
    answers = relationship("AttemptAnswer", back_populates="attempt")
    report = relationship("Report", back_populates="attempt", uselist=False)

class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    time_taken_seconds = Column(Integer, default=0)
    confidence_level = Column(Enum(ConfidenceEnum), nullable=True)
    is_skipped = Column(Boolean, default=False)
    is_changed = Column(Boolean, default=False)
    marked_for_review = Column(Boolean, default=False)

    attempt = relationship("Attempt", back_populates="answers")
    question = relationship("Question", back_populates="attempt_answers")

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), unique=True, nullable=False)
    total_score = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=False) # percentage
    correct_count = Column(Integer, nullable=False)
    incorrect_count = Column(Integer, nullable=False)
    unattempted_count = Column(Integer, nullable=False)
    topic_wise_analysis = Column(JSON, nullable=True)
    confidence_analysis = Column(JSON, nullable=True)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    attempt = relationship("Attempt", back_populates="report")
