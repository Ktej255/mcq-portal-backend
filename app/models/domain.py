from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Enum, JSON
from sqlalchemy.orm import relationship
import enum
from app.db.session import Base

class RoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    STUDENT = "STUDENT"
    EDUCATOR = "EDUCATOR"

class ConfidenceEnum(str, enum.Enum):
    BLIND_GUESS = "BLIND_GUESS"
    FIFTY_FIFTY = "FIFTY_FIFTY"
    EDUCATED_GUESS = "EDUCATED_GUESS"
    FAIRLY_SURE = "FAIRLY_SURE"
    HUNDRED_PERCENT = "HUNDRED_PERCENT"

class AttemptStatusEnum(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    SOVEREIGNTY_PROTECTED = "SOVEREIGNTY_PROTECTED"

class ReviewStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    google_uid = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    profile_picture = Column(String, nullable=True)
    role = Column(Enum(RoleEnum), default=RoleEnum.STUDENT, nullable=False)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=True)
    topic_mastery = Column(JSON, nullable=True) # {topic_id: {mastery_score, last_updated}}
    behavioral_profile = Column(JSON, nullable=True) # {guessing_rate_trend, consistency_score, etc.}
    flourishing_profile = Column(JSON, nullable=True) # {meaning_score, wisdom_depth, optimization_fatigue}
    sovereignty_overrides = Column(JSON, nullable=True) # {opt_out_of_ai: bool, preserve_challenge: bool}
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    institution = relationship("Institution", back_populates="users")
    attempts = relationship("Attempt", back_populates="user")
    memberships = relationship("CohortMembership", back_populates="user")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    
    topics = relationship("Topic", back_populates="subject")
    tests = relationship("Test", back_populates="subject")

class Institution(Base):
    __tablename__ = "institutions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    config = Column(JSON, nullable=True) # Governance settings, intervention aggressiveness, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    cohorts = relationship("Cohort", back_populates="institution")
    users = relationship("User", back_populates="institution")

class Cohort(Base):
    __tablename__ = "cohorts"
    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id"), nullable=False)
    name = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    institution = relationship("Institution", back_populates="cohorts")
    memberships = relationship("CohortMembership", back_populates="cohort")

class CohortMembership(Base):
    __tablename__ = "cohort_memberships"
    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.STUDENT, nullable=False)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    cohort = relationship("Cohort", back_populates="memberships")
    user = relationship("User", back_populates="memberships")

class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    prerequisites = Column(JSON, nullable=True) # List of topic_ids

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
    attempts = relationship("Attempt", back_populates="test", order_by="desc(Attempt.start_time)")

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
    explanation_en = Column(String, nullable=True)
    explanation_hi = Column(String, nullable=True)
    source = Column(String, nullable=True, index=True)
    difficulty = Column(String, default="MEDIUM", index=True)
    question_number = Column(Integer, nullable=True, index=True)

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
    events = relationship("ExamEvent", back_populates="attempt")

class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    time_taken_seconds = Column(Integer, default=0)
    confidence_level = Column(Enum(ConfidenceEnum), nullable=True)
    is_skipped = Column(Boolean, default=False, index=True)
    is_changed = Column(Boolean, default=False)
    marked_for_review = Column(Boolean, default=False, index=True)
    interaction_history = Column(JSON, nullable=True) # List of events: {type, value, timestamp}

    attempt = relationship("Attempt", back_populates="answers")
    question = relationship("Question", back_populates="attempt_answers")

class ExamEvent(Base):
    __tablename__ = "exam_events"
    id = Column(Integer, primary_key=True, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False)
    event_type = Column(String, nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    payload = Column(JSON, nullable=True) # Specific data for the event
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    attempt = relationship("Attempt", back_populates="events")
    question = relationship("Question")

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
    subject_wise_performance = Column(JSON, nullable=True)
    confidence_analysis = Column(JSON, nullable=True)
    average_time_per_question = Column(Float, nullable=True)
    narrative = Column(String, nullable=True) # AI Generated Insight
    behavioral_analysis = Column(JSON, nullable=True) # Full Cognitive Snapshot
    telemetry_summary = Column(JSON, nullable=True) # Pacing, Focus, and Navigation metrics
    processing_status = Column(String, default="COMPLETED", nullable=False) # e.g., PENDING, COMPLETED, FAILED
    evaluation_metadata = Column(JSON, nullable=True) # {hallucination_score, relevance_score, etc.}
    forensic_data = Column(JSON, nullable=True) # Behavioral and performance forensic timeline
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    attempt = relationship("Attempt", back_populates="report")

class StudentEvolution(Base):
    __tablename__ = "student_evolution"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    metric_type = Column(String, nullable=False, index=True) # e.g., ACCURACY, SPEED, CALIBRATION
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

class CognitiveSnapshot(Base):
    __tablename__ = "cognitive_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), unique=True, nullable=False, index=True)
    cognitive_snapshot = Column(JSON, nullable=False)
    telemetry_snapshot = Column(JSON, nullable=True)
    reliability_snapshot = Column(JSON, nullable=True)
    metric_version = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")
    attempt = relationship("Attempt")

class LearningIntervention(Base):
    __tablename__ = "learning_interventions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recommendation_id = Column(String, unique=True, nullable=False, index=True)
    strategy_id = Column(String, nullable=False, index=True)
    experiment_id = Column(String, nullable=True, index=True)
    variant_id = Column(String, nullable=True, index=True)
    recommendation_payload = Column(JSON, nullable=False)
    status = Column(String, default="GENERATED", nullable=False, index=True)
    risk_level = Column(String, default="LOW", nullable=False) # LOW, MEDIUM, HIGH
    approval_status = Column(String, default="AUTO_APPROVED", nullable=False) # AUTO_APPROVED, PENDING_REVIEW, APPROVED, REJECTED
    acceptance_metadata = Column(JSON, nullable=True)
    outcome_metadata = Column(JSON, nullable=True)
    reliability_snapshot = Column(JSON, nullable=True)
    metric_version = Column(String, nullable=False)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")

class EducationalReview(Base):
    __tablename__ = "educational_reviews"
    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String, nullable=False, index=True) # INTERVENTION, RECOMMENDATION, REASONING
    target_id = Column(String, nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(ReviewStatusEnum), default=ReviewStatusEnum.PENDING, nullable=False)
    comment = Column(String, nullable=True)
    override_payload = Column(JSON, nullable=True)
    confidence_level = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    reviewer = relationship("User")

class EducationalEscalation(Base):
    __tablename__ = "educational_escalations"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False, index=True) # CONTRADICTION, INSTABILITY, OVERLOAD
    target_id = Column(String, nullable=False, index=True)
    status = Column(String, default="OPEN", nullable=False) # OPEN, RESOLVED, DISMISSED
    severity = Column(String, default="MEDIUM", nullable=False) # LOW, MEDIUM, HIGH, CRITICAL
    trigger_payload = Column(JSON, nullable=True)
    resolution_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class KnowledgeConcept(Base):
    __tablename__ = "knowledge_concepts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    description = Column(String, nullable=True)
    metadata_payload = Column(JSON, nullable=True) # Conceptual properties, difficulty, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    subject = relationship("Subject")
    out_edges = relationship("KnowledgeEdge", foreign_keys="KnowledgeEdge.source_id", back_populates="source")
    in_edges = relationship("KnowledgeEdge", foreign_keys="KnowledgeEdge.target_id", back_populates="target")

class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_concepts.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("knowledge_concepts.id"), nullable=False)
    edge_type = Column(String, nullable=False, index=True) # PREREQUISITE, MISCONCEPTION_PATH, BRIDGE, REMEDIATION
    strength = Column(Float, default=1.0)
    evidence_quality = Column(Float, default=1.0)
    durability = Column(Float, default=1.0)
    metadata_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    source = relationship("KnowledgeConcept", foreign_keys=[source_id], back_populates="out_edges")
    target = relationship("KnowledgeConcept", foreign_keys=[target_id], back_populates="in_edges")

class CausalInference(Base):
    __tablename__ = "causal_inferences"
    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String, nullable=False, index=True) # CONCEPT, INTERVENTION, COHORT
    target_id = Column(String, nullable=False, index=True)
    estimate = Column(Float, nullable=False)
    confidence_interval = Column(JSON, nullable=True) # [min, max]
    p_value = Column(Float, nullable=True)
    evidence_support = Column(Float, nullable=True)
    confounders = Column(JSON, nullable=True)
    reasoning_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class QualitativeSignal(Base):
    __tablename__ = "qualitative_signals"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    signal_type = Column(String, nullable=False, index=True) # EXPERIENCE, INTUITION, CONTEXT, CULTURAL
    content = Column(String, nullable=False)
    evidence_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")

class RealityAudit(Base):
    __tablename__ = "reality_audits"
    id = Column(Integer, primary_key=True, index=True)
    auditor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_type = Column(String, nullable=False, index=True) # MODEL, PREDICTION, INTERVENTION, GRAPH
    target_id = Column(String, nullable=False, index=True)
    divergence_score = Column(Float, nullable=False)
    findings = Column(String, nullable=True)
    reconciliation_payload = Column(JSON, nullable=True)
    status = Column(String, default="PENDING", nullable=False) # PENDING, COMPLETED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    auditor = relationship("User")

class CulturalContext(Base):
    __tablename__ = "cultural_contexts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    governance_rules = Column(JSON, nullable=True)
    pedagogical_patterns = Column(JSON, nullable=True) # Regional metaphors, reasoning styles, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
